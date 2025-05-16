# snmp_scheduler/forms.py
from django import forms
from .models import TareaSNMP

class TareaSNMPForm(forms.ModelForm):
    class Meta:
        model = TareaSNMP
        fields = '__all__'
        exclude = ['oid_consulta']
        widgets = {
            'tipo': forms.RadioSelect(attrs={'class': 'form-check-input'}),
        }
        help_texts = {
            'tipo': 'El OID se asignará automáticamente según el tipo seleccionado',
        }

    def clean(self):
        cleaned_data = super().clean()
        tipo = cleaned_data.get('tipo')
        oid = cleaned_data.get('oid_consulta')
        
        if tipo != 'descubrimiento' and not oid:
            raise forms.ValidationError(
                "El OID de consulta es requerido para tareas de datos"
            )
            
        return cleaned_data