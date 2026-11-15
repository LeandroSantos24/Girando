# Fase 4 · estado de avance (checkpoint del 15/11/2026, 20:00)

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
   participantes, o moderación solo si hay un mensaje reportado. → `backend/sql/0008_fase4_arreglos.sql`.
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

## Resultado de tests en este punto

- Fases 1 a 3: **62 de 62 verdes** con las migraciones 0004–0007 aplicadas.
- Fase 4 (`backend/tests/test_fase4.py`): **12 de 18 verdes**, 6 en rojo (detalle abajo).
- Falta correr: ruff, bandit, migraciones desde base vacía dos veces, E2E en los tres tamaños.

## Hecho (backend y base)

| Área | Dónde | Estado |
|---|---|---|
| Enums nuevos (carrocerías, rubros de cuenta, espacios publicitarios, eventos) | `sql/0004_fase4_enums.sql` | listo |
| Marketplace: color filtrable, precio normalizado BCRA, historial de precio público, financiación por entidad (TNA+TEA+CFT o ninguna), calculadora | `sql/0005_fase4_marketplace.sql`, `routers/marketplace.py`, `services/search_service.py` | listo, tests verdes |
| Filtros nuevos con contadores reales (versión, color, puertas, permuta, entidad, anticipo máximo, cuota máxima, radio) | `routers/public.py`, `services/search_service.py` | listo, tests verdes |
| Planes por rubro, cupo gratis único del particular (vehículo, taxi o empleo), mejora y baja de plan, candado de repuestos | `sql/0006_fase4_verticales.sql`, `services/account_service.py` | listo, tests verdes salvo repuestos |
| Rutas de cobro: alta, subir 30→60→+60, bajar, cancelar, destacar publicación; webhook y simulador por el mismo camino idempotente | `routers/billing.py`, `routers/payments.py`, `services/payment_gateway.py` | listo, tests verdes |
| Verticales Taxis, Servicios, Repuestos, Empleos (publicar, filtros, moderación, sellos) | `routers/verticals.py` | código escrito, 3 tests en rojo |
| Mensajería interna sin CVs, bloqueo, reporte, moderación | `sql/0007_…`, `routers/messaging.py` | código escrito, 2 tests en rojo |
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

- **Taxis, antigüedad del vehículo**: el contexto del proyecto decía “10 años para incorporarse, uso hasta 13”.
  La Ley 9086 art. 50 dice otra cosa para taxi y remis: taxi 8 años (10 con GNC), remis 5 (6 con GNC), y la unidad
  que entra por renovación no puede superar 5 (taxi) o 3 (remis). Los 13 años son del Decreto 2731/2024 y aplican a
  otros servicios (contratado, escolar, turístico). El texto que muestra Girando quedó con lo del art. 50 y un aviso
  de confirmar en la Dirección de Transporte. **Decisión pendiente del dueño: validar con un gestor antes de lanzar.**
  Fuentes: https://www.mendoza.gov.ar/wp-content/uploads/sites/20/2024/02/Ley-de-Movilidad-No-9086.pdf ·
  https://www.losandes.com.ar/politica/el-gobierno-sumara-400-permisos-de-taxis-en-mendoza-como-estaran-distribuidos
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
