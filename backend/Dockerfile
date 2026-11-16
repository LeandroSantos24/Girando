FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY alembic.ini pyproject.toml ./
COPY app ./app
COPY migrations ./migrations
COPY sql ./sql
COPY docker/entrypoint.sh /entrypoint.sh
# Usuario sin privilegios; el único directorio escribible es el de fotos de desarrollo
# Los archivos se copian con los permisos del disco de quien construye: se normalizan a "lectura para todos"
# para que el usuario sin privilegios pueda leer el código aunque algún archivo esté en 600 en el host.
RUN useradd --system --uid 10001 --home /nonexistent girando \
 && mkdir -p /data/media && chown girando /data/media && chmod 0755 /entrypoint.sh \
 && chmod -R a+rX /app
USER girando
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=30s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2).status == 200 else 1)"
CMD ["/entrypoint.sh"]

FROM base AS dev
USER root
COPY requirements-dev.txt .
RUN pip install -r requirements-dev.txt
# psql: lo usa tests/test_sql_rules.py (sin él, los tests SQL de reglas, arreglos y Georef se saltean)
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client && rm -rf /var/lib/apt/lists/*
COPY tests ./tests
RUN chmod -R a+rX /app/tests
USER girando
