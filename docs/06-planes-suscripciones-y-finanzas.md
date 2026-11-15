# Planes, inventario, suscripciones y finanzas (fase 3)

## Planes (valores en PostgreSQL)

| Código | Nombre | Para | Precio inicial | Publicadas | Destacadas incluidas | Miembros |
|---|---|---|---|---|---|---|
| `particular` | Particular Free | Particulares | Gratis | 1 | 0 | 1 |
| `agencia-30` | Agencia 30 | Agencias | $ 54.900 / mes | 30 | 0 | 3 |
| `agencia-100` | Agencia 100 | Agencias | $ 99.900 / mes | 100 | 2 | 10 |

Los precios son **valores iniciales de desarrollo**: el Super Admin los cambia en Admin → Planes y la App los lee de
`GET /api/plans`. Ningún precio ni límite está escrito en el frontend. Un cambio de precio aplica a suscripciones
nuevas; las vigentes conservan el precio con el que se crearon.

## Inventario vs publicadas

- **Publicadas** = `published` + `pending` (en revisión). Es lo que cuenta para el límite del plan.
- **Inventario** = todo lo cargado y no vendido ni borrado (borradores, pausadas, con cambios pedidos, vencidas, publicadas).
- Ejemplo: una agencia con Agencia 30 puede tener 150 vehículos cargados y 30 publicados. Para publicar el 31.º tiene que pausar uno.
- Lo hace cumplir la base (trigger de límite → `409 LIMITE_ALCANZADO`), no la App. Si un plan termina, el worker pausa lo que excede (`enforce_plan_limit`), sin borrar nada.

## Períodos por mes calendario

`app.next_period_end(inicio, período, día_ancla)` en zona `America/Argentina/Buenos_Aires`:

- Mensual: mismo día del mes siguiente. Si ese día no existe, el último día de ese mes. El día original se guarda en `billing_anchor_day`, así una suscripción del 31/01 vence el 28/02 (o 29/02) y después el 31/03.
- Anual: mismo día del año siguiente (29/02 → 28/02).
- Se conserva la hora de inicio.

## Cómo se extiende una suscripción

Solo la base, cuando un pago **pasa a `approved`** (trigger `tg_payments_effects` → `app.subscription_apply_payment`):

- Renovación (pago dentro de la ventana de `billing.renewal_window_days`, 15 días antes del fin, o durante la gracia): el nuevo período empieza donde terminaba el anterior.
- Pago de un período que ya estaba cubierto: no extiende de nuevo (idempotente; el webhook puede llegar dos veces).
- Primera vez o suscripción vencida: empieza en la fecha de cobro y se re-ancla el día.
- Nunca acorta un período.

Con Mercado Pago, la fecha la confirma el webhook (`preapproval` autorizado usa `next_payment_date` de Mercado Pago). La App
nunca activa ni extiende nada por una fecha calculada en el navegador. El modelo no depende del proveedor: el día que
haya otro, alcanza con que registre el pago aprobado.

## Vencimientos (worker)

`job_subscriptions` (cada corrida del worker):

- Planes asignados a mano, transferencias y suscripciones canceladas: vencen al terminar el período.
- Mercado Pago: al terminar el período sin pago pasa a `grace_period` (`billing.grace_days` = 10) y después a `expired`.
- Al vencer: notificación al dueño y pausa de lo que excede el plan gratuito.
- Aviso `billing.expiry_notice_days` (7) antes del fin.

`job_promotions`: termina las promociones activas o pausadas cuya fecha de fin pasó.

## Plan asignado por Girando (sin cobro)

Admin → Agencias → Ver → **Asignar plan** (solo Super Admin): `provider = manual`, precio 0, un mes calendario, no se
renueva solo, con motivo obligatorio y auditoría. Sirve para convenios, cortesías y para probar en local sin Mercado Pago.
No reemplaza una suscripción paga vigente (hay que cancelarla en el proveedor). **Terminar plan asignado** la vence en el
momento y pausa lo que exceda.

## Panel financiero (Admin → Finanzas)

Administración comercial interna, no contabilidad fiscal. Montos en pesos.

| Concepto | Definición |
|---|---|
| Facturado | Pagos emitidos en el mes (todos menos cancelados), por fecha de creación |
| Cobrado | Pagos `approved`, por fecha de cobro |
| Pendiente | `pending` / `in_process` |
| Por verificar | Transferencias informadas (`submitted`). Hoy deshabilitado: faltan los datos bancarios reales |
| Rechazado | `rejected` / `charged_back` |
| Desglose | Por concepto (suscripción, promoción, verificación), medio y estado |
| Vencimientos | Suscripciones vigentes ordenadas por fin de período |

El ingreso mensual recurrente (Admin → Negocio) suma solo suscripciones con cobro; los planes asignados sin cobro no suman.
