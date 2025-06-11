# facho_deluxe/celery.py
from __future__ import absolute_import
import os
from celery import Celery
from celery.schedules import crontab
# Establecer la configuración de Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'facho_deluxe.settings')

app = Celery('facho_deluxe')
# Leer configuración de Celery desde settings.py con prefijo CELERY_
app.config_from_object('django.conf:settings', namespace='CELERY')

# Configuración de colas
app.conf.task_default_queue = 'principal'
app.conf.task_queues = {
    'principal': {
        'exchange': 'principal',
        'routing_key': 'principal',
    },
    'secundario': {
        'exchange': 'secundario',
        'routing_key': 'secundario',
    }
}

# Planificación de tareas periódicas (Beat)
app.conf.beat_schedule = {
    # Módulo SNMP: cada 15 minutos
    'tareas-snmp-programadas': {
        'task': 'snmp_scheduler.tasks.ejecutar_tareas_programadas',
        'schedule': crontab(minute='*/15'),  # Ejecutar cada 15 minutos
        'options': {'queue': 'principal'},
    },
    # Módulo Scripts: cada 15 minutos
    'ejecutar-bloques-programados': {
        'task': 'scripts.tasks.ejecutar_bloques_programados',
        'schedule': crontab(minute='*/15'),
        'options': {'queue': 'secundario'},
    }
}

app.conf.beat_schedule.update({
    'actualizar-onu-meta-cada-2-min': {
        'task': 'snmp_scheduler.tasks.update_onu_meta',
        'schedule': crontab(minute='*/2'),
        'options': {'queue': 'principal'},
    },
})

# Descubrir automáticamente las tareas en las apps registradas
app.autodiscover_tasks()

# Exportar la app para referenciar con @app.task si se prefiere
__all__ = ('app',)
