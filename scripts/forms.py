# scripts/forms.py
from django import forms
from .models import Script
import os
from django.conf import settings

class AddScriptForm(forms.ModelForm):
    class Meta:
        model = Script
        fields = ['titulo', 'archivo', 'tipo']
        labels = {
            'titulo': 'Título del Script',
            'archivo': 'Script',
            'tipo': 'Tipo de Script',
        }

    def __init__(self, *args, **kwargs):
        super(AddScriptForm, self).__init__(*args, **kwargs)
        # Construir la ruta a la carpeta: BASE_DIR/OLT/scriptsonu
        script_folder = os.path.join(settings.BASE_DIR, 'OLT', 'scriptsonu')
        try:
            files = os.listdir(script_folder)
            # Filtrar solo archivos (puedes ajustar el filtro si deseas, por ejemplo, solo .sh)
            files = [f for f in files if os.path.isfile(os.path.join(script_folder, f))]
            choices = [(f, f) for f in files]
        except Exception as e:
            choices = []
        self.fields['archivo'] = forms.ChoiceField(choices=choices, label="Script")
