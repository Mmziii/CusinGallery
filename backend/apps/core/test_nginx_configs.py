"""
Static checks on the nginx edge configuration.

These tests read the real config files shipped in ``nginx/`` and assert
properties that a syntax check alone would not catch -- properties that
were found the hard way on a live server:

* A ``location`` regular expression containing ``{`` or ``}`` **must** be
  quoted. nginx's config parser does brace counting, so an unquoted
  pattern such as::

      location ~* ^/static/(.+\\.[a-f0-9]{12}\\.[^/]+)$ {

  is split at the first ``{`` and nginx then tries to compile
  ``^/static/(.+\\.[a-f0-9]{12`` as a regex, dying at startup with
  ``pcre2_compile() failed: missing closing parenthesis``. Quoting the
  pattern (``"..."``) makes the parser treat the whole thing as one token.
* The security headers every storefront response must carry, and the
  absence of the nginx version banner.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

BACKEND_DIR = Path(settings.BASE_DIR)
NGINX_ROOT = BACKEND_DIR.parent / "nginx"

# Every server-level config this repo ships. The bootstrap file is an
# example, but it IS what runs on a fresh production box for the few
# minutes before the certificate exists -- it must be as correct as the
# permanent one.
NGINX_FILES = (
    NGINX_ROOT / "conf.d" / "cusin.conf",
    NGINX_ROOT / "prod.d" / "cusin.conf",
    NGINX_ROOT / "prod.d" / "00-bootstrap-http.conf.example",
)

# Server blocks that terminate TLS -- HSTS belongs here and ONLY here
# (sending Strict-Transport-Security over plain http is a no-op at best
# and misleading at worst).
TLS_CONFIGS = {NGINX_ROOT / "prod.d" / "cusin.conf"}

SECURITY_HEADERS = (
    "X-Frame-Options",
    "X-Content-Type-Options",
    "Referrer-Policy",
)


def strip_comments(text):
    """Drop ``#`` comments while leaving ``#`` inside quotes alone.

    Enough of a lexer for these hand-written files: they never use ``#``
    inside an unquoted token.
    """
    out = []
    for line in text.splitlines():
        cleaned = []
        quote = None
        index = 0
        while index < len(line):
            char = line[index]
            if quote:
                cleaned.append(char)
                if char == quote and line[index - 1: index] != "\\":
                    quote = None
            elif char in "\"'":
                quote = char
                cleaned.append(char)
            elif char == "#":
                break
            else:
                cleaned.append(char)
            index += 1
        out.append("".join(cleaned))
    return "\n".join(out)


def regex_locations(text):
    """Yield ``(modifier, pattern, quoted)`` for every regex ``location``.

    ``modifier`` is ``~`` or ``~*``; ``quoted`` is the quote character
    used (``"``/``'``) or ``""`` when the pattern was written bare.

    Deliberately LINE based, mirroring what nginx's own parser does: an
    unquoted token is cut at the first ``{``, so an unquoted
    ``^/static/(.+\\.[a-f0-9]{12}\\.[^/]+)$`` reaches pcre2 as
    ``^/static/(.+\\.[a-f0-9]``. Reading the whole line (up to the block
    brace) is what makes the truncated pattern visible to the test --
    a tokenizing helper would report the truncated, brace-free fragment
    and declare it fine.
    """
    locations = []
    for raw_line in strip_comments(text).splitlines():
        match = re.match(r"\s*location\s+(~\*?)\s+(\S.*)$", raw_line)
        if not match:
            continue
        modifier, rest = match.group(1), match.group(2).strip()
        if rest.startswith("\"") or rest.startswith("'"):
            quote = rest[0]
            end = rest.find(quote, 1)
            if end == -1:
                continue
            locations.append((modifier, rest[1:end], quote))
            continue
        # Unquoted: everything up to the block-opening brace is what
        # nginx tries to compile as a regex.
        body = rest.rstrip()
        if body.endswith("{"):
            body = body[:-1].rstrip()
        locations.append((modifier, body, ""))
    return locations


def _top_level_blocks(text, keyword):
    """Yield ``(header_line, body)`` for every ``server``/``location`` block.

    Indentation based, which is enough for these hand-written files: they
    are uniformly indented and every block's closing ``}`` sits at the
    block's own indent level.
    """
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        match = re.match(r"^(?P<indent>\s*)" + keyword + r"\b(?P<rest>.*?)\{\s*$", line)
        if not match:
            index += 1
            continue
        indent = len(match.group("indent"))
        header = (keyword + match.group("rest")).strip()
        body = []
        index += 1
        while index < len(lines):
            candidate = lines[index]
            if candidate.strip() == "}" and len(candidate) - len(candidate.lstrip()) == indent:
                break
            body.append(candidate)
            index += 1
        yield header, "\n".join(body)


def server_blocks(text):
    """Yield ``(block_text, terminates_tls)`` for every ``server`` block."""
    for header, body in _top_level_blocks(text, "server"):
        yield f"server {header}\n{body}", "listen 443" in f"{header}\n{body}"


def location_blocks(text):
    """Yield ``(header, body)`` for every ``location`` block in the file."""
    yield from _top_level_blocks(text, "location")


class NginxRegexQuotingTests(SimpleTestCase):
    def test_every_regex_location_containing_braces_is_quoted(self):
        """Regression: the collectstatic ``{12}`` hash pattern killed nginx.

        Unquoted, nginx's brace-counting parser ends the pattern at ``{``
        and pcre2 then sees ``^/static/(.+\\.[a-f0-9]{12`` -- "missing
        closing parenthesis" -- and the whole edge server refuses to
        start. Every regex location whose pattern contains a brace must
        therefore be written as a quoted token.
        """
        checked = 0
        for path in NGINX_FILES:
            source = path.read_text(encoding="utf-8")
            locations = regex_locations(source)
            self.assertTrue(locations, f"{path.name}: no regex location found at all")
            for modifier, pattern, quote in locations:
                with self.subTest(config=path.name, pattern=pattern):
                    if "{" in pattern or "}" in pattern:
                        self.assertNotEqual(
                            quote,
                            "",
                            f"{path.name}: regex location '{modifier} {pattern}' contains "
                            f"'{{' or '}}' but is NOT quoted -- nginx fails to start "
                            f"with pcre2_compile() failed: missing closing parenthesis",
                        )
                    checked += 1
        self.assertGreaterEqual(checked, len(NGINX_FILES))

    def test_unquoted_regex_locations_never_shadow_a_block_brace(self):
        """A bare pattern must not contain any brace at all, not just `}`."""
        for path in NGINX_FILES:
            for modifier, pattern, quote in regex_locations(path.read_text(encoding="utf-8")):
                with self.subTest(config=path.name, pattern=pattern):
                    if quote == "":
                        self.assertNotIn("{", pattern)
                        self.assertNotIn("}", pattern)
                        self.assertNotIn(";", pattern)

    def test_hashed_static_pattern_is_the_manifest_pattern(self):
        """The quoted pattern must still express Django's 12-hex suffix."""
        for path in NGINX_FILES:
            patterns = [pattern for _, pattern, _ in regex_locations(path.read_text(encoding="utf-8"))]
            with self.subTest(config=path.name):
                self.assertTrue(
                    any(
                        pattern.startswith("^/static/") and "[a-f0-9]{12}" in pattern
                        for pattern in patterns
                    ),
                    f"{path.name}: no hashed /static/ location found in {patterns}",
                )


class NginxSecurityHeaderTests(SimpleTestCase):
    """The storefront shipped no X-Frame-Options / X-Content-Type-Options /
    Referrer-Policy at all, and nginx happily printed its own version.

    Both are fixed at the edge, because the SPA's HTML never reaches
    Django -- Django's own SECURE_* settings cannot cover it.
    """

    def test_server_tokens_off(self):
        for path in NGINX_FILES:
            with self.subTest(config=path.name):
                self.assertIn(
                    "server_tokens off;",
                    strip_comments(path.read_text(encoding="utf-8")),
                )

    def test_security_headers_present_with_always(self):
        for path in NGINX_FILES:
            source = strip_comments(path.read_text(encoding="utf-8"))
            for header in SECURITY_HEADERS:
                with self.subTest(config=path.name, header=header):
                    self.assertRegex(
                        source,
                        rf"add_header\s+{header}\s+[^;]*\balways\b\s*;",
                        f"{path.name}: '{header}' must be added with `always` "
                        f"(otherwise nginx drops it on error responses)",
                    )

    def test_hsts_only_in_tls_configs(self):
        for path in NGINX_FILES:
            source = strip_comments(path.read_text(encoding="utf-8"))
            has_hsts = "Strict-Transport-Security" in source
            with self.subTest(config=path.name):
                if path in TLS_CONFIGS:
                    self.assertTrue(has_hsts, f"{path.name}: TLS server must send HSTS")
                else:
                    self.assertFalse(
                        has_hsts,
                        f"{path.name}: HSTS over plain HTTP is meaningless and must "
                        f"stay out of the non-TLS configs",
                    )

    def test_hsts_only_in_the_tls_server_block(self):
        """prod.d/cusin.conf has an :80 redirect server too -- no HSTS there."""
        source = strip_comments((NGINX_ROOT / "prod.d" / "cusin.conf").read_text(encoding="utf-8"))
        for block, tls in server_blocks(source):
            with self.subTest(server=block.splitlines()[0]):
                if tls:
                    self.assertIn("Strict-Transport-Security", block)
                else:
                    self.assertNotIn("Strict-Transport-Security", block)

    def test_every_location_owning_add_headers_repeats_the_security_headers(self):
        """nginx's add_header inheritance trap.

        `add_header` is inherited by a nested block ONLY when that block
        defines none of its own. Every location that sets Cache-Control
        therefore has to repeat the security headers, or a static asset
        (or the SPA shell, via the frontend container's own headers) goes
        out with no X-Frame-Options at all.
        """
        for path in NGINX_FILES:
            source = strip_comments(path.read_text(encoding="utf-8"))
            for header, body in location_blocks(source):
                if "add_header" not in body:
                    continue  # inherits the server-level headers -- fine
                for name in SECURITY_HEADERS:
                    with self.subTest(config=path.name, location=header, header=name):
                        self.assertRegex(
                            body,
                            rf"add_header\s+{name}\s+[^;]*\balways\b\s*;",
                            f"{path.name}: location '{header}' sets its own add_header "
                            f"and so drops the server-level '{name}'",
                        )

    @staticmethod
    def _location_body(source, header, want="proxy_pass"):
        """Text of the location block whose body mentions ``want``.

        A config can hold several `location /` blocks (the TLS server's plain
        HTTP twin only redirects); picking the one that actually proxies is
        what makes these assertions about the real storefront block.
        """
        start = 0
        fallback = None
        while True:
            index = source.find(header, start)
            if index == -1:
                return fallback
            end = source.find("\n    }", index)
            block = source[index:end if end != -1 else len(source)]
            if want in block:
                return block
            if fallback is None:
                fallback = block
            start = index + len(header)

    def test_storefront_pages_reach_the_backend_catch_all(self):
        """Audit 19 item 5: page requests must reach Django's catch-all.

        While nginx answered every path with the built index.html, an unknown
        URL was a 200 with the 404 design (a soft 404). The catch-all view
        (apps/core/spa.py) is the only layer that knows both the SPA's route
        table and the product/category slugs, so `location /` must proxy the
        backend -- and the build output must still come from the frontend
        container, which is the only place those files exist.
        """
        for path in NGINX_FILES:
            source = strip_comments(path.read_text(encoding="utf-8"))
            block = self._location_body(source, "location / {")
            with self.subTest(config=path.name):
                self.assertIsNotNone(block, f"{path.name}: no `location /`")
                self.assertIn("proxy_pass http://backend_upstream;", block)
                self.assertNotIn("proxy_pass http://frontend_upstream;", block)
            for asset in ("/assets/", "/fonts/", "/brand/"):
                with self.subTest(config=path.name, asset=asset):
                    self.assertRegex(
                        source,
                        r"location \^~ " + asset + r" \{[^}]*frontend_upstream",
                        f"{path.name}: the built bundle/fonts/brand files must be "
                        f"served by the frontend container",
                    )

    def test_product_and_shop_pages_use_the_catch_all_for_humans_too(self):
        for path in NGINX_FILES:
            source = strip_comments(path.read_text(encoding="utf-8"))
            product = self._location_body(source, "location ~ ^/products/")
            if product is None:
                continue  # the HTTP bootstrap config has no crawler routing
            with self.subTest(config=path.name, block="products"):
                # Bot -> /seo/ and human -> catch-all: BOTH end on the backend,
                # so an unknown slug is a real 404 either way.
                self.assertEqual(product.count("proxy_pass http://backend_upstream;"), 2)
                self.assertNotIn("proxy_pass http://frontend_upstream;", product)
            shop = self._location_body(source, "location = /shop/")
            with self.subTest(config=path.name, block="shop"):
                self.assertIn("proxy_pass http://backend_upstream;", shop)
                self.assertNotIn("proxy_pass http://frontend_upstream;", shop)

    def test_seo_routes_reach_the_backend_in_every_config(self):
        """/robots.txt and /sitemap.xml are rendered by Django, not the SPA.

        Without an exact-match location the SPA fallback answers them with
        index.html, so crawlers were served an HTML shell instead of the
        robots policy / the product sitemap.
        """
        for path in NGINX_FILES:
            source = strip_comments(path.read_text(encoding="utf-8"))
            for route in ("/robots.txt", "/sitemap.xml"):
                with self.subTest(config=path.name, route=route):
                    self.assertRegex(
                        source,
                        rf"location\s+=\s+{route}\s*\{{[^}}]*backend_upstream",
                        f"{path.name}: {route} must be proxied to the backend",
                    )
