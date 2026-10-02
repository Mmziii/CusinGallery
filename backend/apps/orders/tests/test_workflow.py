"""
Order fulfilment workflow tests (Phase B - Store management).

Drives apps/orders/workflow.py with REAL orders: unpaid orders come
from the production checkout service, and paid orders are paid through
the real payment initiate/callback flow -- so "stock was decremented"
is a fact produced by the actual payment path, not a test shortcut.
"""
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import RequestFactory

from apps.core.testing import CacheIsolatedAPITestCase
from apps.orders.admin import OrderAdmin
from apps.orders.models import Order
from apps.orders.workflow import (
    OrderWorkflowError,
    allowed_next_statuses,
    check_transition,
    set_status,
)
from apps.payments.gateways.mock import _sign
from apps.payments.services import handle_callback, initiate_payment
from apps.payments.tests.helpers import make_product, make_unpaid_order, make_user
from apps.products.models import Product

CALLBACK = "http://testserver/api/v1/payments/callback/"


def signed_ok(authority):
    return {"authority": authority, "status": "ok", "sig": _sign(authority, "ok")}


class WorkflowTestBase(CacheIsolatedAPITestCase):
    def make_paid_order(self, stock=10, quantity=2, price=100000):
        """
        A REAL paid order: checkout -> initiate -> signed success
        callback. Returns (order, product); stock has been decremented
        by the real payment path.
        """
        self.user = make_user()
        self.product = make_product(stock_quantity=stock, price=price)
        order = make_unpaid_order(self.user, product=self.product, quantity=quantity)
        initiated = initiate_payment(self.user, order.pk, callback_url=CALLBACK)
        payment = initiated["payment"]
        handle_callback(signed_ok(payment.gateway_transaction_id))
        order.refresh_from_db()
        self.product.refresh_from_db()
        return order, self.product


class TransitionDAGTests(WorkflowTestBase):
    def test_allowed_edges(self):
        S = Order.Status
        expected = {
            S.PENDING: {S.CONFIRMED, S.CANCELLED},
            S.CONFIRMED: {S.PROCESSING, S.CANCELLED},
            S.PROCESSING: {S.SHIPPED, S.CANCELLED},
            S.SHIPPED: {S.DELIVERED, S.RETURNED},
            S.DELIVERED: {S.RETURNED},
            S.CANCELLED: set(),
            S.RETURNED: set(),
        }
        for current, allowed in expected.items():
            self.assertEqual(allowed_next_statuses(current), allowed, current)

    def test_invalid_transitions_are_rejected(self):
        S = Order.Status
        invalid = [
            (S.PENDING, S.PROCESSING),   # cannot skip confirmed
            (S.PENDING, S.SHIPPED),
            (S.PENDING, S.DELIVERED),
            (S.CONFIRMED, S.SHIPPED),    # cannot skip processing
            (S.CONFIRMED, S.DELIVERED),
            (S.PROCESSING, S.DELIVERED),  # cannot skip shipped
            (S.SHIPPED, S.CANCELLED),    # post-shipment: physical flow only
            (S.DELIVERED, S.CANCELLED),
            (S.CANCELLED, S.CONFIRMED),  # terminal
            (S.CANCELLED, S.PROCESSING),
            (S.RETURNED, S.DELIVERED),   # terminal
        ]
        for current, requested in invalid:
            with self.assertRaises(OrderWorkflowError, msg=f"{current} -> {requested}"):
                check_transition(current, requested, tracking_code="X")

    def test_valid_full_lifecycle(self):
        order, product = self.make_paid_order()
        S = Order.Status

        set_status(order, S.PROCESSING)
        order.refresh_from_db()
        self.assertEqual(order.status, S.PROCESSING)

        order.tracking_code = "IRPOST-123456"
        order.save(update_fields=["tracking_code"])
        set_status(order, S.SHIPPED)
        order.refresh_from_db()
        self.assertEqual(order.status, S.SHIPPED)

        set_status(order, S.DELIVERED)
        order.refresh_from_db()
        self.assertEqual(order.status, S.DELIVERED)

        set_status(order, S.RETURNED)
        order.refresh_from_db()
        self.assertEqual(order.status, S.RETURNED)


class ShippedRequiresTrackingCodeTests(WorkflowTestBase):
    def test_shipped_without_tracking_code_is_rejected(self):
        order, _ = self.make_paid_order()
        set_status(order, Order.Status.PROCESSING)
        order.refresh_from_db()
        self.assertEqual(order.tracking_code, "")

        with self.assertRaises(OrderWorkflowError):
            set_status(order, Order.Status.SHIPPED)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PROCESSING)  # unchanged

    def test_shipped_with_tracking_code_succeeds(self):
        order, _ = self.make_paid_order()
        set_status(order, Order.Status.PROCESSING)
        order.tracking_code = "TBA-999"
        order.save(update_fields=["tracking_code"])

        set_status(order, Order.Status.SHIPPED)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.SHIPPED)
        self.assertEqual(order.tracking_code, "TBA-999")


class CancelRestoresStockTests(WorkflowTestBase):
    def test_cancel_paid_order_restores_stock_exactly_once(self):
        order, product = self.make_paid_order(stock=10, quantity=2)
        self.assertEqual(product.stock_quantity, 8)  # decremented at payment

        set_status(order, Order.Status.CANCELLED)

        product.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(product.stock_quantity, 10)
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertIsNotNone(order.stock_restored_at)

    def test_repeated_cancel_is_an_idempotent_noop_and_stock_stays_put(self):
        order, product = self.make_paid_order(stock=10, quantity=2)
        set_status(order, Order.Status.CANCELLED)
        restored_at = Order.objects.get(pk=order.pk).stock_restored_at

        # Repeating the cancel is a safe no-op -- the exactly-once part
        # is that stock is NOT restored a second time.
        set_status(order, Order.Status.CANCELLED)

        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, 10)  # restored once, not twice
        self.assertEqual(Order.objects.get(pk=order.pk).stock_restored_at, restored_at)

        # ...but cancelled is still terminal for every OTHER status.
        with self.assertRaises(OrderWorkflowError):
            set_status(order, Order.Status.PROCESSING)

    def test_restore_flag_layer_alone_is_also_idempotent(self):
        """
        Even if the DAG were somehow bypassed (status manually reset),
        Order.stock_restored_at prevents a second restore. Proves the
        exactly-once guarantee does not rest on the DAG alone.
        """
        order, product = self.make_paid_order(stock=10, quantity=2)
        set_status(order, Order.Status.CANCELLED)
        self.assertEqual(Product.objects.get(pk=product.pk).stock_quantity, 10)

        # Simulate a corrupt/manual reset of status only (flag stays set).
        Order.objects.filter(pk=order.pk).update(status=Order.Status.CONFIRMED)
        set_status(order, Order.Status.CANCELLED)

        self.assertEqual(Product.objects.get(pk=product.pk).stock_quantity, 10)
        self.assertEqual(
            Order.objects.filter(pk=order.pk, stock_restored_at__isnull=False).count(), 1
        )

    def test_cancel_unpaid_order_does_not_touch_stock(self):
        user = make_user()
        product = make_product(stock_quantity=7)
        order = make_unpaid_order(user, product=product, quantity=1)
        # Payment never happened: stock was never decremented.

        set_status(order, Order.Status.CANCELLED)

        product.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(product.stock_quantity, 7)
        self.assertIsNone(order.stock_restored_at)


class OrderAdminWorkflowTests(WorkflowTestBase):
    """Drives OrderAdmin.save_model -- the exact code path the shop
    owner's browser hits -- via RequestFactory, plus the CSV export and
    print views."""

    def setUp(self):
        self.factory = RequestFactory()
        self.superuser = get_user_model().objects.create_superuser(
            username="owner-admin", password="x", phone="+989000000001"
        )
        self.model_admin = OrderAdmin(Order, AdminSite())

    def _make_request(self, method, url):
        request = getattr(self.factory, method)(url)
        request.user = self.superuser
        # RequestFactory skips middleware; attach what message_user needs.
        from django.contrib.messages.storage.fallback import FallbackStorage

        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def _save_via_admin(self, order, new_status, tracking_code=None):
        order.status = new_status
        if tracking_code is not None:
            order.tracking_code = tracking_code
        request = self._make_request("post", f"/admin/orders/order/{order.pk}/change/")
        self.model_admin.save_model(request, order, None, change=True)

    def test_admin_valid_transition_persists(self):
        order, _ = self.make_paid_order()
        self._save_via_admin(order, Order.Status.PROCESSING)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PROCESSING)

    def test_admin_invalid_transition_persists_nothing(self):
        order, _ = self.make_paid_order()
        original_number = order.order_number
        order.status = Order.Status.DELIVERED      # confirmed -> delivered: illegal
        order.tracking_code = "SHOULD-NOT-SAVE"
        request = self.factory.post(f"/admin/orders/order/{order.pk}/change/")
        request.user = self.superuser

        with self.assertRaises(ValidationError):
            self.model_admin.save_model(request, order, None, change=True)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CONFIRMED)  # unchanged
        self.assertEqual(order.tracking_code, "")               # nothing saved
        self.assertEqual(order.order_number, original_number)

    def test_admin_cancel_paid_order_restores_stock(self):
        order, product = self.make_paid_order(stock=5, quantity=3)
        self.assertEqual(product.stock_quantity, 2)

        self._save_via_admin(order, Order.Status.CANCELLED)

        product.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(product.stock_quantity, 5)
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertIsNotNone(order.stock_restored_at)

    def test_admin_shipped_requires_tracking_code(self):
        order, _ = self.make_paid_order()
        self._save_via_admin(order, Order.Status.PROCESSING)
        order.refresh_from_db()

        with self.assertRaises(ValidationError):
            self._save_via_admin(order, Order.Status.SHIPPED)

        self._save_via_admin(order, Order.Status.SHIPPED, tracking_code="POST-42")
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.SHIPPED)
        self.assertEqual(order.tracking_code, "POST-42")

    def test_csv_export_contains_selected_orders(self):
        order, _ = self.make_paid_order()
        request = self._make_request("post", "/admin/orders/order/")

        response = self.model_admin.export_orders_csv(
            request, Order.objects.filter(pk=order.pk)
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        body = response.content.decode("utf-8-sig")
        self.assertIn(order.order_number, body)
        self.assertIn(order.shipping_phone, body)
        self.assertIn("paid", body)

    def test_print_view_renders_label_and_invoice(self):
        order, _ = self.make_paid_order()
        request = self._make_request("get", f"/admin/orders/order/{order.pk}/print/")

        response = self.model_admin.print_view(request, order.pk)
        response.render()

        html = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn(order.order_number, html)
        self.assertIn(order.shipping_recipient_name, html)
        self.assertIn("برچسب ارسال", html)
        self.assertIn("فاکتور سفارش", html)
        item = order.items.first()
        self.assertIn(item.product_name, html)
