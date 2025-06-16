# snmp_scheduler/tasks/host_verifier.py

import logging
import subprocess
import socket
from celery import shared_task
from django.utils import timezone
from django.db import close_old_connections, transaction
from django.core.cache import cache
from ..models import Host
from celery.utils.log import get_task_logger
import time

logger = get_task_logger(__name__)

def check_host_ping(ip_address, num_pings=3):
    """
    Realiza una verificación rigurosa del host:
    1. Múltiples pings con diferentes timeouts
    2. Verifica que la IP sea válida
    3. Registra tiempos de respuesta
    """
    try:
        # Validar formato de IP
        try:
            socket.inet_aton(ip_address)
        except socket.error:
            logger.error(f"[PROTOCOL VERIFICADOR] IP inválida: {ip_address}")
            return False, "IP inválida"

        # Realizar múltiples pings con diferentes timeouts
        successful_pings = 0
        total_time = 0
        
        for i in range(num_pings):
            timeout = 2 if i == 0 else 3  # Primer ping más rápido
            cmd = ['ping', '-c', '1', '-W', str(timeout), ip_address]
            start_time = time.time()
            
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout+1)
                if result.returncode == 0:
                    successful_pings += 1
                    # Extraer tiempo de respuesta
                    for line in result.stdout.split('\n'):
                        if 'time=' in line:
                            try:
                                time_ms = float(line.split('time=')[1].split()[0])
                                total_time += time_ms
                                logger.info(f"[PROTOCOL VERIFICADOR] Ping {i+1} exitoso: {time_ms}ms")
                            except:
                                pass
                else:
                    logger.warning(f"[PROTOCOL VERIFICADOR] Ping {i+1} falló: {result.stderr}")
            except subprocess.TimeoutExpired:
                logger.warning(f"[PROTOCOL VERIFICADOR] Ping {i+1} timeout")
            
            # Pequeña pausa entre pings
            if i < num_pings - 1:
                time.sleep(0.5)
        
        # Análisis de resultados
        success_rate = (successful_pings / num_pings) * 100
        avg_time = total_time / successful_pings if successful_pings > 0 else 0
        
        if successful_pings == 0:
            return False, f"0% pings exitosos ({num_pings} intentos)"
        elif successful_pings < num_pings:
            return False, f"{success_rate}% pings exitosos, tiempo promedio: {avg_time:.1f}ms"
        else:
            return True, f"100% pings exitosos, tiempo promedio: {avg_time:.1f}ms"
            
    except Exception as e:
        logger.error(f"[PROTOCOL VERIFICADOR] Error en verificación de {ip_address}: {str(e)}")
        return False, f"Error: {str(e)}"

@shared_task(
    bind=True,
    name='snmp_scheduler.tasks.verificar_host',
    queue='verificador',
    ignore_result=True,
    max_retries=0,
    time_limit=20  # Aumentado para permitir verificación más rigurosa
)
def verificar_host(self, host_id):
    """
    PROTOCOL VERIFICADOR:
    1. Se ejecuta cuando hay un timeout SNMP
    2. Realiza verificación rigurosa con múltiples pings
    3. Si no responde, desactiva el host
    4. Mantiene estado en Redis para comunicación con PROTOCOL ANTITIMEOUT
    """
    verificacion_key = f"verificacion_en_curso_{host_id}"
    
    try:
        # Intentar establecer la marca de verificación en Redis
        # Si ya existe una verificación, salir inmediatamente
        if not cache.add(verificacion_key, "iniciando", timeout=300):
            logger.info(f"[PROTOCOL VERIFICADOR] Ya existe una verificación en proceso para host_id={host_id}")
            return
            
        with transaction.atomic():
            try:
                host = Host.objects.select_for_update().get(pk=host_id)
            except Host.DoesNotExist:
                logger.error(f"[PROTOCOL VERIFICADOR] No existe host con id={host_id}")
                cache.delete(verificacion_key)
                return
                
            # Si ya está desactivado, no hacer nada
            if not host.activo:
                logger.info(f"[PROTOCOL VERIFICADOR] Host {host.nombre} ya está desactivado")
                cache.delete(verificacion_key)
                return
                
            # Actualizar estado en Redis
            cache.set(verificacion_key, "en_proceso", timeout=300)
            logger.info(f"[PROTOCOL VERIFICADOR] Iniciando verificación rigurosa de {host.nombre} (IP: {host.ip})")
            
            # Realizar verificación rigurosa
            ping_ok, detalles = check_host_ping(host.ip, num_pings=3)
            logger.info(f"[PROTOCOL VERIFICADOR] Resultado verificación de {host.nombre}: {detalles}")
            
            if not ping_ok:
                # Desactivar host
                logger.warning(f"[PROTOCOL VERIFICADOR] Host {host.nombre} no responde - Desactivando. Detalles: {detalles}")
                host.activo = False
                host.save()
                logger.info(f"[PROTOCOL VERIFICADOR] Host {host.nombre} desactivado exitosamente")
                cache.set(verificacion_key, f"desactivado - {detalles}", timeout=300)
            else:
                logger.info(f"[PROTOCOL VERIFICADOR] Host {host.nombre} responde correctamente. Detalles: {detalles}")
                cache.set(verificacion_key, f"activo - {detalles}", timeout=300)
                
    except Exception as e:
        logger.error(f"[PROTOCOL VERIFICADOR] Error verificando host_id={host_id}: {str(e)}")
        cache.set(verificacion_key, f"error - {str(e)}", timeout=300)
    finally:
        # No eliminamos la clave de verificación aquí para mantener el estado
        # Se eliminará automáticamente después del timeout
        pass 