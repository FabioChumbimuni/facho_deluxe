# tasks.py (versión mejorada)
from __future__ import absolute_import
from celery import shared_task
from pysnmp.hlapi import *
from django.utils import timezone
from datetime import timedelta
from django.db import connection
from .models import TareaSNMP, OnuDato, EjecucionTareaSNMP
from celery.utils.log import get_logger

logger = get_logger(__name__)

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=60,
    soft_time_limit=120,
    queue='principal'
)
def ejecutar_tarea_snmp(self, tarea_id):
    """Tarea principal para consultas SNMP regulares"""
    try:
        logger.info(f"Iniciando tarea SNMP ID: {tarea_id}")
        tarea = TareaSNMP.objects.get(id=tarea_id)
        ejecucion = EjecucionTareaSNMP.objects.create(
            tarea=tarea,
            estado='E'
        )
        
        # Actualizar timestamp
        tarea.ultima_ejecucion = timezone.now()
        tarea.save(update_fields=['ultima_ejecucion'])
        
        # Configuración SNMP
        iterator = nextCmd(
            SnmpEngine(),
            CommunityData(tarea.comunidad),
            UdpTransportTarget((tarea.host_ip, 161), timeout=10, retries=2),
            ContextData(),
            ObjectType(ObjectIdentity(tarea.oid_consulta)),
            lexicographicMode=False
        )
        
        processed = 0
        for (errorIndication, errorStatus, errorIndex, varBinds) in iterator:
            if errorIndication:
                raise Exception(f"Error SNMP: {errorIndication}")
            if errorStatus:
                raise Exception(f"Error en respuesta: {errorStatus.prettyPrint()}")
            
            for varBind in varBinds:
                oid_str = varBind[0].prettyPrint()
                snmpindexonu = oid_str.split(tarea.oid_consulta + '.')[-1]
                
                OnuDato.objects.update_or_create(
                    tarea=tarea,
                    snmpindexonu=snmpindexonu,
                    defaults={
                        'host_name': tarea.host_name,
                        'host_ip': tarea.host_ip,
                        'act_susp': varBind[1].prettyPrint(),
                        'onudesc': f"ONU {snmpindexonu}"
                    }
                )
                processed += 1
        
        ejecucion.estado = 'C'
        ejecucion.resultado = {'processed': processed}
        ejecucion.save()
        return {'status': 'success', 'processed': processed}
        
    except TareaSNMP.DoesNotExist:
        logger.error(f"Tarea {tarea_id} no existe")
        return {'status': 'error', 'message': 'Tarea no existe'}
    except Exception as e:
        logger.error(f"Error en tarea {tarea_id}: {str(e)}")
        ejecucion.estado = 'F'
        ejecucion.error = str(e)
        ejecucion.save()
        raise self.retry(exc=e)

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    max_retries=2,
    retry_backoff=30,
    queue='secundario'
)
def ejecutar_descubrimiento(self, tarea_id):
    """Tarea secundaria para descubrimiento de dispositivos"""
    try:
        tarea = TareaSNMP.objects.get(id=tarea_id)
        ejecucion = EjecucionTareaSNMP.objects.create(
            tarea=tarea,
            estado='E'
        )
        
        iterator = nextCmd(
            SnmpEngine(),
            CommunityData(tarea.comunidad),
            UdpTransportTarget((tarea.host_ip, 161)),
            ContextData(),
            ObjectType(ObjectIdentity(tarea.get_oid())),
            lexicographicMode=False
        )

        with connection.cursor() as cursor:
            for (errorIndication, errorStatus, errorIndex, varBinds) in iterator:
                if errorIndication:
                    raise Exception(f"Error SNMP: {errorIndication}")
                
                for varBind in varBinds:
                    oid_parts = varBind[0].prettyPrint().split('.')
                    snmpindexonu = '.'.join(oid_parts[-2:])
                    act_susp = varBind[1].prettyPrint()

                    cursor.execute("""
                        INSERT INTO onu_datos 
                            (snmpindexonu, act_susp, host)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (snmpindexonu, host) 
                        DO UPDATE SET 
                            act_susp = EXCLUDED.act_susp
                    """, [snmpindexonu, act_susp, tarea.host_name])
        
        ejecucion.estado = 'C'
        ejecucion.save()
        return {"status": "success"}
        
    except Exception as e:
        logger.error(f"Error en descubrimiento: {str(e)}")
        ejecucion.estado = 'F'
        ejecucion.error = str(e)
        ejecucion.save()
        raise self.retry(exc=e)

@shared_task(queue='principal')
def ejecutar_tareas_programadas():
    """Ejecutor principal de tareas programadas"""
    ahora = timezone.localtime()
    intervalo_actual = f"{ahora.minute // 15 * 15:02d}"
    
    tareas = TareaSNMP.objects.filter(
        activa=True,
        intervalo=intervalo_actual,
        ultima_ejecucion__lte=ahora - timedelta(minutes=14)
    )
    
    for tarea in tareas:
        ejecutar_descubrimiento.apply_async(
            args=[tarea.id],
            queue='secundario'
        )