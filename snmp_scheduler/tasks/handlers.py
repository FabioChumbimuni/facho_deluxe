# snmp_scheduler/tasks/handlers.py

from .snmp_discovery import ejecutar_descubrimiento
from .snmp_data import ejecutar_tarea_snmp
from .snmp_bulk_data import ejecutar_bulk_data

TASK_HANDLERS = {
    'descubrimiento': ejecutar_descubrimiento,
    'datos': ejecutar_tarea_snmp,
    'datos_bulk': ejecutar_bulk_data
    # más tipos en el futuro aquí…
}
