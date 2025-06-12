# snmp_scheduler/tasks/poller_worker.py

import logging
from celery import shared_task
from django.utils import timezone
from django.db import close_old_connections, transaction, connections
from easysnmp import Session, EasySNMPError, EasySNMPTimeoutError
from ..models import OnuDato, TareaSNMP, EjecucionTareaSNMP, Host
from .common import logger

TIPO_A_CAMPO = {
    'descubrimiento': 'act_susp',
    'onudesc': 'onudesc',
    'estado_onu': 'estado_onu',
    'plan_onu': 'plan_onu',  # Nuevo tipo para plan ONU
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
    soft_time_limit=120  # 2 minutos por lote
)
def poller_worker(self, tarea_id, ejecucion_id, indices, host_id):
    """
    Procesa un conjunto de índices SNMP para una tarea específica.
    
    Args:
        tarea_id: ID de la TareaSNMP
        ejecucion_id: ID de la EjecucionTareaSNMP
        indices: Lista de índices SNMP a consultar
        host_id: ID del Host a consultar
    """
    close_old_connections()

    try:
        # 1. Cargar tarea, ejecución y host
        tarea = TareaSNMP.objects.get(pk=tarea_id)
        ejec = EjecucionTareaSNMP.objects.get(pk=ejecucion_id)
        host = Host.objects.get(pk=host_id)

        # Validar que el host pertenece a la tarea
        if not tarea.hosts.filter(pk=host_id).exists():
            error_msg = f"Host {host_id} no pertenece a la tarea {tarea_id}"
            logger.error(error_msg)
            ejec.error = error_msg
            ejec.estado = 'F'
            ejec.fin = timezone.now()
            ejec.save()
            return {'updated': 0, 'deleted': 0, 'errors': [error_msg], 'to_delete': []}

        # Validaciones críticas PRIMERO
        if not tarea.get_oid():
            error_msg = f"Tarea {tarea_id} sin OID configurado"
            logger.error(error_msg)
            ejec.error = error_msg
            ejec.estado = 'F'
            ejec.fin = timezone.now()
            ejec.save()
            return {'updated': 0, 'deleted': 0, 'errors': [error_msg], 'to_delete': []}
            
        campo = TIPO_A_CAMPO.get(tarea.trabajo.tipo)
        if not campo:
            error_msg = f"Tipo {tarea.trabajo.tipo} no tiene campo destino definido"
            logger.error(error_msg)
            ejec.error = error_msg
            ejec.estado = 'F'
            ejec.fin = timezone.now()
            ejec.save()
            return {'updated': 0, 'deleted': 0, 'errors': [error_msg], 'to_delete': []}

        # Logs DEBUG después de validaciones
        logger.debug(f"[DEBUG] OID: {tarea.get_oid()}, Campo: {campo}")
        
        # Configuración SNMP con timeout ajustado según tipo
        timeout = 10 if tarea.trabajo.tipo == 'modelo_onu' else 6  # Mayor timeout para modelo_onu
        retries = 2 if tarea.trabajo.tipo == 'modelo_onu' else 1   # Más reintentos para modelo_onu
        
        session = Session(
            hostname=host.ip,
            community=host.comunidad,
            version=2,
            timeout=timeout,
            retries=retries
        )

        # Mapeo de índices
        recs = OnuDato.objects.filter(
            host=host.nombre,
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
            error_msg = f"Timeout SNMP en {host.ip}: {str(e)}"
            logger.error(error_msg)
            ejec.error = error_msg
            ejec.estado = 'F'
            ejec.fin = timezone.now()
            ejec.save()
            raise  # Permitir reintento para todos los tipos
            
        except EasySNMPError as e:
            error_msg = f"Error SNMP en {host.ip}: {str(e)}"
            logger.error(error_msg)
            ejec.error = error_msg
            ejec.estado = 'F'
            ejec.fin = timezone.now()
            ejec.save()
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
                try:
                    onu_actual = OnuDato.objects.get(id=onu_id)
                    valor_actual = getattr(onu_actual, campo, None)

                    # Si el valor no es -1, convertir a km y actualizar
                    if val != "-1":
                        try:
                            km = float(val) / 1000
                            nuevo_valor = f"{km:.3f} km"
                            with transaction.atomic():
                                OnuDato.objects.filter(id=onu_id).update(**{campo: nuevo_valor})
                                updated += 1
                                logger.debug(f"[DISTANCIA] Actualizado a {nuevo_valor} para {onu_id}")
                        except ValueError:
                            logger.error(f"Error convirtiendo distancia para {onu_id}")
                    else:
                        # Si es -1 y el valor actual también es -1, cambiar a No Distancia
                        if valor_actual == "-1":
                            with transaction.atomic():
                                OnuDato.objects.filter(id=onu_id).update(**{campo: "No Distancia"})
                                updated += 1
                                logger.debug(f"[DISTANCIA] Cambiado de -1 a No Distancia para {onu_id}")
                        else:
                            # Si es -1 pero el valor actual es diferente, mantener el valor actual
                            logger.debug(f"[DISTANCIA] Valor -1 recibido, manteniendo valor actual '{valor_actual}' para {onu_id}")

                except Exception as e:
                    logger.error(f"Error procesando distancia para {onu_id}: {str(e)}")
                    errors.append(f"Error en ONU {onu_id}: {str(e)}")
                    continue
            elif campo == 'plan_onu':
                try:
                    onu_actual = OnuDato.objects.get(id=onu_id)
                    valor_actual = getattr(onu_actual, campo)
                    logger.info(f"[PLAN_ONU] Procesando ONU {onu_id} - Valor actual: '{valor_actual}', Valor nuevo: '{val}'")
                    
                    if val and val.lower() not in ('no such', 'nosuchinstance', 'nosuchobject'):
                        # Si hay un valor nuevo válido, actualizarlo
                        with transaction.atomic():
                            OnuDato.objects.filter(id=onu_id).update(**{campo: val})
                            updated += 1
                            logger.debug(f"[PLAN_ONU] Actualizado plan_onu={val} ({onu_id})")
                    elif valor_actual:
                        # Si no hay valor nuevo pero hay valor actual, mantener el actual
                        updated += 1
                        logger.debug(f"[PLAN_ONU] Manteniendo plan actual '{valor_actual}' para {onu_id}")
                    else:
                        # Si no hay valor actual ni nuevo, poner No Plan
                        nuevo_valor = "No Plan"
                        with transaction.atomic():
                            OnuDato.objects.filter(id=onu_id).update(**{campo: nuevo_valor})
                            updated += 1
                            logger.debug(f"[PLAN_ONU] Actualizado plan_onu={nuevo_valor} (no había valor) ({onu_id})")
                except Exception as e:
                    logger.error(f"Error procesando plan_onu para {onu_id}: {str(e)}")
                    errors.append(f"Error en ONU {onu_id}: {str(e)}")
                    continue

            # Validación y actualización para otros tipos
            if not val or 'no such' in val.lower() or val.upper() in ('NOSUCHINSTANCE', 'NOSUCHOBJECT'):
                if tarea.trabajo.tipo == 'modelo_onu':
                    # Para modelo_onu, verificar si ya tiene un valor
                    try:
                        onu_actual = OnuDato.objects.get(id=onu_id)
                        valor_actual = getattr(onu_actual, campo)
                        if not valor_actual:
                            # Si no tiene valor, marcar como No Modelo
                            with transaction.atomic():
                                OnuDato.objects.filter(id=onu_id).update(**{campo: "No Modelo"})
                                updated += 1
                                logger.debug(f"[MODELO] Actualizado a No Modelo para {onu_id}")
                    except Exception as e:
                        logger.error(f"Error procesando modelo para {onu_id}: {str(e)}")
                        errors.append(f"Error en ONU {onu_id}: {str(e)}")
                continue

            # Actualización normal para otros tipos
            try:
                with transaction.atomic():
                    OnuDato.objects.filter(id=onu_id).update(**{campo: val})
                    updated += 1
                    logger.debug(f"[NORMAL] Actualizado {campo}={val} ({onu_id})")
            except Exception as e:
                logger.error(f"Error actualizando {campo} para {onu_id}: {str(e)}")
                errors.append(f"Error en ONU {onu_id}: {str(e)}")

        return {
            'updated': updated,
            'deleted': deleted,
            'errors': errors,
            'to_delete': to_delete
        }

    except Exception as e:
        logger.error(f"Error general en poller_worker: {str(e)}", exc_info=True)
        return {
            'updated': 0,
            'deleted': 0,
            'errors': [str(e)],
            'to_delete': []
        }