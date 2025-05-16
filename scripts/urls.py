# scripts/urls.py
from django.urls import path
from . import views
from .views import ejecutar_script
from django.shortcuts import redirect

def bloquear_vista(request):
    return redirect('admin:index')  # Redirigir a la página de administración
urlpatterns = [
    path('', views.index, name='index'),
    path('scripts/dashboard/', bloquear_vista),
    path('asignar/', views.asignar_script, name='asignar_script'),
    path('add-script/', views.add_script, name='add-script'),
    path('history/', bloquear_vista),
    path('toggle-execution/', views.toggle_execution, name='toggle_execution'),
    path('ejecutar-bloque-manual/<int:bloque_id>/', views.ejecutar_bloque_manual, name='ejecutar_bloque_manual'),
    path('ejecutar_script/<int:script_id>/', ejecutar_script, name='ejecutar_script'),

]