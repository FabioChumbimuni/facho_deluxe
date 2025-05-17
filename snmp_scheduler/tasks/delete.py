# snmp_scheduler/tasks/delete.py

import time
from celery import shared_task
from celery.utils.log import get_logger
from ..models import EjecucionTareaSNMP

logger = get_logger(__name__)

@shared_task(
    bind=True,
    name='snmp_scheduler.tasks.delete_history_records',
    queue='background_deletes'
)
def delete_history_records(self, record_ids):
    """
    Borra registros de EjecucionTareaSNMP en background, en lotes con pausa.
    """
    BATCH_SIZE = 500
    PAUSE_SECONDS = 0.5

    total = len(record_ids)
    logger.info(f"delete_history_records: comenzando borrado de {total} registros")

    for start in range(0, total, BATCH_SIZE):
        chunk = record_ids[start:start + BATCH_SIZE]
        deleted, _ = EjecucionTareaSNMP.objects.filter(pk__in=chunk).delete()
        logger.info(f"delete_history_records: borrados {deleted} registros IDs {chunk[0]}–{chunk[-1]}")
        time.sleep(PAUSE_SECONDS)

    logger.info("delete_history_records: terminado")



