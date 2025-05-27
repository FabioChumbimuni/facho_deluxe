#!/bin/bash

# Activar el entorno virtual
source env/bin/activate

# Crear directorios necesarios
mkdir -p static/css static/js static/images
mkdir -p staticfiles

# Asegurar permisos correctos
chown -R noc:www-data static/
chown -R noc:www-data staticfiles/
chmod -R 755 static/
chmod -R 755 staticfiles/

# Limpiar archivos estáticos antiguos
python3 manage.py collectstatic --clear --noinput

# Recolectar archivos estáticos
python3 manage.py collectstatic --noinput

# Reiniciar Gunicorn
sudo systemctl restart gunicorn 