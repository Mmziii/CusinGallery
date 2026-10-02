# Core exposes only abstract base models (see models.py), so there is
# nothing concrete to register with the admin site from this app itself.
#
# This module IS imported by Django's admin autodiscovery (core is an
# installed app), which makes it the single reliable place to brand the
# admin site for the Persian-speaking shop owner (Phase B).
from django.contrib import admin

admin.site.site_header = "مدیریت کوزین گالری"
admin.site.site_title = "کوزین گالری"
admin.site.index_title = "داشبورد مدیریت فروشگاه"
