# snmp_scheduler/tasks/poller_worker.py

import logging
from celery import shared_task
from django.utils import timezone
from django.db import close_old_connections, transaction, connections
from easysnmp import Session, EasySNMPError
from ..models import OnuDato, TareaSNMP, EjecucionTareaSNMP
from .common import logger

@shared_task(
    bind=True,
    name='snmp_scheduler.tasks.poller_worker',
    autoretry_for=(Exception,),
    retry_backoff=30,
    max_retries=2,
    soft_time_limit=60
)
def poller_worker(self, tarea_id, ejecucion_id, indices):
    """
    Procesa un chunk de índices SNMP para la tarea y ejecución dadas.
    - tarea_id: PK de TareaSNMP
    - ejecucion_id: PK de EjecucionTareaSNMP
    - indices: lista de snmpindexonu (strings, p.ej. '4194312192.1', '4194312192.2', ...)
    """
    close_old_connections()

    # 1) Carga de objetos
    tarea = TareaSNMP.objects.get(id=tarea_id)
    ejec  = EjecucionTareaSNMP.objects.get(id=ejecucion_id)

    # 2) Sesión SNMP
    session = Session(
        hostname=tarea.host_ip,
        community=tarea.comunidad,
        version=2,
        timeout=6
    )
    base_oid = tarea.get_oid()  # e.g. '1.3.6.1.4.1.2011.6.128.1.1.2.43.1.9'

    # 3) Mapeo de índices a IDs de OnuDato
    recs = OnuDato.objects.filter(
        host=tarea.host_name,
        snmpindexonu__in=indices
    ).values('id', 'snmpindexonu')
    idx_to_id = {r['snmpindexonu']: r['id'] for r in recs}

    updated = deleted = 0
    errors = []
    to_delete = []

    logger.info(f"[poller_worker] Inicio ejecución={ejecucion_id}, {len(indices)} índices")

    # 4) Construir lista de OIDs completas
    oid_list = [f"{base_oid}.{idx}" for idx in indices]

    # 5) Hacer la consulta SNMP de golpe
    try:
        vars = session.get(oid_list)
    except EasySNMPError as e:
        logger.error(f"[poller_worker] SNMP error ejecución={ejecucion_id}: {e}", exc_info=True)
        raise  # para que Celery reprograme según retry_backoff

    # 6) Procesar respuestas
    for var in vars:
        # Ejemplo var.oid: 'iso.3.6.1.4.1.2011.6.128.1.1.2.43.1.9.4194312192.1'
        parts = var.oid.split('.')
        if len(parts) < 2:
            errors.append(f"{var.oid}: formato de OID inesperado")
            continue
        # Tomamos las dos últimas sub-IDs para reconstruir el índice compuesto
        idx = f"{parts[-2]}.{parts[-1]}"

        if idx not in idx_to_id:
            errors.append(f"{idx}: índice no mapeado")
            continue

        onu_id = idx_to_id[idx]
        val = var.value or ""
        if val.lower().startswith('no such'):
            to_delete.append(onu_id)
            deleted += 1
        else:
            # Actualizamos el onudesc con el valor obtenido
            with transaction.atomic():
                OnuDato.objects.filter(id=onu_id).update(
                    onudesc=val,
                    fecha=timezone.now()
                )
            updated += 1

    # 7) Borrar registros inválidos de una vez
    if to_delete:
        OnuDato.objects.filter(id__in=to_delete).delete()
        logger.debug(f"[poller_worker] Eliminados {len(to_delete)} registros inválidos")

    logger.info(
        f"[poller_worker] Fin ejecución={ejecucion_id}: "
        f"updated={updated}, deleted={deleted}, errors={len(errors)}"
    )

    # 8) Cerrar conexiones Django
    for conn in connections.all():
        conn.close()

    return {
        'updated': updated,
        'deleted': deleted,
        'errors': errors,
        'to_delete': to_delete,
    }
