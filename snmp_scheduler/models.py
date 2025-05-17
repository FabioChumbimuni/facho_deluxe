# snmp_scheduler/models.py

from django.db import models
from django.utils import timezone

class TareaSNMP(models.Model):
    INTERVALO_CHOICES = [
        ('00', '(00)'),
        ('15', '(15)'),
        ('30', '(30)'),
        ('45', '(45)'),
    ]
    
    MODO_CHOICES = [
        ('principal', 'Principal'),
        ('secundario', 'Secundario'),
        ('modo', 'Modo Especial'),
    ]
    
    TIPO_CHOICES = [
        ('descubrimiento', 'Descubrimiento'),
        ('datos', 'Datos'),
    ]

    nombre = models.CharField(max_length=100, verbose_name="Nombre de la Tarea")
    host_name = models.CharField(max_length=50, verbose_name="Nombre del Host")
    host_ip = models.GenericIPAddressField(protocol='IPv4', verbose_name="IP del OLT")
    comunidad = models.CharField(max_length=50, default='public', verbose_name="Comunidad SNMP")
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default='descubrimiento')
    
    oid_consulta = models.CharField(
        max_length=255,
        blank=True,
        editable=False,
        verbose_name="OID Automático"
    )

    intervalo = models.CharField(max_length=10, choices=INTERVALO_CHOICES, default='00')
    modo = models.CharField(max_length=20, choices=MODO_CHOICES, default='principal')
    ultima_ejecucion = models.DateTimeField(null=True, blank=True)
    activa = models.BooleanField(default=True, verbose_name="Tarea Activa")

    registros_activos = models.PositiveIntegerField(
        default=0,
        verbose_name="ONUs Registradas",
        help_text="Contador actualizado automáticamente"
    )

    class Meta:
        verbose_name = "Tarea SNMP"
        verbose_name_plural = "Tareas SNMP"
        unique_together = [['host_ip', 'intervalo', 'modo']]

    def __str__(self):
        return f"{self.nombre} ({self.host_ip})"

    def save(self, *args, **kwargs):
        if self.tipo == 'descubrimiento':
            self.oid_consulta = '1.3.6.1.4.1.2011.6.128.1.1.2.46.1.1'
        elif self.tipo == 'datos':
            self.oid_consulta = '1.3.6.1.4.1.2011.6.128.1.1.2.43.1.15'
        super().save(*args, **kwargs)

    def update_registros(self):
        self.registros_activos = OnuDato.objects.filter(
            host_ip=self.host_ip
        ).count()
        self.save(update_fields=["registros_activos"])

    def get_oid(self):
        OIDS = {
            'descubrimiento': '1.3.6.1.4.1.2011.6.128.1.1.2.46.1.1',
            'datos': '1.3.6.1.4.1.2011.6.128.1.1.2.43.1.15'
        }
        return OIDS.get(self.tipo, '')


class OnuDato(models.Model):
    snmpindexonu = models.CharField(max_length=50, verbose_name="Índice SNMP")
    host_ip = models.GenericIPAddressField(protocol='IPv4', verbose_name="IP del OLT")
    act_susp = models.CharField(max_length=10, verbose_name="Estado ONU")
    onudesc = models.CharField(max_length=255, blank=True, verbose_name="Descripción ONU")

    class Meta:
        managed = False  # Usa una tabla existente
        db_table = 'onu_datos'
        verbose_name = 'Datos ONU'
        verbose_name_plural = 'Datos ONUs'
        indexes = [
            models.Index(fields=['snmpindexonu']),
        ]

    def __str__(self):
        return f"{self.snmpindexonu} ({self.host_ip})"


class EjecucionTareaSNMP(models.Model):
    ESTADOS = (
        ('P', 'Pendiente'),
        ('E', 'En Ejecución'),
        ('C', 'Completada'),
        ('F', 'Fallida')
    )

    tarea = models.ForeignKey(TareaSNMP, on_delete=models.CASCADE, related_name='ejecuciones')
    inicio = models.DateTimeField(auto_now_add=True)
    fin = models.DateTimeField(null=True)
    estado = models.CharField(max_length=1, choices=ESTADOS, default='P')
    resultado = models.JSONField(null=True)
    error = models.TextField(null=True)

    class Meta:
        ordering = ['-inicio']
        verbose_name = "Ejecución de Tarea"
        verbose_name_plural = "Ejecuciones de Tareas"

    def __str__(self):
        return f"{self.tarea} - {self.estado} ({self.inicio.strftime('%Y-%m-%d %H:%M:%S')})"
