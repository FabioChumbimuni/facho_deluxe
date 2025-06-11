# snmp_scheduler/tasks/snmp_discovery.py

from celery import shared_task
from easysnmp import Session, EasySNMPError
from django.db import connection
from django.utils import timezone
from ..models import TareaSNMP, EjecucionTareaSNMP
from .common import logger

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
        # 1) Cargar tarea y crear registro de ejecución
        tarea = TareaSNMP.objects.get(pk=tarea_id)
        ejecucion = EjecucionTareaSNMP.objects.create(
            tarea=tarea,
            estado='E',
            inicio=timezone.now()
        )

        # 2) Actualizar última ejecución en la tarea
        tarea.ultima_ejecucion = timezone.now()
        tarea.save(update_fields=['ultima_ejecucion'])

        # 3) Preparar sesión EasySNMP y obtener el OID base de la tarea
        session = Session(
            hostname=tarea.host_ip,
            community=tarea.comunidad,
            version=2,
            timeout=6,
            retries=1
        )
        base_oid = tarea.get_oid()

        # 4) Hacer walk completo sobre el OID base
        try:
            vars = session.walk(base_oid)
        except EasySNMPError as e:
            raise Exception(f"SNMP walk error: {e}")

        # 5) Insertar o actualizar en bloque usando cursor
        with connection.cursor() as cursor:
            for var in vars:
                # var.oid: e.g.
                # 'iso.3.6.1.4.1.2011.6.128.1.1.2.46.1.1.4194315776.22'
                parts = var.oid.split('.')
                if len(parts) < 2:
                    logger.warning(f"[descubrimiento] OID demasiado corto: {var.oid}")
                    continue

                # Tomamos siempre las dos últimas sub-IDs
                snmpindexonu = f"{parts[-2]}.{parts[-1]}"
                act_susp = var.value.strip().strip('"')

                # Upsert: si ya existe combinación (snmpindexonu, host) la actualiza
                cursor.execute("""
                    INSERT INTO onu_datos (snmpindexonu, act_susp, host)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (snmpindexonu, host)
                    DO UPDATE SET act_susp = EXCLUDED.act_susp
                """, [snmpindexonu, act_susp, tarea.host_name])

        # 6) Marcar ejecución como completa
        ejecucion.estado = 'C'
        ejecucion.fin = timezone.now()
        ejecucion.save()
        return {"status": "success"}

    except Exception as e:
        logger.error(f"[descubrimiento] ERROR en tarea={tarea_id}: {e}", exc_info=True)
        if ejecucion:
            ejecucion.estado = 'F'
            ejecucion.fin = timezone.now()
            ejecucion.error = str(e)[:500]
            ejecucion.save()
        # Reintentar según política de Celery
        raise self.retry(exc=e)
