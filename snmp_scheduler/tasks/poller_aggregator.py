from celery import shared_task
from django.utils import timezone
from django.db import transaction, close_old_connections
from ..models import TareaSNMP, EjecucionTareaSNMP, OnuDato

@shared_task(name='snmp_scheduler.poller_aggregator')
def poller_aggregator(results, tarea_id, ejecucion_id):
    """
    Callback que recibe la lista de resultados de cada worker,
    agrega totales, borra índices inválidos, y cierra la ejecución.
    """
    close_old_connections()
    tarea = TareaSNMP.objects.get(id=tarea_id)
    ejec = EjecucionTareaSNMP.objects.get(id=ejecucion_id)

    total_updated = sum(r['updated'] for r in results)
    total_deleted = sum(r['deleted'] for r in results)
    all_errors = [e for r in results for e in r['errors']]

    # Borrar en bloque los índices inválidos
    invalids = [idx for r in results for idx in r.get('to_delete', [])]
    if invalids:
        with transaction.atomic():
            OnuDato.objects.filter(host=tarea.host_name, snmpindexonu__in=invalids).delete()

    # Actualizar métricas de la tarea
    tarea.ultima_ejecucion = timezone.now()
    tarea.registros_activos = total_updated
    tarea.save(update_fields=['ultima_ejecucion', 'registros_activos'])

    # Completar la ejecución
    ejec.fin = timezone.now()
    ejec.estado = 'C'
    ejec.resultado = {
        'updated': total_updated,
        'deleted': total_deleted,
        'errors': all_errors
    }
    ejec.save()
