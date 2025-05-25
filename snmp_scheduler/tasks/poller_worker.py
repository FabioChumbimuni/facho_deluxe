# snmp_scheduler/tasks/poller_worker.py

import logging
from celery import shared_task
from django.utils import timezone
from django.db import close_old_connections, transaction, connections
from easysnmp import Session, EasySNMPError
from ..models import OnuDato, TareaSNMP, EjecucionTareaSNMP
from .common import logger

TIPO_A_CAMPO = {
    'descubrimiento': 'act_susp',
    'onudesc': 'onudesc',
    'estado_onu': 'estado_onu',
    'last_down': 'ultima_desconexion',
    'pot_rx': 'potencia_rx',
    'pot_tx': 'potencia_tx', 
    'last_down_t': 'last_down_time',
    'distancia_m': 'distancia_m',
    'modelo_onu': 'modelo_onu'
}

@shared_task(
    bind=True,
    name='snmp_scheduler.tasks.poller_worker',
    autoretry_for=(Exception,),
    retry_backoff=30,
    max_retries=2,
    soft_time_limit=60
)
def poller_worker(self, tarea_id, ejecucion_id, indices):
    close_old_connections()

    tarea = TareaSNMP.objects.get(pk=tarea_id)
    ejec  = EjecucionTareaSNMP.objects.get(pk=ejecucion_id)

    # Validaciones críticas PRIMERO
    if not tarea.get_oid():
        logger.error(f"Tarea {tarea_id} sin OID configurado")
        return {'updated': 0, 'deleted': 0, 'errors': ["OID no configurado"], 'to_delete': []}
        
    campo = TIPO_A_CAMPO.get(tarea.tipo)  # 👈 Definir campo aquí
    if not campo:
        logger.error(f"Tipo {tarea.tipo} no tiene campo destino definido")
        return {'updated': 0, 'deleted': 0, 'errors': ["Campo destino desconocido"], 'to_delete': []}

    # Logs DEBUG después de validaciones
    logger.debug(f"[DEBUG] OID: {tarea.get_oid()}, Campo: {campo}")
    
    # Configuración SNMP
    session = Session(
        hostname=tarea.host_ip,
        community=tarea.comunidad,
        version=2,
        timeout=6,
        retries=1
    )

    # Mapeo de índices (usar host_name según modelo)
    recs = OnuDato.objects.filter(
        host=tarea.host_name,
        snmpindexonu__in=indices
    ).values('id', 'snmpindexonu')
    
    idx_to_id = {r['snmpindexonu']: r['id'] for r in recs}
    logger.info(f"Mapeados {len(idx_to_id)}/{len(indices)} índices")

    # Construcción y consulta OIDs
    base_oid = tarea.get_oid()
    oid_list = [f"{base_oid}.{idx}" for idx in indices]
    
    try:
        vars = session.get(oid_list)
    except EasySNMPError as e:
        logger.error(f"Error SNMP: {str(e)}")
        raise

    updated = deleted = 0
    errors = []
    to_delete = []

    # Procesar respuestas (¡Este bloque estaba en posición incorrecta!)
    for var in vars:
        parts = var.oid.split('.')
        if len(parts) < 2:
            errors.append(f"OID inválido: {var.oid}")
            continue
            
        idx = f"{parts[-2]}.{parts[-1]}"
        
        if idx not in idx_to_id:
            errors.append(f"Índice {idx} no existe en BD")
            continue

        onu_id = idx_to_id[idx]
        val = (var.value or "").strip().strip('"')

        if not val or 'no such' in val.lower() or val.upper() in ('NOSUCHINSTANCE', 'NOSUCHOBJECT'):
            to_delete.append(onu_id)
            deleted += 1
            logger.debug(f"Borrando {onu_id} (valor inválido)")
        else:
            try:
                with transaction.atomic():
                    OnuDato.objects.filter(id=onu_id).update(
                        **{campo: val, 'fecha': timezone.now()}
                    )
                    updated += 1
                    logger.debug(f"Actualizado {campo}={val} ({onu_id})")
            except Exception as e:
                errors.append(f"Error BD: {str(e)}")
                logger.error(f"Fallo actualizando {onu_id}: {str(e)}")

    if to_delete:
        OnuDato.objects.filter(id__in=to_delete).delete()
        logger.info(f"Eliminados {len(to_delete)} registros")

    logger.info(f"Ejecución {ejecucion_id}: {updated} act, {deleted} borr, {len(errors)} err")

    for conn in connections.all():
        conn.close()

    return {
        'updated': updated,
        'deleted': deleted,
        'errors': errors,
        'to_delete': to_delete,
    }