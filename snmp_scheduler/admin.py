# snmp_scheduler/admin.py
from django.contrib import admin
from django.urls import path, reverse
from django.http import HttpResponseRedirect
from django.db import models
from django.db.models import Q, Case, When, Value, FloatField, F
from django.db.models.functions import Replace, Cast
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.aggregates import ArrayAgg
from .models import TareaSNMP, EjecucionTareaSNMP, OnuDato
from .tasks.handlers import TASK_HANDLERS
from .tasks.delete import delete_history_records

class EjecucionTareaSNMPInline(admin.TabularInline):
    model = EjecucionTareaSNMP
    extra = 0
    readonly_fields = ('inicio', 'fin', 'estado', 'resultado', 'error')
    can_delete = False

@admin.register(TareaSNMP)
class TareaSNMPAdmin(admin.ModelAdmin):
    save_on_top = True
    inlines = [EjecucionTareaSNMPInline]
    fields = ['nombre', 'host_name', 'host_ip', 'comunidad', 'tipo', 'intervalo', 'modo', 'activa']
    list_display = [
        'nombre',
        'host_ip',
        'tipo',
        'intervalo',
        'modo',
        'activa',
        'ultima_ejecucion',
        'ejecuciones_recientes',
        'estado_actual',
    ]
    list_filter = ('tipo', 'intervalo', 'modo', 'activa')
    search_fields = ('nombre', 'host_ip')
    actions = ['ejecutar_ahora', 'activar_tareas', 'desactivar_tareas']
    change_form_template = "admin/snmp_scheduler/tareasnmp/change_form.html"

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                '<path:object_id>/ejecutar/',
                self.admin_site.admin_view(self.ejecutar_tarea),
                name='snmp_scheduler_tareasnmp_ejecutar'
            ),
        ]
        return custom + urls

    def ejecutar_tarea(self, request, object_id):
        tarea = TareaSNMP.objects.get(pk=object_id)
        handler = TASK_HANDLERS.get(tarea.tipo)
        if not handler:
            self.message_user(request, f"⚠️ Tipo de tarea desconocido: {tarea.tipo}", level='warning')
        else:
            handler.apply_async(args=[object_id])
            self.message_user(request, "✅ Tarea enviada a la cola de ejecución")
        return HttpResponseRedirect(
            reverse('admin:snmp_scheduler_tareasnmp_change', args=[object_id])
        )

    def ejecutar_ahora(self, request, queryset):
        for tarea in queryset:
            handler = TASK_HANDLERS.get(tarea.tipo)
            if handler:
                handler.apply_async(args=[tarea.id])
        self.message_user(request, f"🚀 {queryset.count()} tareas encoladas")
    ejecutar_ahora.short_description = "Ejecutar selección ahora"

    def activar_tareas(self, request, queryset):
        count = queryset.update(activa=True)
        self.message_user(request, f"✅ {count} tareas activadas")
    activar_tareas.short_description = "Activar tareas seleccionadas"

    def desactivar_tareas(self, request, queryset):
        count = queryset.update(activa=False)
        self.message_user(request, f"⏸️ {count} tareas desactivadas")
    desactivar_tareas.short_description = "Desactivar tareas seleccionadas"

    def estado_actual(self, obj):
        última = obj.ejecuciones.first()
        return última.estado if última else '--'
    estado_actual.short_description = 'Último Estado'

    def ejecuciones_recientes(self, obj):
        return obj.ejecuciones.order_by('-inicio')[:5].count()
    ejecuciones_recientes.short_description = 'Ejec. Recientes (24h)'

@admin.register(EjecucionTareaSNMP)
class EjecucionTareaSNMPAdmin(admin.ModelAdmin):
    list_display = (
        'nombre_tarea',  # 👈 Nueva columna
        'host_ip', 
        'tipo_tarea', 
        'inicio', 
        'fin', 
        'estado', 
        'duracion'
    )
    list_filter = ('estado', 'tarea__host_name', 'tarea__tipo')  # Filtro por tipo
    search_fields = ('tarea__nombre', 'error', 'tarea__host_ip')  # Búsqueda por IP
    
    # Nuevos campos personalizados
    def nombre_tarea(self, obj):
        return obj.tarea.nombre  # Nombre de la tarea
    nombre_tarea.short_description = "Tarea"

    def host_ip(self, obj):
        return obj.tarea.host_ip  # IP del OLT
    host_ip.short_description = "IP OLT"

    def tipo_tarea(self, obj):
        return obj.tarea.get_tipo_display()  # Tipo legible (ej. "Descripción ONU")
    tipo_tarea.short_description = "Tipo"

    readonly_fields = ('tarea', 'inicio', 'fin', 'estado', 'resultado', 'error')
    actions = ['borrar_seleccion_async']
    def __str__(self):
        return f"{self.tarea.nombre} ({self.inicio:%Y-%m-%d %H:%M:%S})"  # Nombre + fecha
    def duracion(self, obj):
        return obj.fin - obj.inicio if obj.fin else 'En curso'
    duracion.short_description = 'Duración'

    def borrar_seleccion_async(self, request, queryset):
        ids = list(queryset.values_list('pk', flat=True))
        delete_history_records.delay(ids)
        self.message_user(
            request,
            f"🗑️ {len(ids)} registros programados para borrado en segundo plano"
        )
    borrar_seleccion_async.short_description = "Borrar historial seleccionado (Async)"

@admin.register(OnuDato)
class OnuDatoAdmin(admin.ModelAdmin):
    list_display = [
        'host',
        'slotportonu',
        'onulogico',
        'onudesc',
        'act_susp',
        'modelo_onu',
        'distancia_m'
    ]
    
    list_filter = [
        'host',
        ('modelo_onu', admin.AllValuesFieldListFilter),
    ]
    
    search_fields = ['host', 'slotportonu', 'onudesc', 'modelo_onu']
    list_select_related = True
    list_per_page = 50
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.exclude(host__in=['scripts', 'Host'])
    
    def get_list_filter(self, request):
        class DistanceRangeFilter(admin.SimpleListFilter):
            title = 'Rango de Distancia'
            parameter_name = 'distance_range'
            
            def lookups(self, request, model_admin):
                return (
                    ('0-5', '0 - 5 km'),
                    ('5-10', '5 - 10 km'),
                    ('10-15', '10 - 15 km'),
                    ('15+', 'Más de 15 km'),
                    ('no-distance', 'Sin Distancia'),
                )
            
            def queryset(self, request, queryset):
                if not self.value():
                    return queryset

                if self.value() == 'no-distance':
                    return queryset.filter(
                        Q(distancia_m__in=['No Distancia', 'Error formato', '']) |
                        Q(distancia_m__isnull=True)
                    )

                # Filtrar registros válidos y convertir a número
                valid_records = queryset.exclude(
                    Q(distancia_m__in=['No Distancia', 'Error formato', '']) |
                    Q(distancia_m__isnull=True)
                ).annotate(
                    clean_distance=Cast(
                        Replace(
                            Replace(
                                Replace('distancia_m', Value(' km'), Value('')),
                                Value(','), Value('.')
                            ),
                            Value(' '), Value('')
                        ),
                        FloatField()
                    )
                )
                
                if self.value() == '0-5':
                    return valid_records.filter(clean_distance__gte=0, clean_distance__lt=5)
                elif self.value() == '5-10':
                    return valid_records.filter(clean_distance__gte=5, clean_distance__lt=10)
                elif self.value() == '10-15':
                    return valid_records.filter(clean_distance__gte=10, clean_distance__lt=15)
                elif self.value() == '15+':
                    return valid_records.filter(clean_distance__gte=15)
                
                return queryset
        
        return [
            'host',
            ('modelo_onu', admin.AllValuesFieldListFilter),
            DistanceRangeFilter,
        ]

    class Meta:
        indexes = [
            models.Index(fields=['host', 'modelo_onu']),
            models.Index(fields=['distancia_m']),
        ]