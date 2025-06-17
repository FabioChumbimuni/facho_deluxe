from django.contrib import admin
from .models import (
    Script,
    ExecutionRecord,
    ExecutionControl,
    BloqueEjecucion,
    BloqueEjecucionRecord,
)
from django import forms
from django.conf import settings
from django.urls import reverse
from django.utils.html import format_html
import os

class ScriptAdminForm(forms.ModelForm):
    class Meta:
        model = Script
        fields = ['titulo', 'archivo', 'tipo', 'ejecucion_automatica']
        labels = {
            'titulo': 'Título del Script',
            'archivo': 'Script',
            'tipo': 'Tipo de Script',
            'ejecucion_automatica': 'Ejecutar automáticamente'
        }
        widgets = {
            'ejecucion_automatica': forms.CheckboxInput(),
        }
    
    def __init__(self, *args, **kwargs):
        super(ScriptAdminForm, self).__init__(*args, **kwargs)
        script_folder = os.path.join(settings.BASE_DIR, 'OLT', 'scriptsonu')
        try:
            files = os.listdir(script_folder)
            files = [f for f in files if os.path.isfile(os.path.join(script_folder, f))]
            choices = [(f, f) for f in files]
        except Exception as e:
            choices = []
        self.fields['archivo'] = forms.ChoiceField(choices=choices, label="Script")


@admin.register(Script)
class ScriptAdmin(admin.ModelAdmin):
    form = ScriptAdminForm
    list_display = ('titulo', 'archivo', 'tipo', 'ejecucion_automatica', 'ejecutar_script')
    list_filter = ('tipo', 'ejecucion_automatica')
    search_fields = ('titulo', 'archivo', 'tipo')
    
    def ejecutar_script(self, obj):
        url = reverse('ejecutar_script', args=[obj.id])
        return format_html(
            '<a class="button" href="{}" style="background: #28a745; color: white; padding: 5px 10px; text-decoration: none; border-radius: 5px;">Ejecutar</a>',
            url
        )
    ejecutar_script.short_description = "Acción"



@admin.register(ExecutionRecord)
class ExecutionRecordAdmin(admin.ModelAdmin):
    list_display = ('script', 'estado', 'inicio', 'fin', 'salida_truncada')
    list_filter = ('estado',)
    search_fields = ('script__titulo',)

    def salida_truncada(self, obj):
        if obj.salida and len(obj.salida) > 100:
            return f"{obj.salida[:100]}..."
        return obj.salida
    salida_truncada.short_description = "Salida"



@admin.register(ExecutionControl)
class ExecutionControlAdmin(admin.ModelAdmin):
    list_display = ('active',)


@admin.register(BloqueEjecucion)
class BloqueEjecucionAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'activo', 'get_frecuencia')
    search_fields = ('nombre',)
    filter_horizontal = ('scripts',)

    def get_frecuencia(self, obj):
        return obj.frecuencia
    get_frecuencia.short_description = "Frecuencia"


@admin.register(BloqueEjecucionRecord)
class BloqueEjecucionRecordAdmin(admin.ModelAdmin):
    list_display = ('bloque', 'inicio', 'fin', 'estado')
    list_filter = ('estado', 'bloque__nombre')
    search_fields = ('bloque__nombre',)
