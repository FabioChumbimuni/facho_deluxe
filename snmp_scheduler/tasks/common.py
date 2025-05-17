# snmp_scheduler/tasks/common.py

from celery.utils.log import get_logger
from pysnmp.hlapi import (
    SnmpEngine, CommunityData, UdpTransportTarget, ContextData,
    ObjectType, ObjectIdentity, nextCmd
)
from django.utils import timezone
from datetime import timedelta
from django.db import connection
from django.db.models import Q

logger = get_logger(__name__)
