# snmp_scheduler/tasks/scheduler.py

import logging
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from django.db.models import Q

from ..models import TareaSNMP
from .handlers import TASK_HANDLERS
from .poller_master import ejecutar_bulk_wrapper  # importamos el wrapper

logger = logging.getLogger(__name__)

@shared_task(
    name='snmp_scheduler.tasks.ejecutar_tareas_programadas',
    queue='principal'
)
def ejecutar_tareas_programadas():
    """
    Revisa cada minuto (o según tu crontab) las TareaSNMP que estén activas,
    cuyo intervalo coincida con el minuto actual, y que no se hayan ejecutado
    en los últimos 14 minutos. Encola la tarea correspondiente según su tipo:
      - datos_bulk → ejecutar_bulk_wrapper
      - otros tipos → handler.apply_async([tarea.id])
    """
    ahora = timezone.localtime()
    # Redondeamos al múltiplo de 15 minutos (00,15,30,45)
    intervalo_actual = f"{(ahora.minute // 15) * 15:02d}"
    logger.info(f"[scheduler] Intervalo actual: {intervalo_actual}")

    # Filtrar tareas activas con ese intervalo y que no se hayan ejecutado
    tareas = TareaSNMP.objects.filter(
        activa=True,
        intervalo=int(intervalo_actual)
    ).filter(
        Q(ultima_ejecucion__lte=ahora - timedelta(minutes=14)) |
        Q(ultima_ejecucion__isnull=True)
    )
    logger.info(f"[scheduler] Tareas candidatas: {[t.pk for t in tareas]}")

    # Definimos el orden de ejecución según 'modo'
    modo_orden = ['principal', 'modo', 'secundario']
    for modo in modo_orden:
        tareas_modo = tareas.filter(modo=modo)
        logger.info(f"[scheduler] Modo={modo}, tareas: {[t.pk for t in tareas_modo]}")

        for tarea in tareas_modo:
            # Determinar el handler según el tipo
            handler = TASK_HANDLERS.get(tarea.tipo)
            if not handler:
                logger.warning(f"[scheduler] No handler para tipo '{tarea.tipo}'")
                continue

            if tarea.tipo == 'datos_bulk':
                # Encolamos el wrapper que dispara el chord completo
                ejecutar_bulk_wrapper.delay()
                logger.info(f"[scheduler] Encolado bulk wrapper para tarea {tarea.id}")
            else:
                # Otros tipos: enviamos el id de la tarea
                handler.apply_async(args=[tarea.id])
                logger.info(f"[scheduler] Encolada tarea {tarea.id} → {handler.__name__}")
