# snmp_scheduler/tasks/poller_worker.py

import logging
from celery import shared_task
from django.utils import timezone
from django.db import close_old_connections, transaction, connections
from easysnmp import Session, EasySNMPError, EasySNMPTimeoutError
from ..models import OnuDato, TareaSNMP, EjecucionTareaSNMP, Host
from .common import logger
import time
from threading import Semaphore
from collections import defaultdict
from .host_verifier import verificar_host

# Control de concurrencia por OLT
olt_semaphores = defaultdict(lambda: Semaphore(5))  # Máximo 5 consultas simultáneas por OLT

TIPO_A_CAMPO = {
    'descubrimiento': 'act_susp',
    'onudesc': 'onudesc',
    'estado_onu': 'estado_onu',
    'plan_onu': 'plan_onu',
    'pot_rx': 'potencia_rx',
    'pot_tx': 'potencia_tx', 
    'last_down_t': 'last_down_time',
    'distancia_m': 'distancia_m',
    'modelo_onu': 'modelo_onu'
}

@shared_task(
    bind=True,
    name='snmp_scheduler.tasks.poller_worker',
    autoretry_for=(EasySNMPTimeoutError,),
    retry_backoff=30,
    max_retries=2,
    soft_time_limit=120,
    acks_late=True,
    reject_on_worker_lost=True,
    track_started=True
)
def poller_worker(self, tarea_id, ejecucion_id, indices, host_id):
    """
    Procesa un conjunto de índices SNMP para una tarea específica.
    """
    close_old_connections()
    ejec = None
    semaphore = None

    try:
        # 1. Cargar tarea, ejecución y host
        tarea = TareaSNMP.objects.get(pk=tarea_id)
        ejec = EjecucionTareaSNMP.objects.get(pk=ejecucion_id)
        host = Host.objects.get(pk=host_id)

        # Verificar si el host está activo
        if not host.activo:
            error_msg = f"Host {host.nombre} no está activo"
            logger.warning(error_msg)
            ejec.error = error_msg
            ejec.estado = 'F'
            ejec.fin = timezone.now()
            ejec.save()
            return {
                'updated': 0,
                'deleted': 0,
                'errors': [error_msg],
                'to_delete': []
            }

        # Obtener semáforo para esta OLT
        semaphore = olt_semaphores[host.ip]
        
        # Intentar adquirir el semáforo con timeout
        if not semaphore.acquire(timeout=30):  # Esperar máximo 30 segundos
            error_msg = f"Timeout esperando slot para OLT {host.nombre}"
            logger.error(error_msg)
            ejec.error = error_msg
            ejec.estado = 'F'
            ejec.fin = timezone.now()
            ejec.save()
            return {'updated': 0, 'deleted': 0, 'errors': [error_msg], 'to_delete': []}

        try:
            # Marcar como en ejecución
            ejec.estado = 'E'
            ejec.save(update_fields=['estado'])

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
            
            updated = deleted = 0
            errors = []
            to_delete = []
            timeout_indices = []
            max_retries = 2  # Máximo número de reintentos por índice
            retry_delay = 2  # Segundos entre reintentos

            def procesar_lote(indices_lote, es_reintento=False):
                nonlocal updated, deleted, errors, timeout_indices
                
                # Verificar si el host sigue activo
                try:
                    host.refresh_from_db()
                    if not host.activo:
                        error_msg = f"Host {host.nombre} fue desactivado durante el procesamiento"
                        logger.warning(error_msg)
                        errors.append(error_msg)
                        return False
                except Host.DoesNotExist:
                    error_msg = f"Host {host.nombre} fue eliminado durante el procesamiento"
                    logger.error(error_msg)
                    errors.append(error_msg)
                    return False
                
                oid_list_lote = [f"{base_oid}.{idx}" for idx in indices_lote]
                
                try:
                    vars = session.get(oid_list_lote)
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
                        
                        # Verificar si es un error de "No Such Instance" o similar
                        if (val.lower() in ["no such instance currently exists at this oid", 
                                          "no such instance", 
                                          "nosuchinstance", 
                                          "nosuchobject"] or 
                            "no such" in val.lower()):
                            try:
                                with transaction.atomic():
                                    OnuDato.objects.filter(id=onu_id).delete()
                                    deleted += 1
                                    logger.debug(f"[DELETE] Eliminada ONU {onu_id} por No Such Instance. Valor recibido: '{val}'")
                                    continue
                            except Exception as e:
                                logger.error(f"Error eliminando ONU {onu_id}: {str(e)}")
                                errors.append(f"Error eliminando ONU {onu_id}: {str(e)}")
                                continue

                        # Procesamiento específico por tipo de campo
                        if campo == 'distancia_m':
                            try:
                                # Limpiar el valor recibido
                                val = val.strip() if val else ""

                                # Obtener el valor actual
                                onu_actual = OnuDato.objects.get(id=onu_id)
                                valor_actual = getattr(onu_actual, campo)

                                # Si el valor es -1
                                if val == "-1":
                                    if not valor_actual:
                                        # Si no hay valor actual, poner No Distancia
                                        with transaction.atomic():
                                            OnuDato.objects.filter(id=onu_id).update(**{campo: "No Distancia"})
                                            updated += 1
                                            logger.debug(f"[DISTANCIA] Actualizado a No Distancia para {onu_id} (valor inicial)")
                                    else:
                                        # Si hay valor actual, mantenerlo
                                        logger.debug(f"[DISTANCIA] Valor -1 recibido, manteniendo valor actual '{valor_actual}' para {onu_id}")
                                    continue

                                # Si el valor no es -1
                                try:
                                    # Verificar si ya tiene formato de kilómetros
                                    if '.' in val:
                                        nuevo_valor = f"{val} km"
                                    else:
                                        # Si es un valor en metros, convertir a kilómetros
                                        metros = float(val)
                                        km = metros / 1000
                                        nuevo_valor = f"{km:.3f} km"

                                    # Solo actualizar si el valor actual es "No Distancia" o no existe
                                    if not valor_actual or valor_actual == "No Distancia":
                                        with transaction.atomic():
                                            OnuDato.objects.filter(id=onu_id).update(**{campo: nuevo_valor})
                                            updated += 1
                                            logger.debug(f"[DISTANCIA] Actualizado a {nuevo_valor} para {onu_id}")
                                    else:
                                        logger.debug(f"[DISTANCIA] Manteniendo valor actual '{valor_actual}' para {onu_id}")

                                except ValueError:
                                    logger.error(f"Error procesando distancia para {onu_id}: valor={val}")
                                    errors.append(f"Error procesando distancia para ONU {onu_id}")

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

                        elif tarea.trabajo.tipo == 'modelo_onu' and (not val or 'no such' in val.lower() or val.upper() in ('NOSUCHINSTANCE', 'NOSUCHOBJECT')):
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
                        elif val and 'no such' not in val.lower() and val.upper() not in ('NOSUCHINSTANCE', 'NOSUCHOBJECT'):
                            try:
                                with transaction.atomic():
                                    OnuDato.objects.filter(id=onu_id).update(**{campo: val})
                                    updated += 1
                                    logger.debug(f"[NORMAL] Actualizado {campo}={val} ({onu_id})")
                            except Exception as e:
                                logger.error(f"Error actualizando {campo} para {onu_id}: {str(e)}")
                                errors.append(f"Error en ONU {onu_id}: {str(e)}")
                    return True
                except EasySNMPTimeoutError as e:
                    error_msg = f"Timeout SNMP en {host.ip}: {str(e)}"
                    logger.error(error_msg)
                    if not es_reintento:
                        logger.info(f"Timeout en lote de {len(indices_lote)} índices")
                    return False
                except EasySNMPError as e:
                    error_msg = f"Error SNMP en {host.ip}: {str(e)}"
                    logger.error(error_msg)
                    errors.append(error_msg)
                    return False

            # Si es un lote grande (200), intentamos procesarlo en subgrupos
            protocol_used = False
            protocol_lotes = 0
            
            if len(indices) >= 200:
                logger.info(f"[PROCESO ESTANDAR] Iniciando procesamiento de lote grande ({len(indices)} índices) para host {host.nombre}")
                
                # Verificar estado del host antes del lote principal
                host.refresh_from_db()
                if not host.activo:
                    error_msg = f"Host {host.nombre} desactivado antes de procesar lote principal"
                    logger.warning(error_msg)
                    errors.append(error_msg)
                    return {
                        'updated': updated,
                        'deleted': deleted,
                        'errors': errors,
                        'to_delete': to_delete,
                        'timeout_indices': timeout_indices
                    }
                
                # Primero intentamos con el lote completo
                if not procesar_lote(indices):
                    protocol_used = True
                    protocol_lotes += 1
                    logger.info(f"[PROTOCOL ANTI-TIMEOUT] {host.nombre} - Timeout detectado en lote principal, iniciando protocolo de subgrupos")
                    
                    # Activar protocolo verificador
                    verificar_host.delay(host_id=host.id)
                    
                    # Dividimos en subgrupos de 50
                    subgrupos = [indices[i:i + 50] for i in range(0, len(indices), 50)]
                    logger.info(f"[PROTOCOL ANTI-TIMEOUT] {host.nombre} - Lote principal dividido en {len(subgrupos)} subgrupos de 50 índices")
                    
                    for i, subgrupo in enumerate(subgrupos, 1):
                        # Verificar estado del host antes de cada subgrupo
                        host.refresh_from_db()
                        if not host.activo:
                            error_msg = f"Host {host.nombre} desactivado durante procesamiento de subgrupos"
                            logger.warning(error_msg)
                            errors.append(error_msg)
                            break
                            
                        logger.info(f"[PROTOCOL ANTI-TIMEOUT] {host.nombre} - Procesando subgrupo {i}/{len(subgrupos)} ({len(subgrupo)} índices)")
                        if not procesar_lote(subgrupo):
                            protocol_lotes += 1
                            logger.info(f"[PROTOCOL ANTI-TIMEOUT] {host.nombre} - Timeout en subgrupo {i}, iniciando procesamiento individual")
                            # Si falla el subgrupo, intentamos uno por uno con reintentos
                            for idx in subgrupo:
                                # Verificar estado del host antes de cada índice individual
                                host.refresh_from_db()
                                if not host.activo:
                                    error_msg = f"Host {host.nombre} desactivado durante procesamiento individual"
                                    logger.warning(error_msg)
                                    errors.append(error_msg)
                                    break
                                    
                                retry_count = 0
                                while retry_count < max_retries:
                                    try:
                                        if procesar_lote([idx], es_reintento=(retry_count > 0)):
                                            logger.debug(f"[PROTOCOL ANTI-TIMEOUT] {host.nombre} - Índice {idx} procesado exitosamente")
                                            break
                                        else:
                                            retry_count += 1
                                            if retry_count < max_retries:
                                                logger.info(f"[PROTOCOL ANTI-TIMEOUT] {host.nombre} - Reintentando índice {idx} (intento {retry_count + 1}/{max_retries})")
                                                time.sleep(retry_delay)
                                            else:
                                                timeout_indices.append(idx)
                                                logger.error(f"[PROTOCOL ANTI-TIMEOUT] {host.nombre} - Timeout en índice {idx} después de {max_retries} intentos")
                                    except Exception as e:
                                        logger.error(f"[PROTOCOL ANTI-TIMEOUT] {host.nombre} - Error procesando índice {idx}: {str(e)}")
                                        errors.append(f"Error en índice {idx}: {str(e)}")
                                        break
                        else:
                            logger.info(f"[PROTOCOL ANTI-TIMEOUT] {host.nombre} - Subgrupo {i} procesado exitosamente")
                else:
                    logger.info(f"[PROTOCOL ANTI-TIMEOUT] {host.nombre} - Proceso estándar completado para {host.nombre}")
            else:
                # Para lotes pequeños, verificar estado del host y procesar normalmente
                host.refresh_from_db()
                if not host.activo:
                    error_msg = f"Host {host.nombre} desactivado antes de procesar lote pequeño"
                    logger.warning(error_msg)
                    errors.append(error_msg)
                else:
                    logger.info(f"[PROCESO ESTANDAR] Procesando lote pequeño ({len(indices)} índices) para host {host.nombre}")
                    procesar_lote(indices)

            # Actualizar estado de ejecución
            if errors or timeout_indices:
                if timeout_indices:
                    errors.append(f"[PROTOCOL ANTI-TIMEOUT] {host.nombre} - Timeout en índices después de {max_retries} intentos: {', '.join(timeout_indices)}")
                ejec.error = "\n".join(errors)
                ejec.estado = 'F'  # Fallido si hay errores o timeouts
                ejec.fin = timezone.now()
                ejec.save()
            else:
                # Si no hay errores, marcar como completada
                ejec.estado = 'C'
                ejec.fin = timezone.now()
                ejec.save()

            result = {
                'updated': updated,
                'deleted': deleted,
                'errors': errors,
                'to_delete': to_delete,
                'timeout_indices': timeout_indices
            }

            if protocol_used:
                result['protocol_info'] = {
                    'used': True,
                    'host': host.nombre,
                    'affected_lotes': protocol_lotes,
                    'message': f"Se utilizó PROTOCOL ANTI-TIMEOUT en {protocol_lotes} lotes para {host.nombre}"
                }
            else:
                result['protocol_info'] = {
                    'used': False,
                    'host': host.nombre,
                    'message': f"Proceso estándar completado para {host.nombre}"
                }

            return result

        finally:
            # Liberar el semáforo al terminar
            if semaphore:
                semaphore.release()

    except Exception as e:
        logger.error(f"Error general en poller_worker: {str(e)}", exc_info=True)
        if ejec:
            ejec.error = str(e)
            ejec.estado = 'F'
            ejec.fin = timezone.now()
            ejec.save()
        if semaphore:
            semaphore.release()
        return {
            'updated': 0,
            'deleted': 0,
            'errors': [str(e)],
            'to_delete': []
        }