# snmp_scheduler/urls.py
from django.urls import path, include
from . import views
from django.contrib import admin
urlpatterns = [
    path('admin/', admin.site.urls),
    path('crear/', views.crear_tarea, name='crear_tarea'),
    path('lista/', views.lista_tareas, name='lista_tareas'),
]