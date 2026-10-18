"""Public category subtree traversal, independent of URL/slug conventions."""
from collections import defaultdict

from .models import Category


def category_subtree_ids(slug):
    """The selected active category and every active descendant, one query.

    Cycle guards also tolerate historical/imported rows that bypassed clean().
    Inactive nodes are not traversed because they do not exist in the public
    category tree; the unfiltered product catalog keeps its own active rule.
    """
    rows = list(Category.objects.filter(is_active=True).values_list("id", "parent_id", "slug"))
    root_id = next((pk for pk, _, row_slug in rows if row_slug.casefold() == slug.casefold()), None)
    if root_id is None:
        return []
    children = defaultdict(list)
    for pk, parent_id, _ in rows:
        children[parent_id].append(pk)
    seen = set()
    pending = [root_id]
    while pending:
        pk = pending.pop()
        if pk in seen:
            continue
        seen.add(pk)
        pending.extend(children[pk])
    return list(seen)
