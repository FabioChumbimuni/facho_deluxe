from celery import shared_task
from django.utils import timezone
from django.db import close_old_connections, transaction
from pysnmp.hlapi import (
    SnmpEngine, CommunityData, UdpTransportTarget,
    ContextData, ObjectType, ObjectIdentity, getCmd
)
from ..models import OnuDato

@shared_task(
    bind=True,
    name='snmp_scheduler.poller_worker',
    soft_time_limit=300,
    autoretry_for=(Exception,),
    retry_backoff=60,
    max_retries=2
)
def poller_worker(self, chunk_indices, tarea_id, ejecucion_id):
    """
    Procesa un chunk de índices SNMP:
    - timeout=6s, retries=1
    - actualiza OnuDato o marca para borrado
    """
    from ..models import TareaSNMP, EjecucionTareaSNMP

    close_old_connections()
    tarea = TareaSNMP.objects.get(id=tarea_id)
    ejec = EjecucionTareaSNMP.objects.get(id=ejecucion_id)

    updated = 0
    deleted = 0
    to_delete = []
    errors = []

    for idx in chunk_indices:
        oid = f"{tarea.get_oid()}.{idx}"
        try:
            errorIndication, errorStatus, _, varBinds = next(
                getCmd(
                    SnmpEngine(),
                    CommunityData(tarea.comunidad),
                    UdpTransportTarget((tarea.host_ip, 161), timeout=6, retries=1),
                    ContextData(),
                    ObjectType(ObjectIdentity(oid))
                )
            )
            if errorIndication:
                msg = str(errorIndication)
                if 'NoSuchObject' in msg or 'NoSuchInstance' in msg:
                    to_delete.append(idx)
                    deleted += 1
                else:
                    errors.append(f"{idx}: {msg}")
            elif errorStatus:
                errors.append(f"{idx}: {errorStatus.prettyPrint()}")
            else:
                val = varBinds[0][1].prettyPrint().strip('"')
                with transaction.atomic():
                    OnuDato.objects.filter(host=tarea.host_name, snmpindexonu=idx).update(
                        onudesc=val,
                        fecha=timezone.now()
                    )
                updated += 1
        except Exception as e:
            errors.append(f"{idx}: {e}")

    # Registramos resultados parciales en la ejecución
    ejec.parciales.create(
        updated=updated, deleted=deleted, errors=errors
    )

    return {'updated': updated, 'deleted': deleted, 'errors': errors}
