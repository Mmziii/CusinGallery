"""Regression: the image-import preview's buttons must actually work.

The preview rendered

    <input type="submit" name="confirm" value="تأیید و ذخیره">

so the browser POSTed ``confirm=«تأیید و ذخیره»`` while the view was
testing ``request.POST.get("confirm") == "1"``. The POST fell through to
the upload branch and the owner got «فایلی انتخاب نشده است» -- the job
never started and no image was ever written. Cancel had the same bug.

The earlier tests missed it because they posted ``{"confirm": "1"}`` by
hand. These tests read the real rendered form and post EXACTLY what a
browser would send when a given button is the submitter: every field of
the form plus that button's name/value, and nothing from the other
buttons.
"""
import os
import shutil
import tempfile
from html.parser import HTMLParser

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.products.models import ProductImage

from .helpers import make_product
from .test_image_import import build_zip, png_bytes, zip_upload

TEMP_MEDIA = tempfile.mkdtemp(prefix="cusin-test-image-import-buttons-")
PLAIN_STATIC = {
    "STORAGES": {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
}

CONFIRM_FORM_ID = "cusin-image-import-confirm"


class _FormFields(HTMLParser):
    """Collect the fields of one form, keeping submit buttons separate.

    ``fields`` is what a browser always sends; ``buttons`` is the one
    name/value pair the pressed submitter adds to it.
    """

    def __init__(self, form_id):
        super().__init__()
        self.form_id = form_id
        self.fields = []
        self.buttons = []
        self._depth = None

    # Django's own parser visits the template's tags; we only care about
    # the real markup it produced.
    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "form":
            if attributes.get("id") == self.form_id:
                self._depth = 1
            elif self._depth is not None:
                self._depth += 1
            return
        if self._depth is None:
            return
        if tag not in ("input", "button"):
            return
        name = attributes.get("name")
        if not name:
            return
        kind = (attributes.get("type") or "").lower()
        if tag == "button" or kind in ("submit", "button", "image"):
            self.buttons.append((name, attributes.get("value", "")))
        else:
            self.fields.append((name, attributes.get("value", "")))

    def handle_endtag(self, tag):
        if tag == "form" and self._depth is not None:
            self._depth -= 1
            if self._depth == 0:
                self._depth = None


def browser_payload(html, pressed, form_id=CONFIRM_FORM_ID):
    """The POST body a browser builds when ``pressed`` is the submitter.

    Every field of the form, plus the pressed button's own name/value.
    Other submit buttons contribute nothing -- that is exactly the detail
    the hand-written tests got wrong.
    """
    parser = _FormFields(form_id)
    parser.feed(html)
    parser.close()
    if not parser.fields:
        raise AssertionError(f"form #{form_id} not found in the page")
    buttons = dict(parser.buttons)
    if pressed not in buttons:
        raise AssertionError(
            f"no submit button named {pressed!r} in the form (found {sorted(buttons)})"
        )
    payload = dict(parser.fields)
    payload[pressed] = buttons[pressed]
    return payload


@override_settings(MEDIA_ROOT=TEMP_MEDIA, **PLAIN_STATIC)
class ImageImportButtonTests(TestCase):
    def setUp(self):
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)
        os.makedirs(TEMP_MEDIA, exist_ok=True)
        user_model = get_user_model()
        self.staff = user_model.objects.create_superuser(
            username="owner", email="owner@example.com", password="pass-12345"
        )
        self.client.force_login(self.staff)
        self.add_url = reverse("admin:products_product_image_import")

    def tearDown(self):
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)
        for leftover in os.listdir(tempfile.gettempdir()):
            if leftover.startswith("cusin-image-import-"):
                shutil.rmtree(
                    os.path.join(tempfile.gettempdir(), leftover), ignore_errors=True
                )

    def preview(self, members=None):
        """Upload a ZIP and hand back the preview page's HTML."""
        product = make_product(name="کاسه بلور", sku="SOOLE-001")
        payload = build_zip(members or [
            ("SOOLE-001.jpg", png_bytes((1, 1, 1))),
            ("SOOLE-001-2.jpg", png_bytes((2, 2, 2))),
        ])
        response = self.client.post(
            self.add_url, {"zip": zip_upload(payload), "mode": "add"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ProductImage.objects.count(), 0, "the dry run wrote something")
        return product, response.content.decode()

    def drain_job(self, limit=200):
        """Drive the job the way the progress page's JavaScript does."""
        response = None
        for _ in range(limit):
            response = self.client.post(self.add_url, {"step": "1"}, follow=True)
            if "تصاویر ذخیره شد" in response.content.decode():
                return response
        return response

    # -- the regression itself ------------------------------------------

    def test_the_confirm_button_starts_the_job_and_writes_the_images(self):
        product, html = self.preview()

        payload = browser_payload(html, "confirm")
        # the payload really is what a browser would send from that page
        self.assertEqual(payload["confirm"], "1")
        self.assertNotIn("cancel", payload)
        self.assertTrue(payload.get("csrfmiddlewaretoken"))
        self.assertTrue(payload.get("token"))

        response = self.client.post(self.add_url, payload, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            "فایلی انتخاب نشده است",
            response.content.decode(),
            "the confirm fell through to the upload branch",
        )

        response = self.drain_job()
        content = response.content.decode()
        self.assertIn("تصاویر ذخیره شد", content)
        self.assertEqual(product.images.count(), 2)
        self.assertTrue(product.images.order_by("ordering").first().is_primary)

    def test_the_cancel_button_cancels_without_starting_the_job(self):
        product, html = self.preview()

        payload = browser_payload(html, "cancel")
        self.assertEqual(payload["cancel"], "1")
        self.assertNotIn("confirm", payload)

        response = self.client.post(self.add_url, payload, follow=True)
        content = response.content.decode()
        self.assertIn("عملیات لغو شد", content)
        self.assertEqual(product.images.count(), 0)
        # the canceled upload cannot be resurrected by a late confirm
        self.client.post(self.add_url, browser_payload(html, "confirm"), follow=True)
        self.assertEqual(product.images.count(), 0)

    # -- the two ways the value used to get lost -------------------------

    def test_the_buttons_post_the_value_the_view_checks(self):
        """Not the label: «تأیید و ذخیره» was never equal to "1"."""
        _, html = self.preview()
        parser = _FormFields(CONFIRM_FORM_ID)
        parser.feed(html)
        parser.close()
        buttons = dict(parser.buttons)
        self.assertEqual(buttons.get("confirm"), "1")
        self.assertEqual(buttons.get("cancel"), "1")

    def test_the_confirm_button_is_never_disabled_before_the_post_is_built(self):
        """A disabled submitter is excluded from the form data, so the
        "block double submits" handler must not run synchronously."""
        _, html = self.preview()
        self.assertIn("confirmButton.disabled = true", html)
        start = html.index('form.addEventListener("submit"')
        handler = html[start:html.index("window.addEventListener(\"pageshow\"", start)]
        self.assertIn("setTimeout", handler)
        self.assertLess(
            handler.index("setTimeout"),
            handler.index("confirmButton.disabled = true"),
            "disabling must be deferred until after the submission is built",
        )

    def test_the_button_labels_are_still_the_persian_ones(self):
        _, html = self.preview()
        self.assertIn("تأیید و ذخیره</button>", html)
        self.assertIn("انصراف (بدون تغییر)</button>", html)
