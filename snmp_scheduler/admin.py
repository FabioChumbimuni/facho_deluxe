# snmp_scheduler/admin.py (Versión Corregida)
from django.contrib import admin
from django.urls import path
from django.http import HttpResponseRedirect
from django.urls import reverse
from .models import TareaSNMP, EjecucionTareaSNMP 
from .tasks import ejecutar_descubrimiento

# admin.py
class EjecucionTareaSNMPInline(admin.TabularInline):
    model = EjecucionTareaSNMP
    extra = 0
    readonly_fields = ('inicio', 'fin', 'estado', 'resultado', 'error')
    can_delete = False


@admin.register(TareaSNMP)
class TareaSNMPAdmin(admin.ModelAdmin):
    inlines = [EjecucionTareaSNMPInline]
    # 1. Primero definir el método ejecutar_tarea
    def ejecutar_tarea(self, request, object_id):
        ejecutar_descubrimiento.delay(object_id)
        self.message_user(request, "Tarea enviada a la cola de ejecución")
        return HttpResponseRedirect(
            reverse('admin:snmp_scheduler_tareasnmp_change', args=[object_id]))
    
    # 2. Luego definir get_urls que lo usa
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<path:object_id>/ejecutar/',
                self.admin_site.admin_view(self.ejecutar_tarea),
                name='snmp_scheduler_tareasnmp_ejecutar_tarea'  # Nombre único completo
            ),
        ]
        return custom_urls + urls
    
    # 3. Resto de la configuración
    actions = ['ejecutar_ahora']
    fields = ['nombre', 'host_name', 'host_ip', 'comunidad', 'tipo', 'intervalo', 'modo', 'activa']
    list_display = ['nombre', 'host_ip', 'tipo', 'intervalo', 'activa']

    def ejecutar_ahora(self, request, queryset):
        for tarea in queryset:
            ejecutar_descubrimiento.delay(tarea.id)
        self.message_user(request, f"{queryset.count()} tareas encoladas")
    ejecutar_ahora.short_description = "🗸 Ejecutar selección ahora"

    # Cambiar la línea del template
    change_form_template = "admin/snmp_scheduler/tareasnmp/change_form.html"
