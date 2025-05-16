from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.http import HttpResponse
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
import os
from datetime import datetime

from .models import (
    Script,
    ExecutionRecord,
    ExecutionControl,
    BloqueEjecucion,
    BloqueEjecucionRecord
)
from .forms import AddScriptForm
from .tasks import ejecutar_script_task

# Función para restringir el acceso solo a superusuarios
def es_superusuario(user):
    return user.is_superuser

def index(request):
    return redirect('/admin/')

@user_passes_test(es_superusuario, login_url='/admin/login/')
def dashboard(request):
    scripts = Script.objects.all()
    executing_count = ExecutionRecord.objects.filter(estado='en ejecución').count()
    executed_count = ExecutionRecord.objects.filter(estado='finalizado').count()
    executed_script_ids = ExecutionRecord.objects.filter(estado='finalizado').values_list('script_id', flat=True).distinct()
    remaining_count = Script.objects.exclude(id__in=executed_script_ids).count()

    script_status = []
    prioridad = {'principal': 1, 'modo': 2, 'secundario': 3}
    for script in scripts:
        last_execution = ExecutionRecord.objects.filter(script=script).order_by('-inicio').first()
        color = "#66ccff"  # Azul claro predeterminado
        if last_execution:
            if last_execution.estado == 'finalizado':
                color = "#33cc33"  # Verde
            elif last_execution.estado == 'en ejecución':
                color = "#ffcc00"  # Amarillo
            elif last_execution.estado == 'error':
                color = "#ff3300"  # Rojo
        script_status.append({
            'script': script,
            'last_execution': last_execution,
            'color': color,
        })
    
    bloques = BloqueEjecucion.objects.all()
    block_status = []
    for bloque in bloques:
        last_record = BloqueEjecucionRecord.objects.filter(bloque=bloque).order_by('-inicio').first()
        block_status.append({
            'bloque': bloque,
            'last_record': last_record,
        })
    
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

@user_passes_test(es_superusuario, login_url='/admin/login/')
def history(request):
    """
    Vista de historial consolidado.
    Combina ExecutionRecord y BloqueEjecucionRecord, asigna a cada registro un atributo 'record_type'
    y luego pagina la lista (20 registros por página).
    """
    script_records = list(ExecutionRecord.objects.all().order_by('-inicio'))
    for record in script_records:
        record.record_type = 'script'
    bloque_records = list(BloqueEjecucionRecord.objects.all().order_by('-inicio'))
    for record in bloque_records:
        record.record_type = 'bloque'
    combined = script_records + bloque_records
    combined.sort(key=lambda record: record.inicio, reverse=True)
    
    paginator = Paginator(combined, 20)
    page = request.GET.get('page')
    try:
        records = paginator.page(page)
    except (PageNotAnInteger, EmptyPage):
        records = paginator.page(1)
    
    return render(request, 'scripts/history.html', {'records': records})

def toggle_execution(request):
    control, _ = ExecutionControl.objects.get_or_create(id=1)
    control.active = not control.active
    control.save()
    return redirect('dashboard')

def ejecutar_bloque_manual(request, bloque_id):
    bloque = get_object_or_404(BloqueEjecucion, id=bloque_id)
    prioridad = {'principal': 1, 'modo': 2, 'secundario': 3}
    ordered_scripts = sorted(bloque.scripts.all(), key=lambda s: prioridad.get(s.tipo, 99))
    for script in ordered_scripts:
        ejecutar_script_task.delay(script.id)
    return HttpResponse("Bloque ejecutado manualmente.")

def ejecutar_script(request, script_id):
    """
    Vista para ejecutar un script individual de forma asíncrona.
    Crea un registro en ExecutionRecord y dispara la tarea de Celery para ejecutar el script.
    No espera el resultado, devolviendo inmediatamente una respuesta.
    """
    script = get_object_or_404(Script, id=script_id)
    script_path = os.path.join(settings.BASE_DIR, 'OLT', 'scriptsonu', script.archivo)

    if not os.path.exists(script_path):
        messages.error(request, f"Error: El script '{script.archivo}' no existe.")
        return redirect(request.META.get('HTTP_REFERER', '/admin/'))

    # Registrar el inicio de la ejecución
    execution_record = ExecutionRecord.objects.create(
        script=script,
        inicio=timezone.now(),
        estado='en ejecución'
    )

    # Disparar la tarea asíncrona para ejecutar el script
    ejecutar_script_task.delay(script.id, execution_record.id)
    messages.success(request, f"La ejecución del script '{script.titulo}' se ha iniciado.")

    return redirect(request.META.get('HTTP_REFERER', '/admin/'))
