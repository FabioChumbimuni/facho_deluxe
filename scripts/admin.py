from django.contrib import admin
from django import forms
from django.conf import settings
import os
from .models import (
    Script,
    ExecutionRecord,
    ExecutionControl,
    BloqueEjecucion,
    BloqueEjecucionRecord
)

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
        # Construir la ruta a la carpeta de scripts
        script_folder = os.path.join(settings.BASE_DIR, 'OLT', 'scriptsonu')
        try:
            files = os.listdir(script_folder)
            # Filtra sólo archivos
            files = [f for f in files if os.path.isfile(os.path.join(script_folder, f))]
            choices = [(f, f) for f in files]
        except Exception as e:
            choices = []
        self.fields['archivo'] = forms.ChoiceField(choices=choices, label="Script")

@admin.register(Script)
class ScriptAdmin(admin.ModelAdmin):
    form = ScriptAdminForm
    list_display = ('titulo', 'archivo', 'tipo', 'ejecucion_automatica')
    list_filter = ('tipo', 'ejecucion_automatica')
    search_fields = ('titulo', 'archivo', 'tipo')

@admin.register(ExecutionRecord)
class ExecutionRecordAdmin(admin.ModelAdmin):
    list_display = ('script', 'inicio', 'fin', 'estado')
    list_filter = ('estado', 'script__tipo')
    search_fields = ('script__titulo',)

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
