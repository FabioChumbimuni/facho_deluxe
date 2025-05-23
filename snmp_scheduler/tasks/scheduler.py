import logging
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from django.db.models import Q

from ..models import TareaSNMP
from .handlers import TASK_HANDLERS
from .poller_master import ejecutar_bulk_wrapper  # import correcto

logger = logging.getLogger(__name__)

@shared_task(
    name='snmp_scheduler.tasks.ejecutar_tareas_programadas',
    queue='principal'
)
def ejecutar_tareas_programadas():
    """
    Cada minuto revisa las TareaSNMP cuyo intervalo coincida con el
    múltiplo de 15 minutos actual y que no se hayan corrido en 14'...
    """
    ahora = timezone.localtime()
    intervalo_actual = f"{(ahora.minute // 15) * 15:02d}"
    logger.info(f"[scheduler] Intervalo actual: {intervalo_actual}")

    tareas = TareaSNMP.objects.filter(
        activa=True,
        intervalo=int(intervalo_actual)
    ).filter(
        Q(ultima_ejecucion__lte=ahora - timedelta(minutes=14)) |
        Q(ultima_ejecucion__isnull=True)
    )
    logger.info(f"[scheduler] Tareas candidatas: {[t.pk for t in tareas]}")

    modo_orden = ['principal', 'modo', 'secundario']
    for modo in modo_orden:
        for tarea in tareas.filter(modo=modo):
            handler = TASK_HANDLERS.get(tarea.tipo)
            if not handler:
                logger.warning(f"[scheduler] No handler para tipo '{tarea.tipo}'")
                continue

            if tarea.tipo == 'datos_bulk':
                # PASAMOS el ID de la tarea para que el wrapper lo ejecute incluso si está desactivada
                ejecutar_bulk_wrapper.delay(tarea.id)
                logger.info(f"[scheduler] Encolado bulk wrapper para tarea {tarea.id}")
            else:
                handler.apply_async(args=[tarea.id])
                logger.info(f"[scheduler] Encolada tarea {tarea.id} → {handler.__name__}")
