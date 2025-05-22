from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from .models import TareaSNMP
import json

@receiver(post_save, sender=TareaSNMP)
def upsert_poller_master(sender, instance, **kwargs):
    """
    Crea o actualiza la tarea periódica de poller_master para
    cada TareaSNMP de tipo 'bulk' y activa.
    """
    # Solo para tipo 'bulk' y activa
    if instance.tipo != 'bulk' or not instance.activa:
        # Si existiera una PeriodicTask previa, la eliminamos
        PeriodicTask.objects.filter(name=f"poller-master-{instance.id}").delete()
        return

    # Creamos o actualizamos el Crontab según el intervalo minuto
    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute=str(instance.intervalo),  # o 'intervalo_minuto' si ese es el campo correcto
        hour='*', day_of_week='*', day_of_month='*', month_of_year='*'
    )

    # Upsert de la tarea periódica
    PeriodicTask.objects.update_or_create(
        name=f"poller-master-{instance.id}",
        defaults={
            'crontab': schedule,
            'task': 'snmp_scheduler.poller_master',
            'args': json.dumps([]),
            'enabled': True,
        }
    )

@receiver(post_delete, sender=TareaSNMP)
def delete_poller_master(sender, instance, **kwargs):
    """
    Elimina la tarea periódica asociada al poller_master
    cuando se borra la TareaSNMP.
    """
    PeriodicTask.objects.filter(name=f"poller-master-{instance.id}").delete()
