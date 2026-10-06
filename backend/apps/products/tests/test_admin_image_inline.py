"""
Part S5 item 3 (admin half): the product image inline must let the owner
select SEVERAL files at once, set the primary image, and reorder them via
the position (`ordering`) column.

These tests drive the real admin change form (multipart POST) against the
real formset; image files are genuine PNGs so the normal save() path
(thumbnail + WebP variants) runs exactly like a production upload.
"""
import io
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.forms.models import model_to_dict
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.products.models import Product, ProductImage

from .helpers import make_product

TEMP_MEDIA = tempfile.mkdtemp(prefix="cusin-test-media-inline-")
PLAIN_STATIC = {
    "STORAGES": {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
}


def png(name, color=(200, 30, 30)):
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (600, 600), color).save(buffer, format="PNG")
    buffer.seek(0)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def base_formset_data(product, total, initial=1):
    """The management-form fields of BOTH inlines (the admin validates
    every inline, so the variants formset must be submitted -- empty --
    too, exactly like a browser does)."""
    return {
        "images-TOTAL_FORMS": str(total),
        "images-INITIAL_FORMS": str(initial),
        "images-MIN_NUM_FORMS": "0",
        "images-MAX_NUM_FORMS": "1000",
        "variants-TOTAL_FORMS": "0",
        "variants-INITIAL_FORMS": "0",
        "variants-MIN_NUM_FORMS": "0",
        "variants-MAX_NUM_FORMS": "1000",
    }


@override_settings(MEDIA_ROOT=TEMP_MEDIA, **PLAIN_STATIC)
class ProductImageInlineTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        self.owner = get_user_model().objects.create_superuser(
            username="owner", password="x", phone="+989000000123"
        )
        self.client.force_login(self.owner)
        self.product = make_product(name="Inline Product")

    def tearDown(self):
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)

    def _base_payload(self):
        """Every editable Product field with its current value, taken from
        the real admin form -- so the POST is valid the way a browser
        submits it (a hand-written subset silently fails validation and
        the inlines are never saved)."""
        values = model_to_dict(self.product)
        payload = {}
        for key, value in values.items():
            if value is None:
                value = ""
            elif isinstance(value, bool):
                value = "True" if value else "False"
            elif isinstance(value, (list, tuple)):
                payload[key] = [str(item) for item in value]
                continue
            else:
                value = str(value)
            payload[key] = value
        return payload

    def _post_product_change(self, data, files):
        """POST the real admin change form as a browser would.

        A plain dict whose values are LISTS is required: the test client
        encodes each list entry as its own multipart part, while a
        MultiValueDict would send only the last value of each key (its
        .items() yields one value per key) -- which silently turned a
        three-file upload into a one-file upload.
        """
        url = reverse("admin:products_product_change", args=[self.product.pk])
        payload = {**self._base_payload(), **data}
        form_data = {
            key: value if isinstance(value, list) else [value]
            for key, value in payload.items()
        }
        for key, uploads in files.items():
            form_data[key] = list(uploads)
        return self.client.post(url, form_data, follow=True)

    def _assert_saved(self, response):
        """Fail loudly (with the real errors) if the admin re-rendered the
        form instead of saving."""
        if response.redirect_chain:
            return
        adminform = response.context.get("adminform")
        product_errors = adminform.form.errors.as_text() if adminform else "(no form in context)"
        inline_errors = [
            str(fs.formset.non_form_errors())
            + " "
            + " ".join(str(form.errors.as_text()) for form in fs.formset.forms)
            for fs in response.context.get("inline_admin_formsets", [])
        ]
        self.fail(f"admin form did not save. product: {product_errors} inline: {inline_errors}")

    def test_selecting_several_files_at_once_creates_one_row_each(self):
        data = base_formset_data(self.product, total=1, initial=0)
        files = {
            "images-0-add_images": [
                png("a.png"),
                png("b.png", (30, 200, 30)),
                png("c.png", (30, 30, 200)),
            ],
        }

        response = self._post_product_change(data, files)
        self._assert_saved(response)

        images = ProductImage.objects.filter(product=self.product)
        self.assertEqual(images.count(), 3)
        # Every row really stores a file, with a generated thumbnail.
        for image in images:
            self.assertTrue(image.image)
            self.assertTrue(image.thumbnail)
        # The first one becomes the primary automatically.
        self.assertEqual(images.filter(is_primary=True).count(), 1)
        # Positions are assigned in order, so the gallery order is stable.
        self.assertEqual(
            list(images.order_by("ordering").values_list("ordering", flat=True)),
            sorted(images.values_list("ordering", flat=True)),
        )

    def test_a_second_batch_appends_after_the_existing_images(self):
        first = ProductImage(product=self.product, ordering=0, is_primary=True)
        first.image.save("first.png", png("first.png"), save=True)

        data = base_formset_data(self.product, total=2, initial=1)
        data["images-0-id"] = str(first.pk)
        data["images-0-ordering"] = "0"
        # The primary checkbox of the existing row stays checked, so the
        # new upload must NOT steal the primary flag.
        data["images-0-is_primary"] = "on"
        files = {"images-1-add_images": [png("second.png", (10, 10, 10))]}

        response = self._post_product_change(data, files)
        self._assert_saved(response)

        images = ProductImage.objects.filter(product=self.product).order_by("ordering")
        self.assertEqual([img.ordering for img in images], [0, 1])
        self.assertEqual(images.filter(is_primary=True).count(), 1)
        self.assertTrue(images[0].is_primary)

    def test_the_single_file_field_still_works_and_can_set_the_primary(self):
        data = base_formset_data(self.product, total=1, initial=0)
        data["images-0-is_primary"] = "on"
        files = {"images-0-image": [png("solo.png")]}

        response = self._post_product_change(data, files)
        self._assert_saved(response)

        image = ProductImage.objects.get(product=self.product)
        self.assertTrue(image.is_primary)

    def test_two_primary_images_are_rejected_with_a_readable_error(self):
        data = base_formset_data(self.product, total=2, initial=0)
        data["images-0-is_primary"] = "on"
        data["images-1-is_primary"] = "on"
        files = {"images-0-image": [png("one.png")], "images-1-image": [png("two.png")]}

        response = self._post_product_change(data, files)

        self.assertContains(response, "فقط یک تصویر") 
        self.assertEqual(ProductImage.objects.filter(product=self.product).count(), 0)

    def test_reordering_by_position_changes_the_stored_gallery_order(self):
        rows = []
        for index in range(3):
            image = ProductImage(product=self.product, ordering=index, is_primary=(index == 0))
            image.image.save(f"g{index}.png", png(f"g{index}.png"), save=True)
            rows.append(image)

        data = base_formset_data(self.product, total=3, initial=3)
        for index, row in enumerate(rows):
            data[f"images-{index}-id"] = str(row.pk)
        # The primary checkbox of the first row stays checked in the browser.
        data["images-0-is_primary"] = "on"
        # Put the last image first.
        data["images-0-ordering"] = "5"
        data["images-1-ordering"] = "1"
        data["images-2-ordering"] = "0"

        response = self._post_product_change(data, {})
        self._assert_saved(response)

        order = list(
            ProductImage.objects.filter(product=self.product)
            .order_by("-is_primary", "ordering")
            .values_list("pk", flat=True)
        )
        # Primary first, then the new positions (0 -> the previously-last row).
        self.assertEqual(order[0], rows[0].pk)
        self.assertEqual(order[1], rows[2].pk)
        self.assertEqual(order[2], rows[1].pk)

    def test_a_row_without_any_image_is_not_stored(self):
        data = base_formset_data(self.product, total=1, initial=0)
        # Mark the form as changed with a harmless value but upload nothing.
        data["images-0-ordering"] = "0"

        response = self._post_product_change(data, {})
        self._assert_saved(response)

        self.assertEqual(ProductImage.objects.filter(product=self.product).count(), 0)
        self.assertEqual(Product.objects.get(pk=self.product.pk).images.count(), 0)
