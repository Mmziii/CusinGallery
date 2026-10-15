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
