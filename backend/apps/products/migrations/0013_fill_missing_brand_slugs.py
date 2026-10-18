"""Fill legacy empty slugs without changing any published brand URL.

The unique, allow_unicode slug field already exists. Keep this migration's
algorithm self-contained so future model changes cannot alter its outcome.
"""
from django.db import migrations
from django.utils.text import slugify


def fill_missing_brand_slugs(apps, schema_editor):
    Brand = apps.get_model("products", "Brand")
    brands = Brand.objects.using(schema_editor.connection.alias)
    max_length = Brand._meta.get_field("slug").max_length
    for brand in brands.order_by("pk").iterator():
        if brand.slug and brand.slug.strip():
            continue
        base = slugify(brand.name, allow_unicode=True)[:max_length] or "brand"
        candidate = base
        suffix = 2
        while brands.exclude(pk=brand.pk).filter(slug=candidate).exists():
            tail = f"-{suffix}"
            candidate = f"{base[:max_length - len(tail)]}{tail}"
            suffix += 1
        brands.filter(pk=brand.pk).update(slug=candidate)


class Migration(migrations.Migration):
    dependencies = [("products", "0012_compact_featured_label")]
    operations = [migrations.RunPython(fill_missing_brand_slugs, migrations.RunPython.noop)]
