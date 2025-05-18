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
        ('datos_bulk', 'Recolección Masiva de Datos'),
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
        elif self.tipo == 'datos_bulk':  # Nuevo caso
            self.oid_consulta = '1.3.6.1.4.1.2011.6.128.1.1.2.43.1.9'
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
            'datos': '1.3.6.1.4.1.2011.6.128.1.1.2.43.1.15',
            'datos_bulk': '1.3.6.1.4.1.2011.6.128.1.1.2.43.1.9'  # Nuevo OID para bulk

        }
        return OIDS.get(self.tipo, '')


class OnuDato(models.Model):
    id = models.AutoField(primary_key=True, db_column='id')  # ¡Nuevo campo!
    host = models.CharField(max_length=100, db_column='host')  # Antes host_ip
    snmpindex = models.CharField(max_length=100, db_column='snmpindex')
    snmpindexonu = models.CharField(max_length=50, db_column='snmpindexonu')
    slotportonu = models.CharField(max_length=30, db_column='slotportonu')
    onulogico = models.IntegerField(db_column='onulogico')
    onudesc = models.CharField(max_length=255, db_column='onudesc')  # Campo objetivo
    serialonu = models.CharField(max_length=50, db_column='serialonu')
    act_susp = models.CharField(max_length=10, db_column='act_susp')
    fecha = models.DateTimeField(db_column='fecha')
    enviar = models.BooleanField(default=False, db_column='enviar')
    host_name = models.CharField(max_length=50, db_column='host_name')

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
