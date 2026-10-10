"""B5: customer summary on the user change page + enriched changelist."""
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Address
from apps.orders.models import Order

from .helpers import (
    PLAIN_STATIC,
    make_customer,
    make_order,
    make_superuser,
)


def make_address(user, **overrides):
    defaults = {
        "user": user,
        "recipient_name": "سارا احمدی",
        "phone": "09121112233",
        "province": "تهران",
        "city": "تهران",
        "address": "خیابان ولیعصر، پلاک ۱۰",
        "postal_code": "1234567890",
        "unit": "2",
        "building_number": "10",
        "is_default": True,
    }
    defaults.update(overrides)
    return Address.objects.create(**defaults)


@override_settings(**PLAIN_STATIC)
class CustomerSummaryTests(TestCase):
    maxDiff = None

    def setUp(self):
        self.admin = make_superuser(username="custowner", phone="+989000040001")
        self.client.force_login(self.admin)
        self.customer = make_customer(
            first_name="سارا", last_name="احمدی",
            phone="+989123334455", username="+989123334455",
        )

    def _change(self, user):
        return self.client.get(reverse("admin:accounts_user_change", args=[user.pk]))

    def test_summary_values_exact(self):
        paid = make_order(user=self.customer, total=250000, subtotal=250000,
                          payment_status=Order.PaymentStatus.PAID)
        make_order(user=self.customer, total=100000, subtotal=100000,
                   payment_status=Order.PaymentStatus.UNPAID)
        make_order(user=self.customer, total=400000, subtotal=400000,
                   payment_status=Order.PaymentStatus.PAID,
                   status=Order.Status.CONFIRMED)
        address = make_address(self.customer)

        response = self._change(self.customer)
        self.assertEqual(response.status_code, 200)
        summary = response.context["cusin_customer_summary"]
        self.assertEqual(summary["orders_count"], 3)
        self.assertEqual(summary["total_paid"], 650000)   # paid orders only
        # last order = most recent created_at
        self.assertIn(summary["last_order"].pk,
                      set(self.customer.orders.values_list("pk", flat=True)))
        self.assertEqual(summary["default_address"].pk, address.pk)
        self.assertFalse(summary["sms_consent"])

    def test_summary_shows_sms_consent(self):
        self.customer.marketing_sms_consent = True
        self.customer.save(update_fields=["marketing_sms_consent"])
        summary = self._change(self.customer).context["cusin_customer_summary"]
        self.assertTrue(summary["sms_consent"])

    def test_empty_state_customer(self):
        summary = self._change(self.customer).context["cusin_customer_summary"]
        self.assertEqual(summary["orders_count"], 0)
        self.assertEqual(summary["total_paid"], 0)
        self.assertIsNone(summary["last_order"])
        self.assertIsNone(summary["default_address"])

    def test_summary_links_to_filtered_orders(self):
        make_order(user=self.customer)
        response = self._change(self.customer)
        html = response.content.decode()
        self.assertIn("cusin-customer-summary", html)
        expected = (
            f"{reverse('admin:orders_order_changelist')}"
            f"?user__id__exact={self.customer.pk}"
        )
        self.assertIn(expected, html)
        # and that filtered list really shows only this customer's orders
        other = make_order()
        response = self.client.get(expected)
        self.assertEqual(response.context["cl"].result_count, 1)
        self.assertNotIn(other.order_number, response.content.decode())

    def test_change_form_itself_untouched(self):
        response = self._change(self.customer)
        html = response.content.decode()
        self.assertIn("id_phone", html)          # stock form fields remain
        self.assertIn("cusin-customer-summary", html)  # summary sits above


@override_settings(**PLAIN_STATIC)
class CustomerChangelistTests(TestCase):
    def setUp(self):
        self.admin = make_superuser(username="custlist", phone="+989000040002")
        self.client.force_login(self.admin)

    def test_list_shows_phone_orders_count_and_jalali_join_date(self):
        customer = make_customer(first_name="رضا", last_name="کریمی",
                                 phone="+989120001122", username="+989120001122")
        make_order(user=customer)
        make_order(user=customer)
        response = self.client.get(reverse("admin:accounts_user_changelist"))
        html = response.content.decode()
        self.assertIn("+989120001122", html)          # phone column
        self.assertIn("۱۴۰۵", html)                    # Jalali join date
        # orders-count badge links to the filtered order list
        self.assertIn(f"?user__id__exact={customer.pk}", html)
        # annotate is exact
        row = next(
            u for u in response.context["cl"].queryset if u.pk == customer.pk
        )
        self.assertEqual(row._orders_count, 2)
