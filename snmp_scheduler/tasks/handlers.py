# snmp_scheduler/tasks/handlers.py

from .snmp_discovery import ejecutar_descubrimiento
from .snmp_data import ejecutar_tarea_snmp
from .poller_master import ejecutar_bulk_wrapper

"""
Mapeo de tipos de tarea SNMP al handler correspondiente.
- 'descubrimiento' → snmpwalk
- 'datos'        → consultas SNMP individuales
- 'datos_bulk'   → poller maestro + workers paralelos
"""

TASK_HANDLERS = {
    'descubrimiento':  ejecutar_descubrimiento,
    'datos':           ejecutar_tarea_snmp,
    'datos_bulk':      ejecutar_bulk_wrapper,
}
