# snmp_scheduler/admin.py
from django.contrib import admin
from django.urls import path, reverse
from django.http import HttpResponseRedirect
from django.db import models
from django.db.models import Q, Case, When, Value, FloatField, F
from django.db.models.functions import Replace, Cast
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.aggregates import ArrayAgg
from django.template.response import TemplateResponse
from django.utils import timezone
from django.utils.timezone import localtime
from .models import TareaSNMP, EjecucionTareaSNMP, OnuDato, Host
from .tasks.handlers import TASK_HANDLERS
from .tasks.delete import delete_history_records
from datetime import timedelta

# Modelo proxy para el Supervisor
class Supervisor(TareaSNMP):
    class Meta:
        proxy = True
        verbose_name = 'Supervisor'
        verbose_name_plural = 'Supervisor'
        app_label = 'snmp_scheduler'

class EjecucionTareaSNMPInline(admin.TabularInline):
    model = EjecucionTareaSNMP
    extra = 0
    readonly_fields = ('inicio', 'fin', 'estado', 'resultado', 'error')
    can_delete = False

@admin.register(TareaSNMP)
class TareaSNMPAdmin(admin.ModelAdmin):
    save_on_top = True
    inlines = [EjecucionTareaSNMPInline]
    fields = ['nombre', 'host', 'tipo', 'modo', 'intervalo', 'activa']
    list_display = [
        'nombre',
        'host',
        'tipo',
        'modo',
        'intervalo',
        'activa',
        'ultima_ejecucion',
        'estado_actual',
    ]
    list_filter = ('tipo', 'modo', 'intervalo', 'activa')
    search_fields = ('nombre', 'host__nombre', 'host__ip')
    actions = ['ejecutar_ahora', 'activar_tareas', 'desactivar_tareas', 'cambiar_intervalo_00', 'cambiar_intervalo_15', 'cambiar_intervalo_30', 'cambiar_intervalo_45']

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path('ejecutar/<int:tarea_id>/',
                self.admin_site.admin_view(self.ejecutar_tarea),
                name='%s_%s_ejecutar' % (self.model._meta.app_label, self.model._meta.model_name)),
        ]
        return my_urls + urls

    def ejecutar_tarea(self, request, tarea_id):
        try:
            tarea = TareaSNMP.objects.get(pk=tarea_id)
            handler = TASK_HANDLERS.get(tarea.tipo)
            if handler:
                handler.apply_async(args=[tarea_id])
                self.message_user(request, f"✅ Tarea {tarea.nombre} enviada a la cola de ejecución")
            else:
                self.message_user(request, f"⚠️ Tipo de tarea desconocido: {tarea.tipo}", level='warning')
        except TareaSNMP.DoesNotExist:
            self.message_user(request, f"❌ La tarea con ID {tarea_id} no existe", level='error')
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '../'))

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

    def cambiar_intervalo_00(self, request, queryset):
        count = queryset.update(intervalo='00')
        self.message_user(request, f"✅ {count} tareas cambiadas al intervalo 00")
    cambiar_intervalo_00.short_description = "Cambiar a intervalo 00"

    def cambiar_intervalo_15(self, request, queryset):
        count = queryset.update(intervalo='15')
        self.message_user(request, f"✅ {count} tareas cambiadas al intervalo 15")
    cambiar_intervalo_15.short_description = "Cambiar a intervalo 15"

    def cambiar_intervalo_30(self, request, queryset):
        count = queryset.update(intervalo='30')
        self.message_user(request, f"✅ {count} tareas cambiadas al intervalo 30")
    cambiar_intervalo_30.short_description = "Cambiar a intervalo 30"

    def cambiar_intervalo_45(self, request, queryset):
        count = queryset.update(intervalo='45')
        self.message_user(request, f"✅ {count} tareas cambiadas al intervalo 45")
    cambiar_intervalo_45.short_description = "Cambiar a intervalo 45"

    def estado_actual(self, obj):
        última = obj.ejecuciones.first()
        return última.estado if última else '--'
    estado_actual.short_description = 'Último Estado'

    def ultima_ejecucion(self, obj):
        última = obj.ejecuciones.first()
        return última.inicio if última else '--'
    ultima_ejecucion.short_description = 'Última Ejecución'

@admin.register(Supervisor)
class SupervisorAdmin(admin.ModelAdmin):
    change_list_template = 'admin/snmp_scheduler/supervisor.html'

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return True

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path('ejecutar/<int:tarea_id>/',
                self.admin_site.admin_view(self.ejecutar_tarea),
                name='supervisor_ejecutar'),
        ]
        return my_urls + urls

    def ejecutar_tarea(self, request, tarea_id):
        try:
            tarea = TareaSNMP.objects.get(pk=tarea_id)
            handler = TASK_HANDLERS.get(tarea.tipo)
            if handler:
                # Forzar la ejecución inmediata
                handler.apply_async(args=[tarea_id], countdown=0)
                self.message_user(request, f"✅ Tarea {tarea.nombre} enviada a la cola de ejecución")
            else:
                self.message_user(request, f"⚠️ Tipo de tarea desconocido: {tarea.tipo}", level='warning')
        except TareaSNMP.DoesNotExist:
            self.message_user(request, f"❌ La tarea con ID {tarea_id} no existe", level='error')
        
        # Redirigir a la vista del supervisor
        return HttpResponseRedirect(reverse('admin:snmp_scheduler_supervisor_changelist'))

    def get_task_interval(self, task):
        """Determina el intervalo basado en el campo intervalo de la tarea"""
        try:
            intervalo = task.intervalo.strip('()')
            # Manejar el caso especial de '00'
            if intervalo == '00' or intervalo == '0':
                return 0
            # Para otros intervalos
            valor = int(intervalo)
            return valor if valor in [0, 15, 30, 45] else 15
        except (ValueError, AttributeError):
            return 15

    def get_task_status(self, task, current_time):
        ultima_ejecucion = task.ultima_ejecucion_fecha
        if not ultima_ejecucion:
            return 'pending'
        
        # Convertir a hora local
        ultima_ejecucion = localtime(ultima_ejecucion)
        current_time = localtime(current_time)
        current_minute = current_time.minute
        task_interval = self.get_task_interval(task)
        
        # Manejar el caso especial del intervalo 00
        if task_interval == 0:
            current_hour_start = current_time.replace(minute=0, second=0, microsecond=0)
            if ultima_ejecucion < current_hour_start:
                return 'pending'
        else:
            # Para otros intervalos
            if current_minute < task_interval:
                # Si estamos antes del intervalo, debería ejecutarse
                if ultima_ejecucion < current_time.replace(minute=0, second=0, microsecond=0):
                    return 'pending'
            else:
                # Si ya pasamos el intervalo, la próxima es en la siguiente hora
                if ultima_ejecucion < current_time.replace(minute=task_interval, second=0, microsecond=0):
                    return 'pending'
        
        return 'success' if task.ultimo_estado == 'C' else 'error'

    def get_next_execution(self, task, current_time):
        """Calcula el próximo tiempo de ejecución programado para una tarea"""
        current_time = localtime(current_time)
        task_interval = self.get_task_interval(task)
        
        # Manejar el caso especial del intervalo 00 (cada hora)
        if task_interval == 0:
            # Si estamos en el minuto 0, la próxima ejecución es en la siguiente hora
            next_execution = current_time.replace(
                hour=current_time.hour + 1,
                minute=0,
                second=0,
                microsecond=0
            )
            return next_execution
        
        # Para otros intervalos (15, 30, 45)
        current_minutes = current_time.minute
        current_hour = current_time.hour
        
        # Si el minuto actual es mayor o igual al intervalo de la tarea,
        # la próxima ejecución será en la siguiente hora
        if current_minutes >= task_interval:
            next_execution = current_time.replace(
                hour=current_hour + 1,
                minute=task_interval,
                second=0,
                microsecond=0
            )
        else:
            # Si no, la próxima ejecución será en esta misma hora
            next_execution = current_time.replace(
                minute=task_interval,
                second=0,
                microsecond=0
            )
            
        return next_execution

    def changelist_view(self, request, extra_context=None):
        current_time = timezone.now()
        
        # Obtener todas las tareas activas
        tareas = TareaSNMP.objects.filter(activa=True).annotate(
            ultima_ejecucion_fecha=models.Subquery(
                EjecucionTareaSNMP.objects.filter(
                    tarea=models.OuterRef('pk')
                ).order_by('-inicio').values('inicio')[:1]
            ),
            ultimo_estado=models.Subquery(
                EjecucionTareaSNMP.objects.filter(
                    tarea=models.OuterRef('pk')
                ).order_by('-inicio').values('estado')[:1]
            ),
            duracion=models.Subquery(
                EjecucionTareaSNMP.objects.filter(
                    tarea=models.OuterRef('pk')
                ).order_by('-inicio').values(
                    duracion=models.ExpressionWrapper(
                        models.F('fin') - models.F('inicio'),
                        output_field=models.DurationField()
                    )
                )[:1]
            )
        ).order_by('intervalo', 'nombre')

        # Organizar tareas por intervalos
        intervalos = {
            '00': {'titulo': 'Cada Hora (00)', 'tareas': []},
            '15': {'titulo': 'Minuto 15', 'tareas': []},
            '30': {'titulo': 'Minuto 30', 'tareas': []},
            '45': {'titulo': 'Minuto 45', 'tareas': []}
        }

        for tarea in tareas:
            try:
                intervalo = self.get_task_interval(tarea)
                intervalo_str = str(intervalo).zfill(2)
                
                if intervalo_str not in intervalos:
                    continue

                estado = self.get_task_status(tarea, current_time)
                ultima_ejecucion = tarea.ultima_ejecucion_fecha
                proxima_ejecucion = self.get_next_execution(tarea, current_time)

                if ultima_ejecucion and ultima_ejecucion > current_time:
                    ultima_ejecucion = None

                # Calcular tiempo restante
                tiempo_restante = proxima_ejecucion - localtime(current_time)
                minutos_restantes = max(0, int(tiempo_restante.total_seconds() / 60))

                tarea_info = {
                    'id': tarea.id,
                    'nombre': tarea.nombre,
                    'host_ip': tarea.host.ip,
                    'tipo': tarea.get_tipo_display(),
                    'modo': tarea.get_modo_display(),
                    'estado': estado,
                    'ultima_ejecucion': localtime(ultima_ejecucion).strftime('%d/%m/%Y %H:%M') if ultima_ejecucion else 'No ejecutada',
                    'duracion': str(tarea.duracion).split('.')[0] if tarea.duracion else '--',
                    'proxima_ejecucion': localtime(proxima_ejecucion).strftime('%H:%M'),
                    'minutos_restantes': minutos_restantes,
                    'intervalo': intervalo
                }
                intervalos[intervalo_str]['tareas'].append(tarea_info)
            except Exception as e:
                # Si hay algún error con una tarea específica, la saltamos
                continue

        context = {
            **self.admin_site.each_context(request),
            'title': 'Panel de Supervisión',
            'intervalos': intervalos,
            'has_add_permission': self.has_add_permission(request),
            'current_time': localtime(current_time).strftime('%d/%m/%Y %H:%M'),
        }

        return TemplateResponse(request, self.change_list_template, context)

@admin.register(EjecucionTareaSNMP)
class EjecucionTareaSNMPAdmin(admin.ModelAdmin):
    list_display = (
        'nombre_tarea',
        'host_ip', 
        'tipo_tarea', 
        'inicio', 
        'fin', 
        'estado', 
        'duracion'
    )
    list_filter = ('estado', 'tarea__host__nombre', 'tarea__tipo')
    search_fields = ('tarea__nombre', 'error', 'tarea__host__ip')
    
    def nombre_tarea(self, obj):
        return obj.tarea.nombre
    nombre_tarea.short_description = "Tarea"

    def host_ip(self, obj):
        return obj.tarea.host.ip
    host_ip.short_description = "IP OLT"

    def tipo_tarea(self, obj):
        return obj.tarea.get_tipo_display()
    tipo_tarea.short_description = "Tipo"

    readonly_fields = ('tarea', 'inicio', 'fin', 'estado', 'resultado', 'error')
    actions = ['borrar_seleccion_async']

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

@admin.register(Host)
class HostAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'ip', 'comunidad', 'activo', 'fecha_creacion')
    list_filter = ('activo',)
    search_fields = ('nombre', 'ip')
    ordering = ('nombre',)
    date_hierarchy = 'fecha_creacion'
    
    fieldsets = (
        ('Información Principal', {
            'fields': ('nombre', 'ip', 'comunidad', 'descripcion')
        }),
        ('Estado', {
            'fields': ('activo',)
        }),
    )