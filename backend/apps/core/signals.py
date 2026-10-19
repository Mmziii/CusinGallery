"""Invalidate the cached public site payload whenever its source changes.

Deliberately signal-based rather than scattered ``cache.delete`` calls in
each admin: the public API, the inlined theme variables in the SPA shell and
the info-page endpoint all read the same cache entries, and EVERY write path
(admin form, inline trust items, management command, shell) must invalidate
them. ``post_delete`` matters as much as ``post_save`` -- deleting an info
page has to turn its URL into a 404 immediately.
"""
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .content import invalidate_site_cache
from .models import InfoPage, SiteSettings, TrustStripItem


@receiver([post_save, post_delete], sender=SiteSettings, dispatch_uid="core:site-settings-cache")
def _site_settings_changed(sender, **kwargs):
    invalidate_site_cache()


@receiver([post_save, post_delete], sender=TrustStripItem, dispatch_uid="core:trust-strip-cache")
def _trust_item_changed(sender, **kwargs):
    invalidate_site_cache()


@receiver([post_save, post_delete], sender=InfoPage, dispatch_uid="core:info-page-cache")
def _info_page_changed(sender, **kwargs):
    invalidate_site_cache()
