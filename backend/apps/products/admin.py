"""
Products admin registration (Phase B - Store management).

Designed for the shop owner's daily work: images inline (one marked
primary -- auto-assigned if forgotten, rejected if duplicated), bulk
activate/deactivate/feature actions, and a changelist that shows a
thumbnail, price and an at-a-glance stock warning.
"""
from django import forms
from django.contrib import admin, messages
from django.db.models import Prefetch
from django.http import FileResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

import io

from .importing import (
    UPDATE_TEMPLATE_COLUMNS,
    _update_template_csv,
    export_products_csv,
    export_products_xlsx,
    import_products_from_rows,
    read_rows,
    template_csv,
    update_products_from_rows,
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


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0
    fields = ("sku", "price", "stock_quantity", "is_active", "attribute_values")
    filter_horizontal = ("attribute_values",)
    show_change_link = True


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    # Part R2: featured tiles are managed right from the changelist --
    # tick is_featured and set display_order inline, or use bulk actions.
    list_display = ("name", "slug", "is_featured", "display_order", "is_active")
    list_editable = ("is_featured", "display_order")
    list_filter = ("is_active", "is_featured")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    actions = ("make_featured", "make_not_featured")

    @admin.action(description="برند ویژه: بله")
    def make_featured(self, request, queryset):
        queryset.update(is_featured=True)

    @admin.action(description="برند ویژه: خیر")
    def make_not_featured(self, request, queryset):
        queryset.update(is_featured=False)


class LowStockFilter(admin.SimpleListFilter):
    """Part R4 item 3: one-click view of everything at/below the owner
    low-stock threshold (env LOW_STOCK_THRESHOLD, default 3)."""

    title = "وضعیت موجودی"
    parameter_name = "low_stock"

    def lookups(self, request, model_admin):
        return (("1", "موجودی کم"), ("0", "موجودی کافی"))

    def queryset(self, request, queryset):
        from django.conf import settings

        if self.value() == "1":
            return queryset.filter(stock_quantity__lte=settings.LOW_STOCK_THRESHOLD)
        if self.value() == "0":
            return queryset.filter(stock_quantity__gt=settings.LOW_STOCK_THRESHOLD)
        return queryset


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "thumbnail_column", "name", "sku", "category", "brand", "price",
        "stock_column", "is_active", "is_featured",
    )
    list_filter = ("is_active", "is_featured", "is_new", "is_best_seller", "category", "brand", LowStockFilter)
    search_fields = ("name", "sku", "slug")
    prepopulated_fields = {"slug": ("name",)}
    # Part R5 item 9: complements is an M2M to Product itself -- the
    # autocomplete widget searches by ProductAdmin.search_fields above.
    autocomplete_fields = ("category", "brand", "complements")
    inlines = [ProductImageInline, ProductVariantInline]
    actions = ["activate_products", "deactivate_products", "mark_featured", "unmark_featured"]
    change_list_template = "admin/products/product_change_list.html"

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
        ]
        return custom + super().get_urls()

    _PENDING_KEY = "cusin_product_update_pending"

    def import_template_download(self, request):
        """The documented sample template, generated from the same column
        list the importer validates against."""
        buffer = io.BytesIO(template_csv().encode("utf-8-sig"))
        return FileResponse(
            buffer, as_attachment=True, filename="product_import_template.csv"
        )

    def update_template_download(self, request):
        """Part R4 item 6: minimal price/stock update template."""
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
                buffer, as_attachment=True, filename="cusin_products_export.xlsx"
            )
        buffer = io.BytesIO(export_products_csv().encode("utf-8-sig"))
        return FileResponse(
            buffer, as_attachment=True, filename="cusin_products_export.csv"
        )

    def import_view(self, request):
        context = {
            "opts": self.model._meta,
            "title": "Import products from a file",
            "errors": [],
            "result": None,
            "update_columns": ", ".join(UPDATE_TEMPLATE_COLUMNS),
        }
        if request.method == "POST":
            # Step 2: the owner confirmed the pending update-only preview.
            if request.POST.get("confirm") == "1":
                return self._confirm_pending_update(request)
            if request.POST.get("cancel") == "1":
                request.session.pop(self._PENDING_KEY, None)
                return HttpResponseRedirect(reverse("admin:products_product_changelist"))

            upload = request.FILES.get("file")
            if upload is None:
                context["errors"] = ["Choose a .csv or .xlsx file to import."]
                return TemplateResponse(
                    request, "admin/products/product_import_form.html", context
                )
            try:
                rows, header = read_rows(upload)
            except ValueError as exc:
                context["errors"] = [str(exc)]
                return TemplateResponse(
                    request, "admin/products/product_import_form.html", context
                )

            # Update-only mode: preview first, apply on explicit confirm.
            if request.POST.get("update_only") == "1":
                result = update_products_from_rows(rows, header, dry_run=True)
                if not result.ok:
                    context["errors"] = result.errors
                    return TemplateResponse(
                        request, "admin/products/product_import_form.html", context
                    )
                if result.updated == 0:
                    self.message_user(
                        request,
                        "هیچ تغییری لازم نیست؛ همهٔ مقدارهای فایل با وضعیت فعلی یکسان است.",
                        messages.INFO,
                    )
                    return HttpResponseRedirect(
                        reverse("admin:products_product_changelist")
                    )
                request.session[self._PENDING_KEY] = {
                    "rows": rows,
                    "header": header,
                    "updated": result.updated,
                    "skipped": result.skipped,
                    "changes": result.changes[:200],
                    "changes_total": len(result.changes),
                    "changes_more": max(0, len(result.changes) - 200),
                }
                return HttpResponseRedirect(
                    reverse("admin:products_product_import") + "?pending=1"
                )

            result = import_products_from_rows(rows, header)
            if not result.ok:
                context["errors"] = result.errors
                return TemplateResponse(
                    request, "admin/products/product_import_form.html", context
                )
            self.message_user(
                request,
                f"Import complete: {result.created} created, {result.updated} updated.",
                messages.SUCCESS,
            )
            return HttpResponseRedirect(reverse("admin:products_product_changelist"))

        if request.GET.get("pending") == "1" and self._PENDING_KEY in request.session:
            pending = request.session[self._PENDING_KEY]
            context.update({
                "pending": pending,
                "columns": ", ".join(UPDATE_TEMPLATE_COLUMNS),
            })
            return TemplateResponse(
                request, "admin/products/product_import_preview.html", context
            )
        return TemplateResponse(request, "admin/products/product_import_form.html", context)

    def _confirm_pending_update(self, request):
        pending = request.session.pop(self._PENDING_KEY, None)
        if pending is None:
            self.message_user(request, "پیش‌نمایشی برای تأیید وجود ندارد.", messages.WARNING)
            return HttpResponseRedirect(reverse("admin:products_product_import"))
        result = update_products_from_rows(pending["rows"], pending["header"])
        if not result.ok:
            # Data changed between preview and confirm -- be honest, write
            # nothing, show the new errors.
            context = {
                "opts": self.model._meta,
                "title": "Import products from a file",
                "errors": result.errors,
                "result": None,
                "update_columns": ", ".join(UPDATE_TEMPLATE_COLUMNS),
            }
            return TemplateResponse(
                request, "admin/products/product_import_form.html", context
            )
        self.message_user(
            request,
            f"به‌روزرسانی انجام شد: {result.updated} محصول تغییر کرد، "
            f"{result.skipped} ردیف بدون تغییر ماند.",
            messages.SUCCESS,
        )
        return HttpResponseRedirect(reverse("admin:products_product_changelist"))
    fieldsets = (
        (None, {"fields": ("name", "slug", "sku", "category", "brand")}),
        ("Description", {"fields": ("short_description", "description")}),
        ("Pricing", {"fields": ("price", "compare_at_price", "discount_percentage")}),
        ("Inventory", {"fields": ("stock_quantity", "low_stock_threshold")}),
        ("Flags", {"fields": ("is_active", "is_featured", "is_new", "is_best_seller")}),
    )

    # --- Changelist columns ---------------------------------------------------

    def get_queryset(self, request):
        # One query for every product's primary image (its thumbnail is
        # what the changelist shows) -- no N+1 on the list page.
        return super().get_queryset(request).prefetch_related(
            Prefetch(
                "images",
                queryset=ProductImage.objects.filter(is_primary=True),
                to_attr="primary_images",
            )
        )

    def thumbnail_column(self, obj):
        # Part S4 item 1: same shared placeholder markup as the inline
        # preview -- a product with no image (or a broken file) never shows
        # a broken-image icon or an empty cell.
        from apps.core.image_files import image_or_placeholder_html

        primary = next(iter(getattr(obj, "primary_images", [])), None)
        return image_or_placeholder_html(primary and (primary.thumbnail or primary.image))

    thumbnail_column.short_description = ""

    def stock_column(self, obj):
        if obj.stock_quantity == 0:
            return format_html('<span style="color:#b30000;font-weight:bold">۰ — ناموجود</span>')
        if obj.is_low_stock:
            return format_html(
                '<span style="color:#a05a00;font-weight:bold">{} موجودی کم</span>',
                obj.stock_quantity,
            )
        return str(obj.stock_quantity)

    stock_column.short_description = "موجودی"
    stock_column.admin_order_field = "stock_quantity"

    # --- Bulk actions ----------------------------------------------------------

    @admin.action(description="فعال‌سازی محصولات انتخاب‌شده")
    def activate_products(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f"{count} محصول فعال شد.", messages.SUCCESS)

    @admin.action(description="غیرفعال‌سازی محصولات انتخاب‌شده (عدم نمایش در فروشگاه)")
    def deactivate_products(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, f"{count} محصول غیرفعال شد.", messages.SUCCESS)

    @admin.action(description="ویژه‌کردن محصولات انتخاب‌شده")
    def mark_featured(self, request, queryset):
        count = queryset.update(is_featured=True)
        self.message_user(request, f"{count} محصول ویژه شد.", messages.SUCCESS)

    @admin.action(description="خارج‌کردن محصولات انتخاب‌شده از حالت ویژه")
    def unmark_featured(self, request, queryset):
        count = queryset.update(is_featured=False)
        self.message_user(request, f"{count} محصول از حالت ویژه خارج شد.", messages.SUCCESS)

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
class ProductVariantAdmin(admin.ModelAdmin):
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


@admin.register(BackInStockSubscription)
class BackInStockSubscriptionAdmin(admin.ModelAdmin):
    """Strictly read-only audit of "notify me" signups (Part 2)."""

    list_display = ("phone", "product", "variant", "created_at", "notified_at")
    list_filter = ("notified_at", "created_at")
    search_fields = ("phone", "product__name")
    readonly_fields = tuple(f.name for f in BackInStockSubscription._meta.concrete_fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


from .models import FrequentlyBoughtTogether  # noqa: E402


@admin.register(FrequentlyBoughtTogether)
class FrequentlyBoughtTogetherAdmin(admin.ModelAdmin):
    """Part R5 item 9: read-only view of the mined «خرید همراه» pairs.

    Data is owned by the rebuild_frequently_bought_together command
    (full idempotent rebuild, run daily by the production scheduler);
    hand-editing rows here would be wiped at the next rebuild, so the
    admin is strictly read-only.
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
        return False
