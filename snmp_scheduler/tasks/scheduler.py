# snmp_scheduler/tasks/scheduler.py

import logging
from celery import shared_task, chord
from django.utils import timezone
from datetime import timedelta, datetime
from django.db.models import Q

from ..models import TareaSNMP
from .snmp_discovery import ejecutar_descubrimiento
from .poller_master import ejecutar_bulk_wrapper

logger = logging.getLogger(__name__)

TIPOS_BULK = [
    'onudesc', 'estado_onu', 'last_down', 
    'pot_rx', 'pot_tx', 'last_down_t',
    'distancia_m', 'modelo_onu'
]

def get_current_interval(time):
    """Calcula el intervalo actual (00, 15, 30, 45)"""
    minute = time.minute
    if minute >= 45:
        return '45'
    elif minute >= 30:
        return '30'
    elif minute >= 15:
        return '15'
    return '00'

def get_next_interval_time(ahora, intervalo):
    """
    Calcula el próximo tiempo de ejecución basado en la hora actual y el intervalo deseado
    independientemente de la última ejecución.
    
    Args:
        ahora: datetime actual
        intervalo: string con el intervalo ('00', '15', '30', '45')
    
    Returns:
        datetime con la próxima ejecución programada
    """
    minuto_actual = ahora.minute
    hora_actual = ahora.hour
    
    # Convertir el intervalo a entero
    minuto_intervalo = int(intervalo)
    
    # Para intervalo '00', es la próxima hora en punto
    if intervalo == '00':
        if minuto_actual == 0:
            # Si estamos exactamente en el minuto 0, la próxima es en la siguiente hora
            return ahora.replace(hour=hora_actual + 1, minute=0, second=0, microsecond=0)
        else:
            # Si no, es la siguiente hora en punto
            siguiente = ahora.replace(hour=hora_actual + 1, minute=0, second=0, microsecond=0)
            if siguiente < ahora:
                siguiente += timedelta(hours=1)
            return siguiente
    
    # Para otros intervalos (15, 30, 45)
    # Calculamos cuántos intervalos de 15 minutos han pasado
    intervalos_pasados = minuto_actual // 15
    proximo_intervalo = (intervalos_pasados + 1) * 15
    
    # Si el próximo intervalo supera la hora, pasamos a la siguiente
    if proximo_intervalo >= 60:
        return ahora.replace(hour=hora_actual + 1, minute=0, second=0, microsecond=0)
    
    siguiente = ahora.replace(minute=proximo_intervalo, second=0, microsecond=0)
    if siguiente < ahora:
        siguiente += timedelta(minutes=15)
    
    return siguiente

def get_intervals_to_execute(time):
    """
    Determina qué intervalos deben ejecutarse en este momento.
    Las tareas se ejecutan exactamente en su intervalo:
    - '00': solo en las horas exactas (12:00, 1:00, etc.)
    - '15': solo a los 15 minutos de cada hora (12:15, 1:15, etc.)
    - '30': solo a los 30 minutos de cada hora (12:30, 1:30, etc.)
    - '45': solo a los 45 minutos de cada hora (12:45, 1:45, etc.)
    """
    current = get_current_interval(time)
    return [current]  # Solo ejecutar el intervalo actual

def should_execute_task(tarea, ahora):
    """
    Determina si una tarea debe ejecutarse basado en su última ejecución e intervalo
    """
    # Limpiar el intervalo de paréntesis si los tiene
    intervalo = tarea.intervalo.strip('()')
    
    # Si nunca se ha ejecutado, debe ejecutarse
    if not tarea.ultima_ejecucion:
        logger.info(f"[scheduler] Tarea {tarea.nombre} nunca ejecutada - ejecutando ahora")
        return True
    
    # Calcular el próximo tiempo de ejecución basado en el intervalo
    next_execution = get_next_interval_time(tarea.ultima_ejecucion, intervalo)
    
    should_run = ahora >= next_execution
    
    if should_run:
        logger.info(f"[scheduler] Tarea {tarea.nombre} debe ejecutarse - última: {tarea.ultima_ejecucion}, próxima: {next_execution}, ahora: {ahora}")
    else:
        logger.info(f"[scheduler] Tarea {tarea.nombre} no debe ejecutarse aún - última: {tarea.ultima_ejecucion}, próxima: {next_execution}, ahora: {ahora}")
    
    return should_run

@shared_task(name="snmp_scheduler.tasks._execute_bulk_and_next")
def _execute_bulk_and_next(header_results, bulk_ids, modo_actual, modos_restantes):
    """
    Callback tras completar todos los 'descubrimiento' de la fase current:
    - header_results: lista de resultados del discovery (ignoramos aquí)
    - bulk_ids: lista de IDs de tareas datos_bulk para encolar ahora
    - modo_actual: nombre de la fase actual ('principal','modo','secundario')
    - modos_restantes: lista de las fases que faltan tras ésta
    """
    logger.info(f"[scheduler] Ejecutando bulk y siguiente fase. Modo actual: {modo_actual}, Modos restantes: {modos_restantes}")
    
    # 1) Encolar todos los datos_bulk de esta fase
    for tarea_id in bulk_ids:
        ejecutar_bulk_wrapper.delay(tarea_id)
        logger.info(f"[scheduler] Encolado tarea bulk#{tarea_id} ({modo_actual})")

    # 2) Lanzar inmediatamente la siguiente fase, si la hay
    if modos_restantes:
        siguiente = modos_restantes[0]
        resto = modos_restantes[1:]
        logger.info(f"[scheduler] Iniciando siguiente fase: {siguiente}")
        # Iniciamos la fase siguiente sin header_results
        _start_fase.delay([], siguiente, resto)
    else:
        logger.info(f"[scheduler] Finalizada cadena de ejecución en modo {modo_actual}")

@shared_task(name="snmp_scheduler.tasks._start_fase")
def _start_fase(header_results, modo_actual, modos_restantes):
    """
    Inicia la fase indicada en el orden:
    principal -> modo -> secundario
    """
    ahora = timezone.localtime()
    intervalo = get_current_interval(ahora)
    logger.info(f"[scheduler] Iniciando fase '{modo_actual}' en intervalo {intervalo}")
    logger.info(f"[scheduler] Modos restantes después de esta fase: {modos_restantes}")

    # Obtener el intervalo actual
    intervalos = get_intervals_to_execute(ahora)
    logger.info(f"[scheduler] Intervalos a ejecutar: {intervalos}")

    # Filtrar tareas candidatas para esta fase y el intervalo actual
    qs = TareaSNMP.objects.filter(
        activa=True,
        modo=modo_actual,
        intervalo=intervalo  # Buscar sin paréntesis
    )
    
    logger.info(f"[scheduler] Encontradas {len(qs)} tareas para modo {modo_actual} en intervalo {intervalo}")
    
    # Luego filtramos por tiempo de ejecución
    tareas_a_ejecutar = [t for t in qs if should_execute_task(t, ahora)]

    desc_ids = [t.pk for t in tareas_a_ejecutar if t.tipo == "descubrimiento"]
    bulk_ids = [t.pk for t in tareas_a_ejecutar if t.tipo in TIPOS_BULK]

    logger.info(f"[scheduler] Fase '{modo_actual}': {len(desc_ids)} discovery, {len(bulk_ids)} bulk")
    logger.info(f"[scheduler] Tareas a ejecutar en modo {modo_actual}: {[t.nombre for t in tareas_a_ejecutar]}")

    # Si no hay descubrimiento, saltamos a bulk y luego a la siguiente fase
    if not desc_ids:
        logger.info(f"[scheduler] No hay tareas discovery en fase {modo_actual}, pasando a bulk y siguientes fases")
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
    Tarea disparada por cron cada 15 minutos. Lanza la fase 'principal'
    y de ahí encadena 'modo' y 'secundario'.
    """
    ahora = timezone.localtime()
    intervalo = get_current_interval(ahora)
    logger.info(f"[scheduler] Iniciando ejecución programada en intervalo {intervalo}")

    # Obtener el intervalo actual
    intervalos = get_intervals_to_execute(ahora)
    logger.info(f"[scheduler] Intervalos a ejecutar: {intervalos}")

    # Obtenemos candidatas únicamente en modo PRINCIPAL para el intervalo actual
    qs = TareaSNMP.objects.filter(
        activa=True,
        modo="principal",
        intervalo=intervalo  # Buscar sin paréntesis
    )
    
    logger.info(f"[scheduler] Encontradas {len(qs)} tareas principales para intervalo {intervalo}")
    
    # Luego filtramos por tiempo de ejecución
    tareas_a_ejecutar = [t for t in qs if should_execute_task(t, ahora)]

    desc_ids = [t.pk for t in tareas_a_ejecutar if t.tipo == "descubrimiento"]
    bulk_ids = [t.pk for t in tareas_a_ejecutar if t.tipo in TIPOS_BULK]

    logger.info(f"[scheduler] Fase 'principal': {len(desc_ids)} discovery, {len(bulk_ids)} bulk")
    logger.info(f"[scheduler] Tareas a ejecutar: {[t.nombre for t in tareas_a_ejecutar]}")

    # Si no hay discovery principal, arrancamos bulk y luego resto de fases
    if not desc_ids:
        logger.info("[scheduler] No hay tareas discovery en fase principal, pasando a bulk y siguientes fases")
        _execute_bulk_and_next.delay([], bulk_ids, "principal", ["modo", "secundario"])
        return

    # Si hay discovery, uso chord para esperarlos y luego bulk+fases siguientes
    header = [ejecutar_descubrimiento.s(tid) for tid in desc_ids]
    callback = _execute_bulk_and_next.s(bulk_ids, "principal", ["modo", "secundario"])
    chord(header)(callback)
    logger.info(f"[scheduler] Chord discovery fase='principal' lanzado")
