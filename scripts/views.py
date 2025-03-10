# scripts/views.py
from django.shortcuts import render, redirect
from django.utils import timezone
from .models import Script, ExecutionRecord, ExecutionControl, BloqueEjecucionRecord, BloqueEjecucion
from .forms import AddScriptForm

def index(request):
    return redirect('dashboard')

from .models import Script, ExecutionRecord, ExecutionControl, BloqueEjecucion, BloqueEjecucionRecord

def dashboard(request):
    # Scripts
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
    
    # Bloques
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

def history(request):
    """
    Vista de historial consolidado: incluye registros individuales de ejecución (ExecutionRecord)
    y registros de bloques personalizados (BloqueEjecucionRecord).
    Se ordena por fecha de inicio (descendente).
    """
    script_records = list(ExecutionRecord.objects.all())
    bloque_records = list(BloqueEjecucionRecord.objects.all())
    combined = script_records + bloque_records
    # Ordenar por fecha de inicio descendente (ambos modelos tienen el campo "inicio")
    combined.sort(key=lambda x: x.inicio, reverse=True)
    context = {
        'records': combined,
    }
    return render(request, 'scripts/history.html', context)


def toggle_execution(request):
    """
    Alterna el estado de ejecución continua.
    """
    control, created = ExecutionControl.objects.get_or_create(id=1)
    control.active = not control.active
    control.save()
    return redirect('dashboard')







# scripts/views.py (agrega al final)
from django.http import HttpResponse
from .tasks import ejecutar_script  # O una función para ejecutar todos los scripts de un bloque

def ejecutar_bloque_manual(request, bloque_id):
    """
    Vista para ejecutar manualmente un bloque personalizado.
    Esta vista dispara la ejecución de todos los scripts del bloque indicado.
    """
    from .models import BloqueEjecucion
    try:
        bloque = BloqueEjecucion.objects.get(id=bloque_id)
        # Por ejemplo, enviar una tarea para cada script del bloque:
        for script in bloque.scripts.all():
            ejecutar_script.delay(script.id)
        # Puedes registrar también un BloqueEjecucionRecord si lo deseas.
        return HttpResponse("Bloque ejecutado manualmente.")
    except BloqueEjecucion.DoesNotExist:
        return HttpResponse("Bloque no encontrado.", status=404)
