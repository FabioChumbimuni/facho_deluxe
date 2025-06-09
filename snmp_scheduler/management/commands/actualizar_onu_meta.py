# snmp_scheduler/management/commands/actualizar_onu_meta.py

import json
import os

from django.core.management.base import BaseCommand
from django.db import connection
from django.conf import settings

class Command(BaseCommand):
    help = "Actualiza snmpindex, onulogico y slotportonu usando el JSON de mapeo"

    def handle(self, *args, **options):
        json_path = os.path.join(settings.BASE_DIR, 'snmp_scheduler', 'data', 'snmpindex_slot.json')
        self.stdout.write(f"📄 Cargando mapeo desde {json_path}")

        with open(json_path, 'r') as f:
            mapping = json.load(f)

        # 1) Separar snmpindexonu en snmpindex y onulogico, casteando correctamente
        with connection.cursor() as cursor:
            cursor.execute("""
                UPDATE onu_datos
                SET
                  snmpindex = SPLIT_PART(snmpindexonu, '.', 1),
                  onulogico = CAST( SPLIT_PART(snmpindexonu, '.', 2) AS INTEGER )
                WHERE snmpindexonu LIKE '%.%';
            """)

        # 2) Construir un UPDATE CASE WHEN para slotportonu en una única consulta
        cases = " ".join(
            f"WHEN '{idx}' THEN '{slot}'"
            for idx, slot in mapping.items()
        )
        idx_list = ", ".join(f"'{idx}'" for idx in mapping.keys())

        update_sql = f"""
        UPDATE onu_datos
        SET slotportonu = CASE snmpindex
            {cases}
            ELSE slotportonu
        END
        WHERE snmpindex IN ({idx_list});
        """

        with connection.cursor() as cursor:
            cursor.execute(update_sql)

        self.stdout.write(self.style.SUCCESS("✅ Actualización completada correctamente"))
