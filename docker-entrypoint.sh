#!/bin/bash
set -e

echo "Starting Dogzilla services..."

# Start Nginx in background
echo "Starting Nginx..."
nginx -g 'daemon off;' &

# Start Django with Daphne
echo "Starting Django backend..."
cd /app
python manage.py migrate --noinput || true
exec daphne -b 0.0.0.0 -p 8000 backend.asgi:application
