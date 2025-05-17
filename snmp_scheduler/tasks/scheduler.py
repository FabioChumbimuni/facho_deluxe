# snmp_scheduler/tasks/scheduler.py

from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from django.db.models import Q
from ..models import TareaSNMP
from .handlers import TASK_HANDLERS
import logging
logger = logging.getLogger(__name__)

@shared_task(
    name='snmp_scheduler.tasks.ejecutar_tareas_programadas',
    queue='principal'
)
def ejecutar_tareas_programadas():
    ahora = timezone.localtime()
    intervalo_actual = f"{ahora.minute // 15 * 15:02d}"
    logger.info(f"[scheduler] Intervalo actual: {intervalo_actual}")

    tareas = TareaSNMP.objects.filter(
        activa=True,
        intervalo=intervalo_actual
    ).filter(
        Q(ultima_ejecucion__lte=ahora - timedelta(minutes=14)) |
        Q(ultima_ejecucion__isnull=True)
    )
    logger.info(f"[scheduler] Tareas candidatas: {[t.pk for t in tareas]}")

    modo_orden = ['principal', 'modo', 'secundario']
    for modo in modo_orden:
        tareas_modo = tareas.filter(modo=modo)
        logger.info(f"[scheduler] Modo={modo}, tareas: {[t.pk for t in tareas_modo]}")
        for tarea in tareas_modo:
            handler = TASK_HANDLERS.get(tarea.tipo)
            if not handler:
                logger.warning(f"[scheduler] No handler para tipo {tarea.tipo}")
                continue
            handler.apply_async(args=[tarea.id])
            logger.info(f"[scheduler] Encolada tarea {tarea.id} → {handler.__name__}")
