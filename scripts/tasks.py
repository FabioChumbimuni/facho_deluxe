import subprocess
import logging
import os
from datetime import datetime
from django.utils import timezone
from celery import shared_task
from django.conf import settings
from .models import Script, ExecutionRecord, BloqueEjecucion, BloqueEjecucionRecord

logger = logging.getLogger(__name__)

@shared_task
def ejecutar_script_task(script_id, execution_record_id):
    """
    Tarea asíncrona que ejecuta un script y actualiza el registro de ejecución.
    Se usa subprocess.Popen para manejar scripts pesados con timeout.
    """
    try:
        script = Script.objects.get(id=script_id)
        registro = ExecutionRecord.objects.get(id=execution_record_id)
        script_path = os.path.join(settings.BASE_DIR, 'OLT', 'scriptsonu', script.archivo)
        logger.info("Ejecutando script: %s", script_path)
        
        # Determinar el comando según la extensión del script
        if script_path.endswith(".sh"):
            comando = ["bash", script_path]
        elif script_path.endswith(".py"):
            comando = ["python3", script_path]
        else:
            raise ValueError("Extensión de archivo no soportada")
        
        # Ejecutar el script sin bloquear indefinidamente.
        # Se establece un timeout (por ejemplo, 3600 segundos = 1 hora)
        process = subprocess.Popen(
            comando,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        try:
            stdout, stderr = process.communicate(timeout=3600)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            registro.fin = timezone.now()
            registro.estado = 'error'
            registro.salida = "Timeout expirado"
            registro.save()
            logger.error("Timeout expirado en script: %s", script.titulo)
            return
        
        registro.fin = timezone.now()
        if process.returncode == 0:
            registro.estado = 'finalizado'
            registro.salida = stdout.strip() if stdout.strip() else "Sin salida"
            logger.info("Script '%s' ejecutado correctamente. Salida:\n%s", script.titulo, stdout)
        else:
            registro.estado = 'error'
            registro.salida = stderr.strip() if stderr.strip() else "Error sin salida"
            logger.error("Error al ejecutar script '%s'. Error:\n%s", script.titulo, stderr)
        registro.save()
    
    except subprocess.CalledProcessError as e:
        error_msg = f"Error al ejecutar el script: {e.stderr}"
        try:
            registro.fin = timezone.now()
            registro.estado = 'error'
            registro.salida = error_msg
            registro.save()
        except Exception:
            pass
        logger.error(error_msg)
    except Exception as e:
        try:
            registro.fin = timezone.now()
            registro.estado = 'error'
            registro.salida = str(e)
            registro.save()
        except Exception:
            pass
        logger.error("Error inesperado en ejecutar_script_task: %s", str(e))


@shared_task
def ejecutar_ciclo_scripts():
    """
    Tarea global: Ejecuta todos los scripts que tienen activada la ejecución automática,
    ordenados por prioridad: "principal", "modo", "secundario".
    """
    prioridad = {'principal': 1, 'modo': 2, 'secundario': 3}
    scripts = list(Script.objects.filter(ejecucion_automatica=True))
    scripts.sort(key=lambda s: prioridad.get(s.tipo, 99))
    for script in scripts:
        registro = ExecutionRecord.objects.create(
            script=script,
            inicio=timezone.now(),
            estado='en ejecución'
        )
        ejecutar_script_task.delay(script.id, registro.id)


@shared_task
def ejecutar_bloques_programados():
    """
    Tarea que se ejecuta periódicamente para revisar los bloques activos.
    Si el minuto actual coincide con la frecuencia configurada en el bloque,
    ordena los scripts asignados (por prioridad: "principal", "modo", "secundario")
    y dispara la ejecución de cada uno, registrando la ejecución en BloqueEjecucionRecord.
    """
    current_minute = datetime.now().strftime("%M")
    active_blocks = BloqueEjecucion.objects.filter(activo=True)
    prioridad = {'principal': 1, 'modo': 2, 'secundario': 3}

    for bloque in active_blocks:
        if bloque.frecuencia == current_minute:
            scripts_list = list(bloque.scripts.all())
            ordered_scripts = sorted(scripts_list, key=lambda s: prioridad.get(s.tipo, 99))
            for script in ordered_scripts:
                registro = ExecutionRecord.objects.create(
                    script=script,
                    inicio=timezone.now(),
                    estado='en ejecución'
                )
                ejecutar_script_task.delay(script.id, registro.id)
            bloque_record = BloqueEjecucionRecord.objects.create(
                bloque=bloque,
                estado="finalizado",
                log="Bloque ejecutado a la frecuencia programada"
            )
            bloque_record.fin = timezone.now()
            bloque_record.save()
