import logging
from celery import shared_task, chord, chain
from django.utils import timezone
from django.db import close_old_connections
from ..models import TareaSNMP, OnuDato, EjecucionTareaSNMP, Host
from .poller_worker import poller_worker
from .poller_aggregator import poller_aggregator
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Lista de tipos permitidos (debe coincidir con TIPO_CHOICES en models.py)
TIPOS_PERMITIDOS = [
    'onudesc', 'estado_onu', 'last_down', 'pot_rx', 
    'pot_tx', 'last_down_t', 'distancia_m', 'modelo_onu',
    'plan_onu', 'descubrimiento'  # Agregado descubrimiento a los tipos permitidos
]

# Constantes
MAX_POLLERS_PER_TASK = 10  # Máximo número de pollers por tarea
CHUNK_SIZE = 200           # Tamaño de cada chunk
LOCK_TIMEOUT = 300        # 5 minutos timeout para locks
RETRY_DELAY = 5           # Segundos entre reintentos
MAX_RETRIES = 3           # Máximo número de reintentos

def get_poller_key(tarea_id):
    """Genera una clave única para los pollers de una tarea"""
    return f'task_{tarea_id}_active_pollers'

def init_pollers(tarea_id):
    """Inicializa el contador de pollers para una tarea"""
    key = get_poller_key(tarea_id)
    cache.set(key, 0, LOCK_TIMEOUT)

def get_active_pollers(tarea_id):
    """Obtiene el número de pollers activos para una tarea"""
    key = get_poller_key(tarea_id)
    return int(cache.get(key, 0))

def incr_pollers(tarea_id):
    """Incrementa el contador de pollers activos"""
    key = get_poller_key(tarea_id)
    try:
        count = cache.incr(key)
        return count
    except ValueError:
        cache.set(key, 1, LOCK_TIMEOUT)
        return 1

@shared_task
def decr_pollers(result, tarea_id):
    """Decrementa el contador de pollers y retorna el resultado original"""
    key = get_poller_key(tarea_id)
    try:
        count = cache.decr(key)
        if count < 0:
            cache.set(key, 0, LOCK_TIMEOUT)
    except ValueError:
        cache.set(key, 0, LOCK_TIMEOUT)
    return result

@shared_task(name='snmp_scheduler.tasks.process_chunk', bind=True, max_retries=None)
def process_chunk(self, chunk, tarea_id, ejec_id, host_id):
    """Procesa un chunk individual"""
    try:
        # Verificar límite de pollers
        active = incr_pollers(tarea_id)
        if active > MAX_POLLERS_PER_TASK:
            decr_pollers.delay(None, tarea_id)
            # Usar un número muy alto en lugar de None para garantizar reintentos
            self.retry(countdown=RETRY_DELAY, max_retries=999999)
            return None

        # Ejecutar worker y encadenar con decremento
        chain(
            poller_worker.s(tarea_id, ejec_id, chunk, host_id),
            decr_pollers.s(tarea_id)
        ).apply_async()

    except Exception as e:
        decr_pollers.delay(None, tarea_id)
        raise

@shared_task(name='snmp_scheduler.tasks.process_remaining_chunks', bind=True, max_retries=None)
def process_remaining_chunks(self, tarea_id, ejec_id, host_id, chunks):
    """Procesa los chunks restantes cuando hay slots disponibles"""
    if not chunks:
        return

    active = get_active_pollers(tarea_id)
    if active >= MAX_POLLERS_PER_TASK:
        # Reintentar después de un delay con reintentos infinitos
        self.retry(countdown=RETRY_DELAY, max_retries=999999)
        return

    # Procesar tantos chunks como slots disponibles
    available = MAX_POLLERS_PER_TASK - active
    to_process = chunks[:available]
    remaining = chunks[available:]

    # Lanzar los chunks disponibles
    for chunk in to_process:
        process_chunk.delay(chunk, tarea_id, ejec_id, host_id)

    # Si quedan chunks, programar el siguiente lote
    if remaining:
        process_remaining_chunks.delay(tarea_id, ejec_id, host_id, remaining)

@shared_task(bind=True, name='snmp_scheduler.tasks.ejecutar_bulk_wrapper', queue='principal')
def ejecutar_bulk_wrapper(self, tarea_id=None, host_id=None):
    """Procesa una tarea SNMP para un host específico"""
    close_old_connections()
    
    try:
        # Selección de tareas
        if tarea_id:
            try:
                tarea = TareaSNMP.objects.get(pk=tarea_id, trabajo__tipo__in=TIPOS_PERMITIDOS)
                if host_id:
                    host = Host.objects.get(pk=host_id)
                    if not host.activo:
                        return
                    tareas = [(tarea, host)]
                else:
                    tareas = [(tarea, host) for host in tarea.hosts.filter(activo=True)]
            except (TareaSNMP.DoesNotExist, Host.DoesNotExist):
                return
        else:
            minuto = timezone.now().minute
            tareas = []
            for tarea in TareaSNMP.objects.filter(
                activa=True,
                trabajo__intervalo=f"{minuto:02d}",
                trabajo__tipo__in=TIPOS_PERMITIDOS
            ).order_by('trabajo__modo'):
                tareas.extend((tarea, host) for host in tarea.hosts.filter(activo=True))

        # Procesar cada tarea
        for tarea, host in tareas:
            # Inicializar contador de pollers
            init_pollers(tarea.id)
            
            ejec = EjecucionTareaSNMP.objects.create(
                tarea=tarea,
                inicio=timezone.now(),
                estado='E',
                host=host
            )

            # Obtener índices
            onus = list(OnuDato.objects.filter(host=host.nombre).values_list('snmpindexonu', flat=True))
            if not onus:
                ejec.estado = 'C'
                ejec.fin = timezone.now()
                ejec.save()
                continue

            # Dividir en chunks
            chunks = [onus[i:i + CHUNK_SIZE] for i in range(0, len(onus), CHUNK_SIZE)]
            
            # Procesar chunks iniciales
            initial_chunks = chunks[:MAX_POLLERS_PER_TASK]
            remaining_chunks = chunks[MAX_POLLERS_PER_TASK:]

            # Lanzar chunks iniciales
            for chunk in initial_chunks:
                process_chunk.delay(chunk, tarea.id, ejec.id, host.id)

            # Si hay chunks restantes, programar su procesamiento
            if remaining_chunks:
                process_remaining_chunks.delay(tarea.id, ejec.id, host.id, remaining_chunks)

    finally:
        close_old_connections()