"""Task 4: long customer values stay inside their own changelist cell.

The customer is the name on one line and the Persian-digit phone on a
second muted line, both ellipsised with the full value in ``title``;
the payments list renders its customer/order cells the same way. The
pixel-level widths are asserted via the real cascade in
frontend/src/admin-theme/layoutCascade.test.js.
"""
import re

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.orders.models import Order
from apps.payments.models import Payment

from .helpers import PLAIN_STATIC, make_order, make_superuser


@override_settings(**PLAIN_STATIC)
class OrdersCustomerCellTests(TestCase):
    def setUp(self):
        self.admin = make_superuser()
        self.client.force_login(self.admin)

    def _customer_cell(self, html):
        match = re.search(r'<td class="field-customer_cell">(.*?)</td>', html, re.S)
        self.assertIsNotNone(match, "no customer column rendered")
        return match.group(1)

    def test_long_login_like_name_ellipsises_with_tooltip(self):
        customer = User.objects.create_user(
            username="00doodooltala-very-long-login-name",
            phone="09121112233",
            password="x",
        )
        order = make_order(user=customer)
        order.shipping_phone = "09123334455"
        order.save(update_fields=["shipping_phone"])
        html = self.client.get(reverse("admin:orders_order_changelist")).content.decode()
        cell = self._customer_cell(html)
        # Name on its own line (own element), full value in the tooltip.
        self.assertIn('class="cusin-customer__name"', cell)
        self.assertIn('title="00doodooltala-very-long-login-name"', cell)
        # Phone: second line, LTR-isolated, Persian digits.
        self.assertIn('class="cusin-customer__phone" dir="ltr"', cell)
        self.assertIn("۰۹۱۲۳۳۳۴۴۵۵", cell)
        self.assertNotIn(">09123334455<", cell)

    def test_status_badge_stays_in_its_own_cell(self):
        customer = User.objects.create_user(
            username="00doodooltala", phone="09121112233", password="x"
        )
        make_order(user=customer, status=Order.Status.PENDING)
        html = self.client.get(reverse("admin:orders_order_changelist")).content.decode()
        cell = self._customer_cell(html)
        self.assertNotIn("در انتظار تأیید", cell)
        status = re.search(r'<td class="field-status_badge">(.*?)</td>', html, re.S)
        self.assertIsNotNone(status)
        self.assertIn("در انتظار تأیید", status.group(1))
        self.assertNotIn("00doodooltala", status.group(1))


@override_settings(**PLAIN_STATIC)
class PaymentsCellsTests(TestCase):
    def setUp(self):
        self.admin = make_superuser()
        self.client.force_login(self.admin)

    def test_customer_and_order_number_are_bounded_with_tooltips(self):
        customer = User.objects.create_user(
            username="a-very-long-login-name-that-would-overflow",
            phone="09121112233",
            password="x",
        )
        order = make_order(user=customer)
        Payment.objects.create(
            order=order, amount=order.total, gateway="mock",
            status=Payment.Status.SUCCESS,
        )
        html = self.client.get(
            reverse("admin:payments_payment_changelist")
        ).content.decode()
        customer_cell = re.search(r'<td class="field-customer">(.*?)</td>', html, re.S)
        self.assertIsNotNone(customer_cell)
        self.assertIn("cusin-cell-ellipsis", customer_cell.group(1))
        self.assertIn(
            'title="a-very-long-login-name-that-would-overflow"',
            customer_cell.group(1),
        )
        order_cell = re.search(r'<td class="field-order_number">(.*?)</td>', html, re.S)
        self.assertIsNotNone(order_cell)
        self.assertIn('dir="ltr"', order_cell.group(1))
        self.assertIn(f'title="{order.order_number}"', order_cell.group(1))
