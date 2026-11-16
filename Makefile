# Girando · atajos de desarrollo local (equivalen a los comandos del README).
# Todo corre en Docker Compose. Nada de esto toca producción.
.DEFAULT_GOAL := help
COMPOSE := docker compose
DB_NAME ?= girando

.PHONY: help setup dev down logs test reset reset-dev-db build-web superadmin lint georef

help:  ## Lista los atajos
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  make %-14s %s\n", $$1, $$2}'

setup:  ## Crea .env desde .env.example (si no existe) y construye las imágenes
	@test -f .env || cp .env.example .env
	$(COMPOSE) build

dev:  ## Levanta todo (App http://localhost:3100 · API http://localhost:8100)
	$(COMPOSE) up --build

down:  ## Detiene los servicios (conserva la base)
	$(COMPOSE) down

logs:  ## Sigue los logs
	$(COMPOSE) logs -f --tail=100

test:  ## pytest dentro de Docker contra PostgreSQL real (base efímera girando_test)
	$(COMPOSE) --profile test run --rm --build tests

reset:  ## BORRA la base local y los volúmenes (docker compose down -v)
	$(COMPOSE) down -v

reset-dev-db:  ## Vacía la base local de desarrollo, migra desde cero y carga los seeds (solo ENV=development)
	$(COMPOSE) up -d db redis
	$(COMPOSE) run --rm --no-deps --build api python -m app.cli reset-dev-db --confirm $(DB_NAME)
	$(COMPOSE) up -d --build --force-recreate api worker

build-web:  ## Regenera web/index.html y web/admin/index.html desde web/src
	python3 scripts/build_web.py

georef:  ## Descarga provincias, departamentos y localidades del dataset oficial Georef (datos.gob.ar) al repo
	python3 scripts/georef_descargar.py

superadmin:  ## Crea el primer superadmin: make superadmin EMAIL=vos@dominio.com (pide SUPERADMIN_PASSWORD)
	@test -n "$(EMAIL)" || (echo "Falta EMAIL=..." && exit 1)
	$(COMPOSE) exec -e SUPERADMIN_PASSWORD api python -m app.cli create-superadmin $(EMAIL)

lint:  ## ruff + bandit dentro de la imagen de desarrollo
	$(COMPOSE) --profile test run --rm --build tests sh -c "ruff check --no-cache . && bandit -q -r app -c pyproject.toml"
