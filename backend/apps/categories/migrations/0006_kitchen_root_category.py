"""Data migration: introduce the root category «آشپزخانه».

Every category that is currently top-level becomes a child of it, so
there is exactly ONE catalog root while the existing groups keep their
names, slugs, URLs, products and display order untouched -- only the
``parent`` of the former roots changes.

The preferred root slug is ``kitchen``. If that slug is already assigned
to any category (including a non-root), a free ``kitchen-root`` slug is
used instead. The migration is idempotent when the named root already
exists with either slug family. Reversible: groups move back to the top
level and the root is removed (or deactivated if it has direct products
or children).
"""
from django.db import migrations

KITCHEN_SLUG = "kitchen"
KITCHEN_FALLBACK_SLUG = "kitchen-root"
KITCHEN_NAME = "آشپزخانه"


def _is_kitchen_root_slug(slug):
    if slug in (KITCHEN_SLUG, KITCHEN_FALLBACK_SLUG):
        return True
    prefix = f"{KITCHEN_FALLBACK_SLUG}-"
    suffix = slug[len(prefix):] if slug.startswith(prefix) else ""
    return bool(suffix) and suffix.isascii() and suffix.isdigit()


def _named_kitchen_root(Category):
    roots = Category.objects.filter(name=KITCHEN_NAME, parent__isnull=True)
    return next((root for root in roots if _is_kitchen_root_slug(root.slug)), None)


def _next_kitchen_slug(Category):
    if not Category.objects.filter(slug=KITCHEN_SLUG).exists():
        return KITCHEN_SLUG

    candidate = KITCHEN_FALLBACK_SLUG
    suffix = 1
    while Category.objects.filter(slug=candidate).exists():
        candidate = f"{KITCHEN_FALLBACK_SLUG}-{suffix}"
        suffix += 1
    return candidate


def forward(apps, schema_editor):
    Category = apps.get_model("categories", "Category")
    if _named_kitchen_root(Category) is not None:
        return

    kitchen = Category.objects.create(
        name=KITCHEN_NAME,
        slug=_next_kitchen_slug(Category),
        is_active=True,
        ordering=0,
    )
    # Reparent every CURRENT top-level category under the new root.
    # Products are untouched: their FK points at the (unchanged) leaf
    # categories, and slugs -- hence every category URL -- stay as-is.
    Category.objects.filter(parent__isnull=True).exclude(pk=kitchen.pk).update(
        parent=kitchen
    )


def backward(apps, schema_editor):
    Category = apps.get_model("categories", "Category")
    kitchen = Category.objects.filter(
        slug=KITCHEN_SLUG, parent__isnull=True
    ).first()
    if kitchen is None:
        kitchen = _named_kitchen_root(Category)
    if kitchen is None:
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
