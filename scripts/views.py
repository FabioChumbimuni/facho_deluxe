# scripts/views.py
from django.shortcuts import render, redirect
from django.utils import timezone
from .models import Script, ExecutionRecord, ExecutionControl, BloqueEjecucionRecord, BloqueEjecucion
from .forms import AddScriptForm
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

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

# scripts/views.py
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.shortcuts import render
from .models import ExecutionRecord, BloqueEjecucionRecord

def history(request):
    """
    Vista de historial consolidado.
    Combina ExecutionRecord y BloqueEjecucionRecord en una sola lista,
    asigna a cada registro un atributo 'record_type' y luego pagina la lista.
    """
    # Obtén los registros individuales de ejecución de scripts
    script_records = list(ExecutionRecord.objects.all())
    # Asigna el tipo "script"
    for record in script_records:
        record.record_type = 'script'
    
    # Obtén los registros de ejecución de bloques personalizados
    bloque_records = list(BloqueEjecucionRecord.objects.all())
    # Asigna el tipo "bloque"
    for record in bloque_records:
        record.record_type = 'bloque'
    
    # Combina ambas listas
    combined = script_records + bloque_records
    # Ordena la lista combinada por el campo 'inicio' en orden descendente
    combined.sort(key=lambda record: record.inicio, reverse=True)
    
    # Configura la paginación: 20 registros por página
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
