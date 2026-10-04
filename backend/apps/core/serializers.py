"""Public representation of the singleton SiteSettings (Part 1)."""
from rest_framework import serializers

from .models import SiteSettings


class SiteSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteSettings
        fields = [
            "phone", "whatsapp", "telegram", "instagram",
            "address", "working_hours", "pickup_address", "pickup_hours",
            "enamad_html",
        ]
        read_only_fields = fields
