from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django_celery_beat.models import PeriodicTask, IntervalSchedule, CrontabSchedule
from .models import TareaSNMP
import json

@receiver(post_save, sender=TareaSNMP)
def crear_tarea_periodica(sender, instance, created, **kwargs):
    schedule, _ = IntervalSchedule.objects.get_or_create(
        every=int(instance.intervalo),
        period=IntervalSchedule.MINUTES
    )
    
    PeriodicTask.objects.update_or_create(
        name=f"SNMP-{instance.id}-{instance.nombre}",
        defaults={
            'interval': schedule,
            'task': 'snmp_scheduler.tasks.ejecutar_tarea_snmp',
            'args': json.dumps([instance.id]),
            'enabled': instance.activa
        }
    )


@receiver(post_save, sender=TareaSNMP)
def upsert_periodic_task(sender, instance, **kwargs):
    # Solo tareas bulk activas
    if instance.tipo != 'bulk' or not instance.activo:
        return

    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute=str(instance.intervalo_minuto),
        hour='*', day_of_week='*', day_of_month='*', month_of_year='*'
    )
    PeriodicTask.objects.update_or_create(
        name=f"poller-master-{instance.id}",
        defaults={
            'crontab': schedule,
            'task': 'snmp_scheduler.poller_master',
            'enabled': True,
            'args': json.dumps([]),
        }
    )

@receiver(post_delete, sender=TareaSNMP)
def delete_periodic_task(sender, instance, **kwargs):
    PeriodicTask.objects.filter(name=f"poller-master-{instance.id}").delete()