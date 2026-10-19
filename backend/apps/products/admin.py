"""
Products admin registration (Phase B - Store management).

Designed for the shop owner's daily work: images inline (one marked
primary -- auto-assigned if forgotten, rejected if duplicated), bulk
activate/deactivate/feature actions, and a changelist that shows a
thumbnail, price and an at-a-glance stock warning.
"""
from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, F, Prefetch, Q
from django.http import FileResponse, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.text import slugify

from decimal import ROUND_HALF_UP, Decimal

from apps.adminui.admin_dates import jalali_column
from apps.adminui.templatetags.adminui_extras import group_thousands, to_fa_digits
from apps.adminui.admin_forms import AutoWebpVariantsMixin, NumericChangelistAdminMixin
from apps.adminui.search import NormalizedSearchMixin
from apps.categories.models import Category

import csv
import glob
import io
import json
import os
import re
import shutil
import tempfile
import uuid

from .importing import (
    STOCK_MODES,
    UPDATE_ALL_COLUMNS,
    _template_xlsx,
    _update_template_csv,
    _update_template_xlsx,
    canonical_rows,
    errors_csv,
    export_products_csv,
    export_products_xlsx,
    import_products_from_rows,
    read_rows,
    resolve_headers,
    sheet_names,
    template_csv,
    update_products_from_rows,
)
from .image_import import (
    DEFAULT_BATCH_SIZE,
    ImageImportLimits,
    ZipImageSource,
    apply_job_batch,
    apply_plan,
    build_plan,
    fa_digits,
    job_progress,
    new_job,
    report_csv as image_report_csv,
)
from .models import Brand, Product, ProductAttribute, ProductAttributeValue, ProductImage, ProductVariant


class MultipleImageInput(forms.ClearableFileInput):
    """File input that accepts several images at once (Part S5 item 3).
    Django's FileInput returns `files.getlist(name)` for it, so it needs a
    matching field (below)."""

    allow_multiple_selected = True


class MultipleImageField(forms.FileField):
    """
    A FileField that accepts SEVERAL uploads and validates each one.

    (The Django version installed here -- 5.0 -- has no bundled
    MultipleFileField, so this is the small equivalent: one FileField
    check per selected file.)
    """

    widget = MultipleImageInput

    def clean(self, data, initial=None):
        if not data:
            return []
        files = data if isinstance(data, (list, tuple)) else [data]
        return [super(MultipleImageField, self).clean(item, initial) for item in files]


class ProductImageInlineForm(forms.ModelForm):
    """
    Part S5 item 3: the inline accepts SEVERAL files in one go.

    `image` (the model's single file) stays for replacing one row; the
    extra `add_images` field takes any number of files and the formset
    turns each of them into its own row (see
    ProductImageInlineFormSet.save_new). One of the two must be filled in.
    """

    add_images = MultipleImageField(
        label="افزودن چند تصویر با هم",
        required=False,
        widget=MultipleImageInput(attrs={"accept": "image/*", "multiple": True}),
        help_text="می‌توانید چند فایل را هم‌زمان انتخاب کنید؛ برای هر فایل یک ردیف ساخته می‌شود.",
    )

    class Meta:
        model = ProductImage
        fields = ["image", "alt_text", "is_primary", "ordering", "add_images"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # A brand-new row may be filled through `add_images` alone, so the
        # single-file field cannot be unconditionally required -- and the
        # position gets a sensible default (the formset appends extra files
        # after the existing rows either way).
        if not self.instance.pk:
            self.fields["image"].required = False
            self.fields["ordering"].required = False

    def clean(self):
        cleaned = super().clean()
        # Each extra file gets the same content check a normal upload gets
        # (real image, allowed format, size limit) -- with a Persian
        # message naming the offending file.
        from apps.core.image_files import validate_image_file

        for upload in cleaned.get("add_images") or []:
            try:
                validate_image_file(upload)
            except forms.ValidationError:
                raise forms.ValidationError(
                    f"فایل «{upload.name}» تصویر معتبری نیست؛ فقط JPEG، PNG، WEBP یا GIF "
                    "با حجم حداکثر ۵ مگابایت."
                )
        if self.instance.pk or self.errors:
            return cleaned
        has_single = bool(cleaned.get("image"))
        has_many = bool(cleaned.get("add_images"))
        if not has_single and not has_many and self.has_changed():
            raise forms.ValidationError("یک تصویر انتخاب کنید (یا چند تصویر با هم).")
        return cleaned


class ProductImageInlineFormSet(forms.BaseInlineFormSet):
    """
    Friendly handling of the 'one primary image' rule on top of the
    database's partial unique constraint: two checked boxes become a
    readable form error instead of an IntegrityError page.

    Part S5 item 3: `save_new` also turns every file picked in the
    multi-image field into its own row (never an empty image row).
    """

    def clean(self):
        super().clean()
        primaries = 0
        for form in self.forms:
            if self._should_delete_form(form):
                continue
            if form.cleaned_data.get("is_primary"):
                primaries += 1
        if primaries > 1:
            raise forms.ValidationError(
                "برای هر محصول فقط یک تصویر را به‌عنوان تصویر اصلی علامت بزنید."
            )

    def save_new(self, form, commit=True):
        extras = form.cleaned_data.get("add_images") or []
        has_single = bool(form.cleaned_data.get("image"))
        if not has_single and not extras:
            # Nothing to store for this row (an untouched extra row).
            return ProductImage(product=self.instance)
        if not has_single and not form.instance.pk:
            # Only the multi-file picker was used: no empty row, just the
            # rows created below (an ImageField cannot be blank).
            instance = ProductImage(product=self.instance)
        else:
            instance = super().save_new(form, commit=commit)

        if extras:
            product = self.instance
            last = (
                ProductImage.objects.filter(product=product)
                .order_by("-ordering")
                .values_list("ordering", flat=True)
                .first()
            )
            ordering = (last or 0) + 1
            has_primary = ProductImage.objects.filter(product=product, is_primary=True).exists()
            alt_text = form.cleaned_data.get("alt_text") or ""
            for offset, upload in enumerate(extras):
                row = ProductImage(
                    product=product,
                    alt_text=alt_text,
                    ordering=ordering + offset,
                )
                # The first image of a product with none becomes the primary
                # one, so a freshly uploaded gallery always has a valid
                # "main" image (the DB allows exactly one per product).
                if not has_primary:
                    row.is_primary = True
                    has_primary = True
                row.image = upload
                row.save()
        return instance


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    form = ProductImageInlineForm
    formset = ProductImageInlineFormSet
    extra = 1
    fields = (
        "image",
        "add_images",
        "thumbnail_preview",
        "alt_text",
        "is_primary",
        "ordering",
    )
    readonly_fields = ("thumbnail_preview",)
    # A5: cards in a thumbnail grid instead of stock table rows. Field
    # names, widgets and the set-primary/ordering rules are unchanged. With
    # ADMIN_THEME_ENABLED=0 this falls back to Django's stock tabular inline.
    @property
    def template(self):
        from django.conf import settings

        if getattr(settings, "ADMIN_THEME_ENABLED", True):
            return "admin/products/productimage_gallery_inline.html"
        return "admin/edit_inline/tabular.html"
    # Part S5 item 3: `ordering` is the gallery position -- the storefront
    # orders images by (primary first, then ordering) everywhere.
    verbose_name = "تصویر"
    verbose_name_plural = "تصاویر (ترتیب نمایش با ستون «ترتیب» تعیین می‌شود؛ عدد کوچک‌تر = جلوتر)"

    def thumbnail_preview(self, obj):
        # Part S4 item 1: the shared placeholder (brand mark on the warm-grey
        # field) when there is no image -- and when the stored file is gone,
        # an onerror swap shows the same thing instead of a broken icon.
        from apps.core.image_files import image_or_placeholder_html

        return image_or_placeholder_html(
            (obj.thumbnail or obj.image) if obj.pk else None
        )

    thumbnail_preview.short_description = "پیش‌نمایش"


class AdminSkuDirectionMixin:
    """Render every editable SKU as an explicit left-to-right control."""

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if formfield is not None and db_field.name == "sku":
            formfield.widget.attrs["dir"] = "ltr"
        return formfield


class ProductVariantInline(AdminSkuDirectionMixin, admin.TabularInline):
    model = ProductVariant
    extra = 0
    fields = ("sku", "price", "stock_quantity", "is_active", "attribute_values")
    # A two-panel FilteredSelectMultiple makes each tabular row hundreds of
    # pixels tall. The same multi-value relationship uses the existing,
    # searchable ProductAttributeValueAdmin autocomplete instead.
    autocomplete_fields = ("attribute_values",)
    show_change_link = True


@admin.register(Brand)
class BrandAdmin(AutoWebpVariantsMixin, NumericChangelistAdminMixin, admin.ModelAdmin):
    # Part R2: featured tiles are managed right from the changelist --
    # tick is_featured and set display_order inline, or use bulk actions.
    list_display = ("name", "slug", "is_featured", "display_order", "is_active")
    list_editable = ("is_featured", "display_order")
    list_filter = ("is_active", "is_featured")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    actions = ("make_featured", "make_not_featured")

    image_field = "tile_image"
    image_help = (
        "اندازهٔ پیشنهادی کاشی ۸۰۰×۸۰۰ پیکسل (مربع) و حداکثر ۲ مگابایت؛ "
        "JPG یا PNG یا WebP."
    )
    fieldsets = (
        (None, {"fields": ("name", "slug", "logo")}),
        ("کاشی صفحهٔ اصلی", {
            "fields": (
                "is_featured", "display_order", "tile_image",
                "webp_400_readonly", "webp_800_readonly", "webp_1200_readonly",
            ),
            "description": (
                "سه نسخهٔ WebP هنگام ذخیرهٔ تصویر کاشی به‌طور خودکار ساخته "
                "می‌شوند و قابل ویرایش نیستند."
            ),
        }),
        (None, {"fields": ("is_active",)}),
    )
    readonly_fields = ("webp_400_readonly", "webp_800_readonly", "webp_1200_readonly")

    @admin.action(description="برند ویژه: بله")
    def make_featured(self, request, queryset):
        queryset.update(is_featured=True)

    @admin.action(description="برند ویژه: خیر")
    def make_not_featured(self, request, queryset):
        queryset.update(is_featured=False)


class ProductStockChangelistWidget(forms.NumberInput):
    """Keep the editable stock field and its status badge in one cell.

    Django renders a ``list_editable`` field in place of the normal column
    value, so the widget owns both pieces of presentation while preserving
    the original input name, value and POST semantics.
    """

    def render(self, name, value, attrs=None, renderer=None):
        input_html = super().render(name, value, attrs, renderer)
        try:
            quantity = int(value or 0)
        except (TypeError, ValueError):
            quantity = 0

        if quantity <= 0:
            badge_class, label = "stock-out", "ناموجود"
        elif quantity <= getattr(
            self,
            "low_stock_threshold",
            getattr(self, "_settings_threshold", settings.LOW_STOCK_THRESHOLD),
        ):
            badge_class = "stock-low"
            label = f"{fa_digits(quantity)} موجودی کم"
        else:
            return format_html('<div class="cusin-stock-edit">{}</div>', input_html)

        return format_html(
            '<div class="cusin-stock-edit">{}'
            '<span class="cusin-badge {}">{}</span></div>',
            input_html,
            badge_class,
            label,
        )


def price_hint(value) -> str:
    """``910000`` -> ``۹۱۰٬۰۰۰ تومان``.

    The editable changelist cell can only hold the raw number (that is what
    the form has to POST), so the amount the owner can actually read goes
    underneath it, grouped and in Persian digits.
    """
    try:
        amount = Decimal(str(value if value not in (None, "") else ""))
    except (ArithmeticError, ValueError, TypeError):
        return "—"
    if amount <= 0:
        return "—"
    return f"{to_fa_digits(group_thousands(int(amount)))} تومان"


class ProductPriceChangelistWidget(forms.NumberInput):
    """Show the price the way an invoice does, under the bare number.

    Same contract as ProductStockChangelistWidget: the input keeps its
    original name, value and POST semantics, and only the presentation
    around it changes.
    """

    def render(self, name, value, attrs=None, renderer=None):
        input_html = super().render(name, value, attrs, renderer)
        return format_html(
            '<div class="cusin-price-edit">{}'
            '<span class="cusin-price-hint" data-cusin-price-hint>{}</span>'
            "</div>",
            input_html,
            price_hint(value),
        )


class BrandFilter(admin.RelatedFieldListFilter):
    """Django's related filter labels its «no value» option with the admin's
    empty-value marker, i.e. a bare «-». On the product list that reads as
    a broken row; it means «بدون برند»."""

    empty_choice_title = "بدون برند"

    def choices(self, changelist):
        original = self.empty_value_display
        self.empty_value_display = self.empty_choice_title
        try:
            yield from super().choices(changelist)
        finally:
            self.empty_value_display = original


class LowStockFilter(admin.SimpleListFilter):
    """Part R4 item 3: one-click view of everything at/below the owner
    low-stock threshold (env LOW_STOCK_THRESHOLD, default 3).

    Admin-panel work adds the «ناموجود» (exactly zero) lookup -- purely
    additive: the existing "1"/"0" values are untouched (covered by
    apps/products/tests/test_admin_products.py).

    Every comparison is against each product's OWN low_stock_threshold,
    never the global LOW_STOCK_THRESHOLD -- see the note in queryset().
    """

    title = "وضعیت موجودی"
    parameter_name = "low_stock"

    def lookups(self, request, model_admin):
        return (
            ("1", "موجودی کم"),
            ("0", "موجودی کافی"),
            ("2", "ناموجود"),
            ("3", "موجودی کم (بدون ناموجود)"),
        )

    def queryset(self, request, queryset):
        # ONE rule: a product's own «آستانهٔ هشدار موجودی کم». The env
        # LOW_STOCK_THRESHOLD is only the default for a NEW product -- it
        # is not a second, competing rule, and comparing against it made
        # the filter disagree with the badge on the very same row (a
        # product with stock 4 and threshold 5 was "موجودی کافی" here and
        # "موجودی کم" there).
        own_threshold = F("low_stock_threshold")
        if self.value() == "1":
            return queryset.filter(stock_quantity__lte=own_threshold)
        if self.value() == "0":
            return queryset.filter(stock_quantity__gt=own_threshold)
        if self.value() == "2":
            return queryset.filter(stock_quantity=0)
        if self.value() == "3":
            # Dashboard card «موجودی کم» counts items with some stock left
            # (zero-stock rows live on their own «ناموجود» card), so its
            # link must land on exactly that set.
            return queryset.filter(
                stock_quantity__lte=own_threshold,
                stock_quantity__gt=0,
            )
        return queryset


class HasImageFilter(admin.SimpleListFilter):
    """Additive filter for the dashboard's «بدون تصویر» action card."""

    title = "تصویر محصول"
    parameter_name = "has_image"

    def lookups(self, request, model_admin):
        return (("1", "تصویر دارد"), ("0", "بدون تصویر"))

    def queryset(self, request, queryset):
        if self.value() == "1":
            return queryset.filter(images__isnull=False).distinct()
        if self.value() == "0":
            return queryset.filter(images__isnull=True)
        return queryset


LEAF_CATEGORY_HELP = "محصول را فقط در زیردسته‌ها قرار دهید؛ دسته‌های والد فقط گروه‌بندی هستند."


def leaf_categories_queryset(include_pk=None):
    """Leaf categories (no sub-categories), in tree order.

    Products live on leaves only (Task 3). ``include_pk`` keeps a
    legacy product's current parent category selectable while editing
    it, so fixing other fields is not blocked before it is moved.
    """
    if include_pk:
        qs = Category.objects.filter(Q(children__isnull=True) | Q(pk=include_pk))
    else:
        qs = Category.objects.filter(children__isnull=True)
    return (
        qs.distinct()
        .select_related("parent", "parent__parent", "parent__parent__parent")
        .order_by(
            "parent__parent__ordering", "parent__ordering", "ordering", "name"
        )
    )


class LeafCategoryChoiceField(forms.ModelChoiceField):
    """Category choice labelled with its full path («آشپزخانه › …»)."""

    def label_from_instance(self, obj):
        return obj.full_path


@admin.register(Product)
class ProductAdmin(
    AdminSkuDirectionMixin,
    NumericChangelistAdminMixin,
    NormalizedSearchMixin,
    admin.ModelAdmin,
):
    # The owner edits prices, stock and flags inline as before. Product name,
    # image and identifying metadata share one compact, sortable link cell;
    # the stock widget keeps its status badge beside the editable value.
    list_display = (
        "product_summary", "price", "compare_at_price", "stock_quantity",
        "is_active", "is_featured", "storefront_data",
    )
    list_display_links = ("product_summary",)
    list_editable = ("price", "compare_at_price", "stock_quantity", "is_active", "is_featured")
    list_filter = (
        "is_active", "is_featured", "is_new", "is_best_seller", "category",
        ("brand", BrandFilter), LowStockFilter, HasImageFilter,
    )
    search_fields = ("name", "sku", "slug")

    # The changelist column must stay SHORT («SKU» is a narrow column and
    # the table has to fit a 125%-scaled Windows screen), but the FORM
    # should say what the code means -- «SKU:» alone is English jargon.
    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change=change, **kwargs)
        if "sku" in form.base_fields:
            form.base_fields["sku"].label = "کد کالا (SKU)"
        if "category" in form.base_fields:
            field = form.base_fields["category"]
            # Reset on every call: base_fields live on the form class,
            # so a legacy parent included for one product must not leak
            # into the next add form.
            include_pk = obj.category_id if obj is not None else None
            field.queryset = leaf_categories_queryset(include_pk=include_pk)
            field.help_text = LEAF_CATEGORY_HELP
            if obj is not None and obj.category_id and obj.category.children.exists():
                field.help_text += (
                    f" این محصول اکنون در دستهٔ والد «{obj.category.name}» است؛ "
                    "آن را به یک زیردسته منتقل کنید."
                )
        return form

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "category":
            kwargs.setdefault("queryset", leaf_categories_queryset())
            kwargs.setdefault("help_text", LEAF_CATEGORY_HELP)
            return LeafCategoryChoiceField(**kwargs)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    prepopulated_fields = {"slug": ("name",)}
    # Category is deliberately NOT an autocomplete (Task 3): the plain
    # dropdown lists leaf categories only, each labelled with its full
    # path. Complements (Part R5 item 9) is an M2M to Product itself --
    # its autocomplete searches by ProductAdmin.search_fields above.
    autocomplete_fields = ("brand", "complements")
    inlines = [ProductImageInline, ProductVariantInline]
    actions = [
        "activate_products", "deactivate_products", "mark_featured",
        "unmark_featured", "duplicate_product", "change_price_percentage",
        "move_to_category", "export_products_xlsx_action",
    ]
    change_list_template = "admin/products/product_change_list.html"
    # B4d: anchored sections + live preview + client-side formatting.
    # Extends admin/change_form.html, so the stock form is untouched.
    change_form_template = "admin/products/product_change_form.html"

    # --- Excel export of the selected/filtered rows (Task 3) -------------------

    @admin.action(
        description="خروجی اکسل محصولات انتخاب‌شده",
        permissions=("view",),
    )
    def export_products_xlsx_action(self, request, queryset):
        """Real .xlsx with SKU, brand, category path, price, stock, views, sales.

        Views/sales come from ONE correlated aggregate each (no N+1), the
        export is row-capped with a Persian notice, and money is written as
        a real number.
        """
        from django.db.models import OuterRef, Subquery, Sum

        from apps.analytics.exports import row_limit, xlsx_bytes, xlsx_response
        from apps.analytics.models import Event
        from apps.orders.models import OrderItem

        sales_subquery = (
            OrderItem.objects.filter(
                product=OuterRef("pk"),
                order__payment_status="paid",
            )
            .exclude(order__status__in=["cancelled", "returned"])
            .order_by()
            .values("product")
            .annotate(quantity_total=Sum("quantity"))
            .values("quantity_total")[:1]
        )
        limit = row_limit()
        rows_qs = (
            queryset.select_related("brand", "category__parent__parent")
            .annotate(
                _views=Count(
                    "analytics_events",
                    filter=Q(analytics_events__event_type=Event.Type.PRODUCT_VIEW),
                    distinct=True,
                ),
                _sales=Subquery(sales_subquery),
            )
            .order_by("pk")
        )
        selected = list(rows_qs[: limit + 1])
        truncated = len(selected) > limit

        def category_path(category):
            names, seen, current = [], set(), category
            while current is not None and current.pk not in seen and len(names) < 6:
                names.append(current.name)
                seen.add(current.pk)
                current = current.parent
            return " › ".join(reversed(names))

        rows = [
            [
                product.name,
                product.sku,
                product.brand.name if product.brand_id else "",
                category_path(product.category),
                product.price,
                product.stock_quantity,
                product._views or 0,
                product._sales or 0,
            ]
            for product in selected[:limit]
        ]
        if truncated:
            self.message_user(
                request,
                f"خروجی به {limit:,} ردیف محدود شد؛ برای بقیهٔ ردیف‌ها فیلتر را محدودتر کنید.",
                messages.WARNING,
            )
        data, _written = xlsx_bytes(
            [
                "نام محصول", "کد کالا (SKU)", "برند", "دسته‌بندی",
                "قیمت (تومان)", "موجودی", "بازدید", "تعداد فروش",
            ],
            rows,
            sheet_title="محصولات",
            numeric_columns={4, 5, 6, 7},
        )
        from django.utils import timezone

        stamp = timezone.now().strftime("%Y%m%d-%H%M%S")
        return xlsx_response(data, f"products-{stamp}.xlsx")

    # --- Bulk import (CSV / Excel) --------------------------------------------

    def get_urls(self):
        # Custom URLs BEFORE the admin's own so "import/" is not swallowed
        # by the <object_id> change route.
        custom = [
            path(
                "import/",
                self.admin_site.admin_view(self.import_view),
                name="products_product_import",
            ),
            path(
                "import/template/",
                self.admin_site.admin_view(self.import_template_download),
                name="products_product_import_template",
            ),
            path(
                "import/update-template/",
                self.admin_site.admin_view(self.update_template_download),
                name="products_product_update_template",
            ),
            path(
                "export/",
                self.admin_site.admin_view(self.export_view),
                name="products_product_export",
            ),
            path(
                "image-import/",
                self.admin_site.admin_view(self.image_import_view),
                name="products_product_image_import",
            ),
            # B4c: percentage price change (preview -> apply / CSV).
            path(
                "price-percent/",
                self.admin_site.admin_view(self.price_percent_view),
                name="products_product_price_percent",
            ),
            # Task 3: bulk «انتقال به دسته…» (leaf categories only).
            path(
                "move-to-category/",
                self.admin_site.admin_view(self.move_to_category_view),
                name="products_product_move_to_category",
            ),
        ]
        return custom + super().get_urls()

    _PENDING_KEY = "cusin_product_update_pending"

    def import_template_download(self, request):
        """The documented sample template, generated from the same column
        list the importer validates against."""
        if request.GET.get("format") == "xlsx":
            return FileResponse(
                io.BytesIO(_template_xlsx()),
                as_attachment=True,
                filename="product_import_template.xlsx",
                content_type=self.XLSX_CONTENT_TYPE,
            )
        buffer = io.BytesIO(template_csv().encode("utf-8-sig"))
        return FileResponse(
            buffer, as_attachment=True, filename="product_import_template.csv"
        )

    def update_template_download(self, request):
        """Part R4 item 6 / S5 item 8: minimal price/stock update template."""
        if request.GET.get("format") == "xlsx":
            return FileResponse(
                io.BytesIO(_update_template_xlsx()),
                as_attachment=True,
                filename="product_price_stock_template.xlsx",
                content_type=self.XLSX_CONTENT_TYPE,
            )
        buffer = io.BytesIO(_update_template_csv().encode("utf-8-sig"))
        return FileResponse(
            buffer, as_attachment=True, filename="product_price_stock_template.csv"
        )

    def export_view(self, request):
        """Part R4 item 6: download the current catalog in EXACTLY the
        import template format (CSV or Excel) so the owner edits it in
        Excel and re-uploads it."""
        fmt = request.GET.get("format", "csv").lower()
        if fmt == "xlsx":
            buffer = io.BytesIO(export_products_xlsx())
            return FileResponse(
                buffer,
                as_attachment=True,
                filename="cusin_products_export.xlsx",
                content_type=self.XLSX_CONTENT_TYPE,
            )
        buffer = io.BytesIO(export_products_csv().encode("utf-8-sig"))
        return FileResponse(
            buffer, as_attachment=True, filename="cusin_products_export.csv"
        )

    # --- Bulk image import from a ZIP (matched by SKU) -------------------------

    _IMAGE_PENDING_KEY = "cusin_product_image_import_pending"
    _IMAGE_REPORT_KEY = "cusin_product_image_import_report"

    @staticmethod
    def _image_stash_dir():
        return os.path.join(tempfile.gettempdir(), "cusin-product-image-imports")

    def _stash_image_upload(self, upload):
        """Stream the uploaded ZIP to a temp file (never into memory) and
        hand back a short token. The previous stashed ZIP is dropped, so
        abandoned uploads cannot pile up on disk."""
        os.makedirs(self._image_stash_dir(), exist_ok=True)
        for old in glob.glob(os.path.join(self._image_stash_dir(), "*")):
            try:
                os.remove(old)
            except OSError:
                pass
        token = uuid.uuid4().hex
        path = os.path.join(self._image_stash_dir(), token + ".zip")
        with open(path, "wb") as handle:
            for chunk in upload.chunks():
                handle.write(chunk)
        return token

    def _stashed_image_path(self, token):
        if not token or not re.fullmatch(r"[0-9a-f]{32}", str(token)):
            return None
        path = os.path.join(self._image_stash_dir(), str(token) + ".zip")
        return path if os.path.exists(path) else None

    def _image_context(self, request, **extra):
        from django.conf import settings as django_settings

        context = {
            "opts": self.model._meta,
            "title": "ورود گروهی تصاویر (فایل زیپ)",
            "errors": [],
            "plan": None,
            "token": "",
            "mode": "add",
            "skip_existing": False,
            "limits": ImageImportLimits.from_settings(),
            "owner_guide_url": getattr(django_settings, "OWNER_GUIDE_URL", ""),
        }
        context.update(extra)
        return context

    def _build_image_plan(self, request, source_path, *, extract_dir, thumbs):
        """Plan against a private temp directory.

        The caller owns `extract_dir`: the confirm step must keep it alive
        until apply_plan() has finished reading (and ProductImage.save()
        has copied) the extracted files.
        """
        source = ZipImageSource(source_path, limits=ImageImportLimits.from_settings())
        return build_plan(
            source,
            mode=request.POST.get("mode") or request.GET.get("mode") or "add",
            skip_existing=(request.POST.get("skip_existing") == "1"),
            extract_dir=extract_dir,
            thumbs=thumbs,
        )

    def image_import_view(self, request):
        """
        Upload the ZIP, see exactly what would happen (dry run, nothing
        written), then confirm -- and the save runs in BATCHES.

        A 176-image ZIP took ~27s on a fast core and blew gunicorn's 60s
        worker timeout on the 1-vCPU server, which killed the worker
        mid-import: the browser got a bare 502 and nothing was saved.
        The confirm step therefore only STARTS a resumable job
        (apps.products.image_import.new_job / apply_job_batch); the page
        then drives it 20 images per request, each batch its own
        transaction, with a progress bar and a resume-if-reloaded job
        file. Failures come back as Persian text on this page, never as a
        502.
        """
        context = self._image_context(
            request,
            mode=request.POST.get("mode") or request.GET.get("mode") or "add",
            skip_existing=(request.POST.get("skip_existing") == "1"),
        )

        if request.GET.get("report") == "csv":
            rows = request.session.get(self._IMAGE_REPORT_KEY) or []
            text = image_report_csv(rows)
            return HttpResponse(
                text.encode("utf-8-sig"),
                content_type="text/csv; charset=utf-8",
                headers={
                    "Content-Disposition": 'attachment; filename="image-import-report.csv"'
                },
            )

        if request.method == "POST":
            if request.POST.get("cancel") == "1":
                self._forget_image_job(request)
                self.message_user(request, "عملیات لغو شد؛ چیزی ذخیره نشد.", messages.INFO)
                return HttpResponseRedirect(reverse("admin:products_product_changelist"))

            if request.POST.get("confirm") == "1":
                return self._start_image_job(request, context)

            if request.POST.get("step") == "1":
                return self._apply_image_batch(request, context)

            upload = request.FILES.get("zip")
            if upload is None:
                context["errors"] = [
                    "فایلی انتخاب نشده است. یک فایل زیپ (.zip) شامل تصاویر بارگذاری کنید."
                ]
                return TemplateResponse(
                    request, "admin/products/product_image_import.html", context
                )

            token = self._stash_image_upload(upload)
            extract_dir = tempfile.mkdtemp(prefix="cusin-image-import-")
            try:
                try:
                    plan = self._build_image_plan(
                        request,
                        self._stashed_image_path(token),
                        extract_dir=extract_dir,
                        thumbs=True,
                    )
                except (ValueError, OSError) as exc:
                    self._drop_stashed(self._stashed_image_path(token))
                    context["errors"] = [str(exc)]
                    return TemplateResponse(
                        request, "admin/products/product_image_import.html", context
                    )
            finally:
                # The preview carries its thumbnails inline (data URIs), so
                # the extracted files are not needed once the plan exists.
                shutil.rmtree(extract_dir, ignore_errors=True)
            if not plan.ok:
                self._drop_stashed(self._stashed_image_path(token))
                context["errors"] = plan.errors
                return TemplateResponse(
                    request, "admin/products/product_image_import.html", context
                )

            # The dry run already knows the whole work list -- remember it,
            # so confirming is instant and the save can be batched.
            job = new_job(plan, token)
            self._save_image_job(job)
            request.session[self._IMAGE_PENDING_KEY] = {
                "token": token,
                "mode": plan.mode,
                "skip_existing": plan.skip_existing,
            }
            request.session[self._IMAGE_REPORT_KEY] = plan.report_rows()
            context.update({"plan": plan, "token": token, "step": "preview"})
            return TemplateResponse(
                request, "admin/products/product_image_import_preview.html", context
            )

        # GET: an unfinished job survives a reload -- show it and carry on.
        job = self._load_image_job(request)
        if job is not None:
            return self._image_progress_response(request, context, job)
        return TemplateResponse(request, "admin/products/product_image_import.html", context)

    # -- resumable job plumbing -------------------------------------------

    def _image_job_path(self, token):
        if not token or not re.fullmatch(r"[0-9a-f]{32}", str(token)):
            return None
        return os.path.join(self._image_stash_dir(), str(token) + ".json")

    def _save_image_job(self, job):
        """Atomic write: a half-written job file must never be reloadable."""
        path = self._image_job_path(job.get("token"))
        if path is None:
            return
        os.makedirs(self._image_stash_dir(), exist_ok=True)
        temporary = path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(job, handle, ensure_ascii=False)
        os.replace(temporary, path)

    def _load_image_job(self, request):
        pending = request.session.get(self._IMAGE_PENDING_KEY) or {}
        path = self._image_job_path(pending.get("token"))
        if not path or not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as handle:
                job = json.load(handle)
        except (OSError, ValueError):
            return None
        return job if isinstance(job, dict) and job.get("version") == 1 else None

    def _forget_image_job(self, request):
        pending = request.session.get(self._IMAGE_PENDING_KEY) or {}
        for candidate in (
            self._stashed_image_path(pending.get("token")),
            self._image_job_path(pending.get("token")),
        ):
            self._drop_stashed(candidate)
        request.session.pop(self._IMAGE_PENDING_KEY, None)

    def _start_image_job(self, request, context):
        job = self._load_image_job(request)
        if job is None:
            self.message_user(
                request,
                "پیش‌نمایشی برای تأیید وجود ندارد؛ فایل را دوباره بارگذاری کنید.",
                messages.WARNING,
            )
            return HttpResponseRedirect(reverse("admin:products_product_image_import"))
        if job["status"] == "error":
            # Let the owner retry the very same job (only the failed batch
            # was lost; committed batches are already on disk).
            job["status"] = "running"
            job["error"] = ""
            self._save_image_job(job)
        elif job["status"] == "done":
            return self._finish_image_job(request, context, job)
        elif job["status"] == "preview":
            job["status"] = "running"
            self._save_image_job(job)
        return self._image_progress_response(request, context, job)

    def _apply_image_batch(self, request, context):
        """Write ONE batch (its own transaction) and report progress."""
        job = self._load_image_job(request)
        if job is None:
            return self._image_progress_response(
                request,
                context,
                None,
                error="نشستِ ورود تصاویر پیدا نشد (یا منقضی شده است)؛ "
                "فایل زیپ را دوباره بارگذاری کنید.",
            )
        zip_path = self._stashed_image_path(job.get("token"))
        if zip_path is None:
            return self._image_progress_response(
                request,
                context,
                job,
                error="فایل زیپ دیگر روی سرور نیست؛ آن را دوباره بارگذاری کنید.",
            )

        job["status"] = "running"
        job["error"] = ""
        extract_dir = tempfile.mkdtemp(prefix="cusin-image-import-")
        try:
            source = ZipImageSource(zip_path, limits=ImageImportLimits.from_settings())
            try:
                apply_job_batch(job, source, extract_dir=extract_dir)
            except Exception as exc:  # a batch failure must not become a 502
                job["status"] = "error"
                job["error"] = (
                    "ذخیره‌سازی متوقف شد: "
                    f"{exc}. تصاویر این مرحله ذخیره نشدند؛ دکمهٔ «ادامهٔ ذخیره‌سازی» "
                    "را بزنید تا از همان‌جا دنبال شود."
                )
        except (ValueError, OSError) as exc:
            job["status"] = "error"
            job["error"] = f"فایل زیپ خوانده نشد: {exc}"
        finally:
            shutil.rmtree(extract_dir, ignore_errors=True)
            self._save_image_job(job)

        if job["status"] == "done":
            return self._finish_image_job(request, context, job)
        return self._image_progress_response(request, context, job)

    def _finish_image_job(self, request, context, job):
        request.session[self._IMAGE_REPORT_KEY] = self._image_report_rows(request, job)
        if job["created"]:
            self.message_user(
                request,
                f"تصاویر ذخیره شد: {fa_digits(job['created'])} تصویر برای "
                f"{fa_digits(job['products'])} محصول"
                + (
                    f" (و {fa_digits(job['replaced'])} تصویر قبلی جایگزین شد)."
                    if job["replaced"]
                    else "."
                ),
                messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                "هیچ تصویری ذخیره نشد (احتمالاً همه تکراری یا نامعتبر بودند).",
                messages.WARNING,
            )
        if self._wants_json(request):
            return self._image_progress_json(
                job, redirect=reverse("admin:products_product_changelist")
            )
        self._forget_image_job(request)
        return HttpResponseRedirect(reverse("admin:products_product_changelist"))

    @staticmethod
    def _wants_json(request):
        return (
            request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or request.GET.get("format") == "json"
            or "application/json" in (request.headers.get("Accept") or "")
        )

    def _image_report_rows(self, request, job):
        """The CSV report, updated with what the job actually did.

        The dry run wrote one row per member into the session; this marks
        the members the batches saved as «ذخیره شد» and the ones that
        failed as «تصویر نامعتبر» with the Persian reason, so the
        downloaded report describes the run, not just the plan.
        """
        rows = [dict(row) for row in (request.session.get(self._IMAGE_REPORT_KEY) or [])]
        applied = {}
        for step in job.get("steps") or []:
            for member in step["members"][: step["cursor"]]:
                applied[member] = step["sku"]
        problems = {item["member"]: item["reason"] for item in (job.get("problems") or [])}
        for row in rows:
            member = row.get("file", "")
            if member in problems:
                row["status"] = "invalid"
                row["reason"] = problems[member]
            elif member in applied:
                row["status"] = "applied"
        return rows

    def _image_progress_json(self, job, redirect=None):
        payload = job_progress(job)
        payload["finished"] = job["status"] == "done"
        payload["failed"] = job["status"] == "error"
        payload["redirect"] = redirect or ""
        payload["summary"] = {
            "created": job["created"],
            "replaced": job["replaced"],
            "products": job["products"],
            "problems": job.get("problems") or [],
        }
        from django.http import JsonResponse

        return JsonResponse(payload)

    def _image_progress_response(self, request, context, job, error=""):
        """"The page shown while the job runs: progress bar, resume button,
        or the final summary."""
        if job is None:
            context.update(
                {
                    "job": None,
                    "progress": {"done": 0, "total": 0, "percent": 0, "status": "error", "label": ""},
                    "error_message": error or "هیچ عملیاتی در حال انجام نیست.",
                    "step": "progress",
                }
            )
            return TemplateResponse(
                request, "admin/products/product_image_import_progress.html", context
            )

        if error:
            job["error"] = error
        context.update(
            {
                "job": job,
                "progress": job_progress(job),
                "error_message": job.get("error") or "",
                "token": job.get("token") or "",
                "step": "progress",
                "batch_size": job.get("batch_size") or DEFAULT_BATCH_SIZE,
            }
        )
        if self._wants_json(request):
            return self._image_progress_json(job)
        return TemplateResponse(
            request, "admin/products/product_image_import_progress.html", context
        )

    # --- Import / update / export (Part R4 item 6 + Part S5 item 8) -----------

    _ERRORS_KEY = "cusin_product_import_errors"

    @staticmethod
    def _stash_dir():
        return os.path.join(tempfile.gettempdir(), "cusin-product-imports")

    def _stash_upload(self, upload):
        """Keep the uploaded workbook on disk while the owner completes the
        sheet / column-mapping steps (a browser cannot re-send a file it
        already sent), and hand back a short token instead."""
        os.makedirs(self._stash_dir(), exist_ok=True)
        suffix = os.path.splitext(getattr(upload, "name", "") or "")[1].lower() or ".csv"
        token = uuid.uuid4().hex
        with open(os.path.join(self._stash_dir(), token + suffix), "wb") as handle:
            for chunk in upload.chunks():
                handle.write(chunk)
        return token

    def _stashed_path(self, token):
        if not token or not re.fullmatch(r"[0-9a-f]{32}", str(token)):
            return None
        matches = glob.glob(os.path.join(self._stash_dir(), str(token) + ".*"))
        return matches[0] if matches else None

    @staticmethod
    def _drop_stashed(path):
        if path:
            try:
                os.remove(path)
            except OSError:
                pass

    def _import_context(self, request, *, mode="full", **extra):
        stock_mode = request.POST.get("stock_mode") or request.GET.get("stock_mode") or "replace"
        if stock_mode not in STOCK_MODES:
            stock_mode = "replace"
        context = {
            "opts": self.model._meta,
            "title": "ورود محصولات از اکسل",
            "errors": [],
            "result": None,
            "mode": mode,
            "stock_mode": stock_mode,
            "update_columns": "، ".join(UPDATE_ALL_COLUMNS),
            "all_columns": ", ".join(UPDATE_ALL_COLUMNS),
            "stock_modes": STOCK_MODES,
        }
        context.update(extra)
        return context

    def _render_import(self, request, context, template="admin/products/product_import_form.html"):
        # Every error page offers the per-row error report as a download.
        errors = context.get("errors") or []
        request.session[self._ERRORS_KEY] = errors
        return TemplateResponse(request, template, context)

    def _errors_response(self, request):
        text = errors_csv(request.session.get(self._ERRORS_KEY) or [])
        return HttpResponse(
            text.encode("utf-8-sig"),
            content_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="import-errors.csv"'},
        )

    def import_view(self, request):
        """One page, four steps: choose the file, choose the sheet (only
        when the workbook has several), map the columns nobody recognizes,
        then preview and confirm. Nothing is written before the confirm."""
        mode = request.POST.get("mode") or request.GET.get("mode") or "full"
        if mode not in ("full", "update"):
            mode = "full"
        # A plain HTML checkbox cannot set the mode by itself.
        if request.POST.get("update_only") == "1":
            mode = "update"
        context = self._import_context(request, mode=mode)

        if request.GET.get("errors") == "csv":
            return self._errors_response(request)

        if request.method == "POST":
            # Step: the owner confirmed a pending preview.
            if request.POST.get("confirm") == "1":
                return self._confirm_pending(request, context, mode=mode)
            if request.POST.get("cancel") == "1":
                request.session.pop(self._PENDING_KEY, None)
                self.message_user(request, "عملیات لغو شد؛ چیزی ذخیره نشد.", messages.INFO)
                return HttpResponseRedirect(reverse("admin:products_product_changelist"))

            # Locate the file: a fresh upload, or the stashed copy from a
            # previous step of the same flow.
            token = request.POST.get("token") or ""
            stashed = self._stashed_path(token)
            upload = request.FILES.get("file")
            source = upload or stashed
            if source is None:
                context["errors"] = ["فایلی انتخاب نشده است. یک فایل .csv یا .xlsx بارگذاری کنید."]
                return self._render_import(request, context)

            try:
                sheets = sheet_names(source) if upload is not None or stashed else []
            except Exception:  # pragma: no cover - corrupt workbook
                sheets = []

            sheet = request.POST.get("sheet") or ""
            if len(sheets) > 1 and not sheet:
                # Ask which worksheet to read before touching the data.
                if upload is not None:
                    token = self._stash_upload(upload)
                return self._render_import(
                    request,
                    self._import_context(
                        request, mode=mode, step="sheet", sheets=sheets, token=token
                    ),
                    template="admin/products/product_import_sheet.html",
                )

            try:
                rows, header = read_rows(source, sheet=sheet or None)
            except (ValueError, OSError) as exc:
                context["errors"] = [str(exc)]
                self._drop_stashed(stashed)
                return self._render_import(request, context)

            mapping, unknown = resolve_headers(header, mode=mode)

            if unknown and request.POST.get("step") != "mapping":
                # Columns we do not recognize: ask the owner what they are
                # (dropdown per column) and show a preview of the values.
                if upload is not None:
                    token = self._stash_upload(upload)
                preview_columns = list(header)
                preview_rows = [
                    [row.get(key) for key in preview_columns] for row in rows[:5]
                ]
                unknown_columns = [
                    {
                        "name": column,
                        # A few real values so the owner recognizes the column.
                        "samples": "، ".join(
                            str(row.get(column))
                            for row in rows
                            if row.get(column) not in (None, "") 
                        )[:60] or "—",
                    }
                    for column in unknown
                ]
                return self._render_import(
                    request,
                    self._import_context(
                        request,
                        mode=mode,
                        step="mapping",
                        token=token,
                        sheet=sheet,
                        unknown_columns=unknown_columns,
                        preview_columns=preview_columns,
                        preview_rows=preview_rows,
                        mapping_options=self._mapping_options(mode),
                    ),
                    template="admin/products/product_import_mapping.html",
                )

            if request.POST.get("step") == "mapping":
                # Apply the owner's choices ("" = ignore this column).
                unknown_columns = request.POST.getlist("unknown_columns")
                choices = request.POST.getlist("map")
                for index, column in enumerate(unknown_columns):
                    choice = choices[index] if index < len(choices) else ""
                    mapping[column] = choice or None

            rows, header = canonical_rows(rows, mapping, mode=mode)
            self._drop_stashed(stashed)

            if mode == "update":
                return self._start_update(request, context, rows, header)

            if request.POST.get("dry_run") == "1":
                result = import_products_from_rows(rows, header, dry_run=True)
                if not result.ok:
                    context["errors"] = result.errors
                    return self._render_import(request, context)
                return self._render_import(
                    request, {**context, "result": result, "dry_run": True}
                )

            result = import_products_from_rows(rows, header)
            if not result.ok:
                context["errors"] = result.errors
                return self._render_import(request, context)
            self.message_user(
                request,
                f"ورود انجام شد: {result.created} کالای جدید ساخته شد، "
                f"{result.updated} کالا به‌روزرسانی شد.",
                messages.SUCCESS,
            )
            return HttpResponseRedirect(reverse("admin:products_product_changelist"))

        if request.GET.get("pending") == "1" and self._PENDING_KEY in request.session:
            pending = request.session[self._PENDING_KEY]
            context.update({
                "pending": pending,
                "columns": ", ".join(UPDATE_ALL_COLUMNS),
                "mode": pending.get("mode", mode),
            })
            return TemplateResponse(
                request, "admin/products/product_import_preview.html", context
            )
        return TemplateResponse(
            request, "admin/products/product_import_form.html", context
        )

    @staticmethod
    def _mapping_options(mode):
        """What an unrecognized column can be mapped to."""
        if mode == "update":
            return [
                ("", "— نادیده بگیر (بدون تغییر) —"),
                ("sku", "کد کالا (sku)"),
                ("name", "نام کالا"),
                ("price", "قیمت فروش"),
                ("compare_at_price", "قیمت حراج / قیمت با تخفیف"),
                ("stock_quantity", "موجودی"),
                ("category_slug", "دسته‌بندی"),
                ("brand_name", "برند"),
                ("is_active", "فعال / وضعیت"),
            ]
        return [
            ("", "— نادیده بگیر —"),
            ("name", "نام کالا (name)"),
            ("slug", "شناسه (slug)"),
            ("sku", "کد کالا (sku)"),
            ("category_slug", "دسته‌بندی (category_slug)"),
            ("brand_name", "برند (brand_name)"),
            ("price", "قیمت (price)"),
            ("compare_at_price", "قیمت حراج / قبل از تخفیف"),
            ("discount_percentage", "درصد تخفیف"),
            ("stock_quantity", "موجودی (stock_quantity)"),
            ("low_stock_threshold", "آستانهٔ کمبودی"),
            ("short_description", "توضیح کوتاه"),
            ("description", "توضیحات"),
            ("is_active", "فعال (is_active)"),
            ("is_featured", "ویژه (is_featured)"),
        ]

    def _start_update(self, request, context, rows, header):
        """Price/stock update: always preview first, then confirm."""
        stock_mode = context["stock_mode"]
        result = update_products_from_rows(
            rows, header, dry_run=True, stock_mode=stock_mode
        )
        if not result.ok:
            context["errors"] = result.errors
            return self._render_import(request, context)
        if result.updated == 0:
            self.message_user(
                request,
                "هیچ تغییری لازم نیست؛ همهٔ مقدارهای فایل با وضعیت فعلی یکسان است.",
                messages.INFO,
            )
            return HttpResponseRedirect(reverse("admin:products_product_changelist"))
        request.session[self._PENDING_KEY] = {
            "mode": "update",
            "rows": rows,
            "header": header,
            "stock_mode": stock_mode,
            "updated": result.updated,
            "skipped": result.skipped,
            "changes": result.changes[:200],
            "changes_total": len(result.changes),
            "changes_more": max(0, len(result.changes) - 200),
        }
        return HttpResponseRedirect(
            reverse("admin:products_product_import") + "?pending=1"
        )

    def _confirm_pending(self, request, context, mode="full"):
        pending = request.session.pop(self._PENDING_KEY, None)
        if pending is None:
            self.message_user(request, "پیش‌نمایشی برای تأیید وجود ندارد.", messages.WARNING)
            return HttpResponseRedirect(reverse("admin:products_product_import"))
        result = update_products_from_rows(
            pending["rows"], pending["header"], stock_mode=pending.get("stock_mode", "replace")
        )
        if not result.ok:
            # Data changed between preview and confirm -- be honest, write
            # nothing, show the new errors.
            context["errors"] = result.errors
            return self._render_import(request, context)
        self.message_user(
            request,
            f"به‌روزرسانی انجام شد: {result.updated} محصول تغییر کرد، "
            f"{result.skipped} ردیف بدون تغییر ماند.",
            messages.SUCCESS,
        )
        return HttpResponseRedirect(reverse("admin:products_product_changelist"))

    fieldsets = (
        ("اطلاعات اصلی", {"fields": ("name", "slug", "sku", "category", "brand")}),
        ("توضیحات", {"fields": ("short_description", "description")}),
        ("قیمت‌گذاری", {"fields": ("price", "compare_at_price", "discount_percentage")}),
        ("موجودی", {"fields": ("stock_quantity", "low_stock_threshold")}),
        ("وضعیت و نمایش", {"fields": ("is_active", "is_featured", "is_new", "is_best_seller")}),
    )

    # --- Changelist columns ---------------------------------------------------

    def get_queryset(self, request):
        # Load the product metadata and primary thumbnail in batches -- no
        # per-row queries for category, brand or image.
        return super().get_queryset(request).select_related(
            "category", "brand"
        ).prefetch_related(
            Prefetch(
                "images",
                queryset=ProductImage.objects.filter(is_primary=True),
                to_attr="primary_images",
            )
        )

    # Excel files downloaded from the panel used to fall back to whatever
    # the server's mime registry guessed (often application/zip), which
    # some browsers then refused to open with Excel. Name the type.
    XLSX_CONTENT_TYPE = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    def get_changelist_formset(self, request, **kwargs):
        formset = super().get_changelist_formset(request, **kwargs)
        # «910000» is hard to read; both money columns get a grouped,
        # Persian-digit hint under the input.
        for money_field in ("price", "compare_at_price"):
            field = formset.form.base_fields[money_field]
            attrs = dict(field.widget.attrs)
            attrs.update({"dir": "ltr", "inputmode": "numeric"})
            field.widget = ProductPriceChangelistWidget(attrs=attrs)
        stock_field = formset.form.base_fields["stock_quantity"]
        attrs = dict(stock_field.widget.attrs)
        attrs.update({"dir": "ltr", "inputmode": "numeric"})
        stock_field.widget = ProductStockChangelistWidget(attrs=attrs)

        form_class = formset.form
        base_init = form_class.__init__

        def init_with_product_threshold(form, *args, **form_kwargs):
            base_init(form, *args, **form_kwargs)
            form.fields["stock_quantity"].widget.low_stock_threshold = getattr(
                form.instance,
                "low_stock_threshold",
                settings.LOW_STOCK_THRESHOLD,
            )

        form_class.__init__ = init_with_product_threshold
        return formset

    def thumbnail_column(self, obj):
        # Part S4 item 1: same shared placeholder markup as the inline
        # preview -- a product with no image (or a broken file) never shows
        # a broken-image icon or an empty cell.
        from apps.core.image_files import image_or_placeholder_html

        primary = next(iter(getattr(obj, "primary_images", [])), None)
        return image_or_placeholder_html(primary and (primary.thumbnail or primary.image))

    thumbnail_column.short_description = ""

    @admin.display(description="محصول", ordering="name")
    def product_summary(self, obj):
        """One linked, sortable cell for the product identity and metadata."""
        category_name = obj.category.name if obj.category_id else "—"
        brand_name = obj.brand.name if obj.brand_id else "—"
        return format_html(
            '<span class="cusin-product-summary" dir="rtl">'
            '<span class="cusin-product-summary__thumbnail">{}</span>'
            '<span class="cusin-product-summary__details">'
            '<span class="cusin-product-summary__name" title="{}">{}</span>'
            '<bdi class="cusin-product-summary__sku" dir="ltr" title="{}">{}</bdi>'
            '<span class="cusin-product-summary__meta">'
            '<span class="cusin-product-summary__category" title="{}">{}</span>'
            '<span class="cusin-product-summary__separator" aria-hidden="true">·</span>'
            '<span class="cusin-product-summary__brand" title="{}">{}</span>'
            '</span></span></span>',
            self.thumbnail_column(obj),
            obj.name,
            obj.name,
            obj.sku,
            obj.sku,
            category_name,
            category_name,
            brand_name,
            brand_name,
        )

    @admin.display(description="", ordering="name")
    def storefront_data(self, obj):
        """Expose the existing public product URL to the row-action menu.

        This empty presentation-only cell is hidden by the admin theme; it
        neither changes routes nor grants access to the storefront.
        """
        store_url = f"{settings.FRONTEND_URL.rstrip('/')}/products/{obj.slug}/"
        return format_html('<span data-cusin-store-url="{}" hidden></span>', store_url)

    def stock_column(self, obj):
        # Same Persian wording as before, now rendered with the theme's
        # badge classes (A4/B4a); with the theme disabled the classes
        # simply have no styling and the text still reads identically.
        if obj.stock_quantity == 0:
            return format_html(
                '<span class="cusin-badge stock-out">۰ — ناموجود</span>'
            )
        if obj.is_low_stock:
            return format_html(
                '<span class="cusin-badge stock-low">{} موجودی کم</span>',
                obj.stock_quantity,
            )
        return format_html(
            '<span class="cusin-badge stock-ok">{}</span>', obj.stock_quantity
        )

    stock_column.short_description = "وضعیت"
    stock_column.admin_order_field = "stock_quantity"

    # --- Bulk actions ----------------------------------------------------------

    @admin.action(description="فعال‌سازی محصولات انتخاب‌شده")
    def activate_products(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f"{count} محصول فعال شد.", messages.SUCCESS)

    @admin.action(description="پنهان کردن از فروشگاه")
    def deactivate_products(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(
            request,
            f"{fa_digits(count)} محصول از فروشگاه پنهان شد؛ "
            "هر وقت خواستید با «فعال‌سازی محصولات انتخاب‌شده» برمی‌گردند.",
            messages.SUCCESS,
        )

    @admin.action(description="ویژه‌کردن محصولات انتخاب‌شده")
    def mark_featured(self, request, queryset):
        count = queryset.update(is_featured=True)
        self.message_user(request, f"{count} محصول ویژه شد.", messages.SUCCESS)

    @admin.action(description="خارج‌کردن محصولات انتخاب‌شده از حالت ویژه")
    def unmark_featured(self, request, queryset):
        count = queryset.update(is_featured=False)
        self.message_user(request, f"{count} محصول از حالت ویژه خارج شد.", messages.SUCCESS)

    # --- B4b: duplicate a product --------------------------------------------

    @staticmethod
    def _unique_product_name(base: str) -> str:
        """«نام (کپی)», «نام (کپی ۲)», ... -- first unused, within max_length."""
        max_len = Product._meta.get_field("name").max_length
        from apps.adminui.jalali import fa_digits

        candidate = f"{base} (کپی)"
        n = 2
        while Product.objects.filter(name=candidate).exists():
            suffix = f" (کپی {fa_digits(n)})"
            keep = max_len - len(suffix)
            candidate = f"{base[:keep]}{suffix}"
            n += 1
            if n > 500:  # pragma: no cover - defensive
                raise ValidationError("نام مناسبی برای کپی پیدا نشد.")
        return candidate[:max_len]

    @staticmethod
    def _unique_slug(base_slug: str) -> str:
        max_len = Product._meta.get_field("slug").max_length
        candidate = slugify(f"{base_slug}-copy", allow_unicode=True)[:max_len]
        n = 2
        while Product.objects.filter(slug=candidate).exists():
            suffix = f"-copy-{n}"
            candidate = f"{slugify(base_slug, allow_unicode=True)[:max_len - len(suffix)]}{suffix}"
            n += 1
            if n > 500:  # pragma: no cover - defensive
                raise ValidationError("شناسهٔ مناسبی برای کپی پیدا نشد.")
        return candidate

    @staticmethod
    def _unique_sku(base_sku: str) -> str:
        max_len = Product._meta.get_field("sku").max_length
        candidate = f"{base_sku}-copy"[:max_len]
        n = 2
        while Product.objects.filter(sku=candidate).exists():
            suffix = f"-copy-{n}"
            candidate = f"{base_sku[:max_len - len(suffix)]}{suffix}"
            n += 1
            if n > 500:  # pragma: no cover - defensive
                raise ValidationError("کد کالای مناسبی برای کپی پیدا نشد.")
        return candidate

    @admin.action(description="کپی محصول (نسخهٔ غیرفعال، بدون تصویر)")
    def duplicate_product(self, request, queryset):
        if not self.has_add_permission(request):
            self.message_user(
                request, "برای کپی محصول به دسترسی «افزودن محصول» نیاز دارید.",
                messages.ERROR,
            )
            return None

        # Copy scalar fields + FKs + the complements M2M. Images and
        # variants are deliberately NOT copied: image rows would share the
        # same media files (deleting the copy would delete the original's
        # files) and variant SKUs are unique -- both belong to a manual
        # re-upload. The copy starts INACTIVE so it never leaks into the
        # storefront before the owner reviews it.
        skip = {
            "id", "pk", "created_at", "updated_at",
            "search_text", "search_name",
        }
        made = []
        with transaction.atomic():
            for product in queryset.order_by("pk"):
                copy = Product()
                for field in Product._meta.concrete_fields:
                    if field.name in skip:
                        continue
                    setattr(copy, field.attname, getattr(product, field.attname))
                copy.pk = None
                copy.is_active = False
                copy.name = self._unique_product_name(product.name)
                copy.slug = self._unique_slug(product.slug)
                copy.sku = self._unique_sku(product.sku)
                copy.full_clean()  # uniqueness of the suffixed name/slug/sku re-checked
                copy.save()
                copy.complements.set(product.complements.all())
                self.log_addition(request, copy, [
                    {"added": {"name": "کپی محصول", "object": f"از #{product.pk} «{product.name}»"}}
                ])
                made.append(copy)

        if len(made) == 1:
            msg = f"کپی غیرفعال از «{made[0].name}» ساخته شد (SKU: {made[0].sku})."
        else:
            msg = f"{len(made)} کپی غیرفعال از محصولات انتخاب‌شده ساخته شد."
        self.message_user(request, msg, messages.SUCCESS)
        return None

    # --- B4c: percentage price change (all-or-nothing, with preview + CSV) ---

    PRICE_PERCENT_MIN = -99
    PRICE_PERCENT_MAX = 999
    PRICE_ROUNDINGS = {"none": "بدون گردکردن", "100": "گرد به ۱۰۰ تومان", "1000": "گرد به ۱٬۰۰۰ تومان"}

    # --- Task 3: move products to a leaf category ----------------------------

    @admin.action(description="انتقال به دسته…")
    def move_to_category(self, request, queryset):
        if not self.has_change_permission(request):
            self.message_user(
                request,
                "برای انتقال محصول به دسترسی ویرایش محصولات نیاز دارید.",
                messages.ERROR,
            )
            return None
        ids = ",".join(
            str(pk) for pk in queryset.order_by("pk").values_list("pk", flat=True)
        )
        context = {
            **self.admin_site.each_context(request),
            "title": "انتقال به دسته…",
            "opts": self.model._meta,
            "ids": ids,
            "count": queryset.count(),
            "leaf_categories": [
                (category.pk, category.full_path)
                for category in leaf_categories_queryset()
            ],
            "action_url": reverse("admin:products_product_move_to_category"),
            "changelist_url": reverse("admin:products_product_changelist"),
        }
        return TemplateResponse(
            request, "admin/products/product_move_to_category.html", context
        )

    def move_to_category_view(self, request):
        """POST-only: move the chosen products to one leaf category."""
        if request.method != "POST":
            return HttpResponseRedirect(reverse("admin:products_product_changelist"))
        if not self.has_change_permission(request):
            raise PermissionDenied
        changelist_url = reverse("admin:products_product_changelist")
        try:
            ids = sorted(
                {int(x) for x in (request.POST.get("ids") or "").split(",") if x.strip()}
            )
            category_id = int(request.POST.get("category") or "")
        except ValueError:
            self.message_user(
                request, "محصول یا دستهٔ انتخاب‌شده معتبر نیست.", messages.ERROR
            )
            return HttpResponseRedirect(changelist_url)
        try:
            target = Category.objects.get(pk=category_id)
        except Category.DoesNotExist:
            self.message_user(
                request, "دستهٔ انتخاب‌شده پیدا نشد.", messages.ERROR
            )
            return HttpResponseRedirect(changelist_url)
        if target.children.exists():
            self.message_user(
                request,
                f"«{target.name}» دستهٔ والد است؛ "
                + LEAF_CATEGORY_HELP,
                messages.ERROR,
            )
            return HttpResponseRedirect(changelist_url)
        products = list(
            self.get_queryset(request).filter(pk__in=ids).order_by("sku")
        )
        if not products:
            self.message_user(
                request, "محصولی برای انتقال انتخاب نشده است.", messages.ERROR
            )
            return HttpResponseRedirect(changelist_url)
        with transaction.atomic():
            for product in products:
                old_name = product.category.name if product.category_id else "—"
                product.category = target
                # Product.save() recomputes the search index (which
                # embeds the category name); name the fields so the
                # recomputed index is actually written.
                product.save(
                    update_fields=["category", "search_text", "search_name", "updated_at"]
                )
                self.log_change(
                    request,
                    product,
                    f"انتقال دسته: «{old_name}» → «{target.full_path}»",
                )
        self.message_user(
            request,
            f"{fa_digits(len(products))} محصول به دستهٔ «{target.full_path}» منتقل شد.",
            messages.SUCCESS,
        )
        return HttpResponseRedirect(changelist_url)

    @admin.action(description="تغییر درصدی قیمت (با پیش‌نمایش و تأیید)")
    def change_price_percentage(self, request, queryset):
        if not self.has_change_permission(request):
            self.message_user(
                request, "برای تغییر قیمت به دسترسی ویرایش محصولات نیاز دارید.",
                messages.ERROR,
            )
            return None
        ids = ",".join(str(pk) for pk in queryset.order_by("pk").values_list("pk", flat=True))
        context = {
            **self.admin_site.each_context(request),
            "title": "تغییر درصدی قیمت",
            "opts": self.model._meta,
            "ids": ids,
            "count": queryset.count(),
            "roundings": self.PRICE_ROUNDINGS.items(),
            "action_url": reverse("admin:products_product_price_percent"),
        }
        return TemplateResponse(request, "admin/products/product_price_percent_form.html", context)

    def _parse_price_percent_request(self, request):
        """Shared parsing for the preview/apply/CSV steps. Never trusts
        client-side prices: only ids + percent + rounding come back, and
        all maths is recomputed from the database rows."""
        if not self.has_change_permission(request):
            raise PermissionDenied
        try:
            ids = sorted({int(x) for x in (request.POST.get("ids") or "").split(",") if x.strip()})
        except ValueError:
            raise ValidationError("شناسهٔ محصولات نامعتبر است.")
        try:
            # Accept Persian/Arabic digits and a leading '+' for convenience;
            # int() still rejects anything else.
            raw_percent = (
                request.POST.get("percent", "")
                .translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
                .strip()
            )
            percent = int(raw_percent)
        except ValueError:
            raise ValidationError("درصد را به‌صورت عدد صحیح وارد کنید (مثلاً ۱۵ یا ۱۰-).")
        if not self.PRICE_PERCENT_MIN <= percent <= self.PRICE_PERCENT_MAX:
            raise ValidationError(
                f"درصد باید بین {self.PRICE_PERCENT_MIN} و {self.PRICE_PERCENT_MAX} باشد."
            )
        rounding = request.POST.get("rounding", "none")
        if rounding not in self.PRICE_ROUNDINGS:
            raise ValidationError("حالت گردکردن نامعتبر است.")
        products = list(self.get_queryset(request).filter(pk__in=ids).order_by("sku"))
        if not products:
            raise ValidationError("محصولی برای تغییر انتخاب نشده است.")
        return products, percent, rounding

    @staticmethod
    def _apply_percent(value: int | None, percent: int, rounding: str) -> int | None:
        """new = round(value * (1 + percent/100)) then optional rounding to
        the nearest 100/1000 Toman (ROUND_HALF_UP, never negative). The
        function is monotonic non-decreasing, so compare_at >= price is
        preserved when both are scaled identically."""
        if value is None:
            return None
        new = Decimal(value) * (Decimal(100) + Decimal(percent)) / Decimal(100)
        new = new.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        if rounding in ("100", "1000"):
            step = Decimal(rounding)
            new = (new / step).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * step
        return int(max(new, Decimal(0)))

    def _price_percent_rows(self, products, percent, rounding):
        rows = []
        for product in products:
            rows.append({
                "product": product,
                "price_before": product.price,
                "price_after": self._apply_percent(product.price, percent, rounding),
                "compare_before": product.compare_at_price,
                "compare_after": self._apply_percent(product.compare_at_price, percent, rounding),
            })
        return rows

    def price_percent_view(self, request):
        """POST-only multi-step endpoint: preview -> confirm / CSV / cancel."""
        if request.method != "POST":
            return HttpResponseRedirect(reverse("admin:products_product_changelist"))
        try:
            products, percent, rounding = self._parse_price_percent_request(request)
        except (PermissionDenied, ValidationError) as exc:
            if isinstance(exc, PermissionDenied):
                raise
            self.message_user(request, exc.messages[0], messages.ERROR)
            return HttpResponseRedirect(reverse("admin:products_product_changelist"))

        rows = self._price_percent_rows(products, percent, rounding)
        base_context = {
            **self.admin_site.each_context(request),
            "title": "تغییر درصدی قیمت",
            "opts": self.model._meta,
            "ids": request.POST.get("ids", ""),
            "percent": percent,
            "rounding": rounding,
            "rounding_label": self.PRICE_ROUNDINGS[rounding],
            "rows": rows,
            "total_count": len(rows),
            "action_url": reverse("admin:products_product_price_percent"),
            "changelist_url": reverse("admin:products_product_changelist"),
        }

        if "apply" in request.POST:
            try:
                with transaction.atomic():
                    for row in rows:
                        product = row["product"]
                        product.price = row["price_after"]
                        product.compare_at_price = row["compare_after"]
                        # Same validation the change form runs -- a product
                        # that cannot be saved aborts EVERYTHING (rollback).
                        product.full_clean()
                        product.save(update_fields=["price", "compare_at_price", "updated_at"])
                        self.log_change(
                            request, product,
                            f"تغییر درصدی قیمت ({percent:+d}٪، {self.PRICE_ROUNDINGS[rounding]}): "
                            f"{row['price_before']:,} → {row['price_after']:,}"
                            + (
                                f"؛ قیمت قبل تخفیف {row['compare_before']:,} → {row['compare_after']:,}"
                                if row["compare_before"] is not None and row["compare_after"] is not None
                                else ""
                            ),
                        )
            except ValidationError as exc:
                self.message_user(
                    request,
                    "تغییر قیمت اعمال نشد (هیچ محصولی ذخیره نشد): " + "؛ ".join(exc.messages),
                    messages.ERROR,
                )
                return HttpResponseRedirect(reverse("admin:products_product_changelist"))
            self.message_user(
                request,
                f"قیمت {len(rows)} محصول {percent:+d}٪ تغییر کرد ({self.PRICE_ROUNDINGS[rounding]}).",
                messages.SUCCESS,
            )
            return HttpResponseRedirect(reverse("admin:products_product_changelist"))

        if "csv" in request.POST:
            response = HttpResponse(content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = 'attachment; filename="price-changes.csv"'
            response.write("\ufeff")  # BOM so Excel reads Persian correctly
            writer = csv.writer(response)
            writer.writerow([
                "sku", "نام محصول", "درصد", "گردکردن",
                "قیمت قبل", "قیمت بعد", "قیمت قبل تخفیف (قبل)", "قیمت قبل تخفیف (بعد)",
            ])
            for row in rows:
                writer.writerow([
                    row["product"].sku, row["product"].name, percent,
                    self.PRICE_ROUNDINGS[rounding],
                    row["price_before"], row["price_after"],
                    row["compare_before"] if row["compare_before"] is not None else "",
                    row["compare_after"] if row["compare_after"] is not None else "",
                ])
            return response

        return TemplateResponse(request, "admin/products/product_price_percent_preview.html", base_context)

    # --- Image formset post-save: guarantee exactly one primary image ----------

    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)
        if formset.model is not ProductImage:
            return
        product = formset.instance
        images = list(product.images.order_by("ordering", "pk"))
        if not images:
            return
        primaries = [img for img in images if img.is_primary]
        if not primaries:
            # The owner forgot to pick one: the first image (by ordering)
            # becomes the main image instead of the product showing up
            # imageless on the storefront.
            first = images[0]
            first.is_primary = True
            first.save(update_fields=["is_primary", "updated_at"])
            self.message_user(
                request,
                f"«{first.image.name}» به‌صورت خودکار به‌عنوان تصویر اصلی ثبت شد.",
                messages.INFO,
            )


@admin.register(ProductAttribute)
class ProductAttributeAdmin(admin.ModelAdmin):
    list_display = ("name",)
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)


@admin.register(ProductAttributeValue)
class ProductAttributeValueAdmin(admin.ModelAdmin):
    list_display = ("attribute", "value")
    list_filter = ("attribute",)
    search_fields = ("value",)
    autocomplete_fields = ("attribute",)


@admin.register(ProductVariant)
class ProductVariantAdmin(AdminSkuDirectionMixin, admin.ModelAdmin):
    """
    Registered standalone (in addition to being inlined under
    ProductAdmin) purely so `search_fields` exists here -- Django's
    `autocomplete_fields` on other apps' admins (e.g. apps.cart.admin's
    CartItemInline) requires the target model to have its own registered
    ModelAdmin with search_fields, even if it's primarily edited inline.
    """
    list_display = ("sku", "product", "price", "stock_quantity", "is_active")
    list_filter = ("is_active", "attribute_values__attribute")
    search_fields = ("sku", "product__name")
    filter_horizontal = ("attribute_values",)
    autocomplete_fields = ("product",)


from .models import BackInStockSubscription


def _product_delete_permission(request, extra_codenames=()):
    """True when staff may delete a product (or one of ``extra_codenames``).

    Derived/helper rows (back-in-stock subscriptions, mined
    frequently-bought-together pairs) already cascade with their
    product at the database level, but Django's delete confirmation
    also asks each related model's admin for delete permission and
    blocks the whole deletion when it is refused. Returning False
    unconditionally therefore made products with helper rows
    undeletable even for a superuser. Delegating to the product
    delete permission keeps the signup/pair lists read-only for
    everyone else while letting a product deletion take its helper
    rows with it.
    """
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if user.has_perm("products.delete_product"):
        return True
    return any(user.has_perm(codename) for codename in extra_codenames)


@admin.register(BackInStockSubscription)
class BackInStockSubscriptionAdmin(admin.ModelAdmin):
    """Strictly read-only audit of "notify me" signups (Part 2).

    The one exception is deletion by staff who may delete the product
    (or variant) itself -- see ``_product_delete_permission`` -- so a
    product deletion is never blocked by its own subscription rows.
    """

    list_display = (
        "phone", "product", "variant",
        jalali_column("created_at", "تاریخ ثبت", with_time=True),
        jalali_column("notified_at", "زمان اطلاع‌رسانی", with_time=True),
    )
    list_filter = ("notified_at", "created_at")
    search_fields = ("phone", "product__name")
    readonly_fields = tuple(f.name for f in BackInStockSubscription._meta.concrete_fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return _product_delete_permission(
            request, extra_codenames=("products.delete_productvariant",)
        )


from .models import FrequentlyBoughtTogether  # noqa: E402


@admin.register(FrequentlyBoughtTogether)
class FrequentlyBoughtTogetherAdmin(admin.ModelAdmin):
    """Part R5 item 9: read-only view of the mined «خرید همراه» pairs.

    Data is owned by the rebuild_frequently_bought_together command
    (full idempotent rebuild, run daily by the production scheduler);
    hand-editing rows here would be wiped at the next rebuild, so the
    admin is read-only -- except deletion by staff who may delete the
    product itself, so a product deletion is never blocked by its own
    derived pairs (see ``_product_delete_permission``).
    """

    list_display = ("product", "complement", "co_count", "updated_at")
    ordering = ("-co_count",)
    search_fields = ("product__name", "complement__name")
    readonly_fields = tuple(f.name for f in FrequentlyBoughtTogether._meta.concrete_fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return _product_delete_permission(request)
