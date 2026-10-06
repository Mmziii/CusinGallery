"""Seed the singleton SiteSettings row with clearly-placeholder business
content (Part 1). The owner replaces it from the admin UI; the values
here are marked as samples so nobody mistakes them for real data."""
from django.db import migrations


def seed(apps, schema_editor):
    SiteSettings = apps.get_model("core", "SiteSettings")
    SiteSettings.objects.get_or_create(
        pk=1,
        defaults={
            "phone": "+98 21 0000 0000",
            "whatsapp": "",
            "telegram": "",
            "instagram": "",
            "address": "[نشانی واقعی فروشگاه را از پنل مدیریت وارد کنید]",
            "working_hours": "[ساعات پاسخگویی را از پنل مدیریت وارد کنید]",
            "pickup_address": "[نشانی دریافت حضوری را از پنل مدیریت وارد کنید]",
            "pickup_hours": "[ساعات دریافت حضوری را از پنل مدیریت وارد کنید]",
            "enamad_html": "",
        },
    )


def unseed(apps, schema_editor):
    SiteSettings = apps.get_model("core", "SiteSettings")
    SiteSettings.objects.filter(pk=1).delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]
    operations = [migrations.RunPython(seed, unseed)]
