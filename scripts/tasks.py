# scripts/tasks.py
import time
import subprocess  # Para ejecución real, usa subprocess.run()
from datetime import datetime
from django.utils import timezone
from celery import shared_task
from .models import Script, ExecutionRecord, BloqueEjecucion, BloqueEjecucionRecord

@shared_task
def ejecutar_script(script_id):
    """
    Ejecuta un script individual y registra su ejecución.
    Se simula la ejecución con time.sleep(10); para ejecución real, descomenta la línea de subprocess.run().
    """
    try:
        script = Script.objects.get(id=script_id)
        registro = ExecutionRecord.objects.create(
            script=script,
            estado='en ejecución',
            inicio=timezone.now()
        )
        # Construir la ruta completa del script (ajusta según tu estructura)
        script_path = f"/home/noc/facho/OLT/scriptsonu/{script.archivo}"
        # Ejecución real (descomentar si es necesario):
        # subprocess.run(["bash", script_path], check=True)
        # Simulación de ejecución (por ejemplo, 10 segundos)
        time.sleep(10)
        registro.fin = timezone.now()
        registro.estado = 'finalizado'
        registro.log = "Script ejecutado correctamente"
        registro.save()
    except Exception as e:
        registro.fin = timezone.now()
        registro.estado = 'error'
        registro.log = str(e)
        registro.save()

@shared_task
def ejecutar_ciclo_scripts():
    """
    Tarea global: Ejecuta todos los scripts registrados en la base de datos.
    Los scripts se ordenan de acuerdo a la prioridad:
       1. "principal"
       2. "modo"
       3. "secundario"
    Esta tarea puede estar programada, por ejemplo, para ejecutarse cada hora.
    """
    prioridad = {'principal': 1, 'modo': 2, 'secundario': 3}
    scripts = list(Script.objects.all())
    # Ordena los scripts según la prioridad (menor número = mayor prioridad)
    scripts.sort(key=lambda s: prioridad.get(s.tipo, 99))
    for script in scripts:
        ejecutar_script.delay(script.id)

@shared_task
def ejecutar_bloques_programados():
    """
    Tarea para bloques personalizados.
    Se ejecuta periódicamente (por ejemplo, cada minuto) y revisa los bloques activos.
    Para cada bloque activo, si el minuto actual coincide con el valor en el campo `frecuencia`,
    se obtienen los scripts asignados, se ordenan de la siguiente forma:
       1. "principal"
       2. "modo"
       3. "secundario"
    Luego, se dispara la ejecución de cada script (de forma asíncrona) y se registra la ejecución del bloque.
    """
    current_minute = datetime.now().strftime("%M")  # Por ejemplo, "15" para el minuto 15
    active_blocks = BloqueEjecucion.objects.filter(activo=True)
    # Definimos la prioridad deseada
    prioridad = {'principal': 1, 'modo': 2, 'secundario': 3}
    for bloque in active_blocks:
        if bloque.frecuencia == current_minute:
            # Obtener y ordenar los scripts del bloque según la prioridad:
            scripts_list = list(bloque.scripts.all())
            ordered_scripts = sorted(scripts_list, key=lambda s: prioridad.get(s.tipo, 99))
            # Ejecutar cada script del bloque de manera asíncrona
            for script in ordered_scripts:
                ejecutar_script.delay(script.id)
            # Registrar la ejecución del bloque en el historial
            bloque_record = BloqueEjecucionRecord.objects.create(
                bloque=bloque,
                estado="finalizado",  # Si se dispararon las tareas, asumimos que la ejecución fue exitosa
                log="Bloque ejecutado a la frecuencia programada"
            )
            bloque_record.fin = timezone.now()
            bloque_record.save()
