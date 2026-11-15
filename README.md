# Girando

Marketplace de vehículos (compra/venta), con servicios y empleos del rubro transporte como módulos siguientes.
Este repositorio contiene el **primer MVP funcional**: App web, panel de Admin, API y base de datos reales.

```
App (/)  ─┐                                   ┌─ PostgreSQL 16 (reglas, RLS, auditoría)
          ├─ nginx ── /api ── FastAPI ────────┼─ Redis (rate limit)
Admin ────┘  (mismo origen)       │           └─ worker (vencimientos, retención, estadísticas)
                                  └─ Cloudinary · Mercado Pago · Email · Google · BCRA (interfaces; sin credenciales → "no configurado")
```

La **única fuente de verdad es PostgreSQL** a través de la API. La App y el Admin consumen la misma API.
No hay `localStorage` como backend ni datos de ejemplo en producción.

## Requisitos

- Docker y Docker Compose v2 (Docker Desktop, o `docker-ce` + `docker-compose-plugin` en Linux).
- Opcional para desarrollar sin Docker: Python 3.12, Node 20+, PostgreSQL 16 y Redis 7.

## Levantar todo

```bash
git clone https://github.com/LeandroSantos24/Girando.git
cd Girando
cp .env.example .env
docker compose up --build
```

La primera vez tarda unos minutos (descarga imágenes y aplica migraciones). Cuando `api` queda `healthy`:

| Qué | URL |
|---|---|
| App | http://localhost:3100 |
| Admin | http://localhost:3100/admin |
| API | http://localhost:8100 (también en http://localhost:3100/api) |
| Documentación de la API (Swagger) | http://localhost:8100/docs |
| Estado de integraciones | Admin → Integraciones (solo Super Admin) |

Los puertos son 3100/8100 para no chocar con otros proyectos locales en 3000/8000 (se cambian con `WEB_PORT`/`API_PORT` en `.env`).

Atajos equivalentes: `make setup`, `make dev`, `make test`, `make down`, `make reset` (borra la base), `make logs`.

### Usuarios de desarrollo

Solo existen si `ENV=development` y `SEED_DEV=true` (valores del `.env.example`). Contraseña de todos: `DEV_SEED_PASSWORD`
(por defecto `Girando-dev-2026`). **Nunca usar estas cuentas ni esa contraseña en producción.**

| Email | Rol | Entra en | Para probar |
|---|---|---|---|
| `superadmin@girando.test` | superadmin | http://localhost:3100/admin | todo: planes y precios, promociones, Home, negocio, finanzas, roles, auditoría, integraciones |
| `admin@girando.test` | admin | http://localhost:3100/admin | operación: publicaciones, agencias, usuarios, verificaciones, reportes, catálogo |
| `moderador@girando.test` | moderator | http://localhost:3100/admin | moderación de publicaciones, reportes y verificaciones |
| `usuario@girando.test` | particular | http://localhost:3100 | publicar como particular (1 publicada a la vez) |
| `agencia@girando.test` | dueño de agencia | http://localhost:3100 | “Agencia de Prueba (dev)”: plan Agencia 30 asignado sin cobro y verificación pendiente |

Roles y permisos: [docs/05-roles-y-permisos.md](docs/05-roles-y-permisos.md).

¿Olvidaste una contraseña de desarrollo? `docker compose exec api python -m app.cli seed-dev --reset-passwords`
(vuelve a poner la del `.env` y corrige los roles; no borra nada).

### Empezar de cero (solo la base local)

```bash
docker compose exec api python -m app.cli reset-dev-db --confirm girando
docker compose restart api worker
```

Borra **solo los datos** de la base local de desarrollo (esquemas `app` y `api_public`), vuelve a correr todas las
migraciones desde cero, carga los datos de referencia y los usuarios de desarrollo, y borra las fotos locales de prueba.
No toca migraciones, código, documentación, Git ni `.env`. Se niega a correr si `ENV` no es `development`, si el host
no es local (`db`, `localhost`) o si el nombre de la base que pasás en `--confirm` no coincide. Equivale a `make reset-dev-db`.

El seed **no crea publicaciones, ventas, reseñas ni métricas**: todo lo que ves lo generás usando la App.
Para producción: `ENV=production`, sin seed, y el primer superadmin se crea con
`make superadmin EMAIL=vos@dominio.com` (pide `SUPERADMIN_PASSWORD`).

## Probar el checkpoint (18 pasos)

Manual: registrate en la App → Mi Girando → Publicar vehículo (catálogo, fotos) → “Guardar borrador y salir” →
“Continuar borrador” → “Enviar a revisión” → en `/admin` entrá como `moderador@girando.test` → Publicaciones →
Pendiente → Ver → Aprobar → volvé a la App: búsqueda, detalle, Editar (precio), “Vendí este vehículo”, Ventas → Historial.

Automático (navegador real):

```bash
pip install playwright pillow && playwright install chromium
python3 scripts/e2e_checkpoint.py http://localhost:3100 --shots ./capturas
```

## Variables de entorno

Todas están documentadas en [`.env.example`](.env.example). Las importantes:

| Variable | Uso |
|---|---|
| `ENV` | `development` \| `production`. En producción la API **se niega a arrancar** con CORS `*`, JWT débil, cookies sin `Secure`, fotos en disco local o contraseñas por defecto. |
| `POSTGRES_PASSWORD`, `DB_API_PASSWORD` | Dueño del esquema (migraciones) y rol de conexión de la API (sin privilegios propios). |
| `JWT_SECRET` | Firma de la sesión. Generalo con `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`. |
| `CORS_ORIGINS` | Lista explícita separada por comas. |
| `IMAGE_STORAGE` | `local_dev` (solo desarrollo) o `cloudinary` + `CLOUDINARY_*`. |
| `MERCADOPAGO_ACCESS_TOKEN`, `MERCADOPAGO_WEBHOOK_SECRET` | Suscripciones. Sin token el checkout responde “pagos no habilitados”. |
| `EMAIL_FROM_TRANSACTIONAL`, `EMAIL_FROM_OFFICIAL`, `EMAIL_CONTACT_ADDRESS`, `EMAIL_FROM_MARKETING` | Remitentes por tipo (avisos, oficial, contacto/responder a, marketing con consentimiento). Ver [docs/08](docs/08-verificacion-y-email.md). |
| `EMAIL_PROVIDER`, `EMAIL_API_KEY` | Sin proveedor los emails quedan en cola (Admin → Cola de envíos); en desarrollo el enlace se imprime en el log de la API. |
| `DOCUMENTS_*` | Bucket privado S3-compatible (Cloudflare R2) para documentación de verificaciones. |
| `GOOGLE_PLACES_API_KEY` | Calificación de Google de agencias. Sin key no se muestra ninguna. |
| `EXCHANGE_RATE_PROVIDER` | `bcra` (API oficial, Com. A 3500) o `none`. |

## Migraciones y datos

- Migraciones: **Alembic** con archivos SQL versionados. El esquema completo está en una base única, `backend/sql/0001_base/` (dividida por dominio), con una sola versión (`base_0001`). Se aplican solas al arrancar la API (`python -m app.cli migrate`). Detalle y verificación: [docs/11-migraciones.md](docs/11-migraciones.md).
- Crear una migración nueva: agregá `backend/sql/0002_x.sql` y `backend/migrations/versions/0002_x.py` (`down_revision = "base_0001"`) que llame `run_sql("0002_x.sql")`.
- `python -m app.cli bootstrap-db` crea/actualiza el rol `girando_api` (NOINHERIT, sin privilegios propios).
- `python -m app.cli seed-base` carga datos de referencia **reales e idempotentes**: provincias, departamentos y localidades de todo el país desde el dataset oficial Georef versionado en `backend/app/seeds/georef/` (se descarga con `make georef`; sin dataset, lista mínima de Cuyo), catálogo inicial, planes, motivos de reporte, plantillas de email, políticas de retención y textos legales en borrador.
- `python -m app.cli seed-dev [--reset-passwords]` y `reset-dev-db --confirm <base>` solo corren con `ENV=development`.
- `python -m app.cli jobs [--loop 300]` es el worker: vencimientos de publicaciones, suscripciones (gracia, avisos, pausa de excedentes) y promociones, avisos, purga de fotos de vendidos (7 días), purga de patentes (24 meses), agregados de estadísticas, cotización USD y particiones.

## Tests

```bash
make test                     # pytest dentro de Docker contra PostgreSQL real (base efímera girando_test)
```

Sin Docker: con un PostgreSQL 16 local, `cd backend && pip install -r requirements-dev.txt &&
TEST_DATABASE_ADMIN_URL=postgresql+psycopg://usuario:clave@127.0.0.1:5432/postgres pytest`.

Cobertura actual (62 tests + 50 verificaciones SQL): migraciones y reglas de la base, auth (registro, login, refresh
con rotación, bloqueo por intentos, CSRF, recuperación), publicaciones (ciclo completo, límite `409 LIMITE_ALCANZADO`,
fotos, favoritos, búsqueda), seguridad (edición ajena, autoaprobación, acceso al Admin, rate limit, validaciones,
suscripciones, documentos, IP falsificada), Admin (catálogo, moderación, agencias, usuarios, auditoría) y pagos
(webhook firmado, idempotencia, activación solo por Mercado Pago). Fase 3: matriz de roles por API directa, períodos
por mes calendario, renovación idempotente, vencimiento de planes, inventario vs publicadas, promociones, Home,
perfil y estadísticas de agencia, clics externos, checklist de verificación, finanzas y guardas de `reset-dev-db`.

CI (`.github/workflows/ci.yml`): ruff, bandit, pip-audit, migraciones sobre base vacía (dos veces), pytest con PostgreSQL,
gitleaks, control de que no haya `.env` versionado, frontend regenerado al día y `docker compose build`.

## Estructura

```
backend/            FastAPI + SQL (app/, sql/, migrations/, tests/, Dockerfile)
web/                App (index.html) y Admin (admin/index.html) servidos por nginx
  src/              plantillas (app.html, admin.html) y lógica (*-logic.js): fuente de los HTML generados
  css/              estilos: tokens del diseño + capa responsive (app.css, admin.css)
design/prototipo/   diseño original de Claude Design (referencia visual, no se sirve)
scripts/            build_web.py (genera los HTML), dev-web.mjs (web sin Docker), e2e_checkpoint.py
docs/               auditoría, modelo de datos, diccionario y plan de migración
```

La App y el Admin conservan la identidad del diseño original (colores, Sora, radios, componentes) y son responsive:
mobile (barra inferior), tablet y desktop (header, filtros laterales, navegación lateral en Mi Girando y Admin).
`scripts/build_web.py` une `web/src/*.html` + `web/src/*-logic.js` en `web/index.html` y `web/admin/index.html`.
Si cambiás algo de `web/src/` o `web/css/`, corré `make build-web`. Detalle en `docs/04-frontend-responsive.md`.

E2E en distintos tamaños (usa el sistema levantado):

```bash
python3 scripts/e2e_checkpoint.py http://localhost:3100 --viewport 1440x900
python3 scripts/e2e_checkpoint.py http://localhost:3100 --viewport 768x1024
python3 scripts/e2e_checkpoint.py http://localhost:3100 --viewport 390x844
```

### Desarrollo sin Docker

```bash
cd backend && pip install -r requirements-dev.txt
export DATABASE_OWNER_URL=... DATABASE_URL=... DB_API_PASSWORD=... JWT_SECRET=...   # ver .env.example
python -m app.cli migrate && python -m app.cli bootstrap-db && python -m app.cli seed-base && python -m app.cli seed-dev
uvicorn app.main:app --port 8100
node ../scripts/dev-web.mjs     # http://localhost:3100 con proxy a la API y las mismas cabeceras que nginx
```

## Decisiones tomadas (y por qué)

- **PostgreSQL propio (no Supabase)**: el modelo aprobado usa RLS, triggers y roles; corre igual en cualquier PostgreSQL 16 administrado.
- **SQL primero, sin ORM de modelos**: el esquema (constraints, enums, triggers, RLS) vive en SQL versionado; la API usa SQLAlchemy Core con parámetros ligados.
- **Sesión en cookies httpOnly + CSRF** en lugar de tokens en `localStorage` (ver SECURITY.md).
- **Worker con loop simple** en vez de Celery: menos piezas para el MVP; las tareas son idempotentes.
- **Fotos**: interfaz `ImageStorage` con Cloudinary (subida firmada directa) y `local_dev` solo para desarrollo (prohibido en producción).
- **Documentos privados**: Cloudflare R2 (S3-compatible, sin costo de egreso, privado por defecto) con URLs firmadas de 10 minutos máximo.
- **Dólar**: BCRA, Comunicación A 3500 (referencia oficial mayorista), vía la API pública de Estadísticas Cambiarias. Solo para normalizar filtros/estadísticas; nunca se muestra un precio que el vendedor no cargó.
- **Mercado Pago**: preapproval + webhook con firma `x-signature`; la suscripción se activa solo cuando el backend consulta el recurso en Mercado Pago.
- **Retención**: valores iniciales configurables desde Admin → Retención (fotos vendidas 7 días, patente 24 meses, ventas 5 años, mensajes 12 meses, auditoría 10 años). Marcados “pendiente de validación legal” hasta revisión profesional.

## Documentación

| Doc | Tema |
|---|---|
| [00](docs/00-auditoria-prototipo.md) · [01](docs/01-modelo-de-datos.md) · [02](docs/02-diccionario-de-datos.md) · [03](docs/03-migracion-desde-prototipo.md) | Prototipo, modelo y diccionario de datos, migración |
| [04](docs/04-frontend-responsive.md) | Frontend responsive |
| [05](docs/05-roles-y-permisos.md) | Roles: Super Admin, Admin, Moderación, Finanzas |
| [06](docs/06-planes-suscripciones-y-finanzas.md) | Planes, inventario, períodos por calendario, vencimientos, finanzas |
| [07](docs/07-promociones-home-y-metricas.md) | Promociones, publicidad, Home administrable, clics externos y métricas |
| [08](docs/08-verificacion-y-email.md) | Verificación de agencias y remitentes de email |
| [09](docs/09-gap-analysis-fase3.md) | Gap analysis de la fase 3 (resuelto y pendiente) |

## Pendiente (próximas fases)

Ver [docs/09-gap-analysis-fase3.md](docs/09-gap-analysis-fase3.md). Resumen: mensajes entre usuarios, credenciales reales
(Cloudinary, Mercado Pago sandbox, proveedor de email y dominio), compra de promociones por la agencia y su medición,
transferencia bancaria, reglas finales de verificación, textos legales revisados, despliegue y operación (backups,
monitoreo). Después: calificaciones, Google Places, empleos, servicios y repuestos.
