# Girando — Modelo propuesto vs prototipo actual y plan de migración

Como el prototipo no tiene base de datos, **no hay datos reales que migrar ni destruir**: todo lo que hay son datos de ejemplo. "Migrar" significa reemplazar cada fuente simulada por la tabla/endpoint correspondiente **sin perder ninguna funcionalidad ni regla** que el prototipo ya muestra. Nada de lo marcado "ejemplo" pasa a producción.

## 1. Mapa prototipo → modelo

| En el prototipo | Pasa a | Cambio clave |
|---|---|---|
| `girando-store.js` (localStorage compartido) | API + PostgreSQL | Desaparece. App y Admin consultan la API |
| `GIRANDO_CATALOG` (anidado por nombre) | `vehicle_brands/models/generations/versions/engines/version_engines` | IDs; `engine: '1.6 Nafta'` → motor (1598 cc, gasoline); `body`/`type` → enums |
| `CARS[]` | `vehicles` + `listings` + `listing_images` + `listing_contacts` + `geo_areas` | Se separa vehículo / publicación; precio y km numéricos; ubicación por ID |
| `MY_LISTINGS[]`, `LISTING_META` | Misma tabla `listings` filtrada por dueño (`GET /me/listings`) | Un solo modelo para App y Admin |
| `listingStatus`, `listingNote`, `pendingListings` del store | `listings.status`, `status_reason`, cola `WHERE status='pending'` | Máquina de estados en la base |
| Estados `Moderación / Activa / Denunciada` | `pending / published` + `reports` | "Denunciada" deja de ser estado |
| `AGENCIES{}` por nombre + `agencyVerif` | `agencies` + `agency_members` + `verifications` | Clave por ID, CUIT único; el sello sale de `agencies.status` |
| `identityVerif` local | `verifications` (producto identity) → `users.identity_verified_at` | Aprobación del Admin se refleja en la App |
| `GIRANDO_PLANS` (+ `PLANS` viejo) | `plans` | Se elimina `PLANS` (Gratuito/Bronce/…, "5/8/10 fotos") |
| `store.subscription` (global) | `subscriptions` por usuario/agencia | El frontend deja de escribirla |
| `store.payments`, `PAY_HISTORY` | `payments` (+ `payment_events`) | Montos numéricos, referencia propia |
| Checkout MP simulado (`goMercadoPago` activa) | Preapproval + webhook | La activación solo por webhook |
| `confirmTransfer` | `payments(bank_transfer)` → `submitted` | Monto y referencia los pone el servidor |
| `SALES[]` (local de la App) + `commitSale` | `app.register_sale()` → `sales` | `days` calculado; patente a `vehicle_identifiers`; el Admin ve ventas reales |
| `mediaQueue`, `PHOTO_GRACE_DAYS`, `RETENTION` | `listing_images.purge_after` + `retention_policies` | Configurable de verdad |
| `PROMO_PRODUCTS`, `promos` | `promotion_products`, `promotions`, `promotion_events` | Métricas desde `analytics_events` |
| `ADS` / `CAMPAIGNS` | `promotions` tipo `banner_campaign` | Sin duplicado; imagen en Cloudinary, no base64 en localStorage |
| `CONVOS`, `newConvosToday` | `conversations`, `messages` | Anti-spam y bloqueo en servidor; sin respuesta automática simulada |
| `NOTIFS`, `store.notifs` | `notifications` + `notification_types` | Destinatario real (no `juan.martinez@mail.com` fijo) |
| `commPrefs`, `marketingConsentAt` | `notification_preferences`, `consents` | Fecha real, versión de política |
| Cookie consent en `localStorage` | `consents` (anónimo → usuario al registrarse) | Historial y versión |
| `SESSIONS`, `ACCOUNT_EVENTS` | `sessions`, `login_attempts`, `audit_logs` | Cerrar sesiones revoca refresh tokens |
| `REVIEWS_*`, `rateOpen/submitRate` | `reviews` | Requiere interacción válida |
| `REPORT_REASONS`, `submitReport` | `report_reasons`, `reports` | Hoy el reporte no se guarda: pasa a cola de moderación |
| `store.audit` / `AUDIT_SEED` | `audit_logs` (+ `moderation_actions`) | Actor real, rol, IP, antes/después |
| `store.emails` (Pendiente) | `email_events` | Sigue `pending` hasta conectar proveedor |
| `PROVINCES`, `DEPARTMENTS_BY_PROVINCE` | `geo_areas` (Georef) | Todas las provincias |
| `USD_RATE = 1250` | `exchange_rates` | Fuente a definir |
| Datos bancarios en el código | `app_settings` | Datos reales antes de producción |
| Google rating de ejemplo | `external_ratings` | Separado de Girando |
| Filas/KPIs fijos del Admin | Vistas `v_*` y consultas | Ver punto 3 |

## 2. Qué se elimina (no se migra)

- Métricas inventadas: `reviews × 2,4`, `consultas × 0,6`, embudo 24/143/61, `pubCount()` por hash, "40 % bajo el promedio", visitas/favoritos fijos, KPIs y barras del Admin.
- Fallback `|| 'Verificada'` y el filtro "Verificado = cualquier agencia".
- `PLANS` viejo, secciones duplicadas del Admin (`Object.assign` ×3), `applyActOld`, `submitPublish` que crea `'Activa'`.
- Props de diseño `sessionState` / `subscriptionState` (reemplazadas por sesión real).
- Respuesta automática simulada del chat.
- Datos demo con marcas y concesionarias reales (Yacopini, Toyota del Pilar, etc.).

## 3. Qué hay que corregir en App/Admin al conectar

| Pantalla | Hoy | Con backend |
|---|---|---|
| Publicar (5 pasos) | Guarda strings | Crea `vehicle` + `listing` draft; `PATCH` por paso; enviar = `status: pending`; muestra 409 `LIMITE_ALCANZADO` |
| Fotos | Blob URL local; acepta URL externa | Subida firmada a Cloudinary. **Se quita "pegar enlace de imagen"** (hotlinking de terceros y sin control de contenido) o se reimplementa descargando a Cloudinary en el servidor |
| Mis publicaciones | `MY_LISTINGS` | `GET /me/listings` + acciones = transiciones de estado |
| Detalle / búsqueda | Filtra `CARS` parseando texto | `GET /listings?brand_id=&model_id=&year_min=…` sobre `api_public.listings`; facetas por agregación |
| Sello de confianza | Deducido en el frontend | Campos `agency_verified` / `seller_identity_verified` de la API |
| Suscripción / checkout | Escribe el store | `POST /subscriptions` → `init_point`; pantalla "Confirmando" consulta estado |
| Estadísticas del vendedor | Fijas × factor | `v_seller_kpis` + `listing_stats_daily`; si no hay datos, estado vacío honesto |
| Admin → Catálogo | Estado local | CRUD real con activar/desactivar (sin borrar usados) |
| Admin → Planes / Retención / Notificaciones | Store/local | Tablas `plans`, `retention_policies`, `notification_types`, auditadas |
| Admin → Dashboard | Números fijos | Consultas reales (con "sin datos" cuando corresponda) |

## 4. Plan de implementación (tras tu aprobación)

| Etapa | Entregable | Verificación |
|---|---|---|
| **E1 · Base** | Repo `backend/` (FastAPI) + Alembic; migración `0001` generada desde `db/propuesta/*.sql` (enums, tablas, FKs, índices, constraints, triggers, RLS, vistas) | `db/tests` corriendo en CI contra Postgres en Docker |
| **E2 · Seeds de catálogos** | `geo_areas` (Georef AR), catálogo real (fuente a definir), `plans`, `report_reasons`, `notification_types`, `email_templates` (borrador), `verification_products`, `promotion_products`, `app_settings`, `retention_policies` | Sin datos de usuarios/publicaciones de ejemplo |
| **E3 · Auth y cuentas** | Registro, verificación de email, login, refresh/sesiones, recuperar contraseña, bloqueo por intentos, perfil, consentimientos | pytest + tests de RLS |
| **E4 · Catálogo y publicaciones** | Endpoints públicos (búsqueda/detalle) y privados (asistente, estados, moderación) | Contrato OpenAPI + tests |
| **E5 · Fotos (Cloudinary)** | Firma, confirmación, reordenar, portada, borrar, jobs de purga | Cuenta de prueba de Cloudinary |
| **E6 · Agencias y verificaciones** | Alta de agencia, miembros, documentos (bucket privado), cola de verificación | — |
| **E7 · Mensajería, favoritos, búsquedas guardadas, reseñas, reportes** | + notificaciones in-app | — |
| **E8 · Pagos** | MP sandbox (preapproval + webhook + conciliación), transferencia con aprobación de finanzas | Webhooks de prueba de MP |
| **E9 · Ventas y estadísticas** | `register_sale`, agregados, vistas, eventos de analytics | n ≥ 3 |
| **E10 · Conectar App y Admin** | Reemplazar `girando-store.js` y constantes por un cliente API tipado; eliminar lo listado en el punto 2 | Flujos completos de punta a punta |
| **E11 · Emails y retención** | Proveedor de email, cola, jobs de retención | Estados reales `sent/failed` |

Cada etapa mantiene el prototipo funcionando: el cliente API tiene un modo *mock* que responde con el mismo contrato hasta que el endpoint real existe, así la App y el Admin se conectan pantalla por pantalla sin reiniciar el proyecto.
