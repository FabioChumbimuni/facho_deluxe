# snmp_scheduler/tasks/poller_aggregator.py

import logging
from celery import shared_task
from django.utils import timezone
from django.db import transaction, close_old_connections
from ..models import TareaSNMP, EjecucionTareaSNMP, OnuDato, Host

logger = logging.getLogger(__name__)

@shared_task(
    bind=True,
    name='snmp_scheduler.tasks.poller_aggregator',
    queue='principal'
)
def poller_aggregator(self, resultados, tarea_id, ejec_id, host_id):
    """
    Agrega los resultados de los workers y actualiza la ejecución.
    
    Args:
        resultados: Lista de resultados de los workers
        tarea_id: ID de la tarea
        ejec_id: ID de la ejecución
        host_id: ID del host procesado
    """
    close_old_connections()
    
    try:
        ejec = EjecucionTareaSNMP.objects.get(pk=ejec_id)
        
        # Verificar si el host sigue activo
        try:
            host = Host.objects.get(pk=host_id)
            if not host.activo:
                ejec.estado = 'F'
                ejec.error = f"Host {host.nombre} fue desactivado durante el procesamiento"
                ejec.fin = timezone.now()
                ejec.save()
                return
        except Host.DoesNotExist:
            ejec.estado = 'F'
            ejec.error = f"Host ID {host_id} no existe"
            ejec.fin = timezone.now()
            ejec.save()
            return
            
        # Agregar resultados
        updated = deleted = 0
        errors = []
        to_delete = []
        
        for resultado in resultados:
            if isinstance(resultado, dict):
                updated += resultado.get('updated', 0)
                deleted += resultado.get('deleted', 0)
                errors.extend(resultado.get('errors', []))
                to_delete.extend(resultado.get('to_delete', []))
        
        # Actualizar ejecución
        ejec.resultado = {
            'updated': updated,
            'deleted': deleted,
            'errors': errors,
            'to_delete': to_delete
        }
        
        if errors:
            ejec.estado = 'F'
            ejec.error = '\n'.join(errors)
        else:
            ejec.estado = 'C'
            
        ejec.fin = timezone.now()
        ejec.save()
        
    except Exception as e:
        logger.error(f"Error en aggregator: {str(e)}", exc_info=True)
        try:
            ejec = EjecucionTareaSNMP.objects.get(pk=ejec_id)
            ejec.estado = 'F'
            ejec.error = f"Error en aggregator: {str(e)}"
            ejec.fin = timezone.now()
            ejec.save()
        except:
            pass

    close_old_connections()
