# facho_deluxe/management/commands/process_tasks.py
import time
import datetime
from django.core.management.base import BaseCommand
from django_q.tasks import async_task
from scripts.models import Script, ExecutionRecord
from scripts.tasks import ejecutar_script, can_run_script, script_executado

class Command(BaseCommand):
    help = 'Procesa continuamente la cola de scripts, lanzando nuevos scripts cuando otros finalizan.'

    def handle(self, *args, **options):
        self.stdout.write("Iniciando el procesamiento continuo de scripts...")
        while True:
            # Actualizar el estado consultando la base de datos
            pendientes_principales = list(Script.objects.filter(tipo='principal').order_by('orden'))
            pendientes_secundarios = list(Script.objects.filter(tipo='secundario').order_by('orden'))
            script_modo = Script.objects.filter(tipo='modo').first()

            # Fase 1: Ejecutar scripts principales (máximo 2 en paralelo)
            for script in pendientes_principales:
                if not script_executado(script) and can_run_script('principal', 2):
                    async_task(ejecutar_script, script.id)
            
            # Mientras haya principales en ejecución, ejecutar 1 script secundario (solo uno en esta fase)
            for script in pendientes_secundarios:
                if not script_executado(script) and can_run_script('secundario', 1):
                    async_task(ejecutar_script, script.id)
                    break  # Se lanza solo uno en esta fase

            # Si ya no hay scripts principales pendientes, procesar el script modo (si existe)
            if not pendientes_principales and script_modo and not script_executado(script_modo):
                async_task(ejecutar_script, script_modo.id)
                # Esperar a que finalice el script modo antes de continuar
                while ExecutionRecord.objects.filter(script=script_modo, estado='en ejecución').exists():
                    time.sleep(5)

            # Fase 2: Si ya no hay principales pendientes ni modo en ejecución, ejecutar secundarios restantes en lotes de 3
            if not pendientes_principales and (not script_modo or script_executado(script_modo)):
                for script in pendientes_secundarios:
                    if not script_executado(script) and can_run_script('secundario', 3):
                        async_task(ejecutar_script, script.id)

            # Verificar si el ciclo actual se completó (ningún script pendiente)
            pending_principales_count = sum(1 for s in pendientes_principales if not script_executado(s))
            pending_secundarios_count = sum(1 for s in pendientes_secundarios if not script_executado(s))
            pending_modo = script_modo and not script_executado(script_modo)

            if pending_principales_count == 0 and pending_secundarios_count == 0 and not pending_modo:
                self.stdout.write("Ciclo completado. Esperando hasta el inicio del siguiente ciclo...")
                # Calcular el tiempo restante hasta la próxima hora en punto
                now = datetime.datetime.now()
                next_hour = now.replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=1)
                wait_seconds = (next_hour - now).total_seconds()
                self.stdout.write(f"Esperando {int(wait_seconds)} segundos.")
                time.sleep(wait_seconds)

                # Reiniciar el ciclo: se borran los registros para reutilizar los scripts
                for script in pendientes_principales + pendientes_secundarios:
                    ExecutionRecord.objects.filter(script=script).delete()
                if script_modo:
                    ExecutionRecord.objects.filter(script=script_modo).delete()
            
            # Espera corta antes de volver a verificar la cola
            time.sleep(10)
