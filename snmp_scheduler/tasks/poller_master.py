import logging
from celery import shared_task, chord
from django.utils import timezone
from django.db import close_old_connections
from ..models import TareaSNMP, OnuDato, EjecucionTareaSNMP
from .poller_worker import poller_worker
from .poller_aggregator import poller_aggregator

logger = logging.getLogger(__name__)

@shared_task(
    bind=True,
    name='snmp_scheduler.tasks.ejecutar_bulk_wrapper',
    queue='principal'
)
def ejecutar_bulk_wrapper(self, tarea_id=None):
    """
    Envía en paralelo chunks de índices SNMP al poller_worker y luego
    invoca al poller_aggregator para consolidar resultados.

    Si viene tarea_id → invocación manual (no chequea activa=True).
    Si no viene → invocación automática (sólo tareas activas).
    """
    close_old_connections()
    ahora = timezone.localtime()

    # 1) Selección de tareas
    if tarea_id is not None:
        # manual: no filtramos por activa
        try:
            tarea = TareaSNMP.objects.get(pk=tarea_id, tipo='datos_bulk')
        except TareaSNMP.DoesNotExist:
            logger.warning(f"[master] Tarea {tarea_id} no existe o no es datos_bulk")
            return
        tareas = [tarea]
    else:
        # automático: sólo las activas en el minuto actual
        minuto = ahora.minute
        tareas = list(
            TareaSNMP.objects
                     .filter(tipo='datos_bulk', activa=True, intervalo=minuto)
                     .order_by('modo')
        )

    # 2) Para cada tarea
    for tarea in tareas:
        logger.info(f"[master] Ejecutar Ahora tarea {tarea.id}")
        ejec = EjecucionTareaSNMP.objects.create(
            tarea=tarea,
            inicio=ahora,
            estado='E'
        )

        # 3) Leer todos los snmpindexonu existentes
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

        # 4) Partir en chunks
        chunk_size = 200
        chunks = [onus[i:i+chunk_size] for i in range(0, len(onus), chunk_size)]
        logger.info(f"[master] Tarea {tarea.id}: {len(onus)} índices → {len(chunks)} chunks")

        # 5) Construir header para el chord
        header = [
            poller_worker.s(tarea.id, ejec.id, chunk)
            for chunk in chunks
        ]
        callback = poller_aggregator.s(tarea.id, ejec.id)

        # 6) Lanzar chord
        chord(header)(callback)

    close_old_connections()
