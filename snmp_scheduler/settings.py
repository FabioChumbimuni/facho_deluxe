# Configuración de Celery
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TASK_TRACK_STARTED = True
CELERY_TIMEZONE = 'America/Bogota'

# Configuración de colas y prioridades
CELERY_TASK_ROUTES = {
    'snmp_scheduler.tasks.ejecutar_tareas_programadas': {'queue': 'principal'},
    'snmp_scheduler.tasks._start_fase': {'queue': 'principal'},
    'snmp_scheduler.tasks._execute_bulk_and_next': {'queue': 'principal'},
    'snmp_scheduler.tasks._check_and_continue': {'queue': 'principal'},
    'snmp_scheduler.tasks.ejecutar_descubrimiento': {'queue': 'principal'},
    'snmp_scheduler.tasks.ejecutar_bulk_wrapper': {'queue': 'principal'},
    'snmp_scheduler.tasks.poller_worker': {'queue': 'workers'},
    'snmp_scheduler.tasks.poller_aggregator': {'queue': 'principal'},
}

# Configuración de timeouts y reintentos
CELERY_TASK_SOFT_TIME_LIMIT = 300  # 5 minutos
CELERY_TASK_TIME_LIMIT = 360  # 6 minutos

# Configuración de workers
CELERY_WORKER_CONCURRENCY = 20  # 20 workers para aprovechar el hardware
CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # Evitar que un worker tome demasiadas tareas
CELERY_WORKER_MAX_TASKS_PER_CHILD = 1000  # Reiniciar worker después de 1000 tareas
CELERY_WORKER_MAX_MEMORY_PER_CHILD = 200000  # 200MB máximo por worker

# Configuración específica para tareas SNMP
CELERY_TASK_ANNOTATIONS = {
    'snmp_scheduler.tasks.*': {
        'rate_limit': '60/m',  # 60 tareas por minuto
        'max_retries': 2,
        'retry_backoff': True,
        'soft_time_limit': 300,
        'time_limit': 360
    }
}

# Configuración de colas
CELERY_TASK_QUEUES = {
    'principal': {
        'exchange': 'principal',
        'routing_key': 'principal',
    },
    'workers': {
        'exchange': 'workers',
        'routing_key': 'workers',
    }
}

# Configuración de beat
CELERY_BEAT_SCHEDULE = {
    'tareas-snmp-programadas': {
        'task': 'snmp_scheduler.tasks.ejecutar_tareas_programadas',
        'schedule': crontab(minute='*/15'),  # Ejecutar en 00,15,30,45
        'options': {'queue': 'principal'}
    }
} 