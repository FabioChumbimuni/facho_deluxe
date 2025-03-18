# scripts/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.http import HttpResponse
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.conf import settings
import os
import subprocess
from datetime import datetime
from django.contrib import messages
from .models import Script, ExecutionRecord

from .models import (
    Script,
    ExecutionRecord,
    ExecutionControl,
    BloqueEjecucion,
    BloqueEjecucionRecord
)
from .forms import AddScriptForm
from .tasks import ejecutar_script as ejecutar_script_task

def index(request):
    return redirect('dashboard')

def dashboard(request):
    # Procesar scripts individuales
    scripts = Script.objects.all()
    executing_count = ExecutionRecord.objects.filter(estado='en ejecución').count()
    executed_count = ExecutionRecord.objects.filter(estado='finalizado').count()
    executed_script_ids = ExecutionRecord.objects.filter(estado='finalizado').values_list('script_id', flat=True).distinct()
    remaining_count = Script.objects.exclude(id__in=executed_script_ids).count()
    script_status = []
    prioridad = {'principal': 1, 'modo': 2, 'secundario': 3}
    for script in scripts:
        last_execution = ExecutionRecord.objects.filter(script=script).order_by('-inicio').first()
        if last_execution is None:
            color = "#66ccff"  # Azul claro predeterminado
        elif last_execution.estado == 'finalizado':
            color = "#33cc33"  # Verde
        elif last_execution.estado == 'en ejecución':
            color = "#ffcc00"  # Amarillo
        elif last_execution.estado == 'error':
            color = "#ff3300"  # Rojo
        else:
            color = "#66ccff"
        script_status.append({
            'script': script,
            'last_execution': last_execution,
            'color': color,
        })
    
    # Procesar bloques personalizados
    bloques = BloqueEjecucion.objects.all()
    block_status = []
    for bloque in bloques:
        last_record = BloqueEjecucionRecord.objects.filter(bloque=bloque).order_by('-inicio').first()
        block_status.append({
            'bloque': bloque,
            'last_record': last_record,
        })
    
    # Control de ejecución global
    control, _ = ExecutionControl.objects.get_or_create(id=1)
    
    context = {
        'executing_count': executing_count,
        'executed_count': executed_count,
        'remaining_count': remaining_count,
        'script_status': script_status,
        'block_status': block_status,
        'execution_active': control.active,
    }
    return render(request, 'scripts/dashboard.html', context)

def asignar_script(request):
    if request.method == 'POST':
        form = AddScriptForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('asignar_script')
    else:
        form = AddScriptForm()
    return render(request, 'scripts/asignar_script.html', {'form': form})

def add_script(request):
    if request.method == 'POST':
        form = AddScriptForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('dashboard')
    else:
        form = AddScriptForm()
    return render(request, 'scripts/add_script.html', {'form': form})

def history(request):
    """
    Vista de historial consolidado.
    Combina ExecutionRecord y BloqueEjecucionRecord, asigna a cada registro un atributo 'record_type'
    y luego pagina la lista (20 registros por página).
    """
    script_records = list(ExecutionRecord.objects.all())
    for record in script_records:
        record.record_type = 'script'
    bloque_records = list(BloqueEjecucionRecord.objects.all())
    for record in bloque_records:
        record.record_type = 'bloque'
    combined = script_records + bloque_records
    combined.sort(key=lambda record: record.inicio, reverse=True)
    
    paginator = Paginator(combined, 20)
    page = request.GET.get('page')
    try:
        records = paginator.page(page)
    except PageNotAnInteger:
        records = paginator.page(1)
    except EmptyPage:
        records = paginator.page(paginator.num_pages)
    
    context = {
        'records': records,
    }
    return render(request, 'scripts/history.html', context)

def toggle_execution(request):
    """
    Alterna el estado de ejecución global.
    """
    control, created = ExecutionControl.objects.get_or_create(id=1)
    control.active = not control.active
    control.save()
    return redirect('dashboard')

def ejecutar_bloque_manual(request, bloque_id):
    """
    Vista para ejecutar manualmente un bloque personalizado.
    Dispara la ejecución de cada script asignado al bloque, en orden de prioridad.
    """
    try:
        bloque = BloqueEjecucion.objects.get(id=bloque_id)
        # Ordenar scripts del bloque según prioridad
        prioridad = {'principal': 1, 'modo': 2, 'secundario': 3}
        scripts_list = list(bloque.scripts.all())
        ordered_scripts = sorted(scripts_list, key=lambda s: prioridad.get(s.tipo, 99))
        for script in ordered_scripts:
            ejecutar_script_task.delay(script.id)
        return HttpResponse("Bloque ejecutado manualmente.")
    except BloqueEjecucion.DoesNotExist:
        return HttpResponse("Bloque no encontrado.", status=404)

def ejecutar_script(request, script_id):
    script = get_object_or_404(Script, id=script_id)
    script_path = os.path.join(settings.BASE_DIR, 'OLT', 'scriptsonu', script.archivo)

    # Verificar que el archivo exista
    if not os.path.exists(script_path):
        messages.error(request, f"Error: El script '{script.archivo}' no existe.")
        return redirect(request.META.get('HTTP_REFERER', '/admin/'))

    # Registrar inicio de la ejecución
    execution_record = ExecutionRecord.objects.create(
        script=script,
        inicio=timezone.now(),
        estado='en ejecución'
    )

    try:
        # Ejecutar el script en un proceso separado
        resultado = subprocess.run(['bash', script_path], capture_output=True, text=True)

        # Actualizar registro en la base de datos según el resultado
        execution_record.fin = timezone.now()
        execution_record.salida = resultado.stdout if resultado.stdout else 'Sin salida'
        execution_record.estado = 'finalizado' if resultado.returncode == 0 else 'error'
        execution_record.save()

        if resultado.returncode == 0:
            messages.success(request, f"Script '{script.titulo}' ejecutado correctamente.")
        else:
            messages.error(request, f"Error al ejecutar el script: {resultado.stderr}")

    except Exception as e:
        execution_record.fin = timezone.now()
        execution_record.estado = 'error'
        execution_record.salida = str(e)
        execution_record.save()
        messages.error(request, f"Error inesperado: {str(e)}")

    return redirect(request.META.get('HTTP_REFERER', '/admin/'))