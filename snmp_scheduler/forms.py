# snmp_scheduler/forms.py
from django import forms
from .models import TareaSNMP, Host

class TareaSNMPForm(forms.ModelForm):
    class Meta:
        model = TareaSNMP
        fields = ['nombre', 'host', 'tipo', 'comunidad', 'oid_consulta', 'intervalo', 'activa']
        widgets = {
            'host': forms.Select(attrs={'class': 'form-select'}),
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'oid_consulta': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '1.3.6.1.4.1.2011.6.128.1.1.2.46.1.1'
            }),
            'comunidad': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: publica'
            }),
            'intervalo': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'HHMM'
            }),
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'activa': forms.CheckboxInput(attrs={'class': 'form-check-input'})
        }
        help_texts = {
            'oid_consulta': 'Dejar vacío para descubrimiento automático',
            'intervalo': 'Hora de ejecución en formato HHMM',
            'host': 'Seleccione el host para la tarea'
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filtrar solo hosts activos
        self.fields['host'].queryset = Host.objects.filter(activo=True).order_by('nombre')

    def clean(self):
        cleaned_data = super().clean()
        tipo = cleaned_data.get('tipo')
        oid = cleaned_data.get('oid_consulta')
        
        if tipo != 'descubrimiento' and not oid:
            raise forms.ValidationError(
                "El OID de consulta es requerido para tareas de datos"
            )
            
        return cleaned_data