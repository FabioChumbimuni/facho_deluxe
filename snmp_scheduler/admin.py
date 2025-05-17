# snmp_scheduler/admin.py (Versión Final Funcional)
from django.contrib import admin
from django.urls import path
from django.http import HttpResponseRedirect
from django.urls import reverse
from .models import TareaSNMP, EjecucionTareaSNMP
from .tasks.handlers import TASK_HANDLERS
from .tasks import ejecutar_descubrimiento, ejecutar_tarea_snmp
from .tasks.delete import delete_history_records

# ==============================================
# INLINE PARA EJECUCIONES EN TAREA (CORREGIDO)
# ==============================================
class EjecucionTareaSNMPInline(admin.TabularInline):  # Nombre corregido
    model = EjecucionTareaSNMP
    extra = 0
    readonly_fields = ('inicio', 'fin', 'estado', 'resultado', 'error')
    can_delete = False

# ==============================================
# ADMIN PARA TAREAS SNMP (CORREGIDO)
# ==============================================
@admin.register(TareaSNMP)
class TareaSNMPAdmin(admin.ModelAdmin):
    inlines = [EjecucionTareaSNMPInline]  # Usa el inline corregido
    fields = ['nombre', 'host_name', 'host_ip', 'comunidad', 'tipo', 'intervalo', 'modo', 'activa']
    list_display = [
        'nombre',
        'host_ip',
        'tipo',
        'intervalo',      # ← agregamos Intervalo
        'modo',           # ← agregamos Modo
        'activa',
        'ultima_ejecucion',
        'ejecuciones_recientes',
        'estado_actual',
    ]
    list_filter = (
        'tipo',
        'intervalo',      # ← para filtrar por intervalo
        'modo',           # ← para filtrar por modo
        'activa'
    )
    search_fields = ('nombre', 'host_ip')
    actions = ['ejecutar_ahora']
    change_form_template = "admin/snmp_scheduler/tareasnmp/change_form.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<path:object_id>/ejecutar/',
                self.admin_site.admin_view(self.ejecutar_tarea),
                name='ejecutar_tarea'
            ),
        ]
        return custom_urls + urls

    def ejecutar_tarea(self, request, object_id):
        ejecutar_descubrimiento.apply_async(
            args=[object_id],
            queue='secundario'  # Asegurar que coincida con la cola configurada
        )
        self.message_user(request, "Tarea enviada a la cola de ejecución")
        return HttpResponseRedirect(
            reverse('admin:snmp_scheduler_tareasnmp_change', args=[object_id]))

    def ejecutar_ahora(self, request, queryset):
        for tarea in queryset:
            ejecutar_tarea_snmp.apply_async(args=[tarea.id])
        self.message_user(request, f"🚀 {queryset.count()} tareas encoladas")
    ejecutar_ahora.short_description = "Ejecutar selección ahora"

    def estado_actual(self, obj):
        ultima = obj.ejecuciones.first()
        return ultima.estado if ultima else '--'
    estado_actual.short_description = 'Último Estado'
    
    def ejecuciones_recientes(self, obj):
        return obj.ejecuciones.order_by('-inicio')[:5].count()
    ejecuciones_recientes.short_description = 'Ejec. Recientes (24h)'

# ==============================================
# ADMIN PARA HISTORIAL (VERSIÓN CORREGIDA)
# ==============================================
@admin.register(EjecucionTareaSNMP)
class EjecucionTareaSNMPAdmin(admin.ModelAdmin):
    list_display = ('tarea', 'inicio', 'fin', 'estado', 'duracion')
    list_filter = ('estado', 'tarea__host_ip')
    search_fields = ('tarea__nombre', 'error')
    readonly_fields = ('tarea', 'inicio', 'fin', 'estado', 'resultado', 'error')
    actions = ['borrar_seleccion_async']
    def duracion(self, obj):
        return obj.fin - obj.inicio if obj.fin else 'En curso'
    duracion.short_description = 'Duración'

    def borrar_seleccion_async(self, request, queryset):
            """Encola el borrado en background sin bloquear el Admin."""
            ids = list(queryset.values_list('pk', flat=True))
            delete_history_records.delay(ids)
            self.message_user(
                request,
                f"🗑️ {len(ids)} registros programados para borrado en segundo plano"
            )
    borrar_seleccion_async.short_description = "Borrar historial seleccionado (Async)"



    