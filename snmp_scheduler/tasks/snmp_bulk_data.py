# snmp_scheduler/tasks/snmp_bulk_data.py
from celery import shared_task
from pysnmp.hlapi import *
from django.utils import timezone
from django.db import transaction
from .common import logger, get_snmp_engine
from ..models import TareaSNMP, EjecucionTareaSNMP, OnuDato

@shared_task(
    bind=True,
    name='snmp_scheduler.tasks.ejecutar_bulk_data',
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=60,
    queue='principal',
    soft_time_limit=300
)
def ejecutar_bulk_data(self, tarea_id):
    start_time = timezone.now()
    ejecucion = EjecucionTareaSNMP.objects.create(
        tarea_id=tarea_id,
        inicio=start_time,
        estado='E'  # Estado 'En ejecución'
    )
    
    try:
        tarea = TareaSNMP.objects.get(id=tarea_id)
        oid_base = tarea.get_oid()  # Obtiene 1.3.6.1.4.1.2011.6.128.1.1.2.43.1.9
        
        # 1. Configurar parámetros SNMP
        snmp_engine = get_snmp_engine()
        community = CommunityData(tarea.comunidad)
        target = UdpTransportTarget((tarea.host_ip, 161), timeout=10.0)
        
        # 2. Ejecutar GETBULK con max_repetitions=10
        bulk_generator = bulkCmd(
            snmp_engine,
            community,
            target,
            ContextData(),
            0,  # nonRepeaters
            10,  # maxRepetitions (¡valor solicitado!)
            ObjectType(ObjectIdentity(oid_base)),
            lexicographicMode=False,
            lookupMib=False  # Deshabilitar resolución MIB
        )
        
        # 3. Procesar respuestas
        onu_updates = {}
        for (error_indication, error_status, error_index, var_binds) in bulk_generator:
            if error_indication:
                logger.error(f"Error SNMP: {error_indication}")
                continue

            for var_bind in var_binds:
                try:
                    oid_parts = var_bind[0].prettyPrint().split('.')
                    snmpindexonu = '.'.join(oid_parts[-2:])  # Últimos 2 componentes
                    onudesc = var_bind[1].prettyPrint().strip('"')
                    onu_updates[snmpindexonu] = onudesc
                except Exception as e:
                    logger.error(f"Error procesando OID: {str(e)}")

        # 4. Actualización masiva en base de datos
        with transaction.atomic():
            # Usar el nombre correcto del campo host (no host_ip)
            onus = OnuDato.objects.filter(host=tarea.host_ip)
            
            # Actualizar solo onudesc usando valores del diccionario
            for onu in onus:
                new_desc = onu_updates.get(onu.snmpindexonu)
                if new_desc:
                    # ✅ Asignación explícita solo a onudesc
                    OnuDato.objects.filter(pk=onu.id).update(onudesc=new_desc)
                    
            # Marcar ONUs no respondidas (actualizar solo onudesc)
            OnuDato.objects.filter(
                host=tarea.host_ip,
                snmpindexonu__in=[k for k in onu_updates if not onu_updates[k]]
            ).update(onudesc='NO_RESPONSE')

        # 5. Actualizar estado final
        ejecucion.fin = timezone.now()
        ejecucion.estado = 'C'  # 'Completada'
        ejecucion.save()
        
        # Actualizar última ejecución en tarea
        tarea.ultima_ejecucion = start_time
        tarea.save(update_fields=['ultima_ejecucion'])
        
        return {"actualizadas": len(update_list), "no_respondidas": onus.count() - len(responded_ids)}

    except Exception as e:
        logger.error(f"Error en bulk data: {str(e)}")
        ejecucion.estado = 'F'  # 'Fallida'
        ejecucion.error = str(e)[:500]  # Limitar tamaño
        ejecucion.fin = timezone.now()
        ejecucion.save()
        raise self.retry(exc=e)