"""Public representation of the singleton SiteSettings (Part 1)."""
from rest_framework import serializers

from .models import SiteSettings
from .placeholders import clean_value
from .sanitize import sanitize_embed


class NullToBlankTextMixin:
    """
    Part S3 item 11 -- the site-wide safety net for the address-form bug
    class: clients (React controlled inputs, curl, proxies) sometimes send
    ``null`` for an OPTIONAL text field, and DRF answers a plain
    CharField(blank-able, not null-able) with "may not be null" -- an
    opaque 400 for what is really "the field was left empty".

    Every model text field in this codebase is ``blank=True, null=False``
    (empty string, never NULL), so the consistent behaviour is to coerce
    ``None -> ""`` for every declared CharField-based field that does not
    explicitly opt into ``allow_null``. Required-field and format
    validation then runs against the empty string exactly as if the client
    had sent "" -- same rules, same Persian messages, no more null 400s.

    Usage: ``class FooSerializer(NullToBlankTextMixin, serializers.Serializer)``
    (mixin FIRST). Deliberately only touches top-level declared fields
    with their own key in the payload -- nested serializers and ``source``
    remaps are untouched.
    """

    def to_internal_value(self, data):
        if isinstance(data, dict):
            coerced = None
            fields = self.get_fields()
            for name, field in fields.items():
                if name in data and data[name] is None:
                    if isinstance(field, serializers.CharField) and not getattr(
                        field, "allow_null", False
                    ):
                        if coerced is None:
                            coerced = data.copy()
                        coerced[name] = ""
            if coerced is not None:
                data = coerced
        return super().to_internal_value(data)


class SiteSettingsSerializer(serializers.ModelSerializer):
    """Public contact/branding payload.

    Every field passes through ``placeholders.clean_value``: the seeded
    «+98 21 0000 0000» and the bracketed «[… را از پنل مدیریت وارد کنید]»
    sentences are INSTRUCTIONS, not content, and used to be rendered
    verbatim on the storefront. A storefront that receives "" shows its
    own empty state instead of lying to customers.
    """

    class Meta:
        model = SiteSettings
        fields = [
            "phone", "whatsapp", "telegram", "instagram",
            "address", "working_hours", "pickup_address", "pickup_hours",
            "enamad_html", "email", "eitaa", "bale",
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        for name in self.Meta.fields:
            if name == "enamad_html":
                # Trust-seal embed from the e-namad panel. The admin form
                # sanitises it on save; this second pass protects rows
                # written by a migration/management command from ever
                # reaching the storefront with a <script> intact.
                data[name] = sanitize_embed(data.get(name) or "")
                continue
            data[name] = clean_value(data.get(name))
        return data
