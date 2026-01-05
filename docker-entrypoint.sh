#!/bin/sh
set -e

echo "Starting Dogzilla..."

# Start Django backend on port 8000
echo "Starting Django on port 8000..."
cd /backend
python manage.py migrate --noinput || true
daphne -b 0.0.0.0 -p 8000 backend.asgi:application &
DAPHNE_PID=$!

# Start Next.js frontend on port 3000
echo "Starting Next.js on port 3000..."
cd /app/frontend
npm start &
NEXT_PID=$!

# Wait for any process to exit
wait
