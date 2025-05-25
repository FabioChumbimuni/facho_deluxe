import logging
from celery import shared_task, chord
from django.utils import timezone
from django.db import close_old_connections
from ..models import TareaSNMP, OnuDato, EjecucionTareaSNMP
from .poller_worker import poller_worker
from .poller_aggregator import poller_aggregator

logger = logging.getLogger(__name__)

# Lista de tipos permitidos (debe coincidir con TIPO_CHOICES en models.py)
TIPOS_PERMITIDOS = [
    'onudesc', 'estado_onu', 'last_down', 'pot_rx', 
    'pot_tx', 'last_down_t', 'distancia_m', 'modelo_onu'
]

@shared_task(
    bind=True,
    name='snmp_scheduler.tasks.ejecutar_bulk_wrapper',
    queue='principal'
)
def ejecutar_bulk_wrapper(self, tarea_id=None):
    """
    Procesa solo tareas con tipos válidos (TIPOS_PERMITIDOS).
    """
    close_old_connections()
    ahora = timezone.localtime()

    # 1) Selección de tareas
    if tarea_id:
        try:
            tarea = TareaSNMP.objects.get(
                pk=tarea_id,
                activa=True,
                tipo__in=TIPOS_PERMITIDOS  # 👈 Filtro crítico
            )
            tareas = [tarea]
        except TareaSNMP.DoesNotExist:
            logger.warning(f"[master] Tarea {tarea_id} no existe, está inactiva o tiene tipo inválido.")
            return
    else:
        minuto = ahora.minute
        tareas = list(
            TareaSNMP.objects
                     .filter(activa=True, intervalo=f"{minuto:02d}", tipo__in=TIPOS_PERMITIDOS)  # 👈 Filtro crítico
                     .order_by('modo')
        )

    # 2) Procesar cada tarea
    for tarea in tareas:
        logger.info(f"[master] Ejecutando tarea {tarea.id} ({tarea.tipo})")
        ejec = EjecucionTareaSNMP.objects.create(
            tarea=tarea,
            inicio=ahora,
            estado='E'
        )

        # 3) Obtener índices existentes para ese host
        onus = list(
            OnuDato.objects
                   .filter(host=tarea.host_name)
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
        
        header = [poller_worker.s(tarea.id, ejec.id, chunk) for chunk in chunks]
        callback = poller_aggregator.s(tarea.id, ejec.id)
        chord(header)(callback)

    close_old_connections()