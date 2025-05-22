# snmp_scheduler/tasks/poller_master.py

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
    """
    close_old_connections()
    ahora = timezone.localtime()

    # 1) Selección de tareas: por ID o por intervalo de minuto
    if tarea_id:
        try:
            tareas = [TareaSNMP.objects.get(
                pk=tarea_id,
                tipo='datos_bulk',
                activa=True
            )]
        except TareaSNMP.DoesNotExist:
            logger.warning(f"[master] Tarea {tarea_id} no existe o no está activa/bulk")
            return
    else:
        minuto = ahora.minute
        tareas = list(TareaSNMP.objects.filter(
            tipo='datos_bulk',
            activa=True,
            intervalo=minuto
        ).order_by('modo'))

    # 2) Para cada tarea seleccionada
    for tarea in tareas:
        logger.info(f"[master] Ejecutar Ahora tarea {tarea.id}")
        ejec = EjecucionTareaSNMP.objects.create(
            tarea=tarea,
            inicio=ahora,
            estado='E'
        )

        # 3) Obtener todos los índices SNMP para este host
        

        onus = list(OnuDato.objects.filter(host=tarea.host_name).values_list('snmpindexonu', flat=True))
        chunk_size = 200
        chunks = [ onus[i:i+chunk_size] for i in range(0, len(onus), chunk_size) ]

        header = [
            poller_worker.s(tarea.id, ejec.id, chunk)
            for chunk in chunks
        ]

        if not onus:
            # Nada que hacer: cerramos ejecución sin errores
            ejec.fin = timezone.now()
            ejec.estado = 'C'
            ejec.resultado = {'updated': 0, 'deleted': 0, 'errors': []}
            ejec.save()
            continue

        # 4) Partir en chunks de tamaño fijo
        chunk_size = 200
        chunks = [
            onus[i:i + chunk_size]
            for i in range(0, len(onus), chunk_size)
        ]
        logger.info(f"[master] Tarea {tarea.id}: {len(onus)} índices → {len(chunks)} chunks")

        # 5) Construir el header del chord: cada worker recibe (chunk_indices, tarea.id)
        
        header = [
            poller_worker.s(tarea.id, ejec.id, chunk)
            for chunk in chunks
        ]


        # 6) El callback recibirá la lista de resultados + tarea.id + ejec.id
        callback = poller_aggregator.s(tarea.id, ejec.id)

        # 7) Lanzamos el chord
        chord(header)(callback)

    close_old_connections()
