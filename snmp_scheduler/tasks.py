# snmp_scheduler/tasks.py

from __future__ import absolute_import

# Reexportar tareas desde los módulos nuevos
from .tasks.snmp_discovery import ejecutar_descubrimiento
from .tasks.scheduler import ejecutar_tareas_programadas

# Importaciones necesarias para que Celery pueda registrar estas tareas
__all__ = [
    'ejecutar_descubrimiento',
    'ejecutar_tareas_programadas'
]
