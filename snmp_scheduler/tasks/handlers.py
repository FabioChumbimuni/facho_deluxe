# snmp_scheduler/tasks/handlers.py

from .snmp_discovery import ejecutar_descubrimiento
from .snmp_data import ejecutar_tarea_snmp

TASK_HANDLERS = {
    'descubrimiento': ejecutar_descubrimiento,
    'datos': ejecutar_tarea_snmp,
    # más tipos en el futuro aquí…
}
