# snmp_scheduler/tasks/poller_aggregator.py

import logging
from celery import shared_task
from django.utils import timezone
from django.db import transaction, close_old_connections
from ..models import TareaSNMP, EjecucionTareaSNMP, OnuDato, Host

logger = logging.getLogger(__name__)

@shared_task(name='snmp_scheduler.poller_aggregator')
def poller_aggregator(results, tarea_id, ejecucion_id, host_id):
    """
    Recibe la lista de dicts de cada worker, suma totales,
    borra índices inválidos y actualiza ejecución y tarea.
    """
    close_old_connections()
    tarea = TareaSNMP.objects.get(id=tarea_id)
    ejec = EjecucionTareaSNMP.objects.get(id=ejecucion_id)
    host = Host.objects.get(id=host_id)

    total_updated = sum(r['updated'] for r in results)
    total_deleted = sum(r['deleted'] for r in results)
    all_errors = [e for r in results for e in r['errors']]
    invalids = [i for r in results for i in r.get('to_delete', [])]

    if invalids:
        with transaction.atomic():
            OnuDato.objects.filter(
                host=host.nombre,
                snmpindexonu__in=invalids
            ).delete()
        logger.debug(f"[aggregator] Borrados {len(invalids)} índices inválidos")

    # Actualizar TareaSNMP
    tarea.ultima_ejecucion = timezone.now()
    tarea.registros_activos = total_updated
    tarea.save(update_fields=['ultima_ejecucion','registros_activos'])

    # Completar registro de EjecucionTareaSNMP
    ejec.fin = timezone.now()
    
    # Recolectar información del protocolo y errores
    protocol_info = {
        'used': any(r.get('protocol_info', {}).get('used', False) for r in results),
        'affected_lotes': sum(r.get('protocol_info', {}).get('affected_lotes', 0) for r in results),
        'host': host.nombre,
        'timeouts': []
    }
    
    # Procesar errores y timeouts
    processed_errors = []
    for r in results:
        # Agregar errores de timeout al protocolo
        for error in r.get('errors', []):
            if 'timeout' in error.lower() or 'timed out' in error.lower():
                protocol_info['timeouts'].append(error)
            else:
                processed_errors.append(error)
    
    # Determinar el estado final y mensaje
    if protocol_info['used']:
        protocol_info['message'] = (
            f"🛡️ PROTOCOL ANTI-TIMEOUT ACTIVADO\n"
            f"📊 Lotes procesados: {protocol_info['affected_lotes']}\n"
            f"🎯 Host: {host.nombre}"
        )
        if protocol_info['timeouts']:
            protocol_info['message'] += f"\n⚠️ Timeouts amortiguados: {len(protocol_info['timeouts'])}"
        ejec.estado = 'P'  # Parcial si se usó el protocolo
    else:
        protocol_info['message'] = (
            f"✅ PROCESO ESTÁNDAR\n"
            f"🎯 Host: {host.nombre}\n"
            f"📊 Registros actualizados: {total_updated}"
        )
        ejec.estado = 'C'  # Completado si no se usó el protocolo
    
    # Si hay errores no relacionados con timeout, marcar como parcial
    if processed_errors:
        ejec.estado = 'P'
        protocol_info['message'] += f"\n❌ Errores encontrados: {len(processed_errors)}"
    
    # Formatear el resultado final
    summary = f"📈 Actualizados: {total_updated} | 🗑️ Eliminados: {total_deleted} | ❌ Errores: {len(processed_errors)} | 🛡️ Protocolo: {'Activado' if protocol_info['used'] else 'No necesario'}"
    
    # Guardar el resultado completo en el log
    logger.info(f"[aggregator] Completada ejecución {ejecucion_id} para host {host.nombre}: {summary}")
    
    # Guardar solo el resumen en el resultado
    ejec.resultado = summary
    ejec.save()

    close_old_connections()
