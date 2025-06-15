# snmp_scheduler/tasks/host_verifier.py

import logging
import subprocess
from celery import shared_task
from django.utils import timezone
from django.db import close_old_connections
from ..models import Host
from datetime import timedelta

logger = logging.getLogger(__name__)

def check_host_ping(ip_address, num_packets=4):
    """
    Realiza prueba de ping al host.
    Retorna el número de paquetes exitosos.
    """
    try:
        # Usar ping con timeout de 2 segundos y 4 paquetes
        cmd = ['ping', '-c', str(num_packets), '-W', '2', ip_address]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Extraer número de paquetes recibidos
        if result.returncode == 0:
            # Buscar la línea con las estadísticas
            for line in result.stdout.split('\n'):
                if 'packets transmitted' in line:
                    stats = line.split(',')
                    received = int(stats[1].strip().split()[0])
                    return received
        return 0
    except Exception as e:
        logger.error(f"Error checking ping for {ip_address}: {str(e)}")
        return 0

@shared_task(
    bind=True,
    name='snmp_scheduler.tasks.verificar_host',
    queue='secundario'
)
def verificar_host(self, host_id, is_retry=False):
    """
    Verifica el estado de un host mediante ping y actualiza su estado.
    
    Args:
        host_id: ID del host a verificar
        is_retry: Indica si es un reintento después de 15 minutos
    """
    close_old_connections()
    
    try:
        host = Host.objects.get(pk=host_id)
        
        # Si el host fue desactivado manualmente, no ejecutar el protocolo
        if not host.activo and not host.desactivado_por_timeout:
            logger.info(f"Host {host.nombre} fue desactivado manualmente, saltando verificación")
            return
            
        # Realizar prueba de ping
        packets_received = check_host_ping(host.ip)
        logger.info(f"Host {host.nombre} - Paquetes recibidos: {packets_received}/4")
        
        if packets_received <= 1:  # Si fallan 3 o más paquetes
            if not is_retry:
                # Primera falla - Desactivar y programar reintento
                host.activo = False
                host.desactivado_por_timeout = True
                host.ultimo_timeout = timezone.now()
                host.save()
                
                # Programar reintento en 15 minutos
                verificar_host.apply_async(
                    args=[host_id, True],
                    countdown=900  # 15 minutos
                )
                logger.warning(f"Host {host.nombre} desactivado por timeout. Reintento en 15 minutos")
            else:
                # Reintento fallido - Mantener desactivado
                logger.error(f"Host {host.nombre} - Reintento fallido, se mantiene desactivado")
        else:
            # Ping exitoso
            if is_retry or host.desactivado_por_timeout:
                # Reactivar solo si fue desactivado por timeout
                host.activo = True
                host.desactivado_por_timeout = False
                host.save()
                logger.info(f"Host {host.nombre} reactivado después de timeout")
                
    except Host.DoesNotExist:
        logger.error(f"Host {host_id} no existe")
    except Exception as e:
        logger.error(f"Error verificando host {host_id}: {str(e)}")
        
    finally:
        close_old_connections() 