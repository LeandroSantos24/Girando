# Fase 4 · estado de avance (checkpoint del 16/11/2026, 01:40)

Archivo de traspaso: cualquier sesión que retome la fase 4 empieza por acá.
Todo local. Nada desplegado. Nada de datos ni pagos reales.

## Bitácora por paso (CONTEXTO.md §9) — sesión del 15/11/2026 por la noche

> **Límite de esta sesión:** se trabajó sobre un clon del repo, sin Docker ni las dependencias de Python de la API
> (FastAPI, SQLAlchemy, Alembic, psycopg). Por eso **pytest de la API NO se corrió en esta sesión**. Todo lo que es SQL
> se probó contra un PostgreSQL 16 real con `psql`. Cada paso dice qué se verificó y qué falta correr con `make test`.

| Paso | Estado | Verificado | Falta |
|---|---|---|---|
| 1. Git | Ya estaba hecho (commit inicial `a970979` subido por el dueño). `.gitignore` revisado: excluye `.env`, `.env.*`, `*.rdb`, `media/` | `git ls-files` no contiene `.env` | **El repo en GitHub está público**; CONTEXTO.md dice privado (decisión del dueño) |
| 2. Limpieza fuera del repo | **No hecho**: la sesión no puede borrar archivos en la computadora del dueño | — | Borrar a mano `../backend/`, `../Claude outputs/` y `../girando-completo.zip` |
| 3. Limpieza dentro del repo | Hecho | Búsqueda de referencias antes de borrar; `python3 scripts/build_web.py` no cambia los HTML | — |

### Paso 3 · qué se borró o movió y por qué
- `web/ios-frame.jsx` **borrado**: marco de iPhone del prototipo. Ninguna página lo carga (no está en `web/src/*.html`,
  ni en `web/Dockerfile`, ni en nginx); solo lo nombraban un comentario y el prototipo de `design/`.
- `docs/10-contexto-girando.md` y `docs/PROMPT-FASE-4.md` **movidos a `docs/historial/`**: superados por `CONTEXTO.md`.
  Referencias actualizadas en `CONTEXTO.md` y en `docs/INVESTIGACION-DATOS-PUBLICIDAD-PANELES.md`.
- `Makefile` **recreado** según el README (`setup`, `dev`, `down`, `logs`, `test`, `reset`, `reset-dev-db`, `build-web`,
  `superadmin`) más `lint`. El README lo documentaba pero no estaba en el repo.
- Scripts: no hay duplicados (`build_web.py`, `dev-web.mjs`, `e2e_checkpoint.py`, `generar_diccionario.py` están todos referenciados).
- **Pendiente detectado**: el README menciona `.github/workflows/ci.yml` y ese archivo no existe en el repo.

### Paso 4 · tests en rojo de la fase 4
Tres causas, dos de ellas en la base:
1. **Recursión RLS en `messages`**: la política `msg_select` consultaba `app.messages` dentro de sí misma. Ahora usa
   `app.conversation_has_message_report(uuid)` (`SECURITY DEFINER`, devuelve solo un booleano). El alcance no cambia:
   participantes, o moderación solo si hay un mensaje reportado. → hoy en `backend/sql/0001_base/130_rls.sql`.
2. **Casa de repuestos que quedaba `pending`**: la causa no estaba en el endpoint sino en el trigger
   `tg_verifications_effects`, que solo propagaba el resultado a la cuenta cuando el producto era de tipo `agency`;
   el de repuestos es `onsite_visit`. Ahora propaga ambos. El candado de pago (`PAGO_REQUERIDO_ANTES_DE_VERIFICAR`) sigue igual.
3. **Rate limit de registro en los tests**: el helper `register` de `conftest.py` reinicia solo el bucket `register_ip`
   (`ratelimit.reset_memory(bucket)`); los demás límites siguen contando.

Verificado con PostgreSQL 16 real: `tests/sql/910_fase4_arreglos.sql` (nuevo, **11/11 ok**), con control negativo
(sin 0008 falla con `infinite recursion detected in policy for relation "messages"` y con la cuenta en `pending`).
`tests/sql/900_flujos.sql` sigue en **50/50**. `ruff` limpio en los archivos tocados.
**Falta:** correr `make test` para confirmar que los 6 tests de `test_fase4.py` pasan a verde. Los de taxis y servicios
se diagnosticaron como arrastre del rate limit; si quedara otro rojo, es un hallazgo nuevo.

### Paso 5 · Taxis sin antigüedad
- No existía validación de antigüedad por ley en el código ni en la base. Sí había: la nota `taxi.vehicle_age_note`
  (texto de la Ley 9086), su campo `vehicle_age_note` en `GET /api/posts/{code}`, un aviso legal largo específico de
  Mendoza y un piso de año 1980 en `taxi_posts` (más alto que el de vehículos).
- Ahora: único texto, `taxi.legal_notice` = “La transferencia del permiso requiere autorización de la autoridad de
  transporte.” (editable en Admin → Configuración). Nota y campo eliminados. Año de taxi 1900–2100, igual que `vehicles`
  (control de plausibilidad, no de antigüedad). → hoy en `backend/sql/0001_base/180_verticales_planes.sql`, `seeds/base_data.py`,
  `routers/verticals.py`.
- Test actualizado (`test_taxi_post…`): el aviso es exactamente el corto, no existe `vehicle_age_note` y un taxi modelo 1975 se publica.
- Verificado: la migración aplica sobre base vacía y `tx_year` queda 1900–2100; ruff limpio. **Falta:** `make test`.

### Paso 6 · migraciones compactadas en una base única
- `backend/sql/0001_base/` (20 archivos por dominio) + una sola versión de Alembic (`base_0001`). Detalle: `docs/11-migraciones.md`.
- **Esquema equivalente verificado**: `pg_dump --schema-only` antes (0001–0009) y después (base única) → sin diferencias,
  mismo hash incluso con dueños y permisos. 72 tablas, 238 políticas RLS, 80 enums.
- **Dos veces desde base vacía**: mismo resultado las dos veces. Tests SQL sobre la base nueva: 900 = 50/50, 910 = 11/11.
- `migrate` rechaza con mensaje claro una base local en una revisión antigua (`0001`…`0009`): se recrea con `make reset-dev-db`,
  que ahora funciona aunque la API no arranque.
- **Falta (necesita Docker):** `make reset-dev-db`, `make test` y correr `migrate` por segunda vez con Alembic (debe ser un no-op).

### Paso 7 · todo el país con Georef — **herramientas listas, dataset sin descargar**
- `scripts/georef_descargar.py` (`make georef`): baja provincias, departamentos y localidades de la descarga completa oficial
  (`https://apis.datos.gob.ar/georef/api/v2.0/{entidad}.json`), los normaliza a CSV y escribe `FUENTE.json` (URLs, fecha, filas, sha256).
- `backend/app/seeds/georef/cargar.sql` + `seed-base`: carga idempotente por código oficial; adopta las filas viejas sin
  código conservando su `id`; no borra. Sin dataset, `seed-base` usa la lista mínima anterior y lo avisa.
- Verificado: cargador SQL con `tests/sql/920_georef.sql` (**8/8**, PostgreSQL 16); descargador contra un servidor local
  con una muestra en la forma documentada (normaliza, omite huérfanos, corta si las cantidades no son plausibles).
- **Falta (bloqueante para dar el paso por cerrado):** correr `make georef` en una máquina con salida a `apis.datos.gob.ar`
  y versionar los 4 archivos. No se pudo confirmar contra la API real el nombre exacto de los campos de la v2.0; si difiere,
  el script corta con un mensaje claro y no escribe nada.
- A revisar al cargar: `GET /api/geo?level=locality` devuelve todas las localidades sin paginar (hoy solo se usa con `parent_id`).

### Pasos 8, 9 y 10 — **no empezados**
Frontend de la fase 4 (con WhatsApp por `/api/out`), publicidad etapas A y B, y el cierre (docs, ruff, bandit, E2E) necesitan
un entorno donde se pueda levantar la API (Docker, o Python con FastAPI/SQLAlchemy/psycopg) para probar lo que se escribe.
La próxima sesión empieza por: `make reset-dev-db && make test`, confirmar los 80 tests, `make georef`, y seguir con el paso 8.

## Resultado de tests en este punto

**LÍNEA BASE VERDE — tercera corrida (16/11/2026, 01:35, máquina del dueño, commit `f271087`): 80/80, 0 rojos, 0 salteados.**
`make reset-dev-db` (Alembic `base_0001` + seeds) y `make test` completos en Docker, con los tests SQL incluidos.

Pendiente del paso 1 del encargo nuevo: `make lint` (ruff + bandit dentro de Docker), correr `migrate` por segunda vez
(debe ser un no-op), `git push origin main` y `make georef`. Después: paso 3 (frontend de la fase 4).

Historia de cómo se llegó al verde (cinco bugs reales que estaban tapados):

**Primera corrida real con Docker (15/11/2026, 21:55, máquina del dueño): 80 tests → 74 verdes, 5 rojos, 1 salteado.**
`reset-dev-db` y Alembic (`base_0001`) funcionaron. Los arreglos del paso 4 se confirmaron: ya no hay recursión RLS y la
casa de repuestos queda `verified`. Los 5 rojos eran dos fallas que antes quedaban tapadas, ya corregidas (falta volver a correr):

1. **4 tests de verticales** (`parts_store`, `taxi`, `service_provider`, `candidate_contacts`): `GET /api/posts` sin sesión
   devolvía 403 `permission denied for function subscription_grants`. La vista `api_public.posts` usa esa función y las
   funciones de `app` están revocadas a PUBLIC; al visitante le faltaba `EXECUTE`. **El listado público de las cuatro
   verticales nunca funcionó sin sesión.** Arreglo: `GRANT EXECUTE … TO girando_anon` (función pura, no lee tablas).
   Reproducido y verificado con PostgreSQL 16; nuevo control en `910_fase4_arreglos.sql` que lee las 19 vistas públicas como anónimo.
2. **`test_cors_only_allowed_origins`**: el test espera `http://localhost:3000` (valor por defecto) pero en Docker el `.env`
   trae `CORS_ORIGINS=http://localhost:3100`. No es un bug de la API: `conftest.py` ahora fija el valor para los tests.
3. **El salteado** era `test_sql_business_rules`: la imagen de tests no tenía `psql`, así que los tests SQL (900, 910, 920)
   no corrían en `make test`. El Dockerfile de desarrollo ahora instala `postgresql-client`.

También: el Dockerfile normaliza permisos (`chmod -R a+rX /app`), porque 20 archivos estaban en modo 600 en el disco y
la API no los podía leer dentro del contenedor.

**Segunda corrida (16/11/2026, 01:10): 80 tests → 77 verdes, 3 rojos, 0 salteados.** Los 5 anteriores quedaron resueltos, la
imagen se construyó con `psql` y los tests SQL corrieron dentro de `make test`. Los 3 rojos nuevos eran líneas que nunca se
habían ejecutado; dos causas, ya corregidas (falta volver a correr):

4. **Sello de verificación (taxis y servicios), 2 tests:** `POST /api/admin/posts/{id}/seal` devolvía 422 siempre. La ruta
   genérica `/admin/posts/{id}/{action}` estaba registrada antes y capturaba `seal` como una acción inválida.
   **El sello "permiso verificado" / "matrícula verificada" nunca se pudo poner.** Arreglo: `/seal` va antes.
5. **Asunto de la conversación, 1 test:** quien contacta no es dueño de la publicación y RLS no le deja leer
   `listings`/`posts`, así que veía la conversación sin título y con vertical `vehicle` aunque fuera un empleo.
   Arreglo: `app.conversation_subject()` (`SECURITY DEFINER`, solo para participantes, solo datos ya públicos de la ficha).
   Verificado en SQL: la compradora ve el asunto, un tercero no.

- **Tests SQL con PostgreSQL 16:** `900_flujos.sql` 50/50 · `910_fase4_arreglos.sql` 15/15 · `920_georef.sql` 8/8.
- **Falta:** bandit, `migrate` por segunda vez, Georef, E2E.

## Hecho (backend y base)

| Área | Dónde | Estado |
|---|---|---|
| Enums nuevos (carrocerías, rubros de cuenta, espacios publicitarios, eventos) | `sql/0001_base/010_enums.sql` | listo |
| Marketplace: color filtrable, precio normalizado BCRA, historial de precio público, financiación por entidad (TNA+TEA+CFT o ninguna), calculadora | `sql/0001_base/170_…`, `routers/marketplace.py`, `services/search_service.py` | listo, tests verdes |
| Filtros nuevos con contadores reales (versión, color, puertas, permuta, entidad, anticipo máximo, cuota máxima, radio) | `routers/public.py`, `services/search_service.py` | listo, tests verdes |
| Planes por rubro, cupo gratis único del particular (vehículo, taxi o empleo), mejora y baja de plan, candado de repuestos | `sql/0001_base/180_…`, `services/account_service.py` | listo, tests verdes salvo repuestos |
| Rutas de cobro: alta, subir 30→60→+60, bajar, cancelar, destacar publicación; webhook y simulador por el mismo camino idempotente | `routers/billing.py`, `routers/payments.py`, `services/payment_gateway.py` | listo, tests verdes |
| Verticales Taxis, Servicios, Repuestos, Empleos (publicar, filtros, moderación, sellos) | `routers/verticals.py` | código escrito, 3 tests en rojo |
| Mensajería interna sin CVs, bloqueo, reporte, moderación | `sql/0001_base/190_…`, `routers/messaging.py` | código escrito, 2 tests en rojo |
| Publicidad medida, consentimiento de cookies, recomendaciones explicables, búsquedas guardadas, historial | `routers/marketplace.py` | listo salvo 1 test |
| Jobs: vencimiento de posts, límites de plan, retención de mensajes, avisos de búsquedas guardadas | `app/cli.py` | escritos |
| Seeds: planes 60 / repuestos / servicios / empresa, entidades, textos legales de taxis y financiación, checklist de repuestos | `seeds/base_data.py` | listo |

## En rojo ahora (causa conocida)

1. `test_candidate_contacts…`, `test_message_retention…`, `test_taxi_post…`, `test_service_provider…`:
   **recursión infinita en la política RLS de `messages`** (la subconsulta de no leídos sobre `app.messages`
   dispara la política que vuelve a consultar conversaciones/mensajes). Arreglo: función `SECURITY DEFINER`
   para saber si el usuario participa de la conversación y usarla en las políticas, en una migración 0008.
   Los tests de taxis y servicios caen por arrastre (registran muchos usuarios y chocan con el rate limit
   de registro: 5 por hora por IP); hay que reiniciar ese contador en el helper `register` de `conftest.py`.
2. `test_parts_store…`: `POST /api/admin/agencies/{id}/verify` devuelve `pending` para una casa de repuestos;
   revisar el endpoint en `routers/admin.py` o `business.py`.
3. `test_recommendations…`: mismo rate limit de registro.

## Falta

- Frontend completo de la fase 4 (`web/src/`): navegación por vertical, filtros nuevos, calculadora, Mi Girando,
  mensajes, pantallas de Admin (ofertas de financiación, posts, mensajes reportados, productos), tipografía autoservida.
- `docs/11` en adelante, actualización de README, SECURITY y `docs/10`.
- ruff, bandit, migraciones x2, E2E, informe final.

## Hallazgos de cumplimiento (con fuente)

- **Taxis, antigüedad del vehículo**: **resuelto por decisión del dueño (CONTEXTO.md §2): sin límite de antigüedad ni
  validaciones.** Girando no muestra ni aplica ningún régimen de antigüedad. El análisis anterior de la Ley 9086 de Mendoza
  queda en el historial de Git; al ser un portal de todo el país, cada jurisdicción tiene su propio régimen.
- **Transferencia del permiso**: Ley 9086 art. 46 b: no se transfiere sin autorización administrativa previa,
  recién a los dos años de otorgado, y el nuevo titular debe cumplir las mismas condiciones.
- **Publicidad de crédito**: el BCRA exige que el CFT vaya destacado (tipografía al menos cinco veces mayor que la de
  la TNA en la publicidad de las entidades). Girando no es entidad financiera, pero se toma el criterio más exigente:
  CFT como dato principal, TNA y TEA siempre junto. Fuente: https://www.bcra.gob.ar/archivos/Pdfs/Texord/t-tasint.pdf
- **Productores de seguros**: la matrícula se consulta en el registro de la SSN
  (https://www.argentina.gob.ar/superintendencia-de-seguros). En Girando es un dato declarado; el sello lo pone el equipo.

## Decisiones tomadas (valores iniciales, editables en Admin → Planes)

- Agencia 60: $ 79.900 / mes (a confirmar). Agencia +60: 100 publicadas, $ 99.900 (a confirmar).
- Repuestos: $ 4.000 por mes, 500 ítems de catálogo (a confirmar período y tope).
- Servicios: gratis, 1 ficha por rubro y zona. Empresa (empleos): gratis, 3 avisos activos (a confirmar).
- Subir de plan: rige al aprobarse el pago, el período se reinicia, sin prorrateo. Bajar: rige al renovar; lo que
  excede se pausa, no se borra.
- Simulador de pagos: `PAYMENTS_SIMULATOR=true`, solo desarrollo y tests; la API se niega a arrancar con él en producción.

## Cómo correr los tests

```bash
cd backend && TEST_DATABASE_ADMIN_URL=postgresql+psycopg://usuario:clave@127.0.0.1:5432/postgres pytest -q
```
