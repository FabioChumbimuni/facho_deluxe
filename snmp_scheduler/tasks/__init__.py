# snmp_scheduler/tasks/__init__.py

from .snmp_discovery import ejecutar_descubrimiento
from .snmp_data import ejecutar_tarea_snmp
from .scheduler import ejecutar_tareas_programadas
from .update_onu_meta    import actualizar_onu_meta
from . import handlers
__all__ = [
    'ejecutar_descubrimiento',
    'ejecutar_tarea_snmp',
    'ejecutar_tareas_programadas',
    'actualizar_onu_meta',
]
