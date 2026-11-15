# Roles y permisos (fase 3)

El backend decide. El panel solo oculta lo que el servidor igual rechazaría: cada endpoint del Admin tiene
`require_roles(...)` y, por debajo, PostgreSQL aplica RLS (`app_has_staff_role`) y triggers. Probado por API directa
en `backend/tests/test_roles.py` (entrar por URL o con `curl` devuelve 403).

## Roles

| Rol | Para qué | Cómo se asigna |
|---|---|---|
| `superadmin` | Dueños de Girando. Pasa todos los controles. | Solo por consola: `make superadmin EMAIL=…` (o `seed-dev` en local). Nunca desde el panel. |
| `admin` | Operación diaria | Super Admin → Usuarios → Roles de staff |
| `moderator` | Moderación de publicaciones, reportes y verificaciones | Ídem |
| `support` | Atención a usuarios (ver/suspender usuarios) | Ídem |
| `finance` | Lectura comercial (negocio, finanzas, planes, suscripciones, pagos) sin poder modificar | Ídem |
| `catalog_editor` | Catálogo de vehículos | Ídem |

## Matriz (Admin)

| Área | Super Admin | Admin | Moderador | Finanzas |
|---|---|---|---|---|
| Resumen (operativo) | ✓ (+ KPIs comerciales) | ✓ | ✓ | ✓ (+ KPIs comerciales) |
| Publicaciones: aprobar, pedir cambios, rechazar, pausar | ✓ | ✓ | ✓ | — |
| Reportes | ✓ | ✓ | ✓ | — |
| Verificaciones: revisar, checklist, evidencia, aprobar/rechazar | ✓ | ✓ | ✓ | — |
| Agencias: ver, verificar/rechazar | ✓ | ✓ | ✓ | — |
| Agencias: suspender, revocar, reactivar | ✓ | ✓ | — | — |
| Agencias: asignar/terminar plan sin cobro | ✓ | — | — | — |
| Usuarios: suspender, bloquear, reactivar | ✓ | ✓ | — | — |
| Usuarios: roles de staff | ✓ | — | — | — |
| Catálogo | ✓ | ✓ | — | — |
| Negocio, Finanzas, Ventas, Suscripciones, Pagos (lectura) | ✓ | — | — | ✓ |
| Planes y precios (editar) | ✓ | — | — | — (lectura) |
| Promociones, Home, Cola de envíos | ✓ | — | — | — |
| Auditoría, Retención, Integraciones | ✓ | — | — | — |

Usuarios de la App (particular, agencia) no entran a ningún endpoint `/api/admin`. Dentro de la App, cada uno solo ve y
edita sus recursos: otra persona que conozca el id de una publicación, del perfil o de las estadísticas de una agencia
recibe 403/404 (RLS + controles del endpoint).

## Dónde está

- `backend/app/api/routers/admin.py` y `business.py`: constantes `MOD`, `CATALOG`, `USERS`, `FINANCE`, `SUPER`.
- `backend/sql/0001_base/160_roles_suscripciones_home.sql`: políticas RLS de planes, suscripciones, pagos, promociones, Home, emails, auditoría, retención → solo superadmin (lectura comercial también finance).
- `web/src/admin-logic.js`: `ACCESS` (qué secciones se muestran por rol). Es solo presentación.

## Cuentas de desarrollo

`python -m app.cli seed-dev` (solo `ENV=development`) crea una cuenta por rol. Contraseña: `DEV_SEED_PASSWORD`.
Si una cuenta ya existe con otro rol, se corrige (revoca roles de staff que no correspondan). `--reset-passwords`
vuelve a poner la contraseña del `.env`. **Nunca usar estas cuentas ni esta contraseña en producción.**
