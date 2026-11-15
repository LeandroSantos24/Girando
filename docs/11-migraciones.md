# 11 · Migraciones: base única

Desde el 15/11/2026 el esquema completo (fases 1 a 4) vive en **una sola base** y **una sola versión de Alembic**.

```
backend/sql/0001_base/              se aplica en orden alfabético, en una transacción
  000_base.sql                      extensiones, esquemas, roles, contexto de la request
  010_enums.sql                     todos los enums (incluye los valores que antes agregaban 0003 y 0004)
  020 … 110                         identidad, ubicaciones, agencias, catálogo, vehículos, confianza,
                                    interacción, comercial, comunicación, plataforma
  120_reglas.sql                    triggers y reglas de negocio
  130_rls.sql                       políticas RLS
  140_api_publica.sql               vistas públicas + permisos y funciones auxiliares de la API (ex 0002)
  150_estadisticas.sql
  160_roles_suscripciones_home.sql  ex 0003 (fase 3)
  170_marketplace_financiacion.sql  ex 0005 (fase 4)
  180_verticales_planes.sql         ex 0006 (fase 4): taxis, servicios, repuestos, empleos, planes por rubro
  190_mensajes_publicidad.sql       ex 0007 (fase 4)
backend/migrations/versions/0001_base.py   revisión base_0001
```

## Qué se compactó

| Antes | Ahora |
|---|---|
| `0001_initial/` | `0001_base/000`–`150` |
| `0002_api_grants.sql` | final de `140_api_publica.sql` |
| `0003_fase3.sql` | `160_…` (sus `ALTER TYPE … ADD VALUE` pasaron a `010_enums.sql`) |
| `0004_fase4_enums.sql` | plegado en `010_enums.sql`, en el mismo orden |
| `0005`, `0006`, `0007` | `170_…`, `180_…`, `190_…` |
| `0008` arreglo RLS de `messages` | plegado en `130_rls.sql` |
| `0008` verificación de repuestos | plegado en `120_reglas.sql` |
| `0009` taxis sin antigüedad | plegado en `180_…` (`tx_year` 1900–2100) |

Los archivos 160–190 siguen usando `ALTER TABLE … ADD COLUMN` sobre tablas creadas en 020–110. Se dejó así a propósito:
plegar cada columna dentro de su `CREATE TABLE` cambia el orden físico de columnas y no aporta nada funcional.

## Verificación (PostgreSQL 16.x real, `psql` y `pg_dump`)

1. **Antes**: base vacía + migraciones 0001–0009 en orden → `pg_dump --schema-only`.
2. **Después**: base vacía + `0001_base/*.sql` en una sola transacción → `pg_dump --schema-only`.
3. `diff` de los dos volcados: **sin diferencias** (mismo hash, también con dueños y permisos incluidos).
   72 tablas en `app`, 238 políticas RLS, 80 enums.
4. **Dos veces desde base vacía** (`mig1`, `mig2`): mismo resultado las dos veces.
5. Tests SQL sobre la base nueva: `900_flujos.sql` 50/50 y `910_fase4_arreglos.sql` 11/11.
6. Las migraciones no insertan datos (los datos de referencia los carga `seed-base`): 0 filas en ambos casos.

**No verificado en esa sesión** (no había Docker ni las dependencias de Python): `python -m app.cli migrate` con Alembic,
`reset-dev-db` y `pytest`. El SQL se aplicó igual que lo aplica `migrations/sqlfiles.py` (un `execute` por archivo, misma
transacción), pero hay que confirmarlo con:

```bash
make reset-dev-db          # recrea la base local con la base única y los seeds
make test                  # todos los tests
docker compose run --rm api python -m app.cli migrate   # segunda vez: no tiene que hacer nada
```

## Bases locales creadas con las migraciones viejas

No se actualizan en el lugar. `migrate` se niega con un mensaje claro si encuentra `alembic_version` en `0001`…`0009`.
Como no hay datos reales, se recrea: `make reset-dev-db` (funciona aunque la API no arranque) o `make reset && make dev`.

## Cómo agregar una migración

1. `backend/sql/0002_<tema>.sql` (o una carpeta `0002_<tema>/` con varios archivos).
2. `backend/migrations/versions/0002_<tema>.py` con `revision = "0002_<tema>"`, `down_revision = "base_0001"` y `run_sql("0002_<tema>.sql")`.
3. No editar `0001_base/` una vez que exista una base con datos reales.
4. Un valor nuevo de enum no se puede usar en la misma transacción en que se agrega: va en una migración propia, anterior a la que lo usa.
