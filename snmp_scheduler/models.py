# snmp_scheduler/models.py

from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError

# snmp_scheduler/models.py (sólo la sección de TareaSNMP)

class Host(models.Model):
    nombre = models.CharField(max_length=100, verbose_name='Nombre del Host')
    ip = models.GenericIPAddressField(verbose_name='IP del OLT')
    comunidad = models.CharField(max_length=50, default='publica', verbose_name='Comunidad SNMP')
    descripcion = models.TextField(blank=True, null=True, verbose_name='Descripción')
    activo = models.BooleanField(default=True, verbose_name='Activo')
    fecha_creacion = models.DateTimeField(auto_now_add=True, null=True, verbose_name='Fecha de Creación')
    fecha_modificacion = models.DateTimeField(auto_now=True, null=True, verbose_name='Última Modificación')

    class Meta:
        verbose_name = 'Host'
        verbose_name_plural = 'Hosts'
        ordering = ['nombre']

    def __str__(self):
        return f"{self.nombre} ({self.ip})"

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

    # Unificamos aquí todos los "tipos" y "subtipos" SNMP
    TIPO_CHOICES = [
        ('descubrimiento',     'Descubrimiento'),
        ('onudesc',            'Descripción ONU'),
        ('estado_onu',         'Estado ONU'),
        ('plan_onu',           'Plan ONU'),
        ('pot_rx',             'Potencia RX'),
        ('pot_tx',             'Potencia TX'),
        ('last_down_t',        'Last Down Time'),
        ('distancia_m',        'Distancia (m)'),
        ('modelo_onu',         'Modelo ONU'),
       
    ]

    BULK_OIDS = {
        'descubrimiento':    '1.3.6.1.4.1.2011.6.128.1.1.2.46.1.1',
        'onudesc':           '1.3.6.1.4.1.2011.6.128.1.1.2.43.1.9',
        'estado_onu':        '1.3.6.1.4.1.2011.6.128.1.1.2.46.1.15',
        'plan_onu':          '1.3.6.1.4.1.2011.6.128.1.1.2.43.1.7',
        'pot_rx':            '1.3.6.1.4.1.2011.6.128.1.1.2.51.1.6',
        'pot_tx':            '1.3.6.1.4.1.2011.6.128.1.1.2.51.1.4',
        'last_down_t':       '1.3.6.1.4.1.2011.6.128.1.1.2.101.1.7',
        'distancia_m':       '1.3.6.1.4.1.2011.6.128.1.1.2.46.1.20',
        'modelo_onu':        '1.3.6.1.4.1.2011.6.128.1.1.2.45.1.4',
    
    }

    nombre = models.CharField(max_length=100, verbose_name='Nombre de la Tarea')
    host = models.ForeignKey(Host, on_delete=models.CASCADE, verbose_name='Host')
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, verbose_name='Tipo de Tarea')
    intervalo = models.CharField(
        max_length=2,
        choices=INTERVALO_CHOICES,
        default='00',
        verbose_name='Intervalo'
    )
    activa = models.BooleanField(default=True, verbose_name='Activa')
    fecha_creacion = models.DateTimeField(auto_now_add=True, null=True, verbose_name='Fecha de Creación')
    fecha_modificacion = models.DateTimeField(auto_now=True, null=True, verbose_name='Última Modificación')
    registros_activos = models.PositiveIntegerField(
        default=0,
        verbose_name="ONUs Registradas",
        help_text="Contador actualizado automáticamente"
    )

    ultima_ejecucion = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Tarea SNMP'
        verbose_name_plural = 'Tareas SNMP'
        ordering = ['nombre']

    def __str__(self):
        return f"{self.nombre} - {self.host.nombre}"

    @property
    def host_name(self):
        return self.host.nombre

    @property
    def host_ip(self):
        return self.host.ip

    @property
    def comunidad(self):
        return self.host.comunidad

    def get_oid(self):
        return self.BULK_OIDS.get(self.tipo, '')



class OnuDato(models.Model):
    """
    Refleja la tabla existente 'onu_datos'. 
    Incluye nuevas columnas para cada subtipo bulk.
    """
    id             = models.AutoField(primary_key=True, db_column='id')
    host           = models.CharField(max_length=100, db_column='host')
    snmpindex      = models.CharField(max_length=100, db_column='snmpindex')
    snmpindexonu   = models.CharField(max_length=50,  db_column='snmpindexonu')
    slotportonu    = models.CharField(max_length=30,  db_column='slotportonu')
    onulogico      = models.IntegerField(db_column='onulogico')

    # Campos base
    onudesc        = models.CharField(max_length=255, db_column='onudesc', null=True, blank=True)
    act_susp       = models.CharField(max_length=10,  db_column='act_susp')
    serialonu      = models.CharField(max_length=50,  db_column='serialonu')
    fecha          = models.DateTimeField(db_column='fecha')
    enviar         = models.BooleanField(default=False, db_column='enviar')

    # ——— Nuevos campos para cada subtipo bulk ———
    estado_onu         = models.CharField(max_length=50,  db_column='estado_onu',         null=True, blank=True)
    plan_onu           = models.CharField(max_length=50,  db_column='plan_onu',           null=True, blank=True)
    potencia_rx        = models.CharField(max_length=50,  db_column='potencia_rx',        null=True, blank=True)
    potencia_tx        = models.CharField(max_length=50,  db_column='potencia_tx',        null=True, blank=True)
    last_down_time     = models.CharField(max_length=50,  db_column='last_down_time',     null=True, blank=True)
    distancia_m        = models.CharField(max_length=50,  db_column='distancia_m',        null=True, blank=True)
    modelo_onu         = models.CharField(max_length=100, db_column='modelo_onu',         null=True, blank=True)

    class Meta:
        managed = False  # Siguen usando la tabla existente
        db_table = 'onu_datos'
        verbose_name = 'Datos ONU'
        verbose_name_plural = 'Datos ONUs'
        unique_together = (('host', 'snmpindexonu'),)
        indexes = [
            models.Index(fields=['snmpindexonu']),
        ]

    def __str__(self):
        return f"{self.snmpindexonu}"


class EjecucionTareaSNMP(models.Model):
    ESTADOS = (
        ('P', 'Pendiente'),
        ('E', 'En Ejecución'),
        ('C', 'Completada'),
        ('F', 'Fallida'),
    )

    tarea      = models.ForeignKey(TareaSNMP, on_delete=models.CASCADE, related_name='ejecuciones')
    inicio     = models.DateTimeField(auto_now_add=True)
    fin        = models.DateTimeField(null=True, blank=True)
    estado     = models.CharField(max_length=1, choices=ESTADOS, default='P')
    resultado  = models.JSONField(null=True, blank=True)
    error      = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ['-inicio']
        verbose_name = "Ejecución de Tarea"
        verbose_name_plural = "Ejecuciones de Tareas"

    def __str__(self):
        return f"{self.tarea.nombre} - {self.get_estado_display()} ({self.inicio:%Y-%m-%d %H:%M:%S})"
