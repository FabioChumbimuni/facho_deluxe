from .snmp_discovery import ejecutar_descubrimiento
from .snmp_data import ejecutar_tarea_snmp
from .poller_master import ejecutar_bulk_wrapper

"""
Mapeo de tipos de tarea SNMP al handler correspondiente.
Tipos bulk (onudesc, estado_onu, etc.) → ejecutar_bulk_wrapper
"""

TASK_HANDLERS = {
    # Tipos legacy
    'descubrimiento': ejecutar_descubrimiento,
    'datos': ejecutar_tarea_snmp,
    
    # Nuevos tipos bulk (¡ESTOS ERAN LOS FALTANTES!)
    'onudesc': ejecutar_bulk_wrapper,
    'estado_onu': ejecutar_bulk_wrapper,
    'last_down': ejecutar_bulk_wrapper,
    'pot_rx': ejecutar_bulk_wrapper,
    'pot_tx': ejecutar_bulk_wrapper,
    'last_down_t': ejecutar_bulk_wrapper,
    'distancia_m': ejecutar_bulk_wrapper,
    'modelo_onu': ejecutar_bulk_wrapper,
    'datos_bulk': ejecutar_bulk_wrapper,  # Por compatibilidad
}