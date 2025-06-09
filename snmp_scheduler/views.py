# snmp_scheduler/views.py
from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import TareaSNMPForm
from .models import TareaSNMP, OnuDato
from django.db.models import Q

def crear_tarea(request):
    if request.method == 'POST':
        form = TareaSNMPForm(request.POST)
        if form.is_valid():
            tarea = form.save(commit=False)
            tarea.activa = True
            tarea.save()
            messages.success(request, 'Tarea creada exitosamente!')
            return redirect('lista_tareas')
    else:
        form = TareaSNMPForm()
    
    return render(request, 'snmp_scheduler/crear_tarea.html', {'form': form})

def lista_tareas(request):
    tareas = TareaSNMP.objects.filter(activa=True)
    return render(request, 'snmp_scheduler/lista_tareas.html', {'tareas': tareas})

def snmp_programmer_view(request):
    # Get all ONUs
    onus = OnuDato.objects.all()

    # Get unique ONU models for the filter dropdown
    onu_models = OnuDato.objects.values_list('modelo_onu', flat=True).distinct()

    # Apply model filter
    selected_model = request.GET.get('modelo_onu')
    if selected_model:
        onus = onus.filter(modelo_onu=selected_model)

    # Apply distance range filter
    selected_range = request.GET.get('distance_range')
    if selected_range:
        # Convert distance_m to float for comparison
        if selected_range == '0-5':
            onus = onus.filter(Q(distancia_m__gte=0) & Q(distancia_m__lt=5000))
        elif selected_range == '5-10':
            onus = onus.filter(Q(distancia_m__gte=5000) & Q(distancia_m__lt=10000))
        elif selected_range == '10-15':
            onus = onus.filter(Q(distancia_m__gte=10000) & Q(distancia_m__lt=15000))
        elif selected_range == '15+':
            onus = onus.filter(distancia_m__gte=15000)

    context = {
        'onus': onus,
        'onu_models': onu_models,
        'selected_model': selected_model,
        'selected_range': selected_range,
    }

    return render(request, 'snmp_programmer.html', context)