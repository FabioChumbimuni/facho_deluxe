from celery import shared_task, group, chord
from django.utils import timezone
from ..models import TareaSNMP, OnuDato, EjecucionTareaSNMP
from .poller_worker import poller_worker
from .poller_aggregator import poller_aggregator

@shared_task(name='snmp_scheduler.poller_master')
def poller_master():
    """
    Lee todas las TareaSNMP activas de tipo 'bulk', divide sus índices en chunks,
    lanza un group de poller_worker y los agrupa con poller_aggregator.
    """
    # 1. Consultar tareas activas de tipo bulk y ordenarlas por modo
    tareas = TareaSNMP.objects.filter(tipo='bulk', activa=True).order_by('modo')

    for tarea in tareas:
        # 2. Registrar inicio de ejecución
        ejec = EjecucionTareaSNMP.objects.create(
            tarea=tarea,
            inicio=timezone.now(),
            estado='E'
        )

        # 3. Recuperar índices existentes
        indices = list(OnuDato.objects
                       .filter(host=tarea.host_name)
                       .values_list('snmpindexonu', flat=True))
        if not indices:
            ejec.fin = timezone.now()
            ejec.estado = 'C'
            ejec.resultado = {'updated': 0, 'deleted': 0, 'errors': []}
            ejec.save()
            continue

        # 4. Partir en chunks de tamaño configurable
        chunk_size = tarea.chunk_size or 200
        chunks = [indices[i:i+chunk_size] for i in range(0, len(indices), chunk_size)]

        # 5. Construir y lanzar el chord
        header = [poller_worker.s(chunk, tarea.id, ejec.id) for chunk in chunks]
        callback = poller_aggregator.s(tarea.id, ejec.id)
        chord(header)(callback)
