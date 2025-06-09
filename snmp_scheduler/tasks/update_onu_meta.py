# snmp_scheduler/tasks/update_onu_meta.py

from celery import shared_task
from django.conf import settings
from django.db import connection
import json, os
import logging

logger = logging.getLogger(__name__)

@shared_task(
    bind=True,
    name='snmp_scheduler.tasks.update_onu_meta'
)
def actualizar_onu_meta(self):
    """
    Divide snmpindexonu en snmpindex y onulogico (cast int), 
    y actualiza slotportonu usando un JSON de mapeo.
    """
    json_path = os.path.join(settings.BASE_DIR, 'snmp_scheduler', 'data', 'snmpindex_slot.json')
    logger.info(f"[update_onu_meta] Cargando mapeo desde {json_path}")
    with open(json_path) as f:
        mapping = json.load(f)

    with connection.cursor() as cursor:
        # 1) snmpindex (varchar) y onulogico (integer)
        cursor.execute("""
            UPDATE onu_datos
            SET
              snmpindex = SPLIT_PART(snmpindexonu, '.', 1),
              onulogico = CAST( SPLIT_PART(snmpindexonu, '.', 2) AS INTEGER )
            WHERE snmpindexonu LIKE '%.%';
        """)

        # 2) slotportonu con CASE … WHEN … THEN …
        # Construir CASE con comillas para varchar
        cases = "\n".join(
            f"    WHEN snmpindex = '{idx}' THEN '{slot}'"
            for idx, slot in mapping.items()
        )
        idx_list = ", ".join(f"'{idx}'" for idx in mapping.keys())

        sql = f"""
        UPDATE onu_datos
        SET slotportonu = CASE
{cases}
            ELSE slotportonu
        END
        WHERE snmpindex IN ({idx_list});
        """
        cursor.execute(sql)

    logger.info("[update_onu_meta] ✅ Actualización completada")
    return {"status": "ok"}
