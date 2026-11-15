#!/bin/sh
# Arranque de la API: migraciones → rol de conexión → datos base → (dev) seed de desarrollo → uvicorn.
# Todo es idempotente: se puede reiniciar el contenedor sin efectos secundarios.
set -e
python -m app.cli migrate
python -m app.cli bootstrap-db
python -m app.cli seed-base
if [ "$ENV" = "development" ] && [ "${SEED_DEV:-true}" = "true" ]; then
  python -m app.cli seed-dev
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-server-header
