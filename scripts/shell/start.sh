#!/bin/sh
set -e

echo "[START SCRIPT] (i) Waiting for database to be ready..."
# Ensure POSTGRES_HOST, PORT, and USER are set in production env vars
while ! pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$POSTGRES_USER"; do
  echo "[START SCRIPT] (i) Waiting for database connection..."
  sleep 2
done

echo "[START SCRIPT] (i) Running database migrations..."
alembic upgrade head

echo "[START SCRIPT] (i) Starting FastAPI application..."
# Uses Render's $PORT and defaults to 1 worker if not specified
exec gunicorn app.main:main_app -k uvicorn.workers.UvicornWorker --bind "0.0.0.0:$PORT" --workers "${WEB_CONCURRENCY:-1}" --forwarded-allow-ips '*' --proxy-headers