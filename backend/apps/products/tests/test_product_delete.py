"""Task 2: deleting a product must take its derived rows with it.

Frequently-bought-together pairs and back-in-stock subscriptions
already cascade at the database level, but their read-only admins
refused delete permission unconditionally, so Django's delete
confirmation blocked every product that had such rows ("امکان حذف
محصول نیست… خرید همراه (خودکار)، اطلاع‌رسانی موجودی").

Past orders must survive: OrderItem.product is SET_NULL and the
snapshot name/price keep the order historically correct.
"""
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.orders.models import Order, OrderItem
from apps.products.models import (
    BackInStockSubscription,
    FrequentlyBoughtTogether,
    Product,
)

from .helpers import make_product

PLAIN_STATIC = {
    "STORAGES": {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
}

User = get_user_model()


def make_order_for(product, user):
    order = Order.objects.create(
        user=user,
        status=Order.Status.DELIVERED,
        payment_status=Order.PaymentStatus.PAID,
        subtotal=product.price,
        total=product.price,
        shipping_recipient_name="سارا احمدی",
        shipping_phone="09121112233",
        shipping_province="تهران",
        shipping_city="تهران",
        shipping_address="خیابان ولیعصر، پلاک ۱۰",
        shipping_postal_code="1234567890",
        shipping_method="standard",
    )
    OrderItem.objects.create(
        order=order,
        product=product,
        product_name=product.name,
        sku=product.sku,
        unit_price=product.price,
        quantity=2,
        total_price=product.price * 2,
    )
    return order


@override_settings(**PLAIN_STATIC)
class ProductDeleteTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser(
            username="delete-owner", password="a-strong-passw0rd!", phone="+989000099001"
        )
        self.client.force_login(self.owner)
        self.product = make_product(name="قابلمهٔ حذف‌شونده", price=250000)
        self.other = make_product(name="تابه")
        FrequentlyBoughtTogether.objects.create(
            product=self.product, complement=self.other, co_count=4
        )
        FrequentlyBoughtTogether.objects.create(
            product=self.other, complement=self.product, co_count=2
        )
        BackInStockSubscription.objects.create(
            product=self.product, phone="09121112233"
        )
        customer = User.objects.create_user(
            username="+9891200099001", phone="+9891200099001",
            password="a-strong-passw0rd!",
        )
        self.order = make_order_for(self.product, customer)

    def _delete_url(self):
        return reverse("admin:products_product_delete", args=[self.product.pk])

    def test_confirmation_is_persian_and_not_blocked_by_helper_rows(self):
        response = self.client.get(self._delete_url())
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertNotIn("امکان حذف", body)
        self.assertFalse(response.context["perms_lacking"])
        self.assertIn("آیا از حذف محصول", body)
        self.assertIn("همراه این محصول، موارد زیر هم برای همیشه حذف می‌شوند", body)
        self.assertIn("سفارش‌های گذشته حذف نمی‌شوند", body)
        self.assertIn("پنهان کردن از فروشگاه", body)
        self.assertIn("بله، حذف شود", body)

    def test_delete_removes_helpers_but_keeps_order_snapshot(self):
        response = self.client.post(self._delete_url(), {"post": "yes"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Product.objects.filter(pk=self.product.pk).exists())
        self.assertEqual(
            FrequentlyBoughtTogether.objects.filter(
                product_id=self.product.pk
            ).count(), 0,
        )
        self.assertEqual(
            FrequentlyBoughtTogether.objects.filter(
                complement_id=self.product.pk
            ).count(), 0,
        )
        self.assertEqual(BackInStockSubscription.objects.count(), 0)
        # The other product is untouched.
        self.assertTrue(Product.objects.filter(pk=self.other.pk).exists())
        # Order history survives with its snapshot; only the FK nulls.
        self.order.refresh_from_db()
        item = self.order.items.get()
        self.assertIsNone(item.product)
        self.assertEqual(item.product_name, "قابلمهٔ حذف‌شونده")
        self.assertEqual(item.unit_price, 250000)
        self.assertEqual(item.quantity, 2)

    def test_staff_with_only_product_delete_permission_can_delete(self):
        staff = User.objects.create_user(
            username="+989000099002", phone="+989000099002",
            password="a-strong-passw0rd!", is_staff=True,
        )
        staff.user_permissions.set(
            Permission.objects.filter(
                content_type__app_label="products",
                codename__in=("view_product", "delete_product"),
            )
        )
        self.client.force_login(staff)
        response = self.client.get(self._delete_url())
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["perms_lacking"])
        response = self.client.post(self._delete_url(), {"post": "yes"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Product.objects.filter(pk=self.product.pk).exists())

    def test_staff_without_product_delete_permission_is_refused(self):
        staff = User.objects.create_user(
            username="+989000099003", phone="+989000099003",
            password="a-strong-passw0rd!", is_staff=True,
        )
        staff.user_permissions.set(
            Permission.objects.filter(
                content_type__app_label="products", codename="view_product"
            )
        )
        self.client.force_login(staff)
        response = self.client.get(self._delete_url())
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())

    def test_bulk_delete_confirmation_is_persian(self):
        response = self.client.post(
            reverse("admin:products_product_changelist"),
            {
                "action": "delete_selected",
                ACTION_CHECKBOX_NAME: [self.product.pk],
                "index": 0,
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("آیا از حذف محصولات انتخاب‌شده مطمئن هستید؟", body)
        self.assertIn("سفارش‌های گذشته حذف نمی‌شوند", body)
        self.assertIn("بله، حذف شوند", body)

    def test_hide_action_sets_inactive_without_deleting(self):
        response = self.client.post(
            reverse("admin:products_product_changelist"),
            {
                "action": "deactivate_products",
                ACTION_CHECKBOX_NAME: [self.product.pk],
                "index": 0,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_active)
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())
        # The action is offered to the owner under its plain name.
        changelist = self.client.get(reverse("admin:products_product_changelist"))
        self.assertIn("پنهان کردن از فروشگاه", changelist.content.decode())
