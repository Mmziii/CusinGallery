"""
Part S4 item 1: the Django-rendered image surfaces (admin thumbnails and
the printable invoice) use the SAME shared placeholder as the storefront
(brand mark on the warm-grey field, olive at .35 opacity), and a broken
file degrades through an onerror swap instead of a broken-image icon.

The storefront half of this item is covered by
frontend/src/components/SmartImage.test.jsx and the source guard in
frontend/src/assets.guard.test.js.
"""
from django.test import TestCase, override_settings

# Admin pages render static files through the manifest storage; tests swap
# it for the plain backend (same helper the other admin test modules use).
PLAIN_STATIC = {
    "STORAGES": {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
}
from django.urls import reverse

from apps.accounts.tests.helpers import make_user
from apps.core.image_files import image_or_placeholder_html, placeholder_html
from apps.core.testing import CacheIsolatedAPITestCase
from apps.payments.gateways.mock import _sign
from apps.payments.services import handle_callback, initiate_payment
from apps.products.tests.helpers import make_category, make_image, make_product

from apps.orders.tests.helpers import add_to_cart  # noqa: E402  (shared helper)

CB = "http://testserver/api/v1/payments/callback/"


class PlaceholderMarkupTests(TestCase):
    """The helper's markup carries the shared look."""

    def test_placeholder_uses_the_shared_colours_mark_and_opacity(self):
        html = str(placeholder_html(48, 48))
        self.assertIn("#efece4", html)              # warm-grey field
        self.assertIn("#637037", html)              # --brand-green
        self.assertIn("0.35", html)                 # same opacity as the SPA
        self.assertIn("/brand/mark.svg", html)      # the owner's mark, reused
        self.assertIn('aria-label="بدون تصویر"', html)

    def test_missing_image_renders_the_placeholder_not_a_broken_img(self):
        html = str(image_or_placeholder_html(None))
        self.assertNotIn("<img", html)
        self.assertIn("بدون تصویر", html)

    def test_existing_image_renders_an_img_with_an_onerror_swap_to_the_placeholder(self):
        class FakeField:
            url = "/media/products/x.jpg"

        html = str(image_or_placeholder_html(FakeField()))
        self.assertIn('src="/media/products/x.jpg"', html)
        self.assertIn("onerror=", html)
        self.assertIn("this.nextElementSibling.style.display", html)
        # The placeholder is present (hidden) right after the img.
        self.assertIn("بدون تصویر", html)


@override_settings(**PLAIN_STATIC)
class AdminThumbnailTests(TestCase):
    """The product changelist and image inline never show a broken icon."""

    def setUp(self):
        self.admin = make_user(phone="+989551110001", is_staff=True, is_superuser=True)
        self.client.force_login(self.admin)

    def test_changelist_shows_the_placeholder_for_products_without_images(self):
        make_product(name="بدون تصویر")

        response = self.client.get(reverse("admin:products_product_changelist"))

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("بدون تصویر", html)      # the placeholder label
        self.assertIn("#efece4", html)         # the shared field colour

    @override_settings(MEDIA_ROOT="/tmp/cusin-s4-media", **PLAIN_STATIC)
    def test_changelist_shows_an_img_with_error_fallback_for_products_with_images(self):
        product = make_product(name="با تصویر")
        make_image(product, image="products/with.jpg", is_primary=True)

        html = self.client.get(reverse("admin:products_product_changelist")).content.decode()

        self.assertIn("/media/products/with.jpg", html)
        self.assertIn("onerror=", html)


class InvoiceThumbnailTests(CacheIsolatedAPITestCase):
    """The printable invoice uses the same helper for its image column."""

    def _paid_order(self, user, with_image):
        product = make_product(price=150000, stock_quantity=5)
        if with_image:
            make_image(product, image="products/invoice.jpg", is_primary=True)
        add_to_cart(user, product, quantity=1)

        from apps.orders.serializers import CheckoutSerializer
        from apps.orders.services import checkout

        serializer = CheckoutSerializer(data={
            "recipient_name": "Invoice Buyer", "phone": "+989121112233",
            "province": "Tehran", "city": "Tehran", "address": "St 1",
            "postal_code": "1234567890",
        })
        serializer.is_valid(raise_exception=True)
        order = checkout(user, serializer.validated_data)
        payment = initiate_payment(user, order.pk, callback_url=CB)["payment"]
        handle_callback({"authority": payment.gateway_transaction_id, "status": "ok",
                         "sig": _sign(payment.gateway_transaction_id, "ok")})
        order.refresh_from_db()
        return order

    def test_invoice_without_a_product_image_shows_the_shared_placeholder(self):
        user = make_user(phone="+989551110002")
        order = self._paid_order(user, with_image=False)
        self.client.login(username="+989551110002", password="a-strong-passw0rd!")

        response = self.client.get(reverse("order-invoice", args=[order.pk]))

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("بدون تصویر", html)
        self.assertIn("/brand/mark.svg", html)

    @override_settings(MEDIA_ROOT="/tmp/cusin-s4-media-invoice")
    def test_invoice_with_a_product_image_keeps_the_onerror_fallback(self):
        user = make_user(phone="+989551110003")
        order = self._paid_order(user, with_image=True)
        self.client.login(username="+989551110003", password="a-strong-passw0rd!")

        html = self.client.get(reverse("order-invoice", args=[order.pk])).content.decode()

        self.assertIn("/media/products/invoice.jpg", html)
        self.assertIn("onerror=", html)
        self.assertIn("بدون تصویر", html)


@override_settings(**PLAIN_STATIC)
class CategoryImagePlaceholderTests(TestCase):
    """Category images are the other server-side surface (admin list)."""

    def test_category_rows_render_without_error_when_no_image_is_set(self):
        make_category(name="دستهٔ بدون تصویر")
        admin_user = make_user(phone="+989551110004", is_staff=True, is_superuser=True)
        self.client.force_login(admin_user)

        response = self.client.get(reverse("admin:categories_category_changelist"))

        self.assertEqual(response.status_code, 200)
