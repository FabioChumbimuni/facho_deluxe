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
    # Descubrimiento
    'descubrimiento': {
        'oid_base': '1.3.6.1.4.1.2011.6.128.1.1.2.46.1.1',
        'field': 'act_susp',
    },
    # Descripción ONU
    'onudesc': {
        'oid_base': '1.3.6.1.4.1.2011.6.128.1.1.2.43.1.9',
        'field': 'onudesc',
    },
    # Estado ONU
    'estado_onu': {
        'oid_base': '1.3.6.1.4.1.2011.6.128.1.1.2.46.1.15',
        'field': 'estado_onu',
    },
    # Plan ONU
    'plan_onu': {
        'oid_base': '1.3.6.1.4.1.2011.6.128.1.1.2.43.1.7',
        'field': 'plan_onu',
    },
    # Potencia RX
    'pot_rx': {
        'oid_base': '1.3.6.1.4.1.2011.6.128.1.1.2.51.1.6',
        'field': 'potencia_rx',
    },
    # Potencia TX
    'pot_tx': {
        'oid_base': '1.3.6.1.4.1.2011.6.128.1.1.2.51.1.4',
        'field': 'potencia_tx',
    },
    # Last Down Time
    'last_down_t': {
        'oid_base': '1.3.6.1.4.1.2011.6.128.1.1.2.101.1.7',
        'field': 'last_down_time',
    },
    # Distancia
    'distancia_m': {
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

