# facho/celery.py
from __future__ import absolute_import
import os
from celery import Celery
from celery.schedules import crontab  # Import faltante añadido

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'facho.settings')

app = Celery('facho')
app.config_from_object('django.conf:settings', namespace='CELERY')

# Configuración de planificación unificada
app.conf.beat_schedule = {
    # Para el módulo SNMP
    'ejecutar-tareas-snmp': {
        'task': 'snmp_scheduler.tasks.ejecutar_tareas_programadas',
        'schedule': crontab(minute='*/15'),  # Cada 15 minutos
        'options': {'queue': 'principal'}
    },
    # Para el módulo Scripts
    'ejecutar-bloques-scripts': {
        'task': 'scripts.tasks.ejecutar_bloques_programados',
        'schedule': crontab(minute='*/15'),  # Mismo intervalo
        'options': {'queue': 'secundario'}
    }
}

app.autodiscover_tasks()