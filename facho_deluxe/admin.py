from django.contrib import admin
from django.conf import settings

print("Cargando configuración personalizada del admin...")  # Mensaje de depuración

# Customize admin site
admin.site.site_header = settings.ADMIN_SITE_HEADER
admin.site.site_title = settings.ADMIN_SITE_TITLE
admin.site.index_title = settings.ADMIN_INDEX_TITLE 