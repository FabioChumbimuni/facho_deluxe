# snmp_scheduler/tasks/poller_worker.py

import logging
from celery import shared_task
from django.utils import timezone
from django.db import close_old_connections, transaction, connections
from easysnmp import Session, EasySNMPError, EasySNMPTimeoutError
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
    autoretry_for=(EasySNMPTimeoutError,),  # Solo reintentamos timeouts
    retry_backoff=30,
    max_retries=2,
    soft_time_limit=120  # Aumentamos el límite de tiempo
)
def poller_worker(self, tarea_id, ejecucion_id, indices):
    close_old_connections()

    try:
        tarea = TareaSNMP.objects.get(pk=tarea_id)
        ejec = EjecucionTareaSNMP.objects.get(pk=ejecucion_id)

        # Validaciones críticas PRIMERO
        if not tarea.get_oid():
            error_msg = f"Tarea {tarea_id} sin OID configurado"
            logger.error(error_msg)
            ejec.error = error_msg
            ejec.estado = 'F'
            ejec.fin = timezone.now()
            ejec.save()
            return {'updated': 0, 'deleted': 0, 'errors': [error_msg], 'to_delete': []}
            
        campo = TIPO_A_CAMPO.get(tarea.tipo)
        if not campo:
            error_msg = f"Tipo {tarea.tipo} no tiene campo destino definido"
            logger.error(error_msg)
            ejec.error = error_msg
            ejec.estado = 'F'
            ejec.fin = timezone.now()
            ejec.save()
            return {'updated': 0, 'deleted': 0, 'errors': [error_msg], 'to_delete': []}

        # Logs DEBUG después de validaciones
        logger.debug(f"[DEBUG] OID: {tarea.get_oid()}, Campo: {campo}")
        
        # Configuración SNMP con timeout mínimo de 6 segundos
        session = Session(
            hostname=tarea.host_ip,
            community=tarea.comunidad,
            version=2,
            timeout=6,  # Timeout mínimo de 6 segundos
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
        except EasySNMPTimeoutError as e:
            error_msg = f"Timeout SNMP en {tarea.host_ip}: {str(e)}"
            logger.error(error_msg)
            # Registramos el error en la ejecución
            ejec.error = error_msg
            ejec.estado = 'F'
            ejec.fin = timezone.now()
            ejec.save()
            # Registramos "No identificado" en los ONUs afectados
            with transaction.atomic():
                OnuDato.objects.filter(
                    host=tarea.host_name,
                    snmpindexonu__in=indices
                ).update(**{campo: "No identificado", 'fecha': timezone.now()})
            raise  # Permitimos el reintento
        except EasySNMPError as e:
            error_msg = f"Error SNMP en {tarea.host_ip}: {str(e)}"
            logger.error(error_msg)
            ejec.error = error_msg
            ejec.estado = 'F'
            ejec.fin = timezone.now()
            ejec.save()
            # Registramos "No identificado" en los ONUs afectados
            with transaction.atomic():
                OnuDato.objects.filter(
                    host=tarea.host_name,
                    snmpindexonu__in=indices
                ).update(**{campo: "No identificado", 'fecha': timezone.now()})
            return {'updated': 0, 'deleted': 0, 'errors': [error_msg], 'to_delete': []}

        updated = deleted = 0
        errors = []
        to_delete = []

        # Procesar respuestas
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
            
            if campo == 'distancia_m':
                if val == "-1":
                    val = "No Distancia"
                else:
                    try:
                        km = float(val) / 1000
                        val = f"{km:.3f} km"
                    except:
                        val = "Error formato"

            # Validación y actualización
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
                    error_msg = f"Error BD: {str(e)}"
                    errors.append(error_msg)
                    logger.error(f"Fallo actualizando {onu_id}: {str(e)}")
                    # Registramos "No identificado" para este ONU
                    try:
                        OnuDato.objects.filter(id=onu_id).update(
                            **{campo: "No identificado", 'fecha': timezone.now()}
                        )
                    except:
                        pass

        if to_delete:
            OnuDato.objects.filter(id__in=to_delete).delete()
            logger.info(f"Eliminados {len(to_delete)} registros")

        logger.info(f"Ejecución {ejecucion_id}: {updated} act, {deleted} borr, {len(errors)} err")

        # Actualizar estado de ejecución
        ejec.fin = timezone.now()
        ejec.estado = 'C' if not errors else 'F'
        ejec.error = '\n'.join(errors) if errors else None
        ejec.resultado = {
            'updated': updated,
            'deleted': deleted,
            'errors': errors,
            'to_delete': to_delete,
        }
        ejec.save()

    finally:
        for conn in connections.all():
            conn.close()

    return {
        'updated': updated,
        'deleted': deleted,
        'errors': errors,
        'to_delete': to_delete,
    }