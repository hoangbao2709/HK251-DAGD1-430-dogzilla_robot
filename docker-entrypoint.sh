#!/bin/bash
set -e

echo "Starting Dogzilla full stack..."

# Start Nginx
echo "Starting Nginx..."
nginx -g 'daemon off;' &
NGINX_PID=$!

# Start Django backend
echo "Starting Django backend (Daphne)..."
cd /app/backend
python manage.py migrate --noinput || true
exec daphne -b 0.0.0.0 -p 8000 backend.asgi:application
