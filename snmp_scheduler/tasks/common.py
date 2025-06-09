# snmp_scheduler/tasks/common.py

from celery.utils.log import get_logger
from pysnmp.hlapi import (
    SnmpEngine,
    CommunityData,
    UdpTransportTarget,
    ContextData,
    ObjectType,
    ObjectIdentity,
    nextCmd,
    getCmd,
    bulkCmd
)

NMP_ENGINE = SnmpEngine()

def get_snmp_engine():
    return SNMP_ENGINE

from django.utils import timezone
from datetime import timedelta
from django.db import connection
from django.db.models import Q
"""
Configuración de todos los sub-tipos de Recolección Masiva de Datos.
Cada clave es el valor que guardaremos en TareaSNMP.bulk_subtipo.
"""
BULK_CONFIG = {
    # Ya existente: descripción ONU
    'onudesc': {
        # El método de TareaSNMP que devuelve el OID base
        'oid_base_attr': 'get_oid_onda_desc',  
        # Nombre del campo en OnuDato que actualizaremos
        'field': 'onudesc',
    },
    # Estado (offline/online flag)
    'estado': {
        'oid_base': '1.3.6.1.4.1.2011.6.128.1.1.2.46.1.15',
        'field': 'estado_onu',
    },
    # Última desconexión
    'last_disconnect': {
        'oid_base': '1.3.6.1.4.1.2011.6.128.1.1.2.46.1.24',
        'field': 'ultima_desconexion',
    },
    # Potencia de retorno Rx
    'potencia_rx': {
        'oid_base': '1.3.6.1.4.1.2011.6.128.1.1.2.51.1.6',
        'field': 'potencia_rx',
    },
    # Potencia de retorno Tx
    'potencia_tx': {
        'oid_base': '1.3.6.1.4.1.2011.6.128.1.1.2.51.1.4',
        'field': 'potencia_tx',
    },
    # Last Down Time
    'last_down_time': {
        'oid_base': '1.3.6.1.4.1.2011.6.128.1.1.2.101.1.7',
        'field': 'last_down_time',
    },
    # Distancia
    'distancia': {
        'oid_base': '1.3.6.1.4.1.2011.6.128.1.1.2.46.1.20',
        'field': 'distancia_m',
    },
    # Modelo ONU
    'modelo_onu': {
        'oid_base': '1.3.6.1.4.1.2011.6.128.1.1.2.45.1.4',
        'field': 'modelo_onu',
    },
}
logger = get_logger(__name__)

