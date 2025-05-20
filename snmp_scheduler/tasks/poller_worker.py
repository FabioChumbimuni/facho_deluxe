import time
import logging

from celery import shared_task
from django.utils import timezone
from django.db import close_old_connections, transaction
from pysnmp.hlapi import (
    SnmpEngine, CommunityData, UdpTransportTarget,
    ContextData, ObjectType, ObjectIdentity, getCmd
)
from pysnmp.smi import builder

from ..models import OnuDato

logger = logging.getLogger(__name__)

@shared_task(
    bind=True,
    name='snmp_scheduler.poller_worker',
    soft_time_limit=600,        # ampliado a 10 minutos por chunk
    autoretry_for=(Exception,),
    retry_backoff=60,
    max_retries=2
)
def poller_worker(self, chunk_indices, tarea_id, ejecucion_id):
    """
    Procesa un chunk de índices SNMP:
      - timeout=6s, retries=1
      - no carga MIBs (solo OIDs numéricos)
      - control de ritmo para no saturar
      - actualiza OnuDato o marca para borrado
    """
    # Import tardío para evitar circularidades
    from ..models import TareaSNMP, EjecucionTareaSNMP

    # 1. Cerrar conexiones antiguas
    close_old_connections()

    # 2. Cargar metadata de tarea y ejecución
    tarea = TareaSNMP.objects.get(id=tarea_id)
    ejec = EjecucionTareaSNMP.objects.get(id=ejecucion_id)

    # 3. Preparar SNMP engine sin cargar MIBs
    snmp_engine = SnmpEngine()
    clean_mib_builder = builder.MibBuilder()
    snmp_engine.msgAndPduDsp.mibInstrumController.mibBuilder = clean_mib_builder

    updated = 0
    deleted = 0
    to_delete = []
    errors = []

    logger.info(f"[poller_worker] Inicio chunk {ejecucion_id} ({len(chunk_indices)} índices)")

    # 4. Procesar cada índice con un pequeño delay
    delay_between_queries = tarea.delay_segundos or 0.02  # configurable en modelo
    for idx in chunk_indices:
        oid = f"{tarea.get_oid()}.{idx}"
        try:
            errorIndication, errorStatus, _, varBinds = next(
                getCmd(
                    snmp_engine,
                    CommunityData(tarea.comunidad),
                    UdpTransportTarget((tarea.host_ip, 161), timeout=6, retries=1),
                    ContextData(),
                    # Solo OID numérico, sin nombres MIB
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
                    OnuDato.objects.filter(
                        host=tarea.host_name,
                        snmpindexonu=idx
                    ).update(onudesc=val, fecha=timezone.now())
                updated += 1

        except Exception as e:
            # Captura SoftTimeLimitExceeded, timeouts, etc.
            errors.append(f"{idx}: {e}")

        # 4.b Pausa corta para no inundar la OLT
        if delay_between_queries:
            time.sleep(delay_between_queries)

    # 5. Marcar eliminaciones en bloque
    if to_delete:
        with transaction.atomic():
            OnuDato.objects.filter(
                host=tarea.host_name,
                snmpindexonu__in=to_delete
            ).delete()

    # 6. Registrar resultados parciales
    ejec.parciales.create(updated=updated, deleted=deleted, errors=errors)

    logger.info(
        f"[poller_worker] Fin chunk {ejecucion_id}: "
        f"updated={updated}, deleted={deleted}, errors={len(errors)}"
    )

    # 7. Cerrar conexiones de BD
    close_old_connections()

    return {'updated': updated, 'deleted': deleted, 'errors': errors}
