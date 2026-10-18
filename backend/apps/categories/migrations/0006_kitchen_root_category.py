"""Data migration: introduce the root category «آشپزخانه» (slug ``kitchen``).

Every category that is currently top-level becomes a child of it, so
the storefront gains exactly ONE catalog root (breadcrumbs, the header
mega menu, home category tiles) while the existing groups keep their
names, slugs, URLs, products and display order untouched -- only the
``parent`` of the former roots changes.

Idempotent by construction: if a root with slug ``kitchen`` already
exists the migration does nothing, so re-running it (or running it on
a database that already has the root) is a no-op. Reversible: the
groups are moved back to the top level and the root is removed (or,
only if somebody somehow attached products/children to it directly,
deactivated instead of deleted -- deleting would either cascade to
those products or violate the PROTECT on children).
"""
from django.db import migrations

KITCHEN_SLUG = "kitchen"
KITCHEN_NAME = "آشپزخانه"


def forward(apps, schema_editor):
    Category = apps.get_model("categories", "Category")
    if Category.objects.filter(slug=KITCHEN_SLUG, parent__isnull=True).exists():
        # Already migrated (or a pre-existing root with that slug):
        # nothing to do -- running twice must change nothing.
        return
    kitchen = Category.objects.create(
        name=KITCHEN_NAME, slug=KITCHEN_SLUG, is_active=True, ordering=0
    )
    # Reparent every CURRENT top-level category under the new root.
    # Products are untouched: their FK points at the (unchanged) leaf
    # categories, and slugs -- hence every category URL -- stay as-is.
    Category.objects.filter(parent__isnull=True).exclude(pk=kitchen.pk).update(
        parent=kitchen
    )


def backward(apps, schema_editor):
    Category = apps.get_model("categories", "Category")
    try:
        kitchen = Category.objects.get(slug=KITCHEN_SLUG, parent__isnull=True)
    except Category.DoesNotExist:
        return
    # Undo the reparenting: the main groups go back to the top level.
    Category.objects.filter(parent=kitchen).update(parent=None)
    if kitchen.products.exists() or kitchen.children.exists():
        # Something was attached directly to the root after the
        # migration ran -- keep the row (inactive) rather than
        # cascade-delete products or PROTECT-violate on children.
        kitchen.is_active = False
        kitchen.save(update_fields=["is_active"])
        return
    kitchen.delete()


class Migration(migrations.Migration):
    dependencies = [("categories", "0005_alter_category_slug")]
    operations = [migrations.RunPython(forward, backward)]
