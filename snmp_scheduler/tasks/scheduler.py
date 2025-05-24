# snmp_scheduler/tasks/scheduler.py

import logging
from celery import shared_task, chord
from django.utils import timezone
from datetime import timedelta
from django.db.models import Q

from ..models import TareaSNMP
from .snmp_discovery import ejecutar_descubrimiento
from .poller_master import ejecutar_bulk_wrapper

logger = logging.getLogger(__name__)


@shared_task(name="snmp_scheduler.tasks._execute_bulk_and_next")
def _execute_bulk_and_next(header_results, bulk_ids, modo_actual, modos_restantes):
    """
    Callback tras completar todos los 'descubrimiento' de la fase current:
    - header_results: lista de resultados del discovery (ignoramos aquí)
    - bulk_ids: lista de IDs de tareas datos_bulk para encolar ahora
    - modo_actual: nombre de la fase actual ('principal','modo','secundario')
    - modos_restantes: lista de las fases que faltan tras ésta
    """
    # 1) Encolar todos los datos_bulk de esta fase
    for tarea_id in bulk_ids:
        ejecutar_bulk_wrapper.delay(tarea_id)
        logger.info(f"[scheduler] Encolado datos_bulk#{tarea_id} en fase '{modo_actual}'")

    # 2) Lanzar inmediatamente la siguiente fase, si la hay
    if modos_restantes:
        siguiente = modos_restantes[0]
        resto = modos_restantes[1:]
        # Iniciamos la fase siguiente sin header_results
        _start_fase.delay([], siguiente, resto)


@shared_task(name="snmp_scheduler.tasks._start_fase")
def _start_fase(header_results, modo_actual, modos_restantes):
    """
    Inicia la fase indicada:
    - header_results: resultados previos del chord (ignoramos)
    - modo_actual: 'principal'|'modo'|'secundario'
    - modos_restantes: fases posteriores
    """
    ahora = timezone.localtime()
    intervalo = (ahora.minute // 15) * 15

    # Filtrar tareas candidatas para esta fase
    qs = TareaSNMP.objects.filter(
        activa=True,
        modo=modo_actual,
        intervalo=intervalo
    ).filter(
        Q(ultima_ejecucion__lte=ahora - timedelta(minutes=14)) |
        Q(ultima_ejecucion__isnull=True)
    )

    desc_ids = [t.pk for t in qs if t.tipo == "descubrimiento"]
    bulk_ids = [t.pk for t in qs if t.tipo == "datos_bulk"]

    logger.info(f"[scheduler] Fase '{modo_actual}': {len(desc_ids)} discovery, {len(bulk_ids)} bulk")

    # Si no hay descubrimiento, saltamos a bulk y luego a la siguiente fase
    if not desc_ids:
        return _execute_bulk_and_next.delay([], bulk_ids, modo_actual, modos_restantes)

    # Si hay discovery, los ejecutamos en chord, luego bulk y siguiente fase
    header = [ejecutar_descubrimiento.s(tid) for tid in desc_ids]
    callback = _execute_bulk_and_next.s(bulk_ids, modo_actual, modos_restantes)
    chord(header)(callback)
    logger.info(f"[scheduler] Chord discovery fase='{modo_actual}' lanzado")


@shared_task(
    name="snmp_scheduler.tasks.ejecutar_tareas_programadas",
    queue="principal"
)
def ejecutar_tareas_programadas():
    """
    Tarea disparada por cron cada minuto. Lanza la fase 'principal'
    y de ahí encadena 'modo' y 'secundario'.
    """
    ahora = timezone.localtime()
    intervalo = (ahora.minute // 15) * 15
    logger.info(f"[scheduler] Intervalo actual: {intervalo:02d}")

    # Obtenemos candidatas únicamente en modo PRINCIPAL
    qs = TareaSNMP.objects.filter(
        activa=True,
        modo="principal",
        intervalo=intervalo
    ).filter(
        Q(ultima_ejecucion__lte=ahora - timedelta(minutes=14)) |
        Q(ultima_ejecucion__isnull=True)
    )

    desc_ids = [t.pk for t in qs if t.tipo == "descubrimiento"]
    bulk_ids = [t.pk for t in qs if t.tipo == "datos_bulk"]

    logger.info(f"[scheduler] Fase 'principal': {len(desc_ids)} discovery, {len(bulk_ids)} bulk")

    # Si no hay discovery principal, arrancamos bulk y luego resto de fases
    if not desc_ids:
        _execute_bulk_and_next.delay([], bulk_ids, "principal", ["modo", "secundario"])
        return

    # Si hay discovery, uso chord para esperarlos y luego bulk+fases siguientes
    header = [ejecutar_descubrimiento.s(tid) for tid in desc_ids]
    callback = _execute_bulk_and_next.s(bulk_ids, "principal", ["modo", "secundario"])
    chord(header)(callback)
    logger.info(f"[scheduler] Chord discovery fase='principal' lanzado")
