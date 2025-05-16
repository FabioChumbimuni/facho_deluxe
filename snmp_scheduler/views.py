# snmp_scheduler/views.py
from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import TareaSNMPForm
from .models import TareaSNMP

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