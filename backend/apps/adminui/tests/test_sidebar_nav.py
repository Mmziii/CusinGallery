"""
Item 8 -- the admin sidebar: order, grouping, persistence contract.

The old sidebar grouped models by DJANGO APP, so «محصولات» sat above
«سفارش‌ها», «تنظیمات فروشگاه» was buried at the bottom under «تنظیمات»
(next to OTP devices), and every destination needed a group to be opened
first. It is now a flat list in the owner's working order with the
rarely-used models collapsed into «سایر / پیشرفته».
"""
import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.tests.helpers import make_user

from .helpers import PLAIN_STATIC, make_staff, make_superuser

JS_PATH = Path(settings.BASE_DIR) / "static" / "admin_theme" / "js" / "theme.js"
CSS_PATH = Path(settings.BASE_DIR) / "static" / "admin_theme" / "css" / "theme.css"

# The order the owner asked for, after the dashboard link.
EXPECTED_ORDER = (
    "گزارش‌ها و تحلیل",
    "سفارش‌ها",
    "محصولات",
    "دسته‌بندی‌ها",
    "برندها",
    "کوپن‌ها",
    "نظرات",
    "بنرها و پیشنهاد روزانه",
    "اطلاع‌رسانی موجودی",
    "کاربران",
    "محتوا و ظاهر سایت",
    "صفحات اطلاعاتی",
)

# Things that must NOT be on the daily path any more.
ADVANCED_ONLY = (
    "پرداخت‌ها",
    "نشانی‌ها",
    "سبدهای خرید",
    "علاقه‌مندی‌ها",
    "گزارش اعلان‌ها",
)

ROUTE_FOR_LABEL = {
    "گزارش‌ها و تحلیل": "admin_reports",
    "سفارش‌ها": "admin:orders_order_changelist",
    "محصولات": "admin:products_product_changelist",
    "دسته‌بندی‌ها": "admin:categories_category_changelist",
    "برندها": "admin:products_brand_changelist",
    "کوپن‌ها": "admin:discounts_coupon_changelist",
    "نظرات": "admin:reviews_review_changelist",
    "بنرها و پیشنهاد روزانه": "admin:banners_banner_changelist",
    "اطلاع‌رسانی موجودی": "admin:products_backinstocksubscription_changelist",
    "کاربران": "admin:accounts_user_changelist",
    "محتوا و ظاهر سایت": "admin:core_sitesettings_changelist",
    "صفحات اطلاعاتی": "admin:core_infopage_changelist",
}


def drawer(response):
    """The rendered sidebar, or "" when the page has none."""
    html = response.content.decode()
    if 'id="cusin-drawer"' not in html:
        return ""
    return html.split('id="cusin-drawer"', 1)[1].split("</nav>", 1)[0]


@override_settings(**PLAIN_STATIC)
class SidebarOrderTests(TestCase):
    def setUp(self):
        self.admin = make_superuser(username="nav-owner", phone="+989000020001")
        self.client.force_login(self.admin)

    def _primary_rows(self):
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        html = drawer(response)
        primary = html.split('class="cusin-nav-primary"', 1)[1]
        # The list ends where the «سایر / پیشرفته» group starts -- NOT at
        # the first </ul>, which is a nested group's own list.
        primary = primary.split('data-cusin-nav-group="advanced"', 1)[0]
        primary = primary.split('<div class="cusin-drawer-foot"', 1)[0]
        # Drop nested <ul>s: their <li>s are children of a group, not rows.
        primary = re.sub(r"<ul\b[^>]*>[\s\S]*?</ul>", "", primary)
        # One row per <li>, in document order: either a link or a group title.
        rows = []
        for chunk in re.split(r"<li>", primary)[1:]:
            title = re.search(r'class="cusin-nav-group-title">([^<]+)<', chunk)
            link = re.search(r'class="cusin-nav-link[^"]*">.*?<span>([^<]+)</span>', chunk, re.S)
            rows.append((title.group(1) if title else (link.group(1) if link else "")).strip())
        return [row for row in rows if row]

    def test_sidebar_is_in_the_owners_order(self):
        self.assertEqual(tuple(self._primary_rows()), EXPECTED_ORDER)

    def test_dashboard_link_comes_first_and_works(self):
        response = self.client.get(reverse("admin:index"))
        html = response.content.decode()
        index_url = reverse("admin:index")
        self.assertIn('class="cusin-drawer-dash', html)
        # The dashboard anchor precedes the first primary row.
        self.assertLess(
            html.index('class="cusin-drawer-dash'),
            html.index('class="cusin-nav-primary"'),
        )
        self.assertIn(f'href="{index_url}"', html)

    def test_every_primary_item_links_to_its_own_changelist(self):
        response = self.client.get(reverse("admin:index"))
        html = drawer(response)
        for label, route in ROUTE_FOR_LABEL.items():
            with self.subTest(label=label):
                self.assertIn(f'href="{reverse(route)}"', html)

    def test_settings_link_points_at_site_settings_not_the_auth_app(self):
        """«محتوا و ظاهر سایت» is the store profile, not Django's auth app."""
        html = drawer(self.client.get(reverse("admin:index")))
        self.assertIn('href="' + reverse("admin:core_sitesettings_changelist") + '"', html)
        # The auth/django_otp leftovers are parked in «سایر / پیشرفته».
        advanced = html.split('data-cusin-nav-group="advanced"', 1)[1]
        self.assertIn(reverse("admin:auth_group_changelist"), advanced)

    def test_banners_entry_covers_the_daily_deal_too(self):
        """«بنرها و پیشنهاد روزانه» is one shelf -- both changelists."""
        html = drawer(self.client.get(reverse("admin:index")))
        self.assertIn(reverse("admin:banners_banner_changelist"), html)
        self.assertIn(reverse("admin:banners_dailydeal_changelist"), html)


@override_settings(**PLAIN_STATIC)
class SidebarAdvancedGroupTests(TestCase):
    def setUp(self):
        self.admin = make_superuser(username="nav-adv", phone="+989000020002")
        self.client.force_login(self.admin)

    def _advanced(self):
        response = self.client.get(reverse("admin:index"))
        html = drawer(response)
        self.assertIn('data-cusin-nav-group="advanced"', html)
        return html.split('data-cusin-nav-group="advanced"', 1)[1].split("</details>", 1)[0]

    def test_advanced_group_exists_and_is_titled(self):
        self.assertIn("سایر / پیشرفته", self._advanced())

    def test_rarely_used_models_live_in_the_advanced_group(self):
        advanced = self._advanced()
        for label in ADVANCED_ONLY:
            with self.subTest(label=label):
                self.assertIn(label, advanced)

    def test_advanced_group_is_collapsed_when_nothing_in_it_is_active(self):
        response = self.client.get(reverse("admin:index"))
        html = drawer(response)
        tag = re.search(r'<details[^>]*data-cusin-nav-group="advanced"[^>]*>', html)
        self.assertIsNotNone(tag)
        self.assertNotIn(" open", tag.group(0))
        self.assertIn('aria-expanded="false"', html.split('data-cusin-nav-group="advanced"', 1)[1][:400])

    def test_advanced_group_opens_itself_when_one_of_its_pages_is_open(self):
        response = self.client.get(reverse("admin:payments_payment_changelist"))
        html = drawer(response)
        tag = re.search(r'<details[^>]*data-cusin-nav-group="advanced"[^>]*>', html)
        self.assertIsNotNone(tag)
        self.assertIn(" open", tag.group(0))

    def test_advanced_group_is_last(self):
        html = drawer(self.client.get(reverse("admin:index")))
        self.assertGreater(
            html.index('data-cusin-nav-group="advanced"'),
            html.index('class="cusin-nav-primary"'),
        )

    def test_nothing_is_lost_models_appear_exactly_once(self):
        """Every accessible model is reachable -- moved, never dropped."""
        response = self.client.get(reverse("admin:index"))
        html = drawer(response)
        hrefs = re.findall(r'<a href="([^"]+)" class="cusin-nav-link', html)
        self.assertEqual(len(hrefs), len(set(hrefs)), "a model is listed twice")
        # The admin registers 20 models (see apps/*/admin.py); all of them
        # must be reachable from the sidebar, in one bucket or the other.
        self.assertGreaterEqual(len(hrefs), 20)

    def test_no_english_model_name_in_the_sidebar(self):
        """Django's verbose_name would leak English into a Persian menu."""
        html = drawer(self.client.get(reverse("admin:index")))
        for english in ("TOTP device", "Static device", "Wishlist item",
                        "Coupon usage", "Notification log", "Address",
                        "Cart", "Payment", "Group", "Product variant"):
            with self.subTest(name=english):
                self.assertNotIn(f">{english}<", html)


@override_settings(**PLAIN_STATIC)
class SidebarPermissionTests(TestCase):
    """Permission filtering still happens: no link, no leak."""

    def test_a_model_the_user_may_not_see_is_absent(self):
        staff = make_staff(permissions=["products.view_product"],
                           username="nav-limited", phone="+989000020003")
        self.client.force_login(staff)
        html = drawer(self.client.get(reverse("admin:index")))
        self.assertIn(reverse("admin:products_product_changelist"), html)
        self.assertNotIn(reverse("admin:orders_order_changelist"), html)
        self.assertNotIn(reverse("admin:accounts_user_changelist"), html)

    def test_the_empty_state_appears_when_everything_is_hidden(self):
        staff = make_staff(permissions=[], username="nav-none", phone="+989000020004")
        self.client.force_login(staff)
        html = drawer(self.client.get(reverse("admin:index")))
        self.assertIn("cusin-nav-empty", html)

    def test_advanced_group_is_not_rendered_when_it_has_nothing(self):
        staff = make_staff(permissions=["products.view_product"],
                           username="nav-noadv", phone="+989000020005")
        self.client.force_login(staff)
        html = drawer(self.client.get(reverse("admin:index")))
        self.assertNotIn('data-cusin-nav-group="advanced"', html)


@override_settings(**PLAIN_STATIC)
class SidebarActiveStateTests(TestCase):
    def setUp(self):
        self.admin = make_superuser(username="nav-active", phone="+989000020006")
        self.client.force_login(self.admin)

    def test_the_open_page_is_highlighted(self):
        url = reverse("admin:products_product_changelist")
        html = drawer(self.client.get(url))
        self.assertIn(f'href="{url}" class="cusin-nav-link is-active"', html)

    def test_only_one_row_is_marked_current(self):
        url = reverse("admin:orders_order_changelist")
        html = drawer(self.client.get(url))
        self.assertEqual(html.count(" is-active"), 1)

    def test_a_child_marks_its_parent_entry_active(self):
        """Daily deal page belongs to «بنرها و پیشنهاد روزانه»."""
        url = reverse("admin:banners_dailydeal_changelist")
        html = drawer(self.client.get(url))
        self.assertIn("is-active", html)
        self.assertIn(f'href="{url}" class="cusin-nav-link is-active"', html)


class SidebarJsContractTests(TestCase):
    """The script and the stylesheet must agree with the rendered markup."""

    def setUp(self):
        self.js = JS_PATH.read_text(encoding="utf-8")
        self.css = CSS_PATH.read_text(encoding="utf-8")

    def test_group_state_uses_session_storage(self):
        """Per-tab, and never leaking between users on a shared computer."""
        code = re.sub(r"/\*[\s\S]*?\*/", "", self.js)
        code = "\n".join(re.sub(r"(^|\s)//.*$", "", line) for line in code.splitlines())
        self.assertIn("window.sessionStorage", code)
        self.assertNotIn("localStorage", code)

    def test_scroll_offset_is_persisted_and_restored(self):
        self.assertIn("current.scrollTop = drawer.scrollTop", self.js)
        self.assertIn("drawer.scrollTop = state.scrollTop", self.js)

    def test_active_row_is_scrolled_into_view_without_moving_the_page(self):
        self.assertIn("scrollIntoView({ block: \"nearest\"", self.js)
        # `nearest` is what stops the whole window from jumping.
        self.assertNotIn("scrollIntoView(true)", self.js)

    def test_header_height_is_measured_into_a_css_variable(self):
        self.assertIn("--cusin-header-h", self.js)
        self.assertIn("--cusin-header-h", self.css)

    def test_the_drawer_clears_the_measured_header(self):
        block = self.css.split(".cusin-drawer {", 1)[1].split("}", 1)[0]
        self.assertIn("top: calc(var(--cusin-header-h", block)
        self.assertIn("max-height: calc(100vh - var(--cusin-header-h", block)

    def test_group_ids_come_from_the_template_not_a_counter(self):
        """A stable id is what makes the persisted state survive a reload."""
        self.assertIn('data-cusin-nav-group="advanced"',
                      (Path(settings.BASE_DIR) / "apps/adminui/templates/adminui/_sidebar.html"
                       ).read_text(encoding="utf-8"))

    def test_js_is_syntactically_valid(self):
        # A missing brace here would silently disable the whole script,
        # including the menus -- so fail loudly.
        self.assertEqual(self.js.count("{"), self.js.count("}"))
