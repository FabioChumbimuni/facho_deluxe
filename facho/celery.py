# facho/celery.py
from __future__ import absolute_import
import os
from celery import Celery
from celery.schedules import crontab

# Establecer la configuración de Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'facho.settings')

app = Celery('facho')
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
    'snmp-every-15-min': {
        'task': 'snmp_scheduler.tasks.ejecutar_tareas_programadas',
        'schedule': crontab(minute='*/15'),
        'options': {'queue': 'principal'},
    },
    # Módulo Scripts: cada 15 minutos
    'scripts-every-15-min': {
        'task': 'scripts.tasks.ejecutar_bloques_programados',
        'schedule': crontab(minute='*/15'),
        'options': {'queue': 'secundario'},
    }
}

# Descubrir automáticamente las tareas en las apps registradas
app.autodiscover_tasks()

# Exportar la app para referenciar con @app.task si se prefiere
__all__ = ('app',)
