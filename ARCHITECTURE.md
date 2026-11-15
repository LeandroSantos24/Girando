# Arquitectura de Girando (MVP)

```
                 ┌──────────────────────────── navegador ────────────────────────────┐
                 │  App  (web/index.html)                Admin (web/admin/index.html) │
                 │  web/src/*.html (plantillas) + *-logic.js + web/css (responsive)    │
                 │  cliente único: web/girando-api.js  (cookies httpOnly + CSRF)       │
                 └───────────────────────────────┬────────────────────────────────────┘
                                                 │ mismo origen
                                   ┌─────────────▼─────────────┐
                                   │ nginx (web)  :3100         │ estáticos + cabeceras (CSP)
                                   │   /api, /media → api:8000  │ X-Real-IP
                                   └─────────────┬─────────────┘
                                   ┌─────────────▼─────────────┐        ┌──────────────┐
                                   │ FastAPI (api) :8000        │───────▶│ Redis        │ rate limit
                                   │ routers → services → SQL   │        └──────────────┘
                                   └─────────────┬─────────────┘
                     SET LOCAL ROLE anon/app/worker + app.user_id por transacción
                                   ┌─────────────▼─────────────┐        ┌──────────────┐
                                   │ PostgreSQL 16              │◀───────│ worker       │ jobs cada 5 min
                                   │ esquema app + api_public   │        └──────────────┘
                                   │ RLS · triggers · auditoría │
                                   └────────────────────────────┘
      Integraciones (interfaces; sin credenciales → NotConfigured, nunca datos simulados):
      Cloudinary (fotos) · Mercado Pago (suscripciones + webhook) · Email (Resend) · Google Places · BCRA (USD) · R2 (documentos)
```

## Principios

1. **Una sola fuente de verdad**: PostgreSQL. La App y el Admin leen y escriben solo por la API.
2. **Defensa en profundidad**: la API valida y autoriza; la base vuelve a verificar con RLS, CHECK y triggers.
   Un error en un endpoint no alcanza para aprobarse una publicación, activar un plan o ver datos ajenos.
3. **Sin datos inventados**: si no hay datos, la interfaz lo dice (“Sin datos suficientes”, “Todavía no hay ventas
   registradas”). Promedios solo con n ≥ 3 (`stats.min_sample_size`). Sellos de confianza solo con evidencia en la base.
4. **Integraciones honestas**: cada servicio externo tiene interfaz propia y, sin configurar, responde `NotConfigured`.

## Backend (`backend/`)

| Capa | Dónde | Qué hace |
|---|---|---|
| Configuración | `app/core/config.py` | Variables de entorno (Pydantic Settings) + guardas de producción |
| Base | `app/core/db.py` | `unit_of_work(rol, user_id, ctx, reason)`: transacción con `SET LOCAL ROLE` y contexto para RLS/auditoría |
| Seguridad | `app/core/security.py`, `middleware.py`, `ratelimit.py` | Argon2id, JWT, CSRF, cabeceras, request ID, logs JSON, rate limit |
| Errores | `app/core/errors.py` | Formato único `{"error": {"code", "message"}}`; traduce SQLSTATE de reglas (GR403/409/422) |
| Routers | `app/api/routers/` | `auth`, `public`, `me`, `billing`, `admin` |
| Servicios | `app/services/` | auth, cuenta/plan, búsqueda (interpreta “gol trend 2015”), publicaciones, fotos, analítica |
| Integraciones | `app/integrations/` | Mercado Pago, Google, BCRA, email, documentos R2 |
| SQL | `sql/0001_base/*.sql` | Modelo aprobado: 59 tablas, enums, RLS, triggers, vistas `api_public` |
| Migraciones | `migrations/` | Alembic ejecutando los SQL versionados |
| CLI | `app/cli.py` | `migrate`, `bootstrap-db`, `seed-base`, `seed-dev`, `jobs`, `create-superadmin` |

### Roles de base de datos

| Rol | Uso |
|---|---|
| `girando` (dueño) | migraciones, bootstrap y particiones. La API nunca lo usa en runtime. |
| `girando_api` | login de la API, NOINHERIT, sin privilegios propios |
| `girando_anon` | lectura de vistas `api_public.*` (catálogo, búsqueda, detalle, perfiles públicos) |
| `girando_app` | usuario autenticado; RLS por `app.user_id` |
| `girando_worker` | webhook y jobs (sistema) |

### Estados de una publicación

```
draft ──▶ pending ──▶ published ──▶ paused ──▶ pending (reactivar)
  ▲          │  │          │  └──▶ sold (Vendí este vehículo: crea la venta, programa purga de fotos y patente)
  └──────────┘  │          └──▶ expired (worker) ──▶ pending (renovar)
 (retirar)      ├──▶ rejected ──▶ pending (corregir)
                └──▶ requires_changes ──▶ pending
cualquiera (salvo sold) ──▶ deleted
```

Transiciones de usuario y de moderación separadas; la base las valida (`tg_listing_state`, `tg_listing_guard`, `tg_listing_limit`) y guarda historial.
Contar para el límite del plan: `pending` + `published`.

### Suscripciones

```
Agencia elige plan ─▶ API crea subscription 'pending' (precio lo fija la base) ─▶ preapproval en Mercado Pago
     ─▶ usuario paga en Mercado Pago ─▶ webhook firmado ─▶ API consulta el recurso en MP (la verdad)
     ─▶ worker actualiza subscription/payments ─▶ app.effective_plan() ─▶ límite de publicaciones
```
`payment_events` guarda cada webhook (firma válida o no, idempotencia por clave única, resultado).

## Frontend (`web/`)

- El diseño original de Claude Design queda como referencia visual en `design/prototipo/` (no se sirve).
- Desde la fase 2 las plantillas viven en `web/src/app.html` y `web/src/admin.html` (mismo marcado y estilos del diseño,
  más la estructura responsive) y los estilos en `web/css/app.css` / `admin.css`. `scripts/build_web.py` une plantilla +
  lógica y agrega un hash de versión al CSS. Ver `docs/04-frontend-responsive.md` (breakpoints, layouts, componentes).
- Sin marco de iPhone: la App es una web responsive real (mobile, tablet, desktop). Babel ya no se usa.
- `web/src/app-logic.js` y `admin-logic.js` reemplazan a los antiguos `girando-data.js`/`girando-store.js`
  (localStorage): todo el estado viene de la API.
- `web/girando-api.js`: cliente HTTP único (CSRF, refresh automático, errores tipados, formatos es-AR, etiquetas).
- `web/girando-photo.js`: `<image-slot>` de solo lectura (muestra la foto que devuelve la API o un marcador).
- React, ReactDOM y Sora se sirven desde el propio dominio (`web/vendor`, `web/fonts`): sin CDNs de terceros.
- Módulos fuera del MVP (mensajes, empleos, servicios, repuestos, calificaciones, promociones) muestran “Próximamente”.

## Worker

`python -m app.cli jobs --loop 300`: vence publicaciones y avisa antes, purga fotos de vendidas/eliminadas según la
política de retención, borra patentes vencidas, agrega `listing_stats_daily` desde `analytics_events`, trae la
cotización USD del BCRA y crea particiones futuras. Cada tarea es idempotente y falla aislada.

## Pruebas

- `backend/tests/`: integración contra PostgreSQL real (base efímera) + `tests/sql/900_flujos.sql` (50 verificaciones).
- `scripts/e2e_checkpoint.py`: los 18 pasos del checkpoint en un navegador real (Playwright).
- CI en GitHub Actions.

## Documentos relacionados

- `docs/00-auditoria-prototipo.md` — problemas del prototipo y cómo se resolvieron.
- `docs/01-modelo-de-datos.md`, `docs/02-diccionario-de-datos.md` — modelo aprobado.
- `docs/03-migracion-desde-prototipo.md` — plan de migración.
- `SECURITY.md` — controles de seguridad.
