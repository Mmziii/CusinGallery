"""
Audit 19 item 3 (admin side): the password visibility toggle.

Two layers, both checked here:

  * the LOGIN page renders the toggle as markup
    (backend/templates/admin/login.html): a real ``type="button"`` with
    «نمایش رمز» / «پنهان کردن رمز», ``aria-pressed`` and the eye / eye-off
    icons from the inline sprite, inside a ``.cusin-password`` wrapper at the
    inline end of the field;
  * ``theme.js`` enhances every OTHER password input of the panel (the
    password-change form, the reset-confirm form, the user change form), and
    ``theme.css`` styles the control. The behaviour itself is pinned by the
    vitest suite, which runs the real theme.js in a DOM
    (frontend/src/admin-theme/passwordToggle.test.js) -- here we assert the
    shipped assets really contain the pieces the login page relies on.
"""
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .helpers import PLAIN_STATIC, make_superuser

BASE = Path(settings.BASE_DIR)
THEME_JS = BASE / "static" / "admin_theme" / "js" / "theme.js"
THEME_CSS = BASE / "static" / "admin_theme" / "css" / "theme.css"
SPRITE = BASE / "apps" / "adminui" / "templates" / "adminui" / "_sprite.html"


@override_settings(**PLAIN_STATIC)
class AdminPasswordToggleTests(TestCase):
    def setUp(self):
        self.admin = make_superuser(username="pwowner", phone="+989000040001")

    def test_login_page_renders_the_toggle_inside_the_password_field(self):
        response = self.client.get(reverse("admin:login"))
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn('class="cusin-password"', html)
        self.assertIn("data-cusin-password-toggle", html)
        self.assertIn('type="button"', html)
        self.assertIn('aria-label="نمایش رمز"', html)
        self.assertIn('aria-pressed="false"', html)
        self.assertIn('title="نمایش رمز"', html)
        # Both icons come from the inline sprite (no icon font, no emoji).
        self.assertIn("#cusin-i-eye", html)
        self.assertIn("#cusin-i-eye-off", html)
        # The field itself is still the real password input and the form
        # still posts to the same place.
        self.assertIn('type="password"', html)
        self.assertIn(f'action="{reverse("admin:login")}"', html)
        self.assertIn("csrfmiddlewaretoken", html)

    def test_toggle_button_points_at_the_field_it_controls(self):
        html = self.client.get(reverse("admin:login")).content.decode()

        self.assertIn('aria-controls="id_password"', html)
        self.assertIn('id="id_password"', html)

    def test_password_change_pages_load_the_enhancing_script(self):
        """The other admin password pages have no wrapper markup; they rely on
        theme.js, which every themed page loads."""
        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin:password_change"))
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("admin_theme/js/theme.js", html)
        self.assertIn('type="password"', html)

        # ... and the assets really implement the enhancement.
        script = THEME_JS.read_text(encoding="utf-8")
        self.assertIn("function initPasswordToggles()", script)
        self.assertIn('querySelectorAll(\'input[type="password"]\')', script)
        self.assertIn("cusin-password-toggle", script)
        self.assertIn("نمایش رمز", script)
        self.assertIn("پنهان کردن رمز", script)
        # `type="button"` is set on the generated control: it must never submit.
        self.assertIn('button.type = "button";', script)

    def test_theme_css_styles_the_control_for_the_light_panel(self):
        css = THEME_CSS.read_text(encoding="utf-8").replace(" ", "")

        self.assertIn(".cusin-password{", css)
        self.assertIn(".cusin-password-toggle", css)
        # 40px tap target, positioned at the inline end of the field.
        self.assertIn("width:40px;", css)
        self.assertIn("height:40px;", css)
        self.assertIn("inset-inline-end:4px;", css)
        # eye / eye-off visibility follows the button's pressed state.
        self.assertIn('[aria-pressed="true"].cusin-icon--eye-off', css)

    def test_sprite_ships_both_icons(self):
        sprite = SPRITE.read_text(encoding="utf-8")

        self.assertIn('id="cusin-i-eye"', sprite)
        self.assertIn('id="cusin-i-eye-off"', sprite)

    def test_user_change_form_password_fields_are_enhanced_too(self):
        """The user change form's password link page also gets the toggle via
        theme.js -- assert the page ships the script and a password field."""
        self.client.force_login(self.admin)
        url = reverse("admin:accounts_user_change", args=[self.admin.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("admin_theme/js/theme.js", html)

        password_url = reverse("admin:auth_user_password_change", args=[self.admin.pk])
        password_response = self.client.get(password_url)
        self.assertEqual(password_response.status_code, 200)
        self.assertIn("admin_theme/js/theme.js", password_response.content.decode())

    def test_no_password_input_is_left_without_the_hook(self):
        """A guard for future templates: any admin page that renders a bare
        password input must load theme.js (which is what adds the toggle)."""
        self.client.force_login(self.admin)

        pages = [
            reverse("admin:password_change"),
            reverse("admin:auth_user_password_change", args=[self.admin.pk]),
        ]
        for url in pages:
            with self.subTest(url=url):
                html = self.client.get(url).content.decode()
                if 'type="password"' in html:
                    self.assertIn("admin_theme/js/theme.js", html)


@override_settings(**PLAIN_STATIC)
class LoginPageRegressionTests(TestCase):
    """The login page was rewritten for the toggle: it must still log in."""

    def test_the_rewritten_login_page_still_authenticates(self):
        user = get_user_model().objects.create_user(
            username="+989000040002",
            phone="+989000040002",
            password="a-strong-passw0rd!",
            is_staff=True,
        )
        user.is_superuser = True
        user.save(update_fields=["is_superuser"])

        response = self.client.post(
            reverse("admin:login"),
            {
                "username": "+989000040002",
                "password": "a-strong-passw0rd!",
                "next": reverse("admin:index"),
            },
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("admin:index"))

    def test_wrong_credentials_still_show_the_persian_error(self):
        response = self.client.post(
            reverse("admin:login"), {"username": "nobody", "password": "nope"}
        )
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("errornote", html)
        self.assertIn("cusin-password", html)
