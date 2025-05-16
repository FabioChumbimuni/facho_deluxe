from django.db.models.signals import post_save
from django.dispatch import receiver
from django_celery_beat.models import PeriodicTask, IntervalSchedule
from .models import TareaSNMP
import json

@receiver(post_save, sender=TareaSNMP)
def crear_tarea_periodica(sender, instance, created, **kwargs):
    schedule, _ = IntervalSchedule.objects.get_or_create(
        every=instance.intervalo,
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