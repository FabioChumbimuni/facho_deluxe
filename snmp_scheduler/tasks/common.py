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

logger = get_logger(__name__)

