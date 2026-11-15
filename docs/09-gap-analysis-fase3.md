# Gap analysis · fase 3 (06/10/2026)

Exploración en local con la base recién recreada (`reset-dev-db`) y una cuenta por rol, en 1440×900, 768×1024 y 390×844,
como visitante, particular, agencia, moderador, admin y super admin, más pruebas por API directa.

Clasificación: **CRÍTICO** (bloquea probar el negocio o es un riesgo de seguridad/datos) · **IMPORTANTE** (necesario antes de
usuarios reales) · **FUTURO** (después del lanzamiento) · **NO NECESARIO** (no aporta ahora).

## Resueltos en esta fase

| # | Hallazgo | Área | Clase | Qué se hizo |
|---|---|---|---|---|
| 1 | Admin y Super Admin eran lo mismo: `admin@` tenía rol superadmin y la base no distinguía permisos comerciales | Seguridad | CRÍTICO | RLS + `require_roles` por área; matriz probada por API (`test_roles.py`) |
| 2 | Sin credenciales conocidas de Admin/Super Admin | Cuenta | CRÍTICO | `seed-dev` con 5 cuentas (una por rol), `--reset-passwords`, `reset-dev-db` con guardas |
| 3 | `/api/integrations/status` público | Seguridad | CRÍTICO | Solo Super Admin |
| 4 | `POST /admin/users/{id}/roles` respondía 422 (lo capturaba otra ruta) | Administración | CRÍTICO | Orden de rutas corregido + UI “Roles de staff” |
| 5 | `GET /admin/plans` respondía 500 (columna ambigua) | Administración | CRÍTICO | Corregido |
| 6 | Pago aprobado extendía dos veces (Python + trigger) y el período era de 30 días fijos | Pagos | CRÍTICO | Períodos por mes calendario en la base, extensión idempotente solo al pasar a `approved` |
| 7 | Nada vencía suscripciones ni promociones | Pagos | CRÍTICO | `job_subscriptions` (gracia, vencimiento, avisos, pausa de excedentes) y `job_promotions` |
| 8 | Planes distintos al modelo (Agencia 30 / 100) | Planes | CRÍTICO | Particular Free 1, Agencia 30, Agencia 100 en PostgreSQL, editables por Super Admin |
| 9 | Sin Mercado Pago no había forma de que una agencia tuviera plan en local | Planes | CRÍTICO | Plan asignado por Super Admin (sin cobro, auditado, vence solo) |
| 10 | Verificar una agencia era un clic sin confirmación ni registro de qué se revisó | Verificación | CRÍTICO | Tomar revisión, checklist, evidencia, asignación, confirmación con nota |
| 11 | La agencia no podía editar su perfil (web, redes, WhatsApp) | Agencias | IMPORTANTE | Mi agencia (App) + `PATCH /me/agencies/{id}` validado |
| 12 | No se distinguía inventario de publicadas | Vehículos | IMPORTANTE | Contadores en Mi agencia, Mi Girando y Admin → Agencias |
| 13 | Sin tienda online ni medición de clics a canales | Agencias | IMPORTANTE | `store_url` + `/api/out/...` con tracking sin datos personales |
| 14 | La agencia no tenía estadísticas propias | Métricas | IMPORTANTE | Visitas al perfil y clics por canal, “Sin datos suficientes” |
| 15 | Promociones sin gestión | Promociones | IMPORTANTE | Admin → Promociones con estados y reglas de activación |
| 16 | Home fija en el código | Contenido | IMPORTANTE | Admin → Home (bloques con fechas), sin CMS |
| 17 | El dueño no tenía una vista del negocio | Administración | IMPORTANTE | Admin → Negocio y Finanzas |
| 18 | Un solo remitente de email, sin separar marketing | Comunicaciones | IMPORTANTE | Remitentes por tipo; marketing solo con consentimiento |
| 19 | El detalle del Admin mostraba datos viejos después de una acción | UX | IMPORTANTE | Se recarga o se cierra |
| 20 | Moderación veía botones que el servidor le iba a rechazar | UX | IMPORTANTE | Navegación y acciones por rol |
| 21 | Perfil de agencia sin vehículos quedaba vacío; enlaces subrayados como texto | UX | — | Estado vacío y estilo de botón |

## Pendientes

| Hallazgo | Área | Clase | Por qué no ahora / qué hace falta |
|---|---|---|---|
| Mensajes entre comprador y vendedor | Mensajes | IMPORTANTE | Las tablas existen; falta API, UI, moderación y retención. Hoy el contacto es por WhatsApp/teléfono con tracking |
| Credenciales reales de Cloudinary | Fotos | IMPORTANTE | El flujo está hecho (firma → Cloudinary → confirmación → PostgreSQL, máx. 6, portada, orden). En local usa disco (`local_dev`) |
| Mercado Pago en sandbox con credenciales | Pagos | IMPORTANTE | Preapproval + webhook firmado listos; nunca se probó contra Mercado Pago real |
| Compra de promociones por la agencia | Promociones | IMPORTANTE | Hoy solo el Super Admin las crea; falta checkout y producto de promoción |
| Registrar impresiones/clics de promociones desde la App | Métricas | IMPORTANTE | Necesario antes de vender promociones |
| Imagen de banners | Publicidad | IMPORTANTE | Requiere Cloudinary; sin imagen el banner no se activa |
| Proveedor de email y dominio (SPF/DKIM/DMARC) | Comunicaciones | IMPORTANTE | Hoy los emails quedan en la cola |
| Transferencia bancaria | Pagos | IMPORTANTE | Falta definir y cargar datos bancarios reales (decisión del dueño) |
| Reglas definitivas de verificación | Verificación | IMPORTANTE | Decisión de negocio/legal: documentos, vigencia, costo |
| Logo y portada de la agencia | Agencias | IMPORTANTE | Mismo flujo de fotos; depende de Cloudinary |
| Textos legales revisados por un abogado | Legal | IMPORTANTE | Están en borrador |
| Operación: hosting, dominio, HTTPS, backups, monitoreo, alertas, logs | Seguridad operacional | IMPORTANTE | Nada desplegado todavía |
| Invitar miembros a una agencia | Agencias | FUTURO | El plan ya tiene el límite de miembros |
| Verificación de identidad de particulares (DNI) | Verificación | FUTURO | Requiere almacenamiento privado y proveedor |
| Calificaciones y reseñas | Confianza | FUTURO | Tablas existen |
| Google Places | Agencias | FUTURO | Sin API key no se muestra nada |
| Factura electrónica (ARCA) | Pagos | FUTURO | El panel financiero es administración interna, no contabilidad |
| Servicios, Repuestos, Empleos | Módulos | FUTURO | Marcados “Pronto”; sin priorizar |
| CMS completo, segmentación publicitaria, chat en tiempo real, IA de precios | — | NO NECESARIO | No aportan para validar el negocio |
