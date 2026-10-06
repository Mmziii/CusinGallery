"""
Back-in-stock tests (Part 2): strict phone validation, no duplicate
active subscriptions, one SMS per restock through the REAL save()
hooks (admin edit / cancel-restore paths), provider failure contained
with the subscription left active, and a read-only admin.
"""
from unittest import mock

from django.contrib.admin.sites import AdminSite
from django.test import override_settings
from django.urls import reverse
from rest_framework import status

from apps.accounts.tests.helpers import make_user
from apps.orders.tests.helpers import add_to_cart as _cart_add
from apps.core.testing import CacheIsolatedAPITestCase
from apps.notifications.models import NotificationLog
from apps.notifications.tests.helpers import install_fake_provider, provider_error
from apps.orders.workflow import set_status
from apps.payments.gateways.mock import _sign
from apps.payments.services import handle_callback, initiate_payment
from apps.payments.tests.helpers import make_product, make_user as pay_make_user

from ..models import BackInStockSubscription, Product
from apps.orders.models import Order

CB = "http://testserver/api/v1/payments/callback/"


class BackInStockEndpointTests(CacheIsolatedAPITestCase):
    def setUp(self):
        self.url = reverse("back-in-stock")

    def test_strict_iranian_mobile_validation(self):
        product = make_product(stock_quantity=0)
        for bad in ["+989121112233", "0912", "091212345678", "08121234567", ""]:
            response = self.client.post(
                self.url, {"product_id": product.pk, "phone": bad}, format="json"
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, bad)
            self.assertIn("phone", response.data)

    def test_in_stock_product_refuses_subscriptions(self):
        product = make_product(stock_quantity=3)
        response = self.client.post(
            self.url, {"product_id": product.pk, "phone": "09121234567"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_product_is_a_validation_error(self):
        response = self.client.post(
            self.url, {"product_id": 999999, "phone": "09121234567"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_signup_and_duplicate_active_are_idempotent(self):
        product = make_product(stock_quantity=0)
        first = self.client.post(
            self.url, {"product_id": product.pk, "phone": "09121234567"}, format="json"
        )
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        second = self.client.post(
            self.url, {"product_id": product.pk, "phone": "09121234567"}, format="json"
        )
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(BackInStockSubscription.objects.count(), 1)

    def test_variant_must_belong_to_the_product(self):
        product = make_product(stock_quantity=0)
        other = make_product(slug="other-bis", stock_quantity=0)
        variant = other.variants.create(sku="BIS-V1", stock_quantity=0)
        response = self.client.post(
            self.url,
            {"product_id": product.pk, "variant_id": variant.pk, "phone": "09121234567"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class BackInStockDeliveryTests(CacheIsolatedAPITestCase):
    def subscribe(self, product, phone="09121234567"):
        return self.client.post(
            reverse("back-in-stock"), {"product_id": product.pk, "phone": phone},
            format="json",
        )

    def test_restock_sends_one_sms_and_stamps_notified_at(self):
        fake = install_fake_provider(self, also_patch=("apps.products.back_in_stock.get_provider",))
        product = make_product(stock_quantity=0)
        self.subscribe(product)

        with self.captureOnCommitCallbacks(execute=True):
            product.stock_quantity = 4
            product.save(update_fields=["stock_quantity", "updated_at"])

        self.assertEqual(len(fake.sent), 1)
        self.assertIn("09121234567", fake.sent[0]["recipient"])
        self.assertIn(product.name, fake.sent[0]["message"])
        sub = BackInStockSubscription.objects.get()
        self.assertIsNotNone(sub.notified_at)
        log = NotificationLog.objects.get(event="back_in_stock")
        self.assertEqual(log.status, NotificationLog.Status.SENT)
        self.assertNotIn("09121234567", log.recipient_masked)

    def test_no_second_send_after_a_later_restock(self):
        fake = install_fake_provider(self, also_patch=("apps.products.back_in_stock.get_provider",))
        product = make_product(stock_quantity=0)
        self.subscribe(product)

        with self.captureOnCommitCallbacks(execute=True):
            product.stock_quantity = 2
            product.save()
            product.stock_quantity = 0
            product.save()
            product.stock_quantity = 3
            product.save()

        self.assertEqual(len(fake.sent), 1, "notified subscriptions never re-send")

    def test_zero_to_zero_or_n_to_n_never_notifies(self):
        fake = install_fake_provider(self, also_patch=("apps.products.back_in_stock.get_provider",))
        product = make_product(stock_quantity=5)
        self.subscribe(product)  # refused while in stock -> no row
        self.assertEqual(BackInStockSubscription.objects.count(), 0)
        with self.captureOnCommitCallbacks(execute=True):
            product.stock_quantity = 6  # N -> N, no event
            product.save()
        self.assertEqual(fake.sent, [])

    def test_provider_failure_keeps_the_subscription_active(self):
        install_fake_provider(self, error=provider_error("sms down"),
                          also_patch=("apps.products.back_in_stock.get_provider",))
        product = make_product(stock_quantity=0)
        self.subscribe(product)

        with self.captureOnCommitCallbacks(execute=True):
            product.stock_quantity = 2
            product.save()

        sub = BackInStockSubscription.objects.get()
        self.assertIsNone(sub.notified_at, "failure must not consume the subscription")
        self.assertEqual(
            NotificationLog.objects.get(event="back_in_stock").status,
            NotificationLog.Status.FAILED,
        )

        # A later restock cycle finally delivers it.
        fake = install_fake_provider(self, also_patch=("apps.products.back_in_stock.get_provider",))
        with self.captureOnCommitCallbacks(execute=True):
            product.stock_quantity = 0
            product.save()
            product.stock_quantity = 1
            product.save()
        self.assertEqual(len(fake.sent), 1)

    def test_order_cancellation_restore_triggers_the_sms(self):
        fake = install_fake_provider(self, also_patch=("apps.products.back_in_stock.get_provider",))
        product = make_product(stock_quantity=1)  # buying it out empties stock
        user = pay_make_user(phone="+989530000001")
        _cart_add(user, product, quantity=1)
        from apps.orders.serializers import CheckoutSerializer
        from apps.orders.services import checkout

        serializer = CheckoutSerializer(data={
            "recipient_name": "B", "phone": "+989121112233",
            "province": "T", "city": "T", "address": "X", "postal_code": "1234567890",
            "building_number": "10", "unit": "3",
        })
        serializer.is_valid(raise_exception=True)
        order = checkout(user, serializer.validated_data)
        payment = initiate_payment(user, order.pk, callback_url=CB)["payment"]
        with self.captureOnCommitCallbacks(execute=True):
            handle_callback({"authority": payment.gateway_transaction_id, "status": "ok",
                             "sig": _sign(payment.gateway_transaction_id, "ok")})
        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, 0)

        self.subscribe(product)  # now out of stock -> accepted

        with self.captureOnCommitCallbacks(execute=True):
            order.refresh_from_db()
            set_status(order, Order.Status.CANCELLED)

        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, 1, "cancel restored stock")
        # The fake provider also captured the order-confirmation SMS of
        # the payment above; the back-in-stock message is the restock one.
        restock_sends = [m for m in fake.sent if "موجود شد" in m["message"]]
        self.assertEqual(len(restock_sends), 1, "restore path fired the notification")
        self.assertEqual(
            BackInStockSubscription.objects.filter(notified_at__isnull=False).count(), 1
        )

    def test_admin_is_read_only(self):
        from ..admin import BackInStockSubscriptionAdmin

        admin_instance = BackInStockSubscriptionAdmin(BackInStockSubscription, AdminSite())
        self.assertFalse(admin_instance.has_add_permission(None))
        self.assertFalse(admin_instance.has_change_permission(None))
        self.assertFalse(admin_instance.has_delete_permission(None))
