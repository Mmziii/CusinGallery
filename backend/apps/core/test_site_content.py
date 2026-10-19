"""
Owner-editable site content (Task 1): the public payload, caching,
invalidation, info pages (published = 200, unpublished = 404) and the
admin page that edits them.

The most important assertion in this file is the one about the CURRENT
texts: after the data migration the storefront must look exactly like it
did before this feature existed.
"""
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status

from apps.accounts.tests.helpers import make_user
from apps.core.content import get_content_payload, invalidate_site_cache
from apps.core.models import InfoPage, SiteSettings, TrustStripItem
from apps.core.testing import CacheIsolatedAPITestCase


class ContentPayloadTests(CacheIsolatedAPITestCase):
    url = reverse("site-content")

    def test_endpoint_is_public_and_has_every_section(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(response.data),
            {"brand", "home", "trust_strip", "footer", "floating", "theme", "info_pages"},
        )

    def test_brand_and_home_copy_are_the_current_storefront_texts(self):
        data = self.client.get(self.url).data
        self.assertEqual(data["brand"]["name"], "کازین گالری")
        self.assertEqual(data["brand"]["tagline"], "کازین گالری، خانهٔ ظروف دوست‌داشتنی")
        self.assertEqual(data["home"]["sections"]["deals"], "پیشنهاد امروز")
        self.assertEqual(data["home"]["sections"]["featured"], "محصولات منتخب")
        self.assertEqual(data["home"]["sections"]["best_sellers"], "پرفروش‌ترین‌ها")
        self.assertEqual(data["home"]["sections"]["reviews"], "از زبان خریداران")
        self.assertEqual(data["home"]["story"]["title"], "کازین گالری؛ خانهٔ ظروف دوست‌داشتنی")

    def test_five_trust_items_are_seeded_in_order(self):
        data = self.client.get(self.url).data
        self.assertEqual(
            [item["label"] for item in data["trust_strip"]],
            [
                "تضمین اصالت کالا و سلامت فیزیکی اجناس",
                "بسته‌بندی ضدضربهٔ کالا",
                "ارسال به سراسر ایران",
                "پرداخت امن اینترنتی",
                "امکان تحویل اکسپرس",
            ],
        )
        self.assertEqual(data["trust_strip"][0]["icon"], "shield-check")

    def test_hidden_trust_item_disappears_and_order_is_honoured(self):
        second = TrustStripItem.objects.order_by("ordering", "pk")[1]
        second.is_active = False
        second.save()
        first = TrustStripItem.objects.order_by("ordering", "pk")[0]
        first.ordering = 99
        first.save()

        labels = [item["label"] for item in self.client.get(self.url).data["trust_strip"]]
        self.assertNotIn(second.label, labels)
        self.assertEqual(labels[-1], first.label)

    def test_footer_contains_current_copy_and_public_contact_only(self):
        site = SiteSettings.load()
        site.phone = "+98 21 1234 5678"
        site.extra_phones = "+98 21 8765 4321\n+98 912 111 2233"
        site.instagram = "cusin_gallery"
        site.eitaa = "cusin"
        site.bale = "cusin"
        site.save()

        footer = self.client.get(self.url).data["footer"]
        self.assertEqual(
            footer["about"],
            "فروشگاه آنلاین ظروف آشپزخانه، پخت‌وپز، بلور و کریستال و لوازم خانگی. "
            "خریدی مطمئن برای خانه‌ای زیباتر.",
        )
        self.assertEqual(footer["phones"][0], "+98 21 1234 5678")
        self.assertIn("+98 912 111 2233", footer["phones"])
        self.assertEqual(footer["socials"]["instagram"], "https://instagram.com/cusin_gallery")
        self.assertEqual(footer["socials"]["eitaa"], "https://eitaa.com/cusin")
        self.assertEqual(footer["socials"]["bale"], "https://ble.ir/cusin")
        # Nothing private or internal is dumped into the public payload.
        for forbidden in ("pickup_address", "pickup_hours", "created_at", "updated_at"):
            self.assertNotIn(forbidden, footer)

    def test_seeded_placeholder_phone_is_not_exposed(self):
        # The seed migration stores «+98 21 0000 0000» as an INSTRUCTION.
        # The storefront must receive an empty value, never a fake number.
        footer = self.client.get(self.url).data["footer"]
        self.assertNotIn("+98 21 0000 0000", footer["phones"])

    def test_floating_buttons_follow_the_toggles(self):
        site = SiteSettings.load()
        site.phone = "+98 21 1234 5678"
        site.floating_phone = False
        site.save()
        links = self.client.get(self.url).data["floating"]["links"]
        self.assertEqual(links, [])

        site.floating_phone = True
        site.save()
        links = self.client.get(self.url).data["floating"]["links"]
        self.assertEqual(links[0]["key"], "phone")
        self.assertTrue(links[0]["href"].startswith("tel:"))

    def test_enamad_snippet_is_sanitised_in_the_payload(self):
        site = SiteSettings.load()
        site.enamad_html = (
            '<div id="enamad">نماد</div><script>alert(1)</script>'
            '<img src="https://trustseal.enamad.ir/x.png" onerror="alert(1)">'
        )
        site.save()
        html = self.client.get(self.url).data["footer"]["enamad_html"]
        self.assertIn('<div id="enamad">', html)
        self.assertIn("trustseal.enamad.ir/x.png", html)
        self.assertNotIn("script", html)
        self.assertNotIn("onerror", html)

    def test_payload_is_cached_until_invalidated(self):
        first = self.client.get(self.url).data["brand"]["name"]
        # .update() bypasses the model signal on purpose: this proves the
        # response really comes from the cache.
        SiteSettings.objects.filter(pk=1).update(site_name="نام تازه")
        self.assertEqual(self.client.get(self.url).data["brand"]["name"], first)

        invalidate_site_cache()
        self.assertEqual(self.client.get(self.url).data["brand"]["name"], "نام تازه")

    def test_admin_save_invalidates_the_cache_immediately(self):
        self.client.get(self.url)
        site = SiteSettings.load()
        site.site_name = "کازین گالری تازه"
        site.save()
        self.assertEqual(
            self.client.get(self.url).data["brand"]["name"], "کازین گالری تازه"
        )


class InfoPageAPITests(CacheIsolatedAPITestCase):
    def url(self, slug):
        return reverse("site-info-page", args=[slug])

    def test_every_seeded_page_is_published_and_has_content(self):
        data = self.client.get(reverse("site-content")).data
        self.assertEqual(
            {page["slug"] for page in data["info_pages"]},
            {"about", "contact", "shipping-returns", "terms", "privacy"},
        )
        for page in data["info_pages"]:
            self.assertTrue(page["title"])
            self.assertTrue(page["seo_description"])
            self.assertEqual(page["path"], f"/{page['slug']}/")

    def test_published_page_returns_sanitised_html(self):
        page = InfoPage.objects.get(slug="about")
        page.body = '<h2>عنوان</h2><p>متن</p><script>alert(1)</script>'
        page.save()

        response = self.client.get(self.url("about"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["title"], page.title)
        self.assertEqual(response.data["body"], "<h2>عنوان</h2><p>متن</p>")
        self.assertNotIn("script", response.data["body"])

    def test_unpublished_page_is_a_404_and_is_not_advertised(self):
        page = InfoPage.objects.get(slug="terms")
        page.is_published = False
        page.save()

        self.assertEqual(self.client.get(self.url("terms")).status_code, 404)
        slugs = [item["slug"] for item in self.client.get(reverse("site-content")).data["info_pages"]]
        self.assertNotIn("terms", slugs)

    def test_unknown_page_is_a_404(self):
        self.assertEqual(self.client.get(self.url("nope")).status_code, 404)

    def test_unpublished_info_page_url_is_a_real_404_page(self):
        page = InfoPage.objects.get(slug="shipping-returns")
        page.is_published = False
        page.save()
        response = self.client.get("/shipping-returns/")
        self.assertEqual(response.status_code, 404)


@override_settings(ADMIN_THEME_ENABLED=True)
class SiteContentAdminTests(TestCase):
    def setUp(self):
        self.admin = make_user(
            phone="+989300008001", password="content-admin-pw-12345!",
            is_staff=True, is_superuser=True,
        )
        self.client.force_login(self.admin)

    def test_change_form_renders_fieldsets_preview_and_reset(self):
        response = self.client.get(reverse("admin:core_sitesettings_change", args=[1]))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        for label in (
            "برند و هویت", "صفحهٔ اصلی", "فوتر و راه‌های ارتباطی",
            "دکمه‌های شناور تماس",
        ):
            self.assertIn(label, html)
        for field_label in (
            "نام سایت", "شعار سایت", "لوگوی هدر روشن", "لوگوی هدر تیره",
            "متن دربارهٔ فروشگاه در فوتر", "ایتا", "بله", "متن کپی‌رایت",
        ):
            self.assertIn(field_label, html)
        self.assertIn('id="cusin-theme-preview"', html)
        self.assertIn("بازگشت به تنظیمات پیش‌فرض", html)
        self.assertIn("theme_preview.js", html)
        self.assertIn('id="cusin-theme-presets"', html)

    def test_every_editable_model_field_is_in_a_fieldset(self):
        from apps.core.admin import SiteSettingsAdmin

        in_fieldsets = {
            name
            for _title, options in SiteSettingsAdmin.fieldsets
            for name in options["fields"]
        }
        for field in SiteSettings._meta.fields:
            if field.name in {"id", "created_at", "updated_at"}:
                continue
            with self.subTest(field=field.name):
                self.assertIn(field.name, in_fieldsets)

    def test_saving_the_form_sanitises_the_trust_seal(self):
        response = self.client.post(
            reverse("admin:core_sitesettings_change", args=[1]),
            {
                "site_name": "کازین گالری",
                "tagline": "شعار",
                "shop_name": "",
                "home_heading": "عنوان",
                "hero_title": "بنر",
                "hero_subtitle": "زیرعنوان",
                "hero_button_text": "دکمه",
                "hero_button_link": "/shop/",
                "section_categories_title": "دسته‌بندی‌ها",
                "section_deals_title": "پیشنهاد امروز",
                "section_featured_title": "محصولات منتخب",
                "section_new_title": "جدیدترین محصولات",
                "section_best_title": "پرفروش‌ترین‌ها",
                "section_reviews_title": "از زبان خریداران",
                "story_title": "داستان",
                "story_text": "متن",
                "footer_about": "درباره",
                "email": "support@cusin.ir",
                "footer_quick_links_title": "دسترسی سریع",
                "footer_help_links_title": "راهنما",
                "footer_trust_title": "نمادها",
                "enamad_html": '<div id="enamad">نماد</div><script>alert(1)</script>',
                "pickup_address": "",
                "pickup_hours": "",
                "floating_enabled": "on",
                "floating_whatsapp": "on",
                "floating_telegram": "on",
                "floating_phone": "on",
                "theme_preset": "olive_gold",
                "theme_button_radius": "medium",
                "theme_base_font_size": "normal",
                "theme_card_shadow": "soft",
                # No inline edits in this POST: existing trust items stay.
                "trust_items-TOTAL_FORMS": "0",
                "trust_items-INITIAL_FORMS": "0",
                "trust_items-MIN_NUM_FORMS": "0",
                "trust_items-MAX_NUM_FORMS": "1000",
                "_save": "ذخیره",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            SiteSettings.load().enamad_html, '<div id="enamad">نماد</div>'
        )
