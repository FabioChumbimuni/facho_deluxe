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
    desactivado_por_timeout = models.BooleanField(default=False, help_text="Indica si el host fue desactivado por el protocolo anti-timeout")
    ultimo_timeout = models.DateTimeField(null=True, blank=True, help_text="Última vez que el host tuvo un timeout")

    class Meta:
        verbose_name = 'Host'
        verbose_name_plural = 'Hosts'
        ordering = ['nombre']

    def __str__(self):
        return f"{self.nombre} ({self.ip})"

class TrabajoSNMP(models.Model):
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

    MODO_CHOICES = [
        ('principal', 'Principal'),
        ('secundario', 'Secundario'),
        ('modo', 'Modo Especial'),
    ]

    INTERVALO_CHOICES = [
        ('00', '(00)'),
        ('15', '(15)'),
        ('30', '(30)'),
        ('45', '(45)'),
    ]

    nombre = models.CharField(max_length=100, verbose_name='Nombre del Trabajo')
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, verbose_name='Tipo de Tarea')
    modo = models.CharField(
        max_length=20,
        choices=MODO_CHOICES,
        default='principal',
        verbose_name='Modo de Ejecución'
    )
    intervalo = models.CharField(
        max_length=2,
        choices=INTERVALO_CHOICES,
        default='00',
        verbose_name='Intervalo'
    )
    activo = models.BooleanField(default=True, verbose_name='Activo')
    fecha_creacion = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de Creación')
    fecha_modificacion = models.DateTimeField(auto_now=True, verbose_name='Última Modificación')

    class Meta:
        verbose_name = 'Trabajo SNMP'
        verbose_name_plural = 'Trabajos SNMP'
        ordering = ['nombre']
        unique_together = ['tipo', 'modo', 'intervalo']

    def __str__(self):
        return f"{self.nombre} ({self.get_tipo_display()} - {self.get_modo_display()} - {self.intervalo})"

class TareaSNMP(models.Model):
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
    hosts = models.ManyToManyField(Host, verbose_name='Hosts')
    trabajo = models.ForeignKey(
        TrabajoSNMP,
        on_delete=models.PROTECT,
        verbose_name='Trabajo',
        null=True,
        blank=True
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
        hosts_str = ", ".join([h.nombre for h in self.hosts.all()[:3]])
        if self.hosts.count() > 3:
            hosts_str += f" y {self.hosts.count() - 3} más"
        return f"{self.nombre} - [{hosts_str}]"

    @property
    def host_names(self):
        return [host.nombre for host in self.hosts.all()]

    @property
    def host_ips(self):
        return [host.ip for host in self.hosts.all()]

    @property
    def comunidades(self):
        return [host.comunidad for host in self.hosts.all()]

    @property
    def tipo(self):
        return self.trabajo.tipo if self.trabajo else None

    @property
    def modo(self):
        return self.trabajo.modo if self.trabajo else 'principal'

    @property
    def intervalo(self):
        return self.trabajo.intervalo if self.trabajo else '00'

    def get_tipo_display(self):
        return self.trabajo.get_tipo_display() if self.trabajo else ''

    def get_modo_display(self):
        return self.trabajo.get_modo_display() if self.trabajo else 'Principal'

    def get_oid(self):
        if self.trabajo:
            return self.BULK_OIDS.get(self.trabajo.tipo, '')
        return ''

class OnuDato(models.Model):
    """
    Modelo central para la tabla 'onu_datos'.
    Este es el único modelo que debe gestionar esta tabla.
    """
    id             = models.AutoField(primary_key=True)
    host           = models.CharField(max_length=100)
    snmpindex      = models.CharField(max_length=100)
    snmpindexonu   = models.CharField(max_length=50)
    slotportonu    = models.CharField(max_length=30)
    onulogico      = models.IntegerField()
    host_name      = models.CharField(max_length=50, null=True, blank=True)

    # Campos base
    onudesc        = models.CharField(max_length=255, null=True, blank=True)
    act_susp       = models.CharField(max_length=10)
    serialonu      = models.CharField(max_length=50)
    fecha          = models.DateTimeField(auto_now_add=True)
    enviar         = models.BooleanField(default=False)

    # Campos para cada subtipo bulk
    estado_onu         = models.CharField(max_length=50,  null=True, blank=True)
    plan_onu           = models.CharField(max_length=50,  null=True, blank=True)
    potencia_rx        = models.CharField(max_length=50,  null=True, blank=True)
    potencia_tx        = models.CharField(max_length=50,  null=True, blank=True)
    last_down_time     = models.CharField(max_length=50,  null=True, blank=True)
    distancia_m        = models.CharField(max_length=50,  null=True, blank=True)
    modelo_onu         = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        db_table = 'onu_datos'
        managed = True  # Ahora Django gestionará la tabla
        indexes = [
            models.Index(fields=['host', 'snmpindexonu'], name='idx_host_snmpindexonu'),
            models.Index(fields=['fecha'], name='idx_fecha'),
            models.Index(fields=['estado_onu'], name='idx_estado_onu'),
            models.Index(fields=['modelo_onu'], name='idx_modelo_onu'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['host', 'snmpindexonu'],
                name='unique_host_snmpindexonu'
            )
        ]

    def __str__(self):
        return f"{self.host} - {self.snmpindexonu}"


class EjecucionTareaSNMP(models.Model):
    ESTADOS = (
        ('P', 'Pendiente'),
        ('E', 'En Ejecución'),
        ('C', 'Completada'),
        ('F', 'Fallida'),
    )

    tarea      = models.ForeignKey(TareaSNMP, on_delete=models.CASCADE, related_name='ejecuciones')
    host       = models.ForeignKey(Host, on_delete=models.CASCADE, verbose_name='Host', null=True, blank=True)
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
        host_str = f" - {self.host.nombre}" if self.host else ""
        return f"{self.tarea.nombre}{host_str} - {self.get_estado_display()} ({self.inicio:%Y-%m-%d %H:%M:%S})"
