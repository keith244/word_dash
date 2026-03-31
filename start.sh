#!/bin/bash
set -e

echo "Starting Django application..."

# Run migrations
echo "Running database migrations..."
python manage.py migrate --noinput

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput --clear

# Start the application with Daphne for ASGI support (WebSocket support)
echo "Starting Daphne server..."
exec daphne -b 0.0.0.0 -p 8080 core.asgi:application
