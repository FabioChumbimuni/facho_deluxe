# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class AuthGroup(models.Model):
    name = models.CharField(unique=True, max_length=150)

    class Meta:
        managed = False
        db_table = 'auth_group'


class AuthGroupPermissions(models.Model):
    id = models.BigAutoField(primary_key=True)
    group = models.ForeignKey(AuthGroup, models.DO_NOTHING)
    permission = models.ForeignKey('AuthPermission', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_group_permissions'
        unique_together = (('group', 'permission'),)


class AuthPermission(models.Model):
    name = models.CharField(max_length=255)
    content_type = models.ForeignKey('DjangoContentType', models.DO_NOTHING)
    codename = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'auth_permission'
        unique_together = (('content_type', 'codename'),)


class AuthUser(models.Model):
    password = models.CharField(max_length=128)
    last_login = models.DateTimeField(blank=True, null=True)
    is_superuser = models.BooleanField()
    username = models.CharField(unique=True, max_length=150)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.CharField(max_length=254)
    is_staff = models.BooleanField()
    is_active = models.BooleanField()
    date_joined = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'auth_user'


class AuthUserGroups(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(AuthUser, models.DO_NOTHING)
    group = models.ForeignKey(AuthGroup, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_user_groups'
        unique_together = (('user', 'group'),)


class AuthUserUserPermissions(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(AuthUser, models.DO_NOTHING)
    permission = models.ForeignKey(AuthPermission, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_user_user_permissions'
        unique_together = (('user', 'permission'),)


class DjangoAdminLog(models.Model):
    action_time = models.DateTimeField()
    object_id = models.TextField(blank=True, null=True)
    object_repr = models.CharField(max_length=200)
    action_flag = models.SmallIntegerField()
    change_message = models.TextField()
    content_type = models.ForeignKey('DjangoContentType', models.DO_NOTHING, blank=True, null=True)
    user = models.ForeignKey(AuthUser, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'django_admin_log'


class DjangoCeleryBeatClockedschedule(models.Model):
    clocked_time = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'django_celery_beat_clockedschedule'


class DjangoCeleryBeatCrontabschedule(models.Model):
    minute = models.CharField(max_length=240)
    hour = models.CharField(max_length=96)
    day_of_week = models.CharField(max_length=64)
    day_of_month = models.CharField(max_length=124)
    month_of_year = models.CharField(max_length=64)
    timezone = models.CharField(max_length=63)

    class Meta:
        managed = False
        db_table = 'django_celery_beat_crontabschedule'


class DjangoCeleryBeatIntervalschedule(models.Model):
    every = models.IntegerField()
    period = models.CharField(max_length=24)

    class Meta:
        managed = False
        db_table = 'django_celery_beat_intervalschedule'


class DjangoCeleryBeatPeriodictask(models.Model):
    name = models.CharField(unique=True, max_length=200)
    task = models.CharField(max_length=200)
    args = models.TextField()
    kwargs = models.TextField()
    queue = models.CharField(max_length=200, blank=True, null=True)
    exchange = models.CharField(max_length=200, blank=True, null=True)
    routing_key = models.CharField(max_length=200, blank=True, null=True)
    expires = models.DateTimeField(blank=True, null=True)
    enabled = models.BooleanField()
    last_run_at = models.DateTimeField(blank=True, null=True)
    total_run_count = models.IntegerField()
    date_changed = models.DateTimeField()
    description = models.TextField()
    crontab = models.ForeignKey(DjangoCeleryBeatCrontabschedule, models.DO_NOTHING, blank=True, null=True)
    interval = models.ForeignKey(DjangoCeleryBeatIntervalschedule, models.DO_NOTHING, blank=True, null=True)
    solar = models.ForeignKey('DjangoCeleryBeatSolarschedule', models.DO_NOTHING, blank=True, null=True)
    one_off = models.BooleanField()
    start_time = models.DateTimeField(blank=True, null=True)
    priority = models.IntegerField(blank=True, null=True)
    headers = models.TextField()
    clocked = models.ForeignKey(DjangoCeleryBeatClockedschedule, models.DO_NOTHING, blank=True, null=True)
    expire_seconds = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'django_celery_beat_periodictask'


class DjangoCeleryBeatPeriodictasks(models.Model):
    ident = models.SmallIntegerField(primary_key=True)
    last_update = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'django_celery_beat_periodictasks'


class DjangoCeleryBeatSolarschedule(models.Model):
    event = models.CharField(max_length=24)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)

    class Meta:
        managed = False
        db_table = 'django_celery_beat_solarschedule'
        unique_together = (('event', 'latitude', 'longitude'),)


class DjangoContentType(models.Model):
    app_label = models.CharField(max_length=100)
    model = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'django_content_type'
        unique_together = (('app_label', 'model'),)


class DjangoMigrations(models.Model):
    id = models.BigAutoField(primary_key=True)
    app = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    applied = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'django_migrations'


class DjangoQOrmq(models.Model):
    key = models.CharField(max_length=100)
    payload = models.TextField()
    lock = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'django_q_ormq'


class DjangoQSchedule(models.Model):
    func = models.CharField(max_length=256)
    hook = models.CharField(max_length=256, blank=True, null=True)
    args = models.TextField(blank=True, null=True)
    kwargs = models.TextField(blank=True, null=True)
    schedule_type = models.CharField(max_length=1)
    repeats = models.IntegerField()
    next_run = models.DateTimeField(blank=True, null=True)
    task = models.CharField(max_length=100, blank=True, null=True)
    name = models.CharField(max_length=100, blank=True, null=True)
    minutes = models.SmallIntegerField(blank=True, null=True)
    cron = models.CharField(max_length=100, blank=True, null=True)
    cluster = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'django_q_schedule'


class DjangoQTask(models.Model):
    name = models.CharField(max_length=100)
    func = models.CharField(max_length=256)
    hook = models.CharField(max_length=256, blank=True, null=True)
    args = models.TextField(blank=True, null=True)
    kwargs = models.TextField(blank=True, null=True)
    result = models.TextField(blank=True, null=True)
    started = models.DateTimeField()
    stopped = models.DateTimeField()
    success = models.BooleanField()
    id = models.CharField(primary_key=True, max_length=32)
    group = models.CharField(max_length=100, blank=True, null=True)
    attempt_count = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'django_q_task'


class DjangoSession(models.Model):
    session_key = models.CharField(primary_key=True, max_length=40)
    session_data = models.TextField()
    expire_date = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'django_session'


class OnuDatos(models.Model):
    host = models.CharField(max_length=100, blank=True, null=True)
    snmpindex = models.CharField(max_length=100, blank=True, null=True)
    snmpindexonu = models.CharField(max_length=50, blank=True, null=True)
    slotportonu = models.CharField(max_length=30, blank=True, null=True)
    onulogico = models.IntegerField(blank=True, null=True)
    onudesc = models.CharField(max_length=255, blank=True, null=True)
    serialonu = models.CharField(max_length=50, blank=True, null=True)
    act_susp = models.CharField(max_length=10, blank=True, null=True)
    fecha = models.DateTimeField(blank=True, null=True)
    enviar = models.BooleanField(blank=True, null=True)
    host_name = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'onu_datos'
        unique_together = (('host', 'snmpindexonu'), ('snmpindexonu', 'host'),)


class ScriptsBloqueejecucion(models.Model):
    id = models.BigAutoField(primary_key=True)
    nombre = models.CharField(max_length=100)
    activo = models.BooleanField()
    frecuencia = models.CharField(max_length=2)

    class Meta:
        managed = False
        db_table = 'scripts_bloqueejecucion'


class ScriptsBloqueejecucionScripts(models.Model):
    id = models.BigAutoField(primary_key=True)
    bloqueejecucion = models.ForeignKey(ScriptsBloqueejecucion, models.DO_NOTHING)
    script = models.ForeignKey('ScriptsScript', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'scripts_bloqueejecucion_scripts'
        unique_together = (('bloqueejecucion', 'script'),)


class ScriptsBloqueejecucionrecord(models.Model):
    id = models.BigAutoField(primary_key=True)
    inicio = models.DateTimeField()
    fin = models.DateTimeField(blank=True, null=True)
    estado = models.CharField(max_length=20)
    log = models.TextField(blank=True, null=True)
    bloque = models.ForeignKey(ScriptsBloqueejecucion, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'scripts_bloqueejecucionrecord'


class ScriptsExecutioncontrol(models.Model):
    id = models.BigAutoField(primary_key=True)
    active = models.BooleanField()

    class Meta:
        managed = False
        db_table = 'scripts_executioncontrol'


class ScriptsExecutionrecord(models.Model):
    id = models.BigAutoField(primary_key=True)
    inicio = models.DateTimeField()
    fin = models.DateTimeField(blank=True, null=True)
    estado = models.CharField(max_length=20)
    log = models.TextField(blank=True, null=True)
    script = models.ForeignKey('ScriptsScript', models.DO_NOTHING)
    salida = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'scripts_executionrecord'


class ScriptsScript(models.Model):
    id = models.BigAutoField(primary_key=True)
    tipo = models.CharField(max_length=20)
    archivo = models.CharField(max_length=200)
    titulo = models.CharField(max_length=100)
    ejecucion_automatica = models.BooleanField()

    class Meta:
        managed = False
        db_table = 'scripts_script'


class SnmpConsultorOltconfig(models.Model):
    id = models.BigAutoField(primary_key=True)
    host = models.CharField(unique=True, max_length=100)
    comunidad = models.CharField(max_length=50)
    tipo_consulta = models.CharField(max_length=20)
    intervalo = models.CharField(max_length=10)
    activo = models.BooleanField()
    ultima_ejecucion = models.DateTimeField(blank=True, null=True)
    proxima_ejecucion = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'snmp_consultor_oltconfig'


class SnmpConsultorSnmpconfig(models.Model):
    id = models.BigAutoField(primary_key=True)
    olt_ip = models.GenericIPAddressField()
    comunidad = models.CharField(max_length=64)
    tipo = models.CharField(max_length=20)
    consulta = models.CharField(max_length=20, blank=True, null=True)
    intervalos = models.TextField()  # This field type is a guess.
    prioridad = models.CharField(max_length=12)
    activo = models.BooleanField()
    creado = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'snmp_consultor_snmpconfig'


class SnmpOltConfig(models.Model):
    nombre = models.CharField(max_length=50)
    host = models.CharField(max_length=15)
    comunidad = models.CharField(max_length=50, blank=True, null=True)
    tipo_consulta = models.CharField(max_length=20)
    consulta = models.CharField(max_length=20, blank=True, null=True)
    intervalo = models.CharField(max_length=10, blank=True, null=True)
    activo = models.BooleanField(blank=True, null=True)
    creado = models.DateTimeField(blank=True, null=True)
    actualizado = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'snmp_olt_config'


class SnmpSchedulerTareasnmp(models.Model):
    id = models.BigAutoField(primary_key=True)
    nombre = models.CharField(max_length=100)
    comunidad = models.CharField(max_length=50)
    intervalo = models.CharField(max_length=10)
    tipo = models.CharField(max_length=20)
    oid_consulta = models.CharField(max_length=255, blank=True, null=True)
    ultima_ejecucion = models.DateTimeField(blank=True, null=True)
    host_ip = models.GenericIPAddressField()
    host_name = models.CharField(max_length=50)
    modo = models.CharField(max_length=20)
    activa = models.BooleanField()
    registros_activos = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'snmp_scheduler_tareasnmp'
        unique_together = (('host_ip', 'intervalo', 'modo'),)
