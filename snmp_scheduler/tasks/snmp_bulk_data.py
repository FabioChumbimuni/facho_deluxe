# snmp_scheduler/tasks/snmp_bulk_data.py

from celery import shared_task
from django.utils import timezone
from django.db import transaction, close_old_connections, connections
from pysnmp.hlapi import (
    SnmpEngine, CommunityData, UdpTransportTarget,
    ContextData, ObjectType, ObjectIdentity, getCmd
)
from .common import logger
from ..models import TareaSNMP, EjecucionTareaSNMP, OnuDato

@shared_task(
    bind=True,
    name='snmp_scheduler.tasks.ejecutar_bulk_data',
    autoretry_for=(Exception,),
    max_retries=2,
    retry_backoff=180,
    queue='principal',
    soft_time_limit=300
)
def ejecutar_bulk_data(self, tarea_id):
    # 1. Crear registro de ejecución
    ejecucion = EjecucionTareaSNMP.objects.create(
        tarea_id=tarea_id,
        inicio=timezone.now(),
        estado='E'
    )

    try:
        # Asegurarnos de cerrar conexiones viejas
        close_old_connections()

        tarea = TareaSNMP.objects.get(id=tarea_id)
        logger.info(f"[bulk_data] Iniciando para host_name={tarea.host_name}")

        # 2. Cargar ONUs existentes
        onus = list(
            OnuDato.objects
                   .filter(host=tarea.host_name)
                   .values('snmpindexonu', 'id')
        )

        if not onus:
            logger.warning("[bulk_data] No ONUs para este host")
            ejecucion.estado = 'C'
            ejecucion.resultado = {'actualizadas': 0, 'eliminadas': 0}
            ejecucion.fin = timezone.now()
            ejecucion.save()
            return ejecucion.resultado

        base_oid   = tarea.get_oid()
        comunidad  = tarea.comunidad
        host_ip    = tarea.host_ip

        updated   = 0
        deleted   = 0

        # 3. Procesamiento secuencial
        for onu in onus:
            oid_full = f"{base_oid}.{onu['snmpindexonu']}"
            errorIndication, errorStatus, errorIndex, varBinds = next(
                getCmd(
                    SnmpEngine(),
                    CommunityData(comunidad),
                    UdpTransportTarget((host_ip, 161), timeout=3.0),
                    ContextData(),
                    ObjectType(ObjectIdentity(oid_full))
                )
            )
            if errorIndication:
                txt = str(errorIndication)
                if 'NoSuchObject' in txt or 'NoSuchInstance' in txt:
                    with transaction.atomic():
                        OnuDato.objects.filter(id=onu['id']).delete()
                    deleted += 1
                # otros errores los ignoramos aquí
            else:
                new_val = varBinds[0][1].prettyPrint().strip('"')
                with transaction.atomic():
                    OnuDato.objects.filter(id=onu['id']).update(
                        onudesc=new_val,
                        fecha=timezone.now()
                    )
                updated += 1

            # Cerrar la conexión tras cada iteración
            for conn in connections.all():
                conn.close()

        # 4. Actualizar metadatos de la tarea
        tarea.ultima_ejecucion   = timezone.now()
        tarea.registros_activos  = updated
        tarea.save(update_fields=['ultima_ejecucion','registros_activos'])

        # 5. Completar registro de ejecución
        ejecucion.fin       = timezone.now()
        ejecucion.estado    = 'C'
        ejecucion.resultado = {'actualizadas': updated, 'eliminadas': deleted}
        ejecucion.save()

        logger.info(f"[bulk_data] Completado: {ejecucion.resultado}")
        return ejecucion.resultado

    except Exception as e:
        logger.error(f"[bulk_data] ERROR crítico: {e}", exc_info=True)
        ejecucion.fin    = timezone.now()
        ejecucion.estado = 'F'
        ejecucion.error  = str(e)[:500]
        ejecucion.save()
        close_old_connections()
        raise self.retry(exc=e, countdown=180)
