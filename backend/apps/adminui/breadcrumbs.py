"""The admin breadcrumb trail (issue #6).

Django's own admin templates each render their own trail:

    خانه › «سفارش‌ها» (the APP) › «سفارش‌ها» (the MODEL plural) › CG-…

For a single-model app -- orders, products, banners -- the app is named
after the very model it contains, so the trail repeats itself:

    شروع › سفارش‌ها › سفارش‌ها › CG-20261015-75CED575

The theme therefore renders the trail itself (see
``templates/admin/base.html``) from the request and the page's context,
and drops the app crumb when it would simply repeat the model crumb.

Because the theme's ``base.html`` no longer declares a ``breadcrumbs``
block, the blocks that Django's change_form / change_list /
delete_confirmation / object_history / delete_selected_confirmation
templates define have nothing to override and are simply not rendered --
one trail, built here, on every page.
"""
from __future__ import annotations

from django.urls import NoReverseMatch, reverse
from django.utils.text import Truncator, capfirst

#: The words Django uses for the last crumb of the non-model pages.
DELETE_MANY_LABEL = "حذف موارد انتخاب‌شده"
HISTORY_LABEL = "تاریخچه"
DELETE_LABEL = "حذف"
HOME_LABEL = "شروع"


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def _same(left: str, right: str) -> bool:
    """Compare two labels the way an owner reads them.

    «سفارش‌ها» is written with a ZWNJ and a Persian plural suffix; a
    straight ``==`` misses on spacing and on the invisible joiner, so both
    sides are normalised before comparing.
    """
    normalised = []
    for value in (left, right):
        value = _text(value)
        for invisible in ("\u200c", "\u200d", "\u00a0"):
            value = value.replace(invisible, "")
        normalised.append(" ".join(value.split()).casefold())
    return normalised[0] == normalised[1]


def _url(name, *args, **kwargs) -> str:
    try:
        return reverse(name, args=args, kwargs=kwargs)
    except NoReverseMatch:
        return ""


def _truncated(obj) -> str:
    return Truncator(str(obj)).words(18, truncate=" …")


def _object_from(context):
    """The row the page is about, however the view named it."""
    return context.get("original") or context.get("object")


def _model_options(context):
    """``Model._meta``: ``opts`` on object pages, ``cl.opts`` on lists."""
    opts = context.get("opts")
    if opts is not None:
        return opts
    changelist = context.get("cl")
    return getattr(changelist, "opts", None)


def build_crumbs(context) -> list[dict]:
    """[{label, url}] -- the whole trail, from «شروع» to the current page.

    Pure function over the template context, so it can be tested without
    rendering a page.
    """
    request = context.get("request")
    trail = [{"label": HOME_LABEL, "url": _url("admin:index")}]

    opts = _model_options(context)
    if opts is None:
        # A page that is not about a model (the dashboard, a custom admin
        # view, the image importer): the page's own title is the trail.
        title = _text(context.get("title"))
        if title:
            trail.append({"label": title, "url": ""})
        return trail

    app_name = _text(getattr(opts.app_config, "verbose_name", "")) or opts.app_label
    model_name = capfirst(opts.verbose_name_plural)
    url_name = ""
    resolver = getattr(request, "resolver_match", None) if request else None
    if resolver is not None:
        url_name = resolver.url_name or ""

    # The duplicate: an app named after its own single model. One crumb
    # says it, and the changelist below it is the useful one.
    if not _same(app_name, model_name):
        trail.append(
            {
                "label": app_name,
                "url": _url("admin:app_list", app_label=opts.app_label),
            }
        )

    on_changelist = url_name.endswith("_changelist")
    trail.append(
        {
            "label": model_name,
            "url": ""
            if on_changelist
            else _url(f"admin:{opts.app_label}_{opts.model_name}_changelist"),
        }
    )

    trail.extend(_leaf_crumbs(context, opts, url_name, on_changelist))
    return trail


def _leaf_crumbs(context, opts, url_name, on_changelist=False) -> list[dict]:
    """Whatever comes after the model: the row, and the action on it."""
    obj = _object_from(context)

    if on_changelist:
        # The list is the last crumb -- Django ends the trail there too.
        # The one exception is the "delete the selected rows"
        # confirmation, which the changelist view renders instead.
        if context.get("deleted_objects") is not None:
            return [{"label": DELETE_MANY_LABEL, "url": ""}]
        return []

    def change_url():
        pk = getattr(obj, "pk", None)
        if pk is None:
            return ""
        return _url(
            f"admin:{opts.app_label}_{opts.model_name}_change", pk
        )

    if context.get("add") or url_name.endswith("_add"):
        return [{"label": f"افزودن {opts.verbose_name}", "url": ""}]

    if url_name.endswith("_history"):
        crumbs = []
        if obj is not None:
            crumbs.append({"label": _truncated(obj), "url": change_url()})
        crumbs.append({"label": HISTORY_LABEL, "url": ""})
        return crumbs

    if url_name.endswith("_delete"):
        crumbs = []
        if obj is not None:
            crumbs.append({"label": _truncated(obj), "url": change_url()})
        crumbs.append({"label": DELETE_LABEL, "url": ""})
        return crumbs

    if obj is not None:
        return [{"label": _truncated(obj), "url": ""}]

    # Anything else (a custom view registered on this model's admin): the
    # page's own title, so the owner is never left without a trail.
    title = _text(context.get("title"))
    return [{"label": title, "url": ""}] if title else []
