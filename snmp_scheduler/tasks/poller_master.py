import logging
from celery import shared_task, chord
from django.utils import timezone
from django.db import close_old_connections
from ..models import TareaSNMP, OnuDato, EjecucionTareaSNMP, Host
from .poller_worker import poller_worker
from .poller_aggregator import poller_aggregator

logger = logging.getLogger(__name__)

# Lista de tipos permitidos (debe coincidir con TIPO_CHOICES en models.py)
TIPOS_PERMITIDOS = [
    'onudesc', 'estado_onu', 'last_down', 'pot_rx', 
    'pot_tx', 'last_down_t', 'distancia_m', 'modelo_onu',
    'plan_onu'  # Agregado plan_onu a los tipos permitidos
]

@shared_task(
    bind=True,
    name='snmp_scheduler.tasks.ejecutar_bulk_wrapper',
    queue='principal'
)
def ejecutar_bulk_wrapper(self, tarea_id=None, host_id=None):
    """
    Procesa solo tareas con tipos válidos (TIPOS_PERMITIDOS).
    Para ejecución manual (tarea_id especificado) no requiere que la tarea esté activa.
    Para ejecución automática (tarea_id=None) solo procesa tareas activas.
    """
    close_old_connections()
    ahora = timezone.localtime()

    # 1) Selección de tareas
    if tarea_id:
        try:
            # Para ejecución manual solo validamos que exista y tenga tipo válido
            tarea = TareaSNMP.objects.get(
                pk=tarea_id,
                trabajo__tipo__in=TIPOS_PERMITIDOS  # Solo validamos tipo válido
            )
            
            # Si se especifica host_id, verificar que pertenece a la tarea
            if host_id:
                host = Host.objects.get(pk=host_id)
                if not tarea.hosts.filter(pk=host_id).exists():
                    logger.warning(f"[master] Host {host_id} no pertenece a la tarea {tarea_id}")
                    return
            else:
                # Si no se especifica host_id, procesar todos los hosts de la tarea
                for host in tarea.hosts.all():
                    ejecutar_bulk_wrapper.delay(tarea_id, host.id)
                return
                
            tareas = [(tarea, host)]
        except (TareaSNMP.DoesNotExist, Host.DoesNotExist):
            logger.warning(f"[master] Tarea {tarea_id} o host {host_id} no existe o tiene tipo inválido.")
            return
    else:
        # Para ejecución automática sí requerimos que esté activa
        minuto = ahora.minute
        tareas = []
        for tarea in TareaSNMP.objects.filter(
            activa=True,
            trabajo__intervalo=f"{minuto:02d}",
            trabajo__tipo__in=TIPOS_PERMITIDOS
        ).order_by('trabajo__modo'):
            for host in tarea.hosts.all():
                tareas.append((tarea, host))

    # 2) Procesar cada tarea
    for tarea, host in tareas:
        logger.info(f"[master] Ejecutando tarea {tarea.id} ({tarea.trabajo.tipo}) para host {host.nombre}")
        ejec = EjecucionTareaSNMP.objects.create(
            tarea=tarea,
            inicio=ahora,
            estado='E',
            host=host
        )

        # 3) Obtener índices existentes para ese host
        onus = list(
            OnuDato.objects
                   .filter(host=host.nombre)
                   .values_list('snmpindexonu', flat=True)
        )
        if not onus:
            ejec.fin = timezone.now()
            ejec.estado = 'C'
            ejec.resultado = {'updated': 0, 'deleted': 0, 'errors': []}
            ejec.save()
            continue

        # 4) Dividir en chunks y lanzar el chord
        chunk_size = getattr(tarea, 'chunk_size', 200) or 200
        chunks = [onus[i:i + chunk_size] for i in range(0, len(onus), chunk_size)]
        
        header = [poller_worker.s(tarea.id, ejec.id, chunk, host.id) for chunk in chunks]
        callback = poller_aggregator.s(tarea.id, ejec.id, host.id)
        chord(header)(callback)

    close_old_connections()