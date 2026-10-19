"""Task 3: «خروجی اکسل» actions on the Orders / Customers / Products lists."""
import io

from django.test import TestCase, override_settings
from django.urls import reverse
from openpyxl import load_workbook

from apps.adminui.tests.helpers import PLAIN_STATIC, make_customer, make_staff, make_superuser
from apps.analytics.models import Event
from apps.products.models import Product

from .helpers import make_event, make_order, make_product


def workbook(response):
    return load_workbook(io.BytesIO(response.content))


@override_settings(**PLAIN_STATIC, ANALYTICS_EXPORT_ROW_LIMIT=50000)
class AdminChangelistActionTests(TestCase):
    def setUp(self):
        self.owner = make_superuser(username="act-owner", phone="+989173000020")
        self.client.force_login(self.owner)
        self.product = make_product(name="کتری مسی", price=120000)

    def _run_action(self, url, action, pks):
        return self.client.post(url, {
            "action": action,
            "_selected_action": [str(pk) for pk in pks],
        })

    def test_orders_action_exports_selected_rows(self):
        customer = make_customer(
            phone="+989173000021", first_name="سارا", last_name="احمدی",
        )
        order = make_order(customer, self.product, total=120000, discount_amount=10000)
        response = self._run_action(
            reverse("admin:orders_order_changelist"), "export_orders_xlsx", [order.pk],
        )
        self.assertEqual(response.status_code, 200)
        sheet = workbook(response).active
        headers = [cell.value for cell in sheet[1]]
        self.assertEqual(headers, [
            "شمارهٔ سفارش", "تاریخ (شمسی)", "مشتری", "تلفن", "شهر",
            "وضعیت سفارش", "وضعیت پرداخت", "تعداد اقلام", "مبلغ نهایی (تومان)",
            "تخفیف (تومان)", "روش ارسال",
        ])
        self.assertEqual(sheet["A2"].value, order.order_number)
        self.assertRegex(sheet["B2"].value, r"^\d{4}/\d{2}/\d{2}$")
        self.assertEqual(sheet["C2"].value, "سارا احمدی")
        self.assertEqual(sheet["D2"].value, "09121112233")
        self.assertEqual(sheet["I2"].value, 120000)
        self.assertEqual(sheet["I2"].number_format, "#,##0")
        self.assertTrue(sheet.sheet_view.rightToLeft)
        self.assertEqual(sheet.freeze_panes, "A2")

    def test_customers_action_exports_spend_and_last_order(self):
        customer = make_customer(
            phone="+989173000022", first_name="مریم", last_name="کریمی",
        )
        make_order(customer, self.product, total=120000)
        response = self._run_action(
            reverse("admin:accounts_user_changelist"), "export_customers_xlsx",
            [customer.pk],
        )
        self.assertEqual(response.status_code, 200)
        sheet = workbook(response).active
        self.assertEqual([cell.value for cell in sheet[1]], [
            "نام مشتری", "تلفن", "تاریخ عضویت (شمسی)", "تعداد سفارش",
            "مجموع خرید (تومان)", "آخرین سفارش (شمسی)",
        ])
        self.assertEqual(sheet["A2"].value, "مریم کریمی")
        self.assertEqual(sheet["D2"].value, 1)
        self.assertEqual(sheet["E2"].value, 120000)

    def test_products_action_exports_views_and_sales(self):
        make_event(Event.Type.PRODUCT_VIEW, product=self.product)
        make_event(Event.Type.PRODUCT_VIEW, product=self.product)
        customer = make_customer(phone="+989173000023")
        make_order(customer, self.product, total=120000)
        response = self._run_action(
            reverse("admin:products_product_changelist"), "export_products_xlsx_action",
            [self.product.pk],
        )
        self.assertEqual(response.status_code, 200)
        sheet = workbook(response).active
        self.assertEqual([cell.value for cell in sheet[1]], [
            "نام محصول", "کد کالا (SKU)", "برند", "دسته‌بندی",
            "قیمت (تومان)", "موجودی", "بازدید", "تعداد فروش",
        ])
        self.assertEqual(sheet["A2"].value, "کتری مسی")
        self.assertEqual(sheet["E2"].value, 120000)
        self.assertEqual(sheet["G2"].value, 2)
        self.assertEqual(sheet["H2"].value, 1)
        self.assertEqual(sheet["E2"].number_format, "#,##0")

    def test_the_action_is_hidden_without_the_view_permission(self):
        from django.contrib import admin
        from django.test import RequestFactory

        from apps.orders.admin import OrderAdmin
        from apps.orders.models import Order

        staff = make_staff(username="act-staff", phone="+989173000024")
        request = RequestFactory().get("/admin/orders/order/")
        request.user = staff
        model_admin = OrderAdmin(Order, admin.site)
        self.assertNotIn("export_orders_xlsx", model_admin.get_actions(request))

        request.user = self.owner
        self.assertIn("export_orders_xlsx", model_admin.get_actions(request))
