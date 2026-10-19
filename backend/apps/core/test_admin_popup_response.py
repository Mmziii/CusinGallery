"""
Task 4 -- no `window.opener` inside the "+" modal iframe.

Django's stock ``admin/popup_response.html`` loads ``admin/js/popup_response.js``,
which calls the bare global ``opener``. Inside the in-page modal iframe that
value is ``null``, so every successful save logged:

    Cannot read properties of null (reading 'dismissAddRelatedObjectPopup')

The project overrides that template: the iframe document only carries the
documented ``data-popup-response`` payload (read by cusin_popup_modal.js on
iframe load) and never runs code that touches ``opener``. A real browser
popup window keeps the stock behaviour, but only after checking that an
opener actually exists.
"""
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from apps.accounts.tests.helpers import make_user

BRIDGE_PATH = (
    Path(settings.BASE_DIR) / "static" / "admin_theme" / "js" / "popup_response_bridge.js"
)


class PopupResponseTemplateTests(TestCase):
    def setUp(self):
        self.admin = make_user(
            phone="+989300009001", password="popup-admin-pw-12345!", is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.admin)

    def test_admin_save_renders_the_safe_popup_response(self):
        """A real "+" save (POST with _popup=1) must use our template."""
        url = reverse("admin:auth_group_add") + "?_popup=1"
        response = self.client.post(url, {"name": "گروه آزمایشی", "_popup": "1"})
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()

        self.assertIn("django-admin-popup-response-constants", html)
        self.assertIn("popup_response_bridge.js", html)
        # Django's own script (the one that dereferences the null opener) is
        # deliberately NOT loaded as a static <script src> tag.
        self.assertNotIn('src="/static/admin/js/popup_response.js"', html)
        # The response payload itself is still present for the modal.
        self.assertIn("data-popup-response=", html)

    def test_bridge_guards_the_opener_and_skips_iframes(self):
        source = BRIDGE_PATH.read_text(encoding="utf-8")
        # Inside the modal iframe the script returns before any opener access.
        self.assertIn("window.parent !== window", source)
        # (The comment block mentions window.opener too, so compare the two
        # actual code guards instead of the first raw occurrence.)
        self.assertLess(
            source.index("if (window.parent && window.parent !== window) return;"),
            source.index("if (!window.opener"),
            "the iframe guard must run before the opener check",
        )
        # A real popup only loads the stock script when an opener exists.
        self.assertIn("if (!window.opener", source)
        self.assertNotIn("opener.dismiss", source)

    def test_modal_script_has_no_opener_proxy(self):
        modal_js = (
            Path(settings.BASE_DIR) / "static" / "admin_theme" / "js" / "cusin_popup_modal.js"
        ).read_text(encoding="utf-8")
        self.assertNotIn("Object.defineProperty(win, \"opener\"", modal_js)
        self.assertNotIn("win.opener = window", modal_js)
