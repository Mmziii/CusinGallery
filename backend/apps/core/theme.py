"""
Storefront theme: presets, safe color derivation, WCAG contrast guard and
the CSS custom properties the SPA consumes.

Design decisions
----------------
* A preset is a complete, tested palette. Custom overrides are OPTIONAL:
  a blank override inherits the preset value, so the owner can change just
  the primary color without having to re-enter the rest. This is also why
  the owner can always get back to a known-good look with one click.
* Only tokens the storefront actually uses are emitted. The frontend's
  variables.css defines them; the inline block produced here is loaded
  before the first paint by apps/core/spa.py.
* ``contrast_issues`` is the guard the admin form calls on save. It checks
  the three text/background pairs that carry actual information (body text,
  button label, header text) at the WCAG AA threshold of 4.5:1. A palette
  that fails is refused -- "pretty" is never worth unreadable text.
"""
from __future__ import annotations

import re

from django.core.exceptions import ValidationError

from .digits import fa_digits

#: Every preset is a complete palette; the first one is the original brand
#: look, so deploying this feature does not change the site's appearance.
THEME_PRESETS = {
    "olive_gold": {
        "label": "زیتونی و طلایی",
        "primary": "#637037",
        "primary_dark": "#4A5A27",
        "dark": "#2F3A18",
        "accent": "#CEB464",
        "accent_text": "#8A6D1F",
        "background": "#FAF7F0",
        "text": "#1E2412",
        "header_background": "#FFFFFF",
        "header_text": "#1E2412",
        "button_text": "#FFFFFF",
    },
    "cream_brown": {
        "label": "کرم و قهوه‌ای",
        "primary": "#7A4B2A",
        "primary_dark": "#5E3A20",
        "dark": "#4A2F1E",
        "accent": "#C9A227",
        "accent_text": "#8A6A1F",
        "background": "#FBF6EC",
        "text": "#33251A",
        "header_background": "#FBF6EC",
        "header_text": "#33251A",
        "button_text": "#FFFFFF",
    },
    "navy_gold": {
        "label": "سرمه‌ای و طلایی",
        "primary": "#1F3A5F",
        "primary_dark": "#2A4A73",
        "dark": "#14263D",
        "accent": "#C9A227",
        "accent_text": "#8A6A1F",
        "background": "#F7F5EF",
        "text": "#14202E",
        "header_background": "#14263D",
        "header_text": "#F5EFE1",
        "button_text": "#FFFFFF",
    },
    "green_cream": {
        "label": "سبز و کرم",
        "primary": "#2F6B4F",
        "primary_dark": "#3C7A5C",
        "dark": "#24483A",
        "accent": "#B08D3C",
        "accent_text": "#7E6326",
        "background": "#FBF8ED",
        "text": "#1E2A22",
        "header_background": "#FBF8ED",
        "header_text": "#1E2A22",
        "button_text": "#FFFFFF",
    },
}

DEFAULT_PRESET = "olive_gold"

THEME_PRESET_CHOICES = tuple(
    (key, preset["label"]) for key, preset in THEME_PRESETS.items()
)

#: Model field -> palette key for the custom overrides.
OVERRIDE_FIELDS = {
    "theme_primary": "primary",
    "theme_accent": "accent",
    "theme_background": "background",
    "theme_text": "text",
    "theme_header_background": "header_background",
    "theme_header_text": "header_text",
    "theme_button_text": "button_text",
}

COLOR_FIELDS = tuple(OVERRIDE_FIELDS)

BUTTON_RADIUS_CHOICES = (
    ("none", "بدون گردی"),
    ("small", "کم"),
    ("medium", "متوسط"),
    ("large", "زیاد"),
)
BASE_FONT_SIZE_CHOICES = (
    ("small", "کوچک"),
    ("normal", "معمولی"),
    ("large", "بزرگ"),
)
CARD_SHADOW_CHOICES = (
    ("none", "بدون سایه"),
    ("soft", "ملایم"),
)

DEFAULT_BUTTON_RADIUS = "medium"
DEFAULT_BASE_FONT_SIZE = "normal"
DEFAULT_CARD_SHADOW = "soft"

#: WCAG AA for normal-size text.
MIN_CONTRAST = 4.5

_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

_RADII = {
    "none": ("0", "0", "0"),
    "small": ("4px", "8px", "12px"),
    "medium": ("6px", "12px", "22px"),
    "large": ("10px", "20px", "32px"),
}
_SHADOWS = {
    "none": ("none", "none", "none"),
    "soft": (
        "0 1px 3px rgba(30, 36, 18, 0.07)",
        "0 6px 24px rgba(30, 36, 18, 0.10)",
        "0 14px 44px rgba(30, 36, 18, 0.16)",
    ),
}
_FONT_SIZES = {"small": "0.9375rem", "normal": "1rem", "large": "1.125rem"}


# ---------------------------------------------------------------------------
# Color math
# ---------------------------------------------------------------------------
def is_hex_color(value) -> bool:
    return bool(_HEX_RE.match(str(value or "").strip()))


def validate_hex_color(value) -> None:
    """Model/form validation: empty is allowed, anything else must be hex."""
    if value and not is_hex_color(value):
        raise ValidationError("رنگ را به شکل کد شش‌رقمی وارد کنید؛ مثال: #637037.")


def normalize_hex(value, fallback: str = "") -> str:
    """``#abc`` -> ``#aabbcc``; invalid input -> ``fallback``."""
    text = str(value or "").strip()
    if not text:
        return fallback
    if not _HEX_RE.match(text):
        return fallback
    text = text.lower()
    if len(text) == 4:
        text = "#" + "".join(ch * 2 for ch in text[1:])
    return text


def _rgb(color: str) -> tuple[int, int, int]:
    color = normalize_hex(color, "#000000")
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def _hex(rgb) -> str:
    return "#" + "".join(f"{max(0, min(255, round(channel))):02x}" for channel in rgb)


def mix(color_a: str, color_b: str, weight_b: float) -> str:
    """Blend two colors; ``weight_b`` is the share of ``color_b`` (0..1)."""
    a, b = _rgb(color_a), _rgb(color_b)
    return _hex(a[i] * (1 - weight_b) + b[i] * weight_b for i in range(3))


def relative_luminance(color: str) -> float:
    channels = []
    for value in _rgb(color):
        channel = value / 255
        channels.append(channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(foreground: str, background: str) -> float:
    lum_a = relative_luminance(foreground)
    lum_b = relative_luminance(background)
    lighter, darker = max(lum_a, lum_b), min(lum_a, lum_b)
    return (lighter + 0.05) / (darker + 0.05)


def fa_number(value: float, digits: int = 1) -> str:
    """2.31 -> «۲٫۳۱» (Persian decimal separator)."""
    text = f"{value:.{digits}f}".rstrip("0").rstrip(".")
    return fa_digits(text.replace(".", "٫"))


def _text_safe_accent(accent: str, background: str, text_color: str) -> str:
    """Darken/lighten an accent until it can be used as TEXT on the page.

    The gold preset (#CEB464) is decorative by design (1.9:1 on ivory);
    links and small labels use its deeper sibling (#8A6D1F). Custom accent
    colors get the same treatment automatically, so choosing a light gold
    never produces unreadable link text.
    """
    if contrast_ratio(accent, background) >= MIN_CONTRAST:
        return accent
    toward = "#000000" if relative_luminance(background) > 0.4 else "#ffffff"
    candidate = accent
    for step in range(1, 11):
        candidate = mix(accent, toward, step / 10)
        if contrast_ratio(candidate, background) >= MIN_CONTRAST:
            return candidate
    return text_color


def _header_brand_color(header_background: str, header_text: str, primary: str) -> str:
    """The brand name in the header: primary on a light bar, header text on
    a dark one (otherwise it would be dark-on-dark)."""
    return header_text if relative_luminance(header_background) < 0.4 else primary


# ---------------------------------------------------------------------------
# Reading settings -> effective palette
# ---------------------------------------------------------------------------
def _value(source, name: str, default: str = "") -> str:
    if isinstance(source, dict):
        return str(source.get(name) or default)
    return str(getattr(source, name, "") or default)


def _preset_key(source) -> str:
    key = _value(source, "theme_preset", DEFAULT_PRESET)
    return key if key in THEME_PRESETS else DEFAULT_PRESET


def effective_theme(source) -> dict:
    """Resolve preset + overrides into one complete, derived palette.

    ``source`` may be a ``SiteSettings`` instance or a plain dict, which is
    what the admin form uses before anything is saved.
    """
    preset_key = _preset_key(source)
    preset = THEME_PRESETS[preset_key]

    colors = {}
    overridden = set()
    for field, key in OVERRIDE_FIELDS.items():
        raw = normalize_hex(_value(source, field))
        if raw:
            colors[key] = raw
            overridden.add(key)
        else:
            colors[key] = preset[key]

    primary = colors["primary"]
    accent = colors["accent"]
    background = colors["background"]
    text_color = colors["text"]

    primary_dark = preset["primary_dark"]
    if "primary" in overridden:
        primary_dark = mix(primary, "#000000", 0.25)
    dark = preset["dark"]
    if "primary" in overridden:
        dark = mix(primary, "#000000", 0.55)
    accent_text = preset["accent_text"]
    if "accent" in overridden:
        accent_text = _text_safe_accent(accent, background, text_color)

    radius = _value(source, "theme_button_radius", DEFAULT_BUTTON_RADIUS)
    if radius not in _RADII:
        radius = DEFAULT_BUTTON_RADIUS
    font_size = _value(source, "theme_base_font_size", DEFAULT_BASE_FONT_SIZE)
    if font_size not in _FONT_SIZES:
        font_size = DEFAULT_BASE_FONT_SIZE
    shadow = _value(source, "theme_card_shadow", DEFAULT_CARD_SHADOW)
    if shadow not in _SHADOWS:
        shadow = DEFAULT_CARD_SHADOW

    radius_sm, radius_md, radius_lg = _RADII[radius]
    shadow_sm, shadow_md, shadow_lg = _SHADOWS[shadow]

    variables = {
        # Original brand tokens (variables.css aliases most colors to these).
        "--brand-green": primary,
        "--brand-green-mid": primary_dark,
        "--brand-green-dark": dark,
        "--brand-green-tint": mix(primary, "#ffffff", 0.86),
        "--brand-gold": accent,
        "--brand-gold-deep": accent_text,
        "--brand-ivory": background,
        "--brand-ink": text_color,
        # Semantic tokens.
        "--color-primary": primary,
        "--color-primary-dark": primary_dark,
        "--color-accent": accent_text,
        "--color-bg": background,
        "--color-text": text_color,
        "--color-header-bg": colors["header_background"],
        "--color-header-text": colors["header_text"],
        "--color-header-brand": _header_brand_color(
            colors["header_background"], colors["header_text"], primary
        ),
        "--color-header-accent": (
            colors["header_text"]
            if relative_luminance(colors["header_background"]) < 0.4
            else accent_text
        ),
        "--color-button-text": colors["button_text"],
        "--color-border": mix(text_color, background, 0.84),
        # Shape / type / depth.
        "--radius-sm": radius_sm,
        "--radius-md": radius_md,
        "--radius-lg": radius_lg,
        "--shadow-sm": shadow_sm,
        "--shadow-md": shadow_md,
        "--shadow-lg": shadow_lg,
        "--font-size-base": _FONT_SIZES[font_size],
    }

    return {
        "preset": preset_key,
        "preset_label": preset["label"],
        **colors,
        "primary_dark": primary_dark,
        "dark": dark,
        "accent_text": accent_text,
        "button_radius": radius,
        "base_font_size": font_size,
        "card_shadow": shadow,
        "css_variables": variables,
    }


def theme_payload(source) -> dict:
    """The public, read-only theme block of the site content payload."""
    theme = effective_theme(source)
    return {
        "preset": theme["preset"],
        "preset_label": theme["preset_label"],
        "colors": {
            "primary": theme["primary"],
            "accent": theme["accent"],
            "background": theme["background"],
            "text": theme["text"],
            "header_background": theme["header_background"],
            "header_text": theme["header_text"],
            "button_text": theme["button_text"],
        },
        "button_radius": theme["button_radius"],
        "base_font_size": theme["base_font_size"],
        "card_shadow": theme["card_shadow"],
        "css_variables": theme["css_variables"],
    }


# ---------------------------------------------------------------------------
# Contrast guard (admin save)
# ---------------------------------------------------------------------------
PAIR_LABELS = {
    "text_on_background": "متن روی پس‌زمینه",
    "button_text_on_primary": "متن دکمه روی رنگ اصلی",
    "header_text_on_header_background": "متن هدر روی پس‌زمینهٔ هدر",
}


def contrast_issues(source) -> list[dict]:
    """Every WCAG AA pair below 4.5:1, with a ready Persian message."""
    theme = effective_theme(source)
    pairs = (
        ("text_on_background", theme["text"], theme["background"]),
        ("button_text_on_primary", theme["button_text"], theme["primary"]),
        (
            "header_text_on_header_background",
            theme["header_text"],
            theme["header_background"],
        ),
    )
    issues = []
    for key, foreground, background in pairs:
        ratio = contrast_ratio(foreground, background)
        if ratio < MIN_CONTRAST:
            label = PAIR_LABELS[key]
            issues.append(
                {
                    "key": key,
                    "label": label,
                    "foreground": foreground,
                    "background": background,
                    "ratio": ratio,
                    "message": (
                        f"کنتراست «{label}» فقط {fa_number(ratio, 2)} به ۱ است؛ "
                        f"حداقل ۴٫۵ به ۱ لازم است. رنگ متن یا پس‌زمینه را تغییر دهید."
                    ),
                }
            )
    return issues


def theme_defaults() -> dict:
    """The model values that restore the original brand look."""
    preset = THEME_PRESETS[DEFAULT_PRESET]
    values = {field: "" for field in OVERRIDE_FIELDS}
    values.update(
        {
            "theme_preset": DEFAULT_PRESET,
            "theme_button_radius": DEFAULT_BUTTON_RADIUS,
            "theme_base_font_size": DEFAULT_BASE_FONT_SIZE,
            "theme_card_shadow": DEFAULT_CARD_SHADOW,
        }
    )
    # Keep the preset's own colors reachable for the admin live preview.
    values["_preset_colors"] = {
        key: preset[key]
        for key in ("primary", "accent", "background", "text",
                    "header_background", "header_text", "button_text")
    }
    return values
