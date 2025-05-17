# snmp_scheduler/tasks/snmp_discovery.py

from celery import shared_task
from .common import (
    logger, SnmpEngine, CommunityData, UdpTransportTarget,
    ContextData, ObjectType, ObjectIdentity, nextCmd,
    timezone, connection
)
from ..models import TareaSNMP, EjecucionTareaSNMP

@shared_task(
    bind=True,
    name='snmp_scheduler.tasks.ejecutar_descubrimiento',
    autoretry_for=(Exception,),
    max_retries=2,
    retry_backoff=30,
    queue='secundario'
)
def ejecutar_descubrimiento(self, tarea_id):
    ejecucion = None
    try:
        tarea = TareaSNMP.objects.get(id=tarea_id)

        ejecucion = EjecucionTareaSNMP.objects.create(
            tarea=tarea,
            estado='E'
        )

        # ✅ ACTUALIZA ultima_ejecucion
        tarea.ultima_ejecucion = timezone.now()
        tarea.save(update_fields=['ultima_ejecucion'])

        iterator = nextCmd(
            SnmpEngine(),
            CommunityData(tarea.comunidad),
            UdpTransportTarget((tarea.host_ip, 161)),
            ContextData(),
            ObjectType(ObjectIdentity(tarea.get_oid())),
            lexicographicMode=False
        )

        with connection.cursor() as cursor:
            for errorIndication, errorStatus, errorIndex, varBinds in iterator:
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
        ejecucion.fin = timezone.now()
        ejecucion.save()
        return {"status": "success"}

    except Exception as e:
        logger.error(f"Error en descubrimiento: {str(e)}")
        if ejecucion:
            ejecucion.estado = 'F'
            ejecucion.fin = timezone.now()
            ejecucion.error = str(e)
            ejecucion.save()
        raise self.retry(exc=e)
