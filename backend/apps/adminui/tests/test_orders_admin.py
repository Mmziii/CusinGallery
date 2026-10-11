"""B3: orders changelist tabs/queues, change-page summary + stepper, and
the quick-status endpoint (valid transitions only, tracking-code rule,
pickup exemption, permissions, CSRF, LogEntry audit).
"""
from django.contrib.admin.models import LogEntry
from django.core.exceptions import PermissionDenied
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.orders.models import Order
from apps.orders.workflow import allowed_next_statuses

from .helpers import PLAIN_STATIC, make_order, make_staff, make_superuser


@override_settings(**PLAIN_STATIC)
class OrdersChangelistTests(TestCase):
    maxDiff = None

    def setUp(self):
        self.admin = make_superuser(username="ordowner", phone="+989000020001")
        self.client.force_login(self.admin)
        # one order per interesting bucket
        self.paid_open = make_order(status=Order.Status.CONFIRMED,
                                    payment_status=Order.PaymentStatus.PAID)
        self.unpaid = make_order(status=Order.Status.PENDING,
                                 payment_status=Order.PaymentStatus.UNPAID)
        self.pickup = make_order(status=Order.Status.PROCESSING,
                                 payment_status=Order.PaymentStatus.PAID,
                                 shipping_method="pickup")
        self.refund = make_order(status=Order.Status.CANCELLED,
                                 payment_status=Order.PaymentStatus.PAID,
                                 refund_status=Order.RefundStatus.REQUIRED)

    def test_tab_counts_exact(self):
        response = self.client.get(reverse("admin:orders_order_changelist"))
        tabs = {tab["key"]: tab for tab in response.context["queue_tabs"]}
        self.assertEqual(tabs["all"]["count"], 4)
        self.assertEqual(tabs["paid_to_process"]["count"], 2)   # paid_open + pickup
        self.assertEqual(tabs["awaiting_payment"]["count"], 1)  # unpaid
        self.assertEqual(tabs["needs_refund"]["count"], 1)      # refund
        self.assertEqual(tabs["pickup_waiting"]["count"], 1)    # pickup
        self.assertEqual(tabs["shipped"]["count"], 0)
        self.assertEqual(tabs["delivered"]["count"], 0)
        self.assertEqual(tabs["cancelled_returned"]["count"], 1)
        self.assertTrue(tabs["all"]["active"])
        html = response.content.decode()
        self.assertIn("cusin-tab", html)
        self.assertIn("cusin-badge", html)

    def test_queue_param_narrows_result_set(self):
        for queue, expected in (
            ("awaiting_payment", [self.unpaid]),
            ("paid_to_process", [self.paid_open, self.pickup]),
            ("pickup_waiting", [self.pickup]),
            ("needs_refund", [self.refund]),
            ("cancelled_returned", [self.refund]),
        ):
            with self.subTest(queue=queue):
                response = self.client.get(
                    reverse("admin:orders_order_changelist"), {"queue": queue}
                )
                cl = response.context["cl"]
                self.assertEqual(cl.result_count, len(expected))
                self.assertEqual(
                    set(cl.queryset.values_list("pk", flat=True)),
                    {o.pk for o in expected},
                )
                tabs = {t["key"]: t for t in response.context["queue_tabs"]}
                self.assertTrue(tabs[queue]["active"])

    def test_tabs_compose_with_other_params(self):
        # a tab URL keeps the owner's other active GET params (search etc.)
        response = self.client.get(
            reverse("admin:orders_order_changelist"), {"q": self.unpaid.order_number}
        )
        tabs = {t["key"]: t for t in response.context["queue_tabs"]}
        self.assertIn(f"q={self.unpaid.order_number}", tabs["awaiting_payment"]["url"])
        # and the narrowed result respects BOTH
        response = self.client.get(
            reverse("admin:orders_order_changelist"),
            {"q": self.unpaid.order_number, "queue": "awaiting_payment"},
        )
        self.assertEqual(response.context["cl"].result_count, 1)
        response = self.client.get(
            reverse("admin:orders_order_changelist"),
            {"q": self.unpaid.order_number, "queue": "needs_refund"},
        )
        self.assertEqual(response.context["cl"].result_count, 0)

    def test_list_shows_jalali_dates_persian_totals_and_shipping_icon(self):
        response = self.client.get(reverse("admin:orders_order_changelist"))
        html = response.content.decode()
        self.assertIn("۱۴۰۵", html)          # Jalali year on today's rows
        self.assertIn("cusin-ship", html)     # shipping-method icon
        self.assertIn("تومان", html)          # Persian-digit totals
        # existing behaviour kept: refund queue link works
        response = self.client.get(
            reverse("admin:orders_order_changelist"), {"refund_status": "required"}
        )
        self.assertEqual(response.context["cl"].result_count, 1)


@override_settings(**PLAIN_STATIC)
class OrderSummaryTests(TestCase):
    def setUp(self):
        self.admin = make_superuser(username="sumowner", phone="+989000020002")
        self.client.force_login(self.admin)

    def _change(self, order):
        return self.client.get(
            reverse("admin:orders_order_change", args=[order.pk])
        )

    def test_summary_context_and_stepper(self):
        order = make_order(status=Order.Status.PROCESSING,
                           payment_status=Order.PaymentStatus.PAID)
        response = self._change(order)
        self.assertTrue(response.context["cusin_order_summary"])
        steps = response.context["summary_stepper_steps"]
        states = {step["key"]: step["state"] for step in steps}
        self.assertEqual(states[Order.Status.PENDING], "done")
        self.assertEqual(states[Order.Status.CONFIRMED], "done")
        self.assertEqual(states[Order.Status.PROCESSING], "current")
        self.assertEqual(states[Order.Status.SHIPPED], "todo")
        self.assertIsNone(response.context["summary_terminal"])
        html = response.content.decode()
        self.assertIn("cusin-step", html)
        self.assertIn("cusin-order-summary", html)
        # customer card: tap-to-call + WhatsApp + items table + print buttons
        self.assertIn("tel:", html)
        self.assertIn(response.context["whatsapp_link"], html)
        self.assertIn("cusin-items-table", html)
        self.assertIn(response.context["order_print_url"], html)

    def test_terminal_states_render_chip_not_stepper(self):
        order = make_order(status=Order.Status.CANCELLED)
        response = self._change(order)
        self.assertEqual(response.context["summary_stepper_steps"], [])
        self.assertEqual(response.context["summary_terminal"]["key"], "cancelled")

    def test_quick_buttons_show_only_legal_transitions(self):
        cases = {
            Order.Status.PENDING: {"confirmed", "cancelled"},
            Order.Status.CONFIRMED: {"processing", "cancelled"},
            Order.Status.PROCESSING: {"shipped", "cancelled"},
            Order.Status.SHIPPED: {"delivered", "returned"},
            Order.Status.DELIVERED: {"returned"},
            Order.Status.CANCELLED: set(),
        }
        for status, expected in cases.items():
            with self.subTest(status=status):
                order = make_order(status=status)
                response = self._change(order)
                values = {b["value"] for b in response.context["quick_allowed"]}
                self.assertEqual(values, expected)
                # and matches the workflow module itself
                self.assertEqual(values, {s for s in allowed_next_statuses(status)})

    def test_tracking_field_rules(self):
        # courier order without tracking: the inline field must appear
        courier = make_order(status=Order.Status.PROCESSING,
                             shipping_method="standard")
        response = self._change(courier)
        self.assertTrue(response.context["quick_needs_tracking"])
        # already has a code: no field
        courier.tracking_code = "TRK-1"
        courier.save(update_fields=["tracking_code"])
        self.assertFalse(self._change(courier).context["quick_needs_tracking"])
        # pickup never asks for tracking
        pickup = make_order(status=Order.Status.PROCESSING,
                            shipping_method="pickup")
        self.assertFalse(self._change(pickup).context["quick_needs_tracking"])

    def test_view_only_staff_gets_no_quick_buttons(self):
        staff = make_staff(permissions=["orders.view_order"],
                           username="+989000021001", phone="+989000021001")
        self.client.force_login(staff)
        order = make_order(status=Order.Status.PENDING)
        response = self._change(order)
        self.assertFalse(response.context["quick_can_change"])
        self.assertNotIn("cusin-quick-form", response.content.decode())


@override_settings(**PLAIN_STATIC)
class QuickStatusTests(TestCase):
    maxDiff = None

    def setUp(self):
        self.admin = make_superuser(username="quickowner", phone="+989000020003")
        self.client.force_login(self.admin)

    def _url(self, order):
        return reverse("admin:orders_order_quick_status", args=[order.pk])

    def _post(self, order, **data):
        return self.client.post(self._url(order), data)

    def test_get_redirects_to_change_page(self):
        order = make_order()
        response = self.client.get(self._url(order))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            reverse("admin:orders_order_change", args=[order.pk]),
        )

    def test_legal_transition_applies_and_logs(self):
        order = make_order(status=Order.Status.PENDING)
        response = self._post(order, next_status="confirmed")
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CONFIRMED)
        logs = LogEntry.objects.filter(object_id=str(order.pk))
        self.assertEqual(logs.count(), 1)
        self.assertIn("تغییر سریع وضعیت", logs.first().change_message)

    def test_illegal_transition_is_rejected_without_writes(self):
        order = make_order(status=Order.Status.PENDING)
        for bad in ("shipped", "delivered", "returned"):
            with self.subTest(target=bad):
                response = self._post(order, next_status=bad)
                self.assertEqual(response.status_code, 302)
                order.refresh_from_db()
                self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(LogEntry.objects.filter(object_id=str(order.pk)).count(), 0)
        # messages framework carried the error back
        response = self.client.get(
            reverse("admin:orders_order_change", args=[order.pk])
        )
        self.assertContains(response, "مجاز نیست")

    def test_unknown_status_value_is_rejected(self):
        order = make_order(status=Order.Status.PENDING)
        response = self._post(order, next_status="flying")
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)
        response = self.client.get(
            reverse("admin:orders_order_change", args=[order.pk])
        )
        self.assertContains(response, "معتبر نیست")

    def test_shipped_requires_tracking_for_courier_methods(self):
        for method in ("standard", "express"):
            with self.subTest(method=method):
                order = make_order(status=Order.Status.PROCESSING,
                                   shipping_method=method)
                response = self._post(order, next_status="shipped")
                self.assertEqual(response.status_code, 302)
                order.refresh_from_db()
                self.assertEqual(order.status, Order.Status.PROCESSING)  # blocked
                response = self.client.get(
                    reverse("admin:orders_order_change", args=[order.pk])
                )
                self.assertContains(response, "کد رهگیری مرسوله را وارد کنید")

    def test_shipped_with_tracking_saves_code_then_status(self):
        order = make_order(status=Order.Status.PROCESSING,
                           shipping_method="standard")
        response = self._post(order, next_status="shipped", tracking_code="TRK-123")
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.SHIPPED)
        self.assertEqual(order.tracking_code, "TRK-123")
        logs = list(LogEntry.objects.filter(object_id=str(order.pk)).order_by("pk"))
        self.assertEqual(len(logs), 2)  # tracking save + status change
        self.assertIn("کد رهگیری", logs[0].change_message)
        self.assertIn("تغییر سریع وضعیت", logs[1].change_message)

    def test_tracking_code_rejected_for_other_targets(self):
        order = make_order(status=Order.Status.PENDING)
        response = self._post(order, next_status="confirmed", tracking_code="TRK-9")
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)  # nothing applied
        self.assertEqual(order.tracking_code, "")
        self.assertEqual(LogEntry.objects.filter(object_id=str(order.pk)).count(), 0)

    def test_pickup_ships_without_tracking(self):
        order = make_order(status=Order.Status.PROCESSING,
                           shipping_method="pickup")
        response = self._post(order, next_status="shipped")
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.SHIPPED)
        self.assertEqual(order.tracking_code, "")

    def test_cancelling_paid_order_flags_refund_and_warns(self):
        order = make_order(status=Order.Status.PENDING,
                           payment_status=Order.PaymentStatus.PAID)
        response = self._post(order, next_status="cancelled")
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(order.refund_status, Order.RefundStatus.REQUIRED)
        response = self.client.get(
            reverse("admin:orders_order_change", args=[order.pk])
        )
        self.assertContains(response, "بازپرداخت")

    def test_staff_without_change_permission_gets_403(self):
        staff = make_staff(permissions=["orders.view_order"],
                           username="+989000021002", phone="+989000021002")
        self.client.force_login(staff)
        order = make_order(status=Order.Status.PENDING)
        response = self._post(order, next_status="confirmed")
        self.assertEqual(response.status_code, 403)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)

    def test_csrf_is_enforced(self):
        order = make_order(status=Order.Status.PENDING)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.admin)
        response = csrf_client.post(
            self._url(order), {"next_status": "confirmed"}
        )  # no csrfmiddlewaretoken -> must be rejected
        self.assertEqual(response.status_code, 403)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)

    def test_non_staff_cannot_reach_endpoint(self):
        from .helpers import make_customer

        customer = make_customer()
        order = make_order(status=Order.Status.PENDING, user=customer)
        self.client.force_login(customer)
        response = self._post(order, next_status="confirmed")
        # admin_view redirects non-staff to the login page
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("admin:login"), response["Location"])
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)

    def test_existing_form_and_bulk_actions_untouched(self):
        """The classic change form and the CSV bulk action still exist."""
        order = make_order(status=Order.Status.PENDING,
                           payment_status=Order.PaymentStatus.PAID)
        response = self._change_get(order)
        self.assertEqual(response.status_code, 200)
        # the original ModelForm fields are still rendered (status select)
        html = response.content.decode()
        self.assertIn("id_status", html)
        # pre-existing bulk action still offered on the changelist
        response = self.client.get(reverse("admin:orders_order_changelist"))
        self.assertIn("export_orders_csv", response.content.decode())

    def _change_get(self, order):
        return self.client.get(
            reverse("admin:orders_order_change", args=[order.pk])
        )
