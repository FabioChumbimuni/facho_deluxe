from django.db import models
from django.utils.timezone import now

class Script(models.Model):
    TIPO_CHOICES = (
        ('principal', 'Principal'),
        ('secundario', 'Secundario'),
        ('modo', 'Modo'),
    )
    titulo = models.CharField(
        max_length=100,
        verbose_name="Título del Script",
        default="Sin Título"
    )
    archivo = models.CharField(
        max_length=200,
        verbose_name="Script",
        default="default.sh"
    )
    tipo = models.CharField(
        max_length=20,
        choices=TIPO_CHOICES,
        verbose_name="Tipo de Script"
    )
    ejecucion_automatica = models.BooleanField(
        default=True,
        verbose_name="Ejecutar automáticamente"
    )

    def __str__(self):
        return f"{self.titulo} ({self.tipo})"


class ExecutionRecord(models.Model):
    script = models.ForeignKey(Script, on_delete=models.CASCADE)
    inicio = models.DateTimeField(auto_now_add=True)
    fin = models.DateTimeField(null=True, blank=True)
    estado = models.CharField(max_length=20, default="pendiente")
    log = models.TextField(blank=True, null=True)
    salida = models.TextField(blank=True, null=True)  # Campo para guardar la salida del script

    def __str__(self):
        return f"Ejecución de {self.script.titulo} iniciada el {self.inicio}"


class ExecutionControl(models.Model):
    """
    Modelo para controlar si la ejecución continua de scripts está activada o no.
    Se usará un único registro (singleton) para este control.
    """
    active = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Control de Ejecución"
        verbose_name_plural = "Controles de Ejecución"

    def __str__(self):
        return "Ejecución Activa" if self.active else "Ejecución Inactiva"


class BloqueEjecucion(models.Model):
    nombre = models.CharField(max_length=100, verbose_name="Nombre del Bloque")
    scripts = models.ManyToManyField(Script, verbose_name="Scripts incluidos")
    activo = models.BooleanField(default=False, verbose_name="Bloque Activo")
    # Campo para configurar la frecuencia en minutos de la hora: "00", "15", "30" o "45".
    frecuencia = models.CharField(
        max_length=2,
        choices=(("00", "00"), ("15", "15"), ("30", "30"), ("45", "45")),
        default="00",
        verbose_name="Frecuencia (minuto de la hora)"
    )

    def __str__(self):
        return self.nombre


class BloqueEjecucionRecord(models.Model):
    bloque = models.ForeignKey(BloqueEjecucion, on_delete=models.CASCADE, verbose_name="Bloque")
    inicio = models.DateTimeField(auto_now_add=True, verbose_name="Inicio")
    fin = models.DateTimeField(null=True, blank=True, verbose_name="Final")
    estado = models.CharField(max_length=20, default="pendiente", verbose_name="Estado")
    log = models.TextField(blank=True, null=True, verbose_name="Log")

    def __str__(self):
        return f"Ejecución de {self.bloque.nombre} iniciada el {self.inicio}"


class OnuDatos(models.Model):
    id = models.AutoField(primary_key=True)
    host = models.CharField(max_length=100)
    snmpindex = models.CharField(max_length=100)
    snmpindexonu = models.CharField(max_length=50, unique=True)
    slotportonu = models.CharField(max_length=30)
    onudesc = models.CharField(max_length=255)
    serialonu = models.CharField(max_length=50)
    fecha = models.DateTimeField(auto_now_add=True)
    onulogico = models.IntegerField()
    act_susp = models.CharField(max_length=10)

    class Meta:
        managed = False  # Evita que Django intente modificar la tabla existente
        db_table = 'onu_datos'  # Nombre exacto de la tabla en PostgreSQL

    def __str__(self):
        return f"{self.host} - {self.serialonu}"
