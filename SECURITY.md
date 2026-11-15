# Seguridad de Girando

Principio: **el frontend no es seguridad**. Quién es el usuario, qué rol tiene, qué agencia administra, qué
publicaciones puede tocar, qué plan tiene y qué permisos le corresponden lo decide el backend, y la base de datos lo
vuelve a verificar (RLS + triggers). Nada que diga el navegador (`isAdmin`, “plan premium”, “pago aprobado”) se cree.

Para reportar una vulnerabilidad: escribir al responsable del proyecto sin abrir un issue público.

## CORS

- `CORS_ORIGINS`: lista explícita (coma separada). En producción la API **no arranca** si contiene `*`.
- La App y el Admin se sirven desde el mismo origen que la API (nginx hace proxy de `/api`), así que el navegador no
  necesita CORS; la lista existe para clientes de otros orígenes (p. ej. una app móvil).
- Métodos y cabeceras permitidos también son explícitos (`Content-Type`, `X-CSRF-Token`, `X-Request-ID`).

## Autenticación

- Contraseñas con **Argon2id** (argon2-cffi). Nunca en texto plano ni en logs. Política: 8–128 caracteres, letras y
  números, no está en la lista de contraseñas comunes.
- Sesión: **access token JWT (HS256, 15 min)** en cookie `gr_at` + **refresh token opaco** en cookie `gr_rt`
  (path `/api/auth`). Ambas `HttpOnly`, `SameSite=Strict` (refresh) / `Lax` (access), `Secure` obligatorio en producción.
  El JavaScript nunca ve tokens.
- Cada sesión vive en la tabla `sessions`; el refresh token se guarda hasheado (SHA-256) y **rota en cada uso**.
  Cerrar sesión, “cerrar las demás sesiones”, cambiar/restablecer la contraseña o suspender la cuenta revoca sesiones.
  Cada request valida que la sesión siga activa en la base.
- **Bloqueo por intentos**: 5 fallos → 15 minutos (`423 CUENTA_BLOQUEADA_TEMPORALMENTE`), registrado en `login_attempts`.
  El mensaje de error no revela si el email existe.
- Recuperación de contraseña y verificación de email con tokens de un solo uso, hasheados y con vencimiento.
  La recuperación siempre responde igual exista o no la cuenta.
- **CSRF**: doble envío (cookie `gr_csrf` legible + cabecera `X-CSRF-Token`) en todo POST/PUT/PATCH/DELETE bajo `/api`,
  salvo el webhook de Mercado Pago (que se autentica con firma).

## Autorización

- Roles de producto: `user`, `agency_member`, `agency_admin`, `admin`, `super_admin` (derivados de `agency_members` y
  `staff_roles`). Roles de staff: `superadmin`, `admin`, `moderator`, `catalog_editor`, `support`, `finance`.
- La API se conecta con el rol `girando_api` (NOINHERIT, sin privilegios propios) y en cada transacción hace
  `SET LOCAL ROLE girando_anon | girando_app | girando_worker` + `app.user_id`. Las políticas **RLS** filtran filas y los
  triggers impiden transiciones prohibidas aunque alguien encuentre un bug en la API:
  - nadie aprueba su propia publicación (`draft → pending` sí; `pending → published` solo moderación);
  - el límite del plan se controla en la base (`409 LIMITE_ALCANZADO`);
  - una suscripción nace `pending` y solo el webhook (rol worker) o finanzas la cambian; un pago no nace aprobado;
  - nadie se autoconcede roles; solo un superadmin gestiona roles de staff;
  - el público solo lee vistas `api_public.*` (sin email, patente, VIN ni contacto oculto).
- Admin: cada endpoint exige el rol de staff correspondiente (403 si no). La pantalla de login del Admin es solo UX.
- Fase 3: separación Admin (operación) / Super Admin (comercial y sistema) en la API **y** en RLS: planes, precios, promociones,
  Home, emails, auditoría, retención e integraciones solo superadmin; `finance` lee lo comercial sin modificarlo. Matriz en
  [docs/05-roles-y-permisos.md](docs/05-roles-y-permisos.md), probada por API directa (`tests/test_roles.py`).
- Una suscripción se extiende solo en la base cuando un pago pasa a `approved` (idempotente); nunca por una fecha del navegador.
- Redirecciones externas (`/api/out/agency/...`): solo a URLs guardadas por la agencia (sin redirección abierta), sin guardar usuario ni IP.
- `reset-dev-db` se niega fuera de `ENV=development`, con host no local o si `--confirm` no coincide con el nombre de la base.

## Rate limiting

Ventana fija en **Redis** (con respaldo en memoria si Redis no está). Respuesta `429 DEMASIADOS_INTENTOS` con `Retry-After`.

| Acción | Límite |
|---|---|
| Login | 20/15 min por IP y 8/15 min por email |
| Registro | 5/h por IP |
| Recuperación / cambio de contraseña | 5/h |
| Verificación de email | 20/h |
| Refresh | 60/min por IP |
| Búsqueda y facetas | 120/min por IP |
| Crear publicaciones / agencias / suscripciones | 20/h por usuario |
| Editar publicaciones | 120/min por usuario |
| Subir fotos | 60/h por usuario |
| Favoritos | 120/min · Reportes 10/h · Ver contacto 60/h · Mensajes 30/min |
| Admin | 300/min por usuario |
| Global | 600/min por IP |

La IP del cliente sale de `X-Real-IP` **solo si la conexión viene de un proxy de confianza** (`TRUSTED_PROXIES`, en
Docker el contenedor `web`). `X-Forwarded-For` nunca se usa. Así nadie esquiva el límite falsificando cabeceras.

## Validación de datos

- Todo lo que llega del cliente pasa por modelos Pydantic estrictos (`extra=forbid`): precio (> 0, 2 decimales),
  año (1900–2100), km (0–2.000.000), estados (enumeraciones cerradas), IDs (UUID), montos, emails, teléfonos E.164,
  enlaces de YouTube, CUIT. La base repite las reglas con CHECK, FK, enums y triggers.
- Montos de suscripciones, pagos y promociones los fija la base desde el plan/producto; el cliente no puede mandarlos.

## Inyección SQL y XSS

- Todas las consultas usan **parámetros ligados** (SQLAlchemy `text()` con `:param`). Las partes armadas con f-string
  son fragmentos constantes del código o identificadores de listas blancas (Bandit B608 revisado y documentado).
- Texto de usuarios (títulos, descripciones, nombres, motivos, reportes) se normaliza en el backend (sin caracteres de
  control) y **se renderiza siempre como texto** (React escapa); no se usa `innerHTML` con datos de usuarios.
  Las URLs de imágenes se aceptan solo si son de `/media/` (desarrollo) o `https://res.cloudinary.com/`.
- El CSV de ventas neutraliza fórmulas (`=`, `+`, `-`, `@`).

## Archivos

- Fotos: máximo **6** por publicación (API + restricción en la base), **JPG/PNG/WEBP**, **10 MB**, mínimo 320×240.
  Se valida el **contenido real** con Pillow (no la extensión ni el MIME declarado), se corrige la orientación, se
  **re-codifica** (elimina EXIF/GPS y cualquier payload) y se limita a 2560 px.
- Nunca hay blobs en PostgreSQL: solo `public_id` y URL.
- `local_dev` guarda en un volumen del contenedor y **está prohibido en producción**. Cloudinary usa subida firmada
  directa, y la API confirma el recurso contra la Admin API de Cloudinary antes de registrarlo.
- Documentos de verificación: bucket **privado** R2, nunca en `web/`, sin URLs públicas permanentes; solo URLs firmadas
  (SigV4) de hasta 10 minutos emitidas por la API después de autorizar.

## Secretos

- **Nunca en Git**: contraseñas, `JWT_SECRET`, API keys, secretos de Cloudinary, tokens de Mercado Pago, credenciales
  SMTP/R2, claves privadas. Van en `.env` (ignorado por Git). `.env.example` solo tiene valores de desarrollo sin valor real.
- CI corre **gitleaks** y falla si se versiona un `.env`.
- Los secretos se declaran con `repr=False` y el logger redacta claves sensibles; `/api/integrations/status` informa
  si algo está configurado, nunca el valor.
- En producción: gestor de secretos del proveedor (variables cifradas), rotación de `JWT_SECRET` (invalida sesiones) y
  credenciales distintas por entorno.

## Logs

JSON estructurado por línea: `ts`, `level`, `request_id`, `user_id`, método, ruta, status, duración (ms), IP y errores.
Nunca se registran contraseñas, tokens, cookies, cuerpos de requests, documentos ni secretos (redacción por nombre de
campo). El `X-Request-ID` se devuelve en cada respuesta para correlacionar.

## Auditoría

- Trigger `zz_audit` en 27 tablas: actor (usuario o sistema), rol, acción, entidad, ID, **antes**, **después**,
  motivo, IP, user agent, request ID y fecha. La tabla es de solo inserción para la app (sin UPDATE/DELETE).
- Las acciones de moderación exigen motivo (salvo aprobar/reactivar) y quedan además en `moderation_actions`.
- Retención de auditoría: 10 años.

## Cabeceras

- API: `Content-Security-Policy: default-src 'none'` (Swagger tiene la suya), `X-Content-Type-Options: nosniff`,
  `Referrer-Policy`, `Permissions-Policy`, `X-Frame-Options: DENY`, `Cross-Origin-Opener-Policy`, `Cache-Control: no-store`,
  y `Strict-Transport-Security` cuando `COOKIE_SECURE=true` (HTTPS).
- App/Admin (nginx, `web/security-headers.conf`): CSP real y compatible:
  `default-src 'self'; script-src 'self' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https://res.cloudinary.com; connect-src 'self' https://api.cloudinary.com; frame-src https://www.youtube-nocookie.com; object-src 'none'; frame-ancestors 'none'`.
  **Limitación conocida**: `'unsafe-eval'` es necesario porque el runtime del diseño compila plantillas en el navegador.
  No hay scripts inline ni de terceros (React y la tipografía Sora se sirven desde el propio dominio; Babel ya no se usa).
  Eliminarlo requiere precompilar el frontend (pendiente).

## Producción (checklist)

- `ENV=production`, `COOKIE_SECURE=true`, `CORS_ORIGINS` explícito, `JWT_SECRET` fuerte, `IMAGE_STORAGE=cloudinary`.
- TLS en el balanceador/proxy delante de nginx, con HSTS (`max-age=31536000; includeSubDomains`).
- No publicar los puertos 8000 (API) ni 5432/6379; exponer solo el proxy HTTPS.
- PostgreSQL administrado con backups cifrados y PITR; Redis privado.
- `SEED_DEV=false` (el seed igual se niega fuera de desarrollo). Crear el superadmin con `create-superadmin`. Ninguna cuenta `*@girando.test` ni `DEV_SEED_PASSWORD` en producción.
- Webhook de Mercado Pago con `MERCADOPAGO_WEBHOOK_SECRET` configurado.
- Revisar con un profesional los textos legales (hoy “BORRADOR”) y los plazos de retención.
