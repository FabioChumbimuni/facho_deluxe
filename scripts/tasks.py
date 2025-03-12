import time
import subprocess
import logging
from datetime import datetime
from django.utils import timezone
from celery import shared_task
from .models import Script, ExecutionRecord, BloqueEjecucion, BloqueEjecucionRecord

# Configuración del logger
logger = logging.getLogger(__name__)

@shared_task
def ejecutar_script(script_id):
    registro = None
    try:
        script = Script.objects.get(id=script_id)
        registro = ExecutionRecord.objects.create(
            script=script,
            estado='en ejecución',
            inicio=timezone.now()
        )

        script_path = f"/home/facho/OLT/scriptsonu/{script.archivo}"
        logger.info("Ejecutando script: %s", script_path)

        # Detectar si es .sh o .py
        if script_path.endswith(".sh"):
            comando = ["bash", script_path]
        elif script_path.endswith(".py"):
            comando = ["python3", script_path]
        else:
            raise ValueError("Extensión de archivo no soportada")

        # Ejecutar el script y capturar la salida
        resultado = subprocess.run(
            comando, check=True, text=True, capture_output=True
        )

        logger.info("Salida estándar:\n%s", resultado.stdout)
        logger.info("Salida de error:\n%s", resultado.stderr)

        registro.fin = timezone.now()
        registro.estado = 'finalizado'
        registro.log = resultado.stdout
        registro.save()
    except subprocess.CalledProcessError as e:
        error_msg = f"Error al ejecutar el script:\n{e.stderr}"
        if registro:
            registro.fin = timezone.now()
            registro.estado = 'error'
            registro.log = error_msg
            registro.save()
        logger.error(error_msg)

@shared_task
def ejecutar_ciclo_scripts():
    """
    Tarea global: Ejecuta todos los scripts registrados en la base de datos
    que tienen activada la opción de ejecución automática, ordenados por prioridad:
       1. "principal"
       2. "modo"
       3. "secundario"
    """
    prioridad = {'principal': 1, 'modo': 2, 'secundario': 3}
    # Filtra solo los scripts que deben ejecutarse automáticamente
    scripts = list(Script.objects.filter(ejecucion_automatica=True))
    scripts.sort(key=lambda s: prioridad.get(s.tipo, 99))
    for script in scripts:
        ejecutar_script.delay(script.id)

@shared_task
def ejecutar_bloques_programados():
    """
    Ejecuta los bloques activos si coincide con el minuto actual.
    Registra la ejecución de cada bloque en BloqueEjecucionRecord.
    """
    current_minute = datetime.now().strftime("%M")
    active_blocks = BloqueEjecucion.objects.filter(activo=True)
    prioridad = {'principal': 1, 'modo': 2, 'secundario': 3}

    for bloque in active_blocks:
        if bloque.frecuencia == current_minute:
            scripts_list = list(bloque.scripts.all())
            ordered_scripts = sorted(scripts_list, key=lambda s: prioridad.get(s.tipo, 99))

            for script in ordered_scripts:
                ejecutar_script.delay(script.id)

            # Registrar la ejecución del bloque
            bloque_record = BloqueEjecucionRecord.objects.create(
                bloque=bloque,
                estado="finalizado",
                log="Bloque ejecutado a la frecuencia programada"
            )
            bloque_record.fin = timezone.now()
            bloque_record.save()
