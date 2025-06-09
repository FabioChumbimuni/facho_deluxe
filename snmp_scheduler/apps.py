from django.apps import AppConfig

class SnmpSchedulerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'snmp_scheduler'
    def ready(self):
        import snmp_scheduler.signals
    verbose_name = "Programador SNMP"
    