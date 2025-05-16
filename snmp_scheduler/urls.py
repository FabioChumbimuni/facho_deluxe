# snmp_scheduler/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('crear/', views.crear_tarea, name='crear_tarea'),
    path('lista/', views.lista_tareas, name='lista_tareas'),
]