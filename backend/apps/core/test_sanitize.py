"""
HTML sanitiser tests (owner-editable info pages + e-namad embed).

The properties that matter:
* a script/style/iframe cannot survive, and neither does its CONTENT;
* every ``on*`` attribute and every non-allowlisted attribute is dropped;
* javascript:/data:/vbscript: links are removed (including obfuscation via
  entities and control characters), while http/https/mailto/tel/relative
  links keep working;
* markup is re-emitted balanced, so a half-typed tag cannot break the page.
"""
from django.test import SimpleTestCase

from apps.core.sanitize import is_safe_url, sanitize_embed, sanitize_html


class SanitizeHtmlTests(SimpleTestCase):
    def test_scripts_and_styles_are_removed_with_their_content(self):
        value = (
            "<p>سلام</p><script>alert('x')</script>"
            "<style>body{display:none}</style><p>پایان</p>"
        )
        cleaned = sanitize_html(value)
        self.assertEqual(cleaned, "<p>سلام</p><p>پایان</p>")

    def test_event_handlers_and_styles_are_dropped(self):
        cleaned = sanitize_html('<p onclick="alert(1)" style="color:red">متن</p>')
        self.assertEqual(cleaned, "<p>متن</p>")

    def test_allowed_markup_is_kept(self):
        value = (
            "<h2>عنوان</h2><p><strong>پررنگ</strong> و <em>مورب</em></p>"
            "<ul><li>یک</li><li>دو</li></ul><blockquote>نقل</blockquote>"
        )
        self.assertEqual(sanitize_html(value), value)

    def test_javascript_and_data_links_are_unwrapped(self):
        cleaned = sanitize_html(
            '<p><a href="javascript:alert(1)">بد</a> و '
            '<a href="data:text/html;base64,PHNjcmlwdD4=">داده</a></p>'
        )
        self.assertEqual(cleaned, "<p>بد و داده</p>")

    def test_obfuscated_javascript_scheme_is_rejected(self):
        self.assertFalse(is_safe_url("java\nscript:alert(1)"))
        self.assertFalse(is_safe_url("JaVaScRiPt:alert(1)"))
        self.assertFalse(is_safe_url("javascript&colon;alert(1)"))
        self.assertTrue(is_safe_url("https://cusin.ir/x?y=1"))
        self.assertTrue(is_safe_url("/shop/"))
        self.assertTrue(is_safe_url("mailto:support@cusin.ir"))
        self.assertTrue(is_safe_url("tel:+982100000000"))

    def test_blank_target_gets_a_rel_attribute(self):
        cleaned = sanitize_html(
            '<a href="https://example.com" target="_blank">بیرون</a>'
        )
        self.assertIn('rel="noopener noreferrer"', cleaned)

    def test_unclosed_markup_is_balanced(self):
        cleaned = sanitize_html("<p>یک <strong>دو")
        self.assertEqual(cleaned, "<p>یک <strong>دو</strong></p>")

    def test_entities_are_preserved_not_double_escaped(self):
        cleaned = sanitize_html("<p>۳ &lt; ۵ &amp; بیشتر</p>")
        self.assertEqual(cleaned, "<p>۳ &lt; ۵ &amp; بیشتر</p>")

    def test_unknown_tags_are_unwrapped_but_text_is_kept(self):
        cleaned = sanitize_html("<p>سلام <span class='x'>دنیا</span></p>")
        self.assertEqual(cleaned, "<p>سلام دنیا</p>")


class SanitizeEmbedTests(SimpleTestCase):
    def test_trust_seal_markup_keeps_link_and_image(self):
        value = (
            '<div id="enamad"><a href="https://trustseal.enamad.ir/" target="_blank">'
            '<img src="https://trustseal.enamad.ir/logo.png" alt="نماد اعتماد" '
            'onerror="alert(1)"></a></div>'
        )
        cleaned = sanitize_embed(value)
        self.assertIn('<div id="enamad">', cleaned)
        self.assertIn('href="https://trustseal.enamad.ir/"', cleaned)
        self.assertIn('src="https://trustseal.enamad.ir/logo.png"', cleaned)
        self.assertNotIn("onerror", cleaned)
        self.assertNotIn("style", cleaned)

    def test_trust_seal_scripts_are_removed(self):
        cleaned = sanitize_embed("<script>alert(1)</script><div>نماد</div>")
        self.assertEqual(cleaned, "<div>نماد</div>")

    def test_existing_plain_div_is_unchanged(self):
        self.assertEqual(
            sanitize_embed('<div id="enamad">x</div>'),
            '<div id="enamad">x</div>',
        )
