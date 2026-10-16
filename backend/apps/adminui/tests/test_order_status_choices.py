"""
Audit 19 item 6: the admin's status select must not offer impossible moves.

The owner's report: on an UNPAID order the «وضعیت سفارش» select still listed
«تأیید شده» and every later status, although saving them is refused by the
workflow -- an action that can only fail.

The fix (apps/orders/admin.OrderAdminForm / OrderStatusSelect):

  * the SELECTABLE statuses are exactly the order's current status plus the
    transitions the DAG allows AND the payment rule accepts;
  * the transitions the DAG allows but the payment rule forbids are rendered
    as DISABLED options carrying their Persian reason, so the owner sees why
    they are unavailable;
  * the field's help text explains the greyed-out entries;
  * nothing about the server-side rule changes: a crafted POST of a forbidden
    status is still rejected and persists nothing.
"""
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.orders.models import Order
from apps.orders.workflow import allowed_next_statuses, payment_block_reason

from .helpers import PLAIN_STATIC, make_order, make_superuser


@override_settings(**PLAIN_STATIC)
class OrderStatusChoicesTests(TestCase):
    maxDiff = None

    def setUp(self):
        self.admin = make_superuser(username="statusowner", phone="+989000030001")
        self.client.force_login(self.admin)

    def _change(self, order):
        return self.client.get(reverse("admin:orders_order_change", args=[order.pk]))

    @staticmethod
    def _options(html):
        """(value, disabled) for every <option> of the status select."""
        import re

        select = re.search(
            r'<select[^>]*name="status".*?</select>', html, re.DOTALL
        )
        assert select, "the status select is missing from the change form"
        options = []
        for match in re.finditer(r"<option([^>]*)>([^<]*)</option>", select.group(0)):
            attrs, label = match.group(1), match.group(2).strip()
            value = re.search(r'value="([^"]*)"', attrs)
            options.append(
                {
                    "value": value.group(1) if value else "",
                    "label": label,
                    "disabled": "disabled" in attrs,
                    "title": (re.search(r'title="([^"]*)"', attrs) or [None, ""])[1],
                }
            )
        return options

    def test_unpaid_order_offers_only_its_current_status_and_cancellation(self):
        order = make_order(
            status=Order.Status.PENDING, payment_status=Order.PaymentStatus.UNPAID
        )

        options = self._options(self._change(order).content.decode())

        selectable = [option["value"] for option in options if not option["disabled"]]
        self.assertEqual(selectable, [Order.Status.PENDING, Order.Status.CANCELLED])

        disabled = {option["value"] for option in options if option["disabled"]}
        # The DAG-legal-but-unpaid transition is VISIBLE, disabled, with its
        # Persian reason -- never silently missing.
        self.assertEqual(disabled, {Order.Status.CONFIRMED})
        reason = next(o["title"] for o in options if o["value"] == Order.Status.CONFIRMED)
        self.assertEqual(reason, payment_block_reason(order, Order.Status.CONFIRMED))
        self.assertIn("پرداخت نشده", reason)

    def test_paid_open_order_offers_every_legal_next_status(self):
        order = make_order(
            status=Order.Status.CONFIRMED, payment_status=Order.PaymentStatus.PAID
        )

        options = self._options(self._change(order).content.decode())

        selectable = [option["value"] for option in options if not option["disabled"]]
        self.assertEqual(
            selectable,
            [Order.Status.CONFIRMED]
            + [
                status
                for status in Order.Status.values
                if status in allowed_next_statuses(Order.Status.CONFIRMED)
            ],
        )
        self.assertEqual([option for option in options if option["disabled"]], [])
        # A paid order needs no "greyed out" explanation.
        self.assertNotIn("غیرفعال", self._change(order).content.decode())

    def test_terminal_order_offers_only_its_own_status(self):
        order = make_order(
            status=Order.Status.CANCELLED, payment_status=Order.PaymentStatus.UNPAID
        )

        options = self._options(self._change(order).content.decode())

        self.assertEqual([option["value"] for option in options], [Order.Status.CANCELLED])
        self.assertEqual([option for option in options if option["disabled"]], [])

    def test_help_text_explains_the_forbidden_entries(self):
        order = make_order(
            status=Order.Status.PENDING, payment_status=Order.PaymentStatus.UNPAID
        )

        html = self._change(order).content.decode()

        self.assertIn("گزینه‌های خاکستری (غیرفعال)", html)
        self.assertIn("فقط انتقال‌های مجاز گردش کار نمایش داده می‌شوند", html)

    @staticmethod
    def _form(order, **overrides):
        """The real admin form, filled with the order's current values."""
        from django.forms.models import model_to_dict

        from apps.orders.admin import OrderAdminForm

        data = model_to_dict(order)
        data.update(overrides)
        return OrderAdminForm(instance=order, data=data)

    def test_the_form_field_itself_rejects_a_forbidden_status(self):
        """The select is not the only guard: the FIELD refuses the value too."""
        order = make_order(
            status=Order.Status.PENDING, payment_status=Order.PaymentStatus.UNPAID
        )

        form = self._form(order, status=Order.Status.SHIPPED)

        self.assertFalse(form.is_valid())
        self.assertIn("status", form.errors)
        self.assertIn("گزینهٔ معتبر", " ".join(form.errors["status"]))

    def test_saving_a_legal_transition_still_works_through_the_form(self):
        order = make_order(
            status=Order.Status.PENDING, payment_status=Order.PaymentStatus.UNPAID
        )

        form = self._form(order, status=Order.Status.CANCELLED)

        self.assertTrue(form.is_valid(), form.errors)

    def test_the_same_status_stays_saveable_for_an_unrelated_edit(self):
        """Editing (say) the tracking code must not force a status change."""
        order = make_order(
            status=Order.Status.PENDING, payment_status=Order.PaymentStatus.UNPAID
        )

        form = self._form(order, status=Order.Status.PENDING)

        self.assertTrue(form.is_valid(), form.errors)

    def test_quick_status_menu_keeps_its_own_contract(self):
        """The quick menu (B3c) still lists allowed transitions and shows the
        blocked ones disabled -- the form change must not have regressed it."""
        order = make_order(
            status=Order.Status.PENDING, payment_status=Order.PaymentStatus.UNPAID
        )

        response = self._change(order)

        self.assertEqual(
            {entry["value"] for entry in response.context["quick_allowed"]},
            {Order.Status.CANCELLED},
        )
        self.assertEqual(
            {entry["value"] for entry in response.context["quick_blocked"]},
            {Order.Status.CONFIRMED},
        )
