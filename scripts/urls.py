# scripts/urls.py
from django.urls import path
from . import views
from .views import ejecutar_script

urlpatterns = [
    path('', views.index, name='index'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('asignar/', views.asignar_script, name='asignar_script'),
    path('add-script/', views.add_script, name='add-script'),
    path('history/', views.history, name='history'),
    path('toggle-execution/', views.toggle_execution, name='toggle_execution'),
    path('ejecutar-bloque-manual/<int:bloque_id>/', views.ejecutar_bloque_manual, name='ejecutar_bloque_manual'),
    path('ejecutar_script/<int:script_id>/', ejecutar_script, name='ejecutar_script'),

]