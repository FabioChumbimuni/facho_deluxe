# snmp_scheduler/models.py

from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError

# snmp_scheduler/models.py (sólo la sección de TareaSNMP)

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
        ('last_down',          'Última desconexión'),
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
        'last_down':         '1.3.6.1.4.1.2011.6.128.1.1.2.46.1.24',
        'pot_rx':            '1.3.6.1.4.1.2011.6.128.1.1.2.51.1.6',
        'pot_tx':            '1.3.6.1.4.1.2011.6.128.1.1.2.51.1.4',
        'last_down_t':       '1.3.6.1.4.1.2011.6.128.1.1.2.101.1.7',
        'distancia_m':       '1.3.6.1.4.1.2011.6.128.1.1.2.46.1.20',
        'modelo_onu':        '1.3.6.1.4.1.2011.6.128.1.1.2.45.1.4',
    
    }

    nombre           = models.CharField(max_length=100, verbose_name="Nombre de la Tarea")
    host_name        = models.CharField(max_length=50,  verbose_name="Nombre del Host")
    host_ip          = models.GenericIPAddressField(protocol='IPv4', verbose_name="IP del OLT")
    comunidad        = models.CharField(max_length=50,  default='public', verbose_name="Comunidad SNMP")
    tipo             = models.CharField(max_length=20, choices=TIPO_CHOICES, default='descubrimiento')
    intervalo        = models.CharField(max_length=10, choices=INTERVALO_CHOICES, default='00')
    modo             = models.CharField(max_length=20, choices=MODO_CHOICES, default='principal')
    activa           = models.BooleanField(default=True, verbose_name="Tarea Activa")
    ultima_ejecucion = models.DateTimeField(null=True, blank=True)
    registros_activos = models.PositiveIntegerField(
        default=0,
        verbose_name="ONUs Registradas",
        help_text="Contador actualizado automáticamente"
    )

    oid_consulta = models.CharField(
        max_length=255,
        blank=True,
        editable=False,
        verbose_name="OID Automático"
    )

    class Meta:
        verbose_name = "Tarea SNMP"
        constraints = [
            models.UniqueConstraint(
                fields=['host_ip', 'intervalo', 'modo'],
                condition=models.Q(modo__in=['principal', 'modo']),
                name='unique_principal_modo'
            ),
            models.UniqueConstraint(
                fields=['host_ip', 'intervalo', 'modo', 'tipo'],
                condition=models.Q(modo='secundario'),
                name='unique_secundario_por_tipo'
            ),
        ]

    def __str__(self):
        tipo_display = dict(self.TIPO_CHOICES).get(self.tipo, self.tipo)
        return f"{self.nombre} - {tipo_display} ({self.host_name})"

    def save(self, *args, **kwargs):
        # Asignamos el OID automático según el tipo elegido
        self.oid_consulta = self.BULK_OIDS.get(self.tipo, '')
        super().save(*args, **kwargs)

    def get_oid(self):
        return self.oid_consulta



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
    ultima_desconexion = models.CharField(max_length=50,  db_column='ultima_desconexion', null=True, blank=True)
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
