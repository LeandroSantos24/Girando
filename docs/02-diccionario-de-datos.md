# Girando — Diccionario de datos v0 (generado)

> Generado automáticamente desde el catálogo de PostgreSQL por `db/generar_diccionario.py`. **No editar a mano.**
> Visibilidad en cursiva = heredada del default de la tabla (campos técnicos: id, fechas, FKs). Visibilidad: **PÚBLICO** · **PRIVADO** (titular + staff autorizado) · **PROPIETARIO** (solo el titular) · **ADMIN** (solo staff) · **SENSIBLE** (cifrado/restringido y auditado) · **SISTEMA** (secreto técnico, nunca sale del backend).

Tablas: **59** · Enums: **66** · Vistas: **19**

## Índice

- [`users`](#users)
- [`user_personal_data`](#user_personal_data)
- [`user_profiles`](#user_profiles)
- [`staff_roles`](#staff_roles)
- [`sessions`](#sessions)
- [`auth_tokens`](#auth_tokens)
- [`login_attempts`](#login_attempts)
- [`user_blocks`](#user_blocks)
- [`policy_versions`](#policy_versions)
- [`consents`](#consents)
- [`geo_areas`](#geo_areas)
- [`locations`](#locations)
- [`agencies`](#agencies)
- [`agency_members`](#agency_members)
- [`external_ratings`](#external_ratings)
- [`vehicle_brands`](#vehicle_brands)
- [`vehicle_models`](#vehicle_models)
- [`vehicle_generations`](#vehicle_generations)
- [`vehicle_engines`](#vehicle_engines)
- [`vehicle_versions`](#vehicle_versions)
- [`vehicle_version_engines`](#vehicle_version_engines)
- [`catalog_requests`](#catalog_requests)
- [`vehicles`](#vehicles)
- [`vehicle_identifiers`](#vehicle_identifiers)
- [`listings`](#listings)
- [`listing_images`](#listing_images)
- [`listing_contacts`](#listing_contacts)
- [`listing_status_history`](#listing_status_history)
- [`listing_price_history`](#listing_price_history)
- [`verification_products`](#verification_products)
- [`verifications`](#verifications)
- [`documents`](#documents)
- [`reviews`](#reviews)
- [`report_reasons`](#report_reasons)
- [`reports`](#reports)
- [`moderation_actions`](#moderation_actions)
- [`favorites`](#favorites)
- [`saved_searches`](#saved_searches)
- [`conversations`](#conversations)
- [`messages`](#messages)
- [`plans`](#plans)
- [`subscriptions`](#subscriptions)
- [`payments`](#payments)
- [`payment_events`](#payment_events)
- [`exchange_rates`](#exchange_rates)
- [`promotion_products`](#promotion_products)
- [`promotions`](#promotions)
- [`promotion_events`](#promotion_events)
- [`sales`](#sales)
- [`email_templates`](#email_templates)
- [`notification_types`](#notification_types)
- [`notification_preferences`](#notification_preferences)
- [`notifications`](#notifications)
- [`email_events`](#email_events)
- [`audit_logs`](#audit_logs)
- [`analytics_events`](#analytics_events)
- [`listing_stats_daily`](#listing_stats_daily)
- [`app_settings`](#app_settings)
- [`retention_policies`](#retention_policies)

---

## users

Cuenta de acceso. Solo autenticación y estado. Sin datos personales ni de perfil.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _PRIVADO_ | **PK** |
| `email` | citext | sí |  | PRIVADO | Login. Único (case-insensitive). Se reemplaza por alias anónimo al eliminar la cuenta. |
| `phone_e164` | text | no |  | PRIVADO | Teléfono de la cuenta (recuperación/2FA), E.164. No es el teléfono de contacto de publicaciones. |
| `password_hash` | text | no |  | SISTEMA | Argon2id/PBKDF2. NULL si la cuenta usa solo proveedor externo (futuro). |
| `status` | app.user_status | sí | 'pending'::app.user_status | ADMIN | pending→active→suspended/blocked→deleted. Solo staff o sistema lo cambian. |
| `status_reason` | text | no |  | ADMIN | Motivo del último cambio de estado. |
| `email_verified_at` | timestamp with time zone | no |  | PRIVADO | Lo setea el sistema al consumir un auth_token email_verification. |
| `phone_verified_at` | timestamp with time zone | no |  | PRIVADO | Lo setea el sistema al verificar OTP. |
| `identity_verified_at` | timestamp with time zone | no |  | PÚBLICO como booleano | Caché mantenida SOLO por trigger desde verifications (identity aprobada). Nunca editable por el usuario. |
| `failed_login_count` | smallint | sí | 0 | SISTEMA | Contador para bloqueo temporal. |
| `locked_until` | timestamp with time zone | no |  | SISTEMA | Bloqueo temporal por intentos fallidos. |
| `password_changed_at` | timestamp with time zone | no |  | _PRIVADO_ |  |
| `mfa_enabled` | boolean | sí | false | _PRIVADO_ |  |
| `mfa_secret_encrypted` | bytea | no |  | SISTEMA | Preparado para 2FA TOTP (cifrado a nivel aplicación). No usado en v1. |
| `last_login_at` | timestamp with time zone | no |  | PRIVADO | Último acceso exitoso. |
| `deleted_at` | timestamp with time zone | no |  | _PRIVADO_ |  |
| `created_at` | timestamp with time zone | sí | now() | _PRIVADO_ |  |
| `updated_at` | timestamp with time zone | sí | now() | _PRIVADO_ |  |

<details><summary>Restricciones</summary>

- `users_deleted_consistency`: `CHECK (((status = 'deleted'::app.user_status) = (deleted_at IS NOT NULL)))`
- `users_email_format`: `CHECK (((email ~ '^[^@\s]+@[^@\s]+\.[^@\s]{2,}$'::citext) AND (length((email)::text) <= 254)))`
- `users_phone_e164`: `CHECK (((phone_e164 IS NULL) OR (phone_e164 ~ '^\+[1-9][0-9]{7,14}$'::text)))`

</details>

<details><summary>Índices</summary>

- `UNIQUE USING btree (email)` — users_email_uq
- `UNIQUE USING btree (phone_e164) WHERE (phone_verified_at IS NOT NULL)` — users_phone_verified_uq
- `USING btree (status) WHERE (status <> 'active'::app.user_status)` — users_status_idx

</details>

<details><summary>Políticas RLS</summary>

- `users_self_or_staff` (SELECT → girando_app)
- `users_update` (UPDATE → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## user_personal_data

Información personal (1:1 con users). Separada del perfil público y de la autenticación.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `user_id` | uuid | sí |  | _SENSIBLE_ | **PK** · FK → app.users(id) ON DELETE CASCADE |
| `first_name` | text | no |  | PRIVADO | Nombre legal. El nombre visible está en user_profiles.display_name. |
| `last_name` | text | no |  | PRIVADO | Apellido legal. |
| `dni_encrypted` | bytea | no |  | SENSIBLE | DNI cifrado a nivel aplicación (AES-GCM/Fernet, clave fuera de la DB). Validación backend: ^[0-9]{7,8}$. |
| `dni_hash` | bytea | no |  | SISTEMA | HMAC-SHA256(DNI, pepper) para detectar duplicados sin descifrar. |
| `dni_last3` | character(3) | no |  | PRIVADO | Últimos 3 dígitos para mostrar al titular (***.***.123). |
| `birth_date` | date | no |  | SENSIBLE | Opcional. Solo si un producto lo requiere (p.ej. verificación de identidad). |
| `home_location_id` | uuid | no |  | SENSIBLE | FK → app.locations(id) · Domicilio exacto (locations). Solo para verificaciones que lo exijan. |
| `created_at` | timestamp with time zone | sí | now() | _SENSIBLE_ |  |
| `updated_at` | timestamp with time zone | sí | now() | _SENSIBLE_ |  |

<details><summary>Restricciones</summary>

- `upd_birth_date`: `CHECK (((birth_date IS NULL) OR (birth_date >= '1900-01-01'::date)))`
- `upd_dni_pair`: `CHECK (((dni_encrypted IS NULL) = (dni_hash IS NULL)))`
- `upd_names_len`: `CHECK (((COALESCE(length(first_name), 0) <= 80) AND (COALESCE(length(last_name), 0) <= 80)))`

</details>

<details><summary>Índices</summary>

- `UNIQUE USING btree (dni_hash) WHERE (dni_hash IS NOT NULL)` — upd_dni_hash_uq

</details>

<details><summary>Políticas RLS</summary>

- `upd_self` (ALL → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## user_profiles

Perfil público del usuario (1:1). Todo lo público de una persona sale de acá y solo si is_public.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `user_id` | uuid | sí |  | _PÚBLICO_ | **PK** · FK → app.users(id) ON DELETE CASCADE |
| `display_name` | text | sí |  | PÚBLICO | Nombre visible (p.ej. "Juan M."). Independiente del nombre legal. |
| `avatar_public_id` | text | no |  | PÚBLICO | public_id de Cloudinary. |
| `bio` | text | no |  | _PÚBLICO_ |  |
| `geo_area_id` | uuid | no |  | PÚBLICO | FK → app.geo_areas(id) · Ciudad/departamento aproximado. Nunca dirección. |
| `contact_whatsapp_e164` | text | no |  | PRIVADO | Valor por defecto para listing_contacts. Solo se publica vía listing_contacts con show_whatsapp=true. |
| `contact_phone_e164` | text | no |  | PRIVADO | Idem teléfono. |
| `contact_email` | citext | no |  | PRIVADO | Email de contacto comercial (puede diferir del email de login). |
| `instagram_url` | text | no |  | PÚBLICO | Opcional. Validado por dominio. |
| `tiktok_url` | text | no |  | _PÚBLICO_ |  |
| `facebook_url` | text | no |  | _PÚBLICO_ |  |
| `x_url` | text | no |  | _PÚBLICO_ |  |
| `youtube_url` | text | no |  | _PÚBLICO_ |  |
| `website_url` | text | no |  | _PÚBLICO_ |  |
| `is_public` | boolean | sí | true | PROPIETARIO | "Perfil público visible". Si es false, api_public no expone el perfil (las publicaciones muestran solo "Particular"). |
| `show_phone_default` | boolean | sí | false | PROPIETARIO | "Mostrar mi teléfono en publicaciones" (default para nuevas publicaciones). |
| `created_at` | timestamp with time zone | sí | now() | _PÚBLICO_ |  |
| `updated_at` | timestamp with time zone | sí | now() | _PÚBLICO_ |  |

<details><summary>Restricciones</summary>

- `up_bio_len`: `CHECK (((bio IS NULL) OR (length(bio) <= 500)))`
- `up_display_name`: `CHECK (((length(btrim(display_name)) >= 2) AND (length(btrim(display_name)) <= 60)))`
- `up_fb`: `CHECK (((facebook_url IS NULL) OR (facebook_url ~* '^https://(www\.\|m\.)?facebook\.com/\S+$'::text)))`
- `up_ig`: `CHECK (((instagram_url IS NULL) OR (instagram_url ~* '^https://(www\.)?instagram\.com/[A-Za-z0-9_.]{1,30}/?$'::text)))`
- `up_ph`: `CHECK (((contact_phone_e164 IS NULL) OR (contact_phone_e164 ~ '^\+[1-9][0-9]{7,14}$'::text)))`
- `up_tt`: `CHECK (((tiktok_url IS NULL) OR (tiktok_url ~* '^https://(www\.)?tiktok\.com/@[A-Za-z0-9_.]{2,24}/?$'::text)))`
- `up_wa`: `CHECK (((contact_whatsapp_e164 IS NULL) OR (contact_whatsapp_e164 ~ '^\+[1-9][0-9]{7,14}$'::text)))`
- `up_web`: `CHECK (((website_url IS NULL) OR (website_url ~* '^https://[^\s/$.?#].[^\s]*$'::text)))`
- `up_x`: `CHECK (((x_url IS NULL) OR (x_url ~* '^https://(www\.)?(x\|twitter)\.com/[A-Za-z0-9_]{1,15}/?$'::text)))`
- `up_yt`: `CHECK (((youtube_url IS NULL) OR (youtube_url ~* '^https://(www\.)?youtube\.com/\S+$'::text)))`

</details>

<details><summary>Políticas RLS</summary>

- `up_insert` (INSERT → girando_app)
- `up_select` (SELECT → girando_app)
- `up_update` (UPDATE → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## staff_roles

[ADMIN] Roles del panel de administración. Fuente de verdad de permisos de staff (no el JWT).

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _ADMIN_ | **PK** |
| `user_id` | uuid | sí |  | _ADMIN_ | FK → app.users(id) |
| `role` | app.staff_role | sí |  | _ADMIN_ |  |
| `granted_by` | uuid | no |  | _ADMIN_ | FK → app.users(id) |
| `granted_at` | timestamp with time zone | sí | now() | _ADMIN_ |  |
| `revoked_by` | uuid | no |  | _ADMIN_ | FK → app.users(id) |
| `revoked_at` | timestamp with time zone | no |  | _ADMIN_ |  |

<details><summary>Restricciones</summary>

- `sr_no_self_grant`: `CHECK (((granted_by IS NULL) OR (granted_by <> user_id)))`

</details>

<details><summary>Índices</summary>

- `UNIQUE USING btree (user_id, role) WHERE (revoked_at IS NULL)` — staff_roles_active_uq

</details>

<details><summary>Políticas RLS</summary>

- `sr_manage` (INSERT → girando_app)
- `sr_revoke` (UPDATE → girando_app)
- `sr_select` (SELECT → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## sessions

[PROPIETARIO] Sesiones/dispositivos. Permite "cerrar las demás sesiones" revocando en backend.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _PROPIETARIO_ | **PK** |
| `user_id` | uuid | sí |  | _PROPIETARIO_ | FK → app.users(id) ON DELETE CASCADE |
| `refresh_token_hash` | bytea | sí |  | SISTEMA | SHA-256 del refresh token (nunca el token). |
| `platform` | app.client_platform | sí |  | _PROPIETARIO_ |  |
| `device_label` | text | no |  | _PROPIETARIO_ |  |
| `user_agent` | text | no |  | _PROPIETARIO_ |  |
| `ip` | inet | no |  | PRIVADO | Retención: logs técnicos (90 días) — se anonimiza luego. |
| `ip_city` | text | no |  | _PROPIETARIO_ |  |
| `mfa_passed` | boolean | sí | false | _PROPIETARIO_ |  |
| `created_at` | timestamp with time zone | sí | now() | _PROPIETARIO_ |  |
| `last_seen_at` | timestamp with time zone | sí | now() | _PROPIETARIO_ |  |
| `expires_at` | timestamp with time zone | sí |  | _PROPIETARIO_ |  |
| `ended_at` | timestamp with time zone | no |  | _PROPIETARIO_ |  |
| `end_reason` | app.session_end_reason | no |  | _PROPIETARIO_ |  |

<details><summary>Restricciones</summary>

- `sessions_end_pair`: `CHECK (((ended_at IS NULL) = (end_reason IS NULL)))`

</details>

<details><summary>Índices</summary>

- `UNIQUE USING btree (refresh_token_hash)` — sessions_token_uq
- `USING btree (user_id, last_seen_at DESC) WHERE (ended_at IS NULL)` — sessions_user_active_idx

</details>

<details><summary>Políticas RLS</summary>

- `sessions_own` (SELECT → girando_app)
- `sessions_revoke` (UPDATE → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## auth_tokens

[SISTEMA] Tokens de un solo uso (verificar email, recuperar contraseña, OTP teléfono, cambio de email).

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _SISTEMA_ | **PK** |
| `user_id` | uuid | sí |  | _SISTEMA_ | FK → app.users(id) ON DELETE CASCADE |
| `purpose` | app.auth_token_purpose | sí |  | _SISTEMA_ |  |
| `token_hash` | bytea | sí |  | _SISTEMA_ |  |
| `new_value` | text | no |  | _SISTEMA_ |  |
| `expires_at` | timestamp with time zone | sí |  | _SISTEMA_ |  |
| `used_at` | timestamp with time zone | no |  | _SISTEMA_ |  |
| `created_at` | timestamp with time zone | sí | now() | _SISTEMA_ |  |

<details><summary>Índices</summary>

- `UNIQUE USING btree (token_hash)` — auth_tokens_hash_uq
- `USING btree (user_id, purpose) WHERE (used_at IS NULL)` — auth_tokens_user_idx

</details>

<details><summary>Políticas RLS</summary>

- `worker_all` (ALL → girando_worker)

</details>

---

## login_attempts

[ADMIN] Intentos de login para bloqueo y detección de abuso. Retención corta (logs técnicos).

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | bigint | sí |  | _ADMIN_ | **PK** |
| `email` | citext | sí |  | _ADMIN_ |  |
| `user_id` | uuid | no |  | _ADMIN_ | FK → app.users(id) ON DELETE SET NULL |
| `ip` | inet | no |  | _ADMIN_ |  |
| `user_agent` | text | no |  | _ADMIN_ |  |
| `success` | boolean | sí |  | _ADMIN_ |  |
| `failure_reason` | text | no |  | _ADMIN_ |  |
| `created_at` | timestamp with time zone | sí | now() | _ADMIN_ |  |

<details><summary>Índices</summary>

- `USING btree (email, created_at DESC)` — login_attempts_email_idx
- `USING btree (ip, created_at DESC)` — login_attempts_ip_idx

</details>

<details><summary>Políticas RLS</summary>

- `la_staff` (SELECT → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## user_blocks

[PROPIETARIO] Bloqueos entre usuarios. El bloqueado no puede iniciar ni continuar conversaciones.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `blocker_user_id` | uuid | sí |  | _PROPIETARIO_ | **PK** · FK → app.users(id) ON DELETE CASCADE |
| `blocked_user_id` | uuid | sí |  | _PROPIETARIO_ | **PK** · FK → app.users(id) ON DELETE CASCADE |
| `reason` | text | no |  | _PROPIETARIO_ |  |
| `created_at` | timestamp with time zone | sí | now() | _PROPIETARIO_ |  |

<details><summary>Restricciones</summary>

- `ub_not_self`: `CHECK ((blocker_user_id <> blocked_user_id))`

</details>

<details><summary>Índices</summary>

- `USING btree (blocked_user_id)` — user_blocks_blocked_idx

</details>

<details><summary>Políticas RLS</summary>

- `ub_own` (ALL → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## policy_versions

[PÚBLICO] Versiones de Términos, Privacidad y Cookies. El hash prueba qué texto se aceptó.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _PÚBLICO_ | **PK** |
| `doc_type` | app.policy_doc_type | sí |  | _PÚBLICO_ |  |
| `version` | text | sí |  | _PÚBLICO_ |  |
| `content_url` | text | sí |  | _PÚBLICO_ |  |
| `content_sha256` | bytea | sí |  | _PÚBLICO_ |  |
| `published_at` | timestamp with time zone | sí |  | _PÚBLICO_ |  |
| `created_at` | timestamp with time zone | sí | now() | _PÚBLICO_ |  |

<details><summary>Restricciones</summary>

- `policy_versions_doc_type_version_key`: `UNIQUE (doc_type, version)`

</details>

<details><summary>Índices</summary>

- `UNIQUE USING btree (doc_type, version)` — policy_versions_doc_type_version_key

</details>

<details><summary>Políticas RLS</summary>

- `pv_admin` (INSERT → girando_app)
- `pv_read` (SELECT → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## consents

[PROPIETARIO] Registro append-only. Cada cambio inserta una fila nueva y marca superseded_at en la anterior (= fecha de actualización).

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _PROPIETARIO_ | **PK** |
| `user_id` | uuid | no |  | _PROPIETARIO_ | FK → app.users(id) ON DELETE SET NULL |
| `anonymous_id` | uuid | no |  | PRIVADO | ID de dispositivo para visitantes sin cuenta (cookie de primera parte). Se vincula a user_id al registrarse. |
| `consent_type` | app.consent_type | sí |  | _PROPIETARIO_ |  |
| `policy_version_id` | uuid | sí |  | _PROPIETARIO_ | FK → app.policy_versions(id) |
| `state` | app.consent_state | sí |  | _PROPIETARIO_ |  |
| `necessary` | boolean | sí | true | _PROPIETARIO_ |  |
| `preferences` | boolean | no |  | _PROPIETARIO_ |  |
| `analytics` | boolean | no |  | _PROPIETARIO_ |  |
| `marketing` | boolean | no |  | _PROPIETARIO_ |  |
| `channel` | app.client_platform | sí |  | _PROPIETARIO_ |  |
| `user_agent` | text | no |  | _PROPIETARIO_ |  |
| `created_at` | timestamp with time zone | sí | now() | _PROPIETARIO_ |  |
| `superseded_at` | timestamp with time zone | no |  | _PROPIETARIO_ |  |

<details><summary>Restricciones</summary>

- `consents_cookie_fields`: `CHECK (((consent_type = 'cookies'::app.consent_type) = ((preferences IS NOT NULL) AND (analytics IS NOT NULL) AND (marketing IS NOT NULL))))`
- `consents_necessary`: `CHECK (necessary)`
- `consents_subject`: `CHECK ((num_nonnulls(user_id, anonymous_id) >= 1))`

</details>

<details><summary>Índices</summary>

- `UNIQUE USING btree (anonymous_id, consent_type) WHERE ((superseded_at IS NULL) AND (user_id IS NULL))` — consents_current_anon_uq
- `UNIQUE USING btree (user_id, consent_type) WHERE ((superseded_at IS NULL) AND (user_id IS NOT NULL))` — consents_current_user_uq

</details>

<details><summary>Políticas RLS</summary>

- `cs_insert` (INSERT → girando_app)
- `cs_own` (SELECT → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## geo_areas

[PÚBLICO] Divisiones geográficas de referencia. Un solo árbol autorreferenciado en vez de 4 tablas.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _PÚBLICO_ | **PK** |
| `parent_id` | uuid | no |  | _PÚBLICO_ | FK → app.geo_areas(id) |
| `level` | app.geo_level | sí |  | _PÚBLICO_ |  |
| `name` | text | sí |  | _PÚBLICO_ |  |
| `official_code` | text | no |  | PÚBLICO | Código oficial (INDEC/Georef) para sincronizar sin duplicar. |
| `country_code` | character(2) | sí | 'AR'::bpchar | _PÚBLICO_ |  |
| `centroid_lat` | numeric(9,6) | no |  | PÚBLICO | Centroide del área: es la única coordenada que se muestra en mapas públicos. |
| `centroid_lng` | numeric(9,6) | no |  | _PÚBLICO_ |  |
| `is_active` | boolean | sí | true | _PÚBLICO_ |  |
| `name_search` | text | no |  | _PÚBLICO_ | generada |

<details><summary>Restricciones</summary>

- `geo_lat`: `CHECK (((centroid_lat IS NULL) OR ((centroid_lat >= ('-90'::integer)::numeric) AND (centroid_lat <= (90)::numeric))))`
- `geo_lng`: `CHECK (((centroid_lng IS NULL) OR ((centroid_lng >= ('-180'::integer)::numeric) AND (centroid_lng <= (180)::numeric))))`
- `geo_parent_rule`: `CHECK (((level = 'country'::app.geo_level) = (parent_id IS NULL)))`

</details>

<details><summary>Índices</summary>

- `UNIQUE USING btree (country_code, level, official_code) WHERE (official_code IS NOT NULL)` — geo_areas_code_uq
- `USING gin (name_search gin_trgm_ops)` — geo_areas_name_trgm
- `USING btree (parent_id)` — geo_areas_parent_idx

</details>

<details><summary>Políticas RLS</summary>

- `geo_admin_i` (INSERT → girando_app)
- `geo_admin_u` (UPDATE → girando_app)
- `geo_read` (SELECT → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## locations

Dirección exacta. [PRIVADO] por defecto. Nunca se expone para usuarios particulares.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _PRIVADO_ | **PK** |
| `country_code` | character(2) | sí | 'AR'::bpchar | _PRIVADO_ |  |
| `province_id` | uuid | sí |  | _PRIVADO_ | FK → app.geo_areas(id) |
| `department_id` | uuid | no |  | _PRIVADO_ | FK → app.geo_areas(id) |
| `locality_id` | uuid | no |  | _PRIVADO_ | FK → app.geo_areas(id) |
| `postal_code` | text | no |  | PRIVADO | CP de 4 dígitos o CPA (M5500ABC). |
| `neighborhood` | text | no |  | PRIVADO para particulares | Barrio/zona. El vendedor puede optar por mostrarlo (listings.show_neighborhood). |
| `street` | text | no |  | PRIVADO | Calle. |
| `street_number` | text | no |  | PRIVADO | Altura. |
| `unit` | text | no |  | _PRIVADO_ |  |
| `lat` | numeric(9,6) | no |  | PRIVADO | Coordenada exacta. Público solo el centroide de geo_areas. |
| `lng` | numeric(9,6) | no |  | _PRIVADO_ |  |
| `created_by` | uuid | no |  | _PRIVADO_ | FK → app.users(id) |
| `created_at` | timestamp with time zone | sí | now() | _PRIVADO_ |  |
| `updated_at` | timestamp with time zone | sí | now() | _PRIVADO_ |  |

<details><summary>Restricciones</summary>

- `loc_cp`: `CHECK (((postal_code IS NULL) OR (postal_code ~ '^([0-9]{4}\|[A-Z][0-9]{4}[A-Z]{3})$'::text)))`
- `loc_lat`: `CHECK (((lat IS NULL) OR ((lat >= ('-90'::integer)::numeric) AND (lat <= (90)::numeric))))`
- `loc_latlng_pair`: `CHECK (((lat IS NULL) = (lng IS NULL)))`
- `loc_lng`: `CHECK (((lng IS NULL) OR ((lng >= ('-180'::integer)::numeric) AND (lng <= (180)::numeric))))`

</details>

<details><summary>Índices</summary>

- `USING btree (locality_id)` — locations_locality_idx

</details>

<details><summary>Políticas RLS</summary>

- `loc_insert` (INSERT → girando_app)
- `loc_select` (SELECT → girando_app)
- `loc_update` (UPDATE → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## agencies

Agencia o concesionaria (organización). Los datos comerciales son públicos por naturaleza; los fiscales se muestran solo verificados.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _PRIVADO_ | **PK** |
| `slug` | text | sí |  | PÚBLICO | URL pública: girando.app/agencias/{slug}. |
| `kind` | app.agency_kind | sí | 'agency'::app.agency_kind | PÚBLICO | Agencia / Concesionaria oficial. "Concesionaria oficial" requiere verificación específica (contrato de marca). |
| `legal_name` | text | sí |  | PRIVADO | Razón social. Se usa para facturación y verificación. |
| `trade_name` | text | sí |  | PÚBLICO | Nombre comercial. |
| `cuit` | character(11) | sí |  | PRIVADO | CUIT (11 dígitos, validado con dígito verificador). Único entre agencias no revocadas. |
| `tax_condition` | app.tax_condition | no |  | PRIVADO | Condición fiscal. |
| `description` | text | no |  | _PRIVADO_ |  |
| `logo_public_id` | text | no |  | _PRIVADO_ |  |
| `cover_public_id` | text | no |  | _PRIVADO_ |  |
| `phone_e164` | text | no |  | PÚBLICO | Teléfono comercial (no el de los miembros). |
| `whatsapp_e164` | text | no |  | PÚBLICO | WhatsApp comercial. |
| `email` | citext | no |  | PÚBLICO | Email comercial. |
| `website_url` | text | no |  | _PRIVADO_ |  |
| `instagram_url` | text | no |  | _PRIVADO_ |  |
| `facebook_url` | text | no |  | _PRIVADO_ |  |
| `tiktok_url` | text | no |  | _PRIVADO_ |  |
| `youtube_url` | text | no |  | _PRIVADO_ |  |
| `x_url` | text | no |  | _PRIVADO_ |  |
| `location_id` | uuid | no |  | PÚBLICO | FK → app.locations(id) · Domicilio comercial del local (a diferencia de un particular). |
| `geo_area_id` | uuid | sí |  | PÚBLICO | FK → app.geo_areas(id) · Ciudad/departamento. |
| `business_hours` | jsonb | no |  | PÚBLICO | [{"day":1..7,"open":"09:00","close":"18:00"}]. JSON porque no se filtra por horario; schema validado en backend. |
| `status` | app.agency_status | sí | 'pending'::app.agency_status | PÚBLICO como distintivo | pending/review/verified/rejected/suspended/revoked. Solo staff (o el flujo de verificación) lo cambia. |
| `status_reason` | text | no |  | ADMIN | Motivo del último cambio. |
| `verified_at` | timestamp with time zone | no |  | _PRIVADO_ |  |
| `created_by` | uuid | sí |  | _PRIVADO_ | FK → app.users(id) |
| `created_at` | timestamp with time zone | sí | now() | _PRIVADO_ |  |
| `updated_at` | timestamp with time zone | sí | now() | _PRIVADO_ |  |

<details><summary>Restricciones</summary>

- `ag_cuit`: `CHECK (app.is_valid_cuit((cuit)::text))`
- `ag_desc_len`: `CHECK (((description IS NULL) OR (length(description) <= 2000)))`
- `ag_email`: `CHECK (((email IS NULL) OR (email ~ '^[^@\s]+@[^@\s]+\.[^@\s]{2,}$'::citext)))`
- `ag_fb`: `CHECK (((facebook_url IS NULL) OR (facebook_url ~* '^https://(www\.\|m\.)?facebook\.com/\S+$'::text)))`
- `ag_hours`: `CHECK (((business_hours IS NULL) OR (jsonb_typeof(business_hours) = 'array'::text)))`
- `ag_ig`: `CHECK (((instagram_url IS NULL) OR (instagram_url ~* '^https://(www\.)?instagram\.com/\S+$'::text)))`
- `ag_names`: `CHECK ((((length(btrim(legal_name)) >= 2) AND (length(btrim(legal_name)) <= 150)) AND ((length(btrim(trade_name)) >= 2) AND (length(btrim(trade_name)) <= 80))))`
- `ag_phone`: `CHECK (((phone_e164 IS NULL) OR (phone_e164 ~ '^\+[1-9][0-9]{7,14}$'::text)))`
- `ag_slug`: `CHECK (((slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'::text) AND (length(slug) <= 60)))`
- `ag_tt`: `CHECK (((tiktok_url IS NULL) OR (tiktok_url ~* '^https://(www\.)?tiktok\.com/@\S+$'::text)))`
- `ag_verified_pair`: `CHECK (((status = 'verified'::app.agency_status) <= (verified_at IS NOT NULL)))`
- `ag_wa`: `CHECK (((whatsapp_e164 IS NULL) OR (whatsapp_e164 ~ '^\+[1-9][0-9]{7,14}$'::text)))`
- `ag_web`: `CHECK (((website_url IS NULL) OR (website_url ~* '^https://\S+$'::text)))`
- `ag_x`: `CHECK (((x_url IS NULL) OR (x_url ~* '^https://(www\.)?(x\|twitter)\.com/\S+$'::text)))`
- `ag_yt`: `CHECK (((youtube_url IS NULL) OR (youtube_url ~* '^https://(www\.)?youtube\.com/\S+$'::text)))`

</details>

<details><summary>Índices</summary>

- `UNIQUE USING btree (cuit) WHERE (status <> ALL (ARRAY['rejected'::app.agency_status, 'revoked'::app.agency_status]))` — agencies_cuit_uq
- `USING btree (geo_area_id)` — agencies_geo_idx
- `UNIQUE USING btree (slug)` — agencies_slug_uq
- `USING btree (status)` — agencies_status_idx

</details>

<details><summary>Políticas RLS</summary>

- `ag_insert` (INSERT → girando_app)
- `ag_select` (SELECT → girando_app)
- `ag_update` (UPDATE → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## agency_members

[PRIVADO] Usuarios que operan una agencia (N:N usuarios↔agencias con rol). Límite de miembros según plan.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _PRIVADO_ | **PK** |
| `agency_id` | uuid | sí |  | _PRIVADO_ | FK → app.agencies(id) |
| `user_id` | uuid | sí |  | _PRIVADO_ | FK → app.users(id) |
| `role` | app.agency_member_role | sí | 'seller'::app.agency_member_role | _PRIVADO_ |  |
| `status` | app.member_status | sí | 'invited'::app.member_status | _PRIVADO_ |  |
| `invited_by` | uuid | no |  | _PRIVADO_ | FK → app.users(id) |
| `invited_at` | timestamp with time zone | sí | now() | _PRIVADO_ |  |
| `joined_at` | timestamp with time zone | no |  | _PRIVADO_ |  |
| `removed_at` | timestamp with time zone | no |  | _PRIVADO_ |  |
| `created_at` | timestamp with time zone | sí | now() | _PRIVADO_ |  |
| `updated_at` | timestamp with time zone | sí | now() | _PRIVADO_ |  |

<details><summary>Restricciones</summary>

- `am_joined`: `CHECK (((status = 'active'::app.member_status) <= (joined_at IS NOT NULL)))`

</details>

<details><summary>Índices</summary>

- `UNIQUE USING btree (agency_id, user_id) WHERE (status <> 'removed'::app.member_status)` — agency_members_uq
- `USING btree (user_id) WHERE (status = 'active'::app.member_status)` — agency_members_user_idx
- `UNIQUE USING btree (agency_id) WHERE ((role = 'owner'::app.agency_member_role) AND (status = 'active'::app.member_status))` — agency_one_owner_uq

</details>

<details><summary>Políticas RLS</summary>

- `am_insert` (INSERT → girando_app)
- `am_select` (SELECT → girando_app)
- `am_update` (UPDATE → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## external_ratings

[PÚBLICO] Puntaje y cantidad de Google (Places API), con enlace a la fuente y fecha de sincronización. PENDIENTE DE INTEGRACIÓN REAL.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _PÚBLICO_ | **PK** |
| `agency_id` | uuid | sí |  | _PÚBLICO_ | FK → app.agencies(id) |
| `provider` | text | sí | 'google'::text | _PÚBLICO_ |  |
| `external_place_id` | text | sí |  | _PÚBLICO_ |  |
| `rating` | numeric(2,1) | no |  | _PÚBLICO_ |  |
| `review_count` | integer | no |  | _PÚBLICO_ |  |
| `source_url` | text | no |  | _PÚBLICO_ |  |
| `synced_at` | timestamp with time zone | no |  | _PÚBLICO_ |  |
| `sync_error` | text | no |  | _PÚBLICO_ |  |
| `created_at` | timestamp with time zone | sí | now() | _PÚBLICO_ |  |

<details><summary>Restricciones</summary>

- `er_count`: `CHECK (((review_count IS NULL) OR (review_count >= 0)))`
- `er_provider`: `CHECK ((provider = 'google'::text))`
- `er_rating`: `CHECK (((rating IS NULL) OR ((rating >= (1)::numeric) AND (rating <= (5)::numeric))))`
- `external_ratings_agency_id_provider_key`: `UNIQUE (agency_id, provider)`

</details>

<details><summary>Índices</summary>

- `UNIQUE USING btree (agency_id, provider)` — external_ratings_agency_id_provider_key

</details>

<details><summary>Políticas RLS</summary>

- `er_read` (SELECT → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## vehicle_brands

[PÚBLICO] Marcas.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _PÚBLICO_ | **PK** |
| `name` | text | sí |  | _PÚBLICO_ |  |
| `slug` | text | sí |  | _PÚBLICO_ |  |
| `logo_public_id` | text | no |  | _PÚBLICO_ |  |
| `status` | app.catalog_status | sí | 'active'::app.catalog_status | _PÚBLICO_ |  |
| `created_at` | timestamp with time zone | sí | now() | _PÚBLICO_ |  |
| `updated_at` | timestamp with time zone | sí | now() | _PÚBLICO_ |  |

<details><summary>Restricciones</summary>

- `vb_slug`: `CHECK ((slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'::text))`

</details>

<details><summary>Índices</summary>

- `UNIQUE USING btree (lower(name))` — vehicle_brands_name_uq
- `UNIQUE USING btree (slug)` — vehicle_brands_slug_uq

</details>

<details><summary>Políticas RLS</summary>

- `cat_ins` (INSERT → girando_app)
- `cat_read` (SELECT → girando_app)
- `cat_upd` (UPDATE → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## vehicle_models

[PÚBLICO] Modelos de una marca.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _PÚBLICO_ | **PK** |
| `brand_id` | uuid | sí |  | _PÚBLICO_ | FK → app.vehicle_brands(id) ON DELETE RESTRICT |
| `name` | text | sí |  | _PÚBLICO_ |  |
| `slug` | text | sí |  | _PÚBLICO_ |  |
| `vehicle_type` | app.vehicle_type | sí |  | PÚBLICO | Auto, Camioneta, Utilitario, Camión, Moto, Cuatriciclo. |
| `default_body_type` | app.body_type | no |  | _PÚBLICO_ |  |
| `segment` | text | no |  | PÚBLICO | Segmento de mercado (A, B, C, D, E, F o descriptivo). |
| `status` | app.catalog_status | sí | 'active'::app.catalog_status | _PÚBLICO_ |  |
| `created_at` | timestamp with time zone | sí | now() | _PÚBLICO_ |  |
| `updated_at` | timestamp with time zone | sí | now() | _PÚBLICO_ |  |

<details><summary>Restricciones</summary>

- `vm_segment`: `CHECK (((segment IS NULL) OR (length(segment) <= 30)))`
- `vm_slug`: `CHECK ((slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'::text))`

</details>

<details><summary>Índices</summary>

- `UNIQUE USING btree (brand_id, slug)` — vehicle_models_slug_uq
- `UNIQUE USING btree (brand_id, lower(name))` — vehicle_models_uq

</details>

<details><summary>Políticas RLS</summary>

- `cat_ins` (INSERT → girando_app)
- `cat_read` (SELECT → girando_app)
- `cat_upd` (UPDATE → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## vehicle_generations

[PÚBLICO] Generaciones (p.ej. Gol "G4", Corsa "Classic"). year_to NULL = vigente.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _PÚBLICO_ | **PK** |
| `model_id` | uuid | sí |  | _PÚBLICO_ | FK → app.vehicle_models(id) ON DELETE RESTRICT |
| `name` | text | sí |  | _PÚBLICO_ |  |
| `year_from` | smallint | sí |  | _PÚBLICO_ |  |
| `year_to` | smallint | no |  | _PÚBLICO_ |  |
| `status` | app.catalog_status | sí | 'active'::app.catalog_status | _PÚBLICO_ |  |
| `created_at` | timestamp with time zone | sí | now() | _PÚBLICO_ |  |
| `updated_at` | timestamp with time zone | sí | now() | _PÚBLICO_ |  |

<details><summary>Restricciones</summary>

- `vg_years`: `CHECK ((((year_from >= 1900) AND (year_from <= 2100)) AND ((year_to IS NULL) OR (year_to >= year_from))))`

</details>

<details><summary>Índices</summary>

- `UNIQUE USING btree (model_id, lower(name))` — vehicle_generations_uq

</details>

<details><summary>Políticas RLS</summary>

- `cat_ins` (INSERT → girando_app)
- `cat_read` (SELECT → girando_app)
- `cat_upd` (UPDATE → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## vehicle_engines

[PÚBLICO] Motores reutilizables entre versiones (p.ej. "1.6 Nafta 8v"). Cilindrada, potencia y combustible viven acá.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _PÚBLICO_ | **PK** |
| `name` | text | sí |  | _PÚBLICO_ |  |
| `fuel` | app.fuel_type | sí |  | _PÚBLICO_ |  |
| `displacement_cc` | integer | no |  | _PÚBLICO_ |  |
| `power_hp` | smallint | no |  | _PÚBLICO_ |  |
| `torque_nm` | smallint | no |  | _PÚBLICO_ |  |
| `cylinders` | smallint | no |  | _PÚBLICO_ |  |
| `aspiration` | app.engine_aspiration | no |  | _PÚBLICO_ |  |
| `battery_kwh` | numeric(5,1) | no |  | _PÚBLICO_ |  |
| `status` | app.catalog_status | sí | 'active'::app.catalog_status | _PÚBLICO_ |  |
| `created_at` | timestamp with time zone | sí | now() | _PÚBLICO_ |  |
| `updated_at` | timestamp with time zone | sí | now() | _PÚBLICO_ |  |

<details><summary>Restricciones</summary>

- `ve_cc`: `CHECK (((displacement_cc IS NULL) OR ((displacement_cc >= 49) AND (displacement_cc <= 20000))))`
- `ve_cyl`: `CHECK (((cylinders IS NULL) OR ((cylinders >= 1) AND (cylinders <= 16))))`
- `ve_electric`: `CHECK (((fuel = 'electric'::app.fuel_type) <= (displacement_cc IS NULL)))`
- `ve_hp`: `CHECK (((power_hp IS NULL) OR ((power_hp >= 1) AND (power_hp <= 2000))))`
- `ve_nm`: `CHECK (((torque_nm IS NULL) OR ((torque_nm >= 1) AND (torque_nm <= 5000))))`

</details>

<details><summary>Índices</summary>

- `UNIQUE USING btree (lower(name))` — vehicle_engines_name_uq

</details>

<details><summary>Políticas RLS</summary>

- `cat_ins` (INSERT → girando_app)
- `cat_read` (SELECT → girando_app)
- `cat_upd` (UPDATE → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## vehicle_versions

[PÚBLICO] Versión/terminación (p.ej. "Trendline 1.6", "LTZ 2.8 TD 4x4 AT"). Define carrocería, puertas, transmisión, tracción.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _PÚBLICO_ | **PK** |
| `generation_id` | uuid | sí |  | _PÚBLICO_ | FK → app.vehicle_generations(id) ON DELETE RESTRICT |
| `name` | text | sí |  | _PÚBLICO_ |  |
| `body_type` | app.body_type | no |  | _PÚBLICO_ |  |
| `doors` | smallint | no |  | _PÚBLICO_ |  |
| `seats` | smallint | no |  | _PÚBLICO_ |  |
| `transmission` | app.transmission_type | no |  | _PÚBLICO_ |  |
| `gears` | smallint | no |  | _PÚBLICO_ |  |
| `traction` | app.traction_type | no |  | _PÚBLICO_ |  |
| `origin_country` | character(2) | no |  | PÚBLICO | Origen de fabricación (ISO-3166 alfa-2). |
| `year_from` | smallint | no |  | _PÚBLICO_ |  |
| `year_to` | smallint | no |  | _PÚBLICO_ |  |
| `external_code` | text | no |  | ADMIN | Código de catálogo externo (p.ej. guías de precios) para futura tasación. Sin integración. |
| `status` | app.catalog_status | sí | 'active'::app.catalog_status | _PÚBLICO_ |  |
| `created_at` | timestamp with time zone | sí | now() | _PÚBLICO_ |  |
| `updated_at` | timestamp with time zone | sí | now() | _PÚBLICO_ |  |

<details><summary>Restricciones</summary>

- `vv_doors`: `CHECK (((doors IS NULL) OR ((doors >= 0) AND (doors <= 6))))`
- `vv_gears`: `CHECK (((gears IS NULL) OR ((gears >= 1) AND (gears <= 12))))`
- `vv_seats`: `CHECK (((seats IS NULL) OR ((seats >= 1) AND (seats <= 60))))`
- `vv_years`: `CHECK (((year_from IS NULL) OR (year_to IS NULL) OR (year_to >= year_from)))`

</details>

<details><summary>Índices</summary>

- `UNIQUE USING btree (generation_id, lower(name))` — vehicle_versions_uq

</details>

<details><summary>Políticas RLS</summary>

- `cat_ins` (INSERT → girando_app)
- `cat_read` (SELECT → girando_app)
- `cat_upd` (UPDATE → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## vehicle_version_engines

[PÚBLICO] Combinaciones válidas versión+motor. vehicles referencia esta combinación (FK compuesta).

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `version_id` | uuid | sí |  | _PÚBLICO_ | **PK** · FK → app.vehicle_versions(id) ON DELETE RESTRICT |
| `engine_id` | uuid | sí |  | _PÚBLICO_ | **PK** · FK → app.vehicle_engines(id) ON DELETE RESTRICT |
| `is_default` | boolean | sí | false | _PÚBLICO_ |  |
| `status` | app.catalog_status | sí | 'active'::app.catalog_status | _PÚBLICO_ |  |

<details><summary>Índices</summary>

- `UNIQUE USING btree (version_id) WHERE is_default` — vve_default_uq
- `USING btree (engine_id)` — vve_engine_idx

</details>

<details><summary>Políticas RLS</summary>

- `cat_ins` (INSERT → girando_app)
- `cat_read` (SELECT → girando_app)
- `cat_upd` (UPDATE → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## catalog_requests

[PROPIETARIO] Texto libre SOLO como pedido al staff; nunca como identidad del vehículo.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _PROPIETARIO_ | **PK** |
| `requested_by` | uuid | sí |  | _PROPIETARIO_ | FK → app.users(id) |
| `vehicle_type` | app.vehicle_type | no |  | _PROPIETARIO_ |  |
| `brand_text` | text | sí |  | _PROPIETARIO_ |  |
| `model_text` | text | no |  | _PROPIETARIO_ |  |
| `version_text` | text | no |  | _PROPIETARIO_ |  |
| `year` | smallint | no |  | _PROPIETARIO_ |  |
| `status` | app.catalog_request_status | sí | 'pending'::app.catalog_request_status | _PROPIETARIO_ |  |
| `resolved_version_id` | uuid | no |  | _PROPIETARIO_ | FK → app.vehicle_versions(id) |
| `resolved_by` | uuid | no |  | _PROPIETARIO_ | FK → app.users(id) |
| `resolved_at` | timestamp with time zone | no |  | _PROPIETARIO_ |  |
| `created_at` | timestamp with time zone | sí | now() | _PROPIETARIO_ |  |

<details><summary>Índices</summary>

- `USING btree (created_at) WHERE (status = 'pending'::app.catalog_request_status)` — catalog_requests_pending_idx

</details>

<details><summary>Políticas RLS</summary>

- `cr_insert` (INSERT → girando_app)
- `cr_select` (SELECT → girando_app)
- `cr_update` (UPDATE → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## vehicles

Vehículo físico. Su identidad es el catálogo (version+engine), nunca texto libre. Marca/modelo/generación se derivan de la versión (no se duplican).

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _PRIVADO_ | **PK** |
| `owner_user_id` | uuid | sí |  | PRIVADO | FK → app.users(id) · Cuenta responsable en Girando (no implica titularidad registral). |
| `agency_id` | uuid | no |  | PÚBLICO vía publicación | FK → app.agencies(id) · Si pertenece al stock de una agencia. |
| `version_id` | uuid | no |  | PÚBLICO | FK → app.vehicle_versions(id) ON DELETE RESTRICT · NULL solo en borradores. Obligatorio para enviar a revisión. |
| `engine_id` | uuid | no |  | PÚBLICO | FK → app.vehicle_engines(id) ON DELETE RESTRICT · Debe ser una combinación válida de vehicle_version_engines. |
| `year` | smallint | no |  | PÚBLICO | Año modelo. Validado contra el rango de la versión/generación al publicar. |
| `color` | text | no |  | PÚBLICO | Color declarado. |
| `fuel_override` | app.fuel_type | no |  | PÚBLICO | Solo si difiere del motor de catálogo (p.ej. conversión a GNC). |
| `created_at` | timestamp with time zone | sí | now() | _PRIVADO_ |  |
| `updated_at` | timestamp with time zone | sí | now() | _PRIVADO_ |  |

<details><summary>Restricciones</summary>

- `veh_color`: `CHECK (((color IS NULL) OR (length(color) <= 40)))`
- `veh_engine_needs_version`: `CHECK (((engine_id IS NULL) OR (version_id IS NOT NULL)))`
- `veh_year`: `CHECK (((year IS NULL) OR ((year >= 1900) AND (year <= 2100))))`
- `veh_version_engine_fk`: `FOREIGN KEY (version_id, engine_id) REFERENCES app.vehicle_version_engines(version_id, engine_id) ON DELETE RESTRICT`

</details>

<details><summary>Índices</summary>

- `USING btree (agency_id) WHERE (agency_id IS NOT NULL)` — vehicles_agency_idx
- `USING btree (owner_user_id)` — vehicles_owner_idx
- `USING btree (version_id)` — vehicles_version_idx

</details>

<details><summary>Políticas RLS</summary>

- `veh_insert` (INSERT → girando_app)
- `veh_select` (SELECT → girando_app)
- `veh_update` (UPDATE → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## vehicle_identifiers

[SENSIBLE] Nunca públicos. Solo dueño del vehículo y staff. Se usan para verificación y detección de fraude (mismo VIN/patente en publicaciones de distintos dueños).

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _SENSIBLE_ | **PK** |
| `vehicle_id` | uuid | sí |  | _SENSIBLE_ | FK → app.vehicles(id) |
| `type` | app.identifier_type | sí |  | _SENSIBLE_ |  |
| `value` | text | sí |  | SENSIBLE | Normalizado: mayúsculas, sin espacios ni guiones. |
| `country_code` | character(2) | sí | 'AR'::bpchar | _SENSIBLE_ |  |
| `status` | app.identifier_status | sí | 'declared'::app.identifier_status | PRIVADO | declared → pending → verified \| rejected. |
| `is_current` | boolean | sí | true | _SENSIBLE_ |  |
| `declared_by` | uuid | sí |  | _SENSIBLE_ | FK → app.users(id) |
| `verified_by` | uuid | no |  | _SENSIBLE_ | FK → app.users(id) |
| `verified_at` | timestamp with time zone | no |  | _SENSIBLE_ |  |
| `rejection_reason` | text | no |  | _SENSIBLE_ |  |
| `purge_after` | timestamp with time zone | no |  | SISTEMA | Fecha de borrado por retención (p.ej. patente de vehículo vendido: 24 meses). |
| `created_at` | timestamp with time zone | sí | now() | _SENSIBLE_ |  |
| `updated_at` | timestamp with time zone | sí | now() | _SENSIBLE_ |  |

<details><summary>Restricciones</summary>

- `vi_no_self_verify`: `CHECK (((verified_by IS NULL) OR (verified_by <> declared_by)))`
- `vi_other_len`: `CHECK (((type = ANY (ARRAY['plate'::app.identifier_type, 'vin'::app.identifier_type])) OR ((length(value) >= 5) AND (length(value) <= 30))))`
- `vi_plate_ar`: `CHECK (((type <> 'plate'::app.identifier_type) OR (country_code <> 'AR'::bpchar) OR app.is_valid_ar_plate(value)))`
- `vi_value_norm`: `CHECK ((value = app.normalize_plate(value)))`
- `vi_verified_pair`: `CHECK (((status = 'verified'::app.identifier_status) = (verified_at IS NOT NULL)))`
- `vi_vin`: `CHECK (((type <> 'vin'::app.identifier_type) OR (value ~ '^[A-HJ-NPR-Z0-9]{17}$'::text)))`

</details>

<details><summary>Índices</summary>

- `UNIQUE USING btree (vehicle_id, type) WHERE is_current` — vi_current_uq
- `USING btree (type, country_code, value)` — vi_lookup_idx
- `USING btree (purge_after) WHERE (purge_after IS NOT NULL)` — vi_purge_idx

</details>

<details><summary>Políticas RLS</summary>

- `vi_insert` (INSERT → girando_app)
- `vi_select` (SELECT → girando_app)
- `vi_update` (UPDATE → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## listings

Publicación (oferta) de un vehículo. Pertenece a la agencia si agency_id no es NULL; si no, al usuario.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _PRIVADO_ | **PK** |
| `public_code` | text | sí | app.gen_public_code('P'::text) | PÚBLICO | Código corto para URL y soporte (P-7K2M9QXA). |
| `owner_user_id` | uuid | sí |  | PRIVADO | FK → app.users(id) · Responsable. En agencias: el dueño de la cuenta/agencia; created_by = el vendedor que la cargó. |
| `agency_id` | uuid | no |  | PÚBLICO | FK → app.agencies(id) · Agencia dueña de la publicación. |
| `created_by` | uuid | sí |  | ADMIN | FK → app.users(id) · Miembro que la creó (trazabilidad dentro de la agencia). |
| `vehicle_id` | uuid | sí |  | _PRIVADO_ | FK → app.vehicles(id) |
| `geo_area_id` | uuid | no |  | PÚBLICO | FK → app.geo_areas(id) · Ubicación aproximada que se muestra ("Godoy Cruz, Mendoza"). |
| `location_id` | uuid | no |  | PRIVADO | FK → app.locations(id) · Dirección exacta opcional (para coordinar visitas). Nunca pública. |
| `show_neighborhood` | boolean | sí | false | PROPIETARIO | Mostrar barrio (nunca calle ni número). |
| `title` | text | sí | ''::text | PÚBLICO | Texto libre del vendedor. No alimenta filtros. |
| `description` | text | no |  | PÚBLICO | Texto libre. Girando no genera texto en nombre del vendedor. |
| `price_amount` | numeric(14,2) | no |  | PÚBLICO | Precio publicado. Cambios quedan en listing_price_history. |
| `currency` | app.currency_code | sí | 'ARS'::app.currency_code | PÚBLICO | ARS o USD. |
| `condition` | app.vehicle_condition | sí | 'used'::app.vehicle_condition | PÚBLICO | Nuevo / usado. |
| `km` | integer | no |  | PÚBLICO | Kilometraje declarado al publicar (no verificado salvo producto de verificación). |
| `is_financeable` | boolean | sí | false | PÚBLICO | El vendedor ofrece financiación. |
| `accepts_trade_in` | boolean | sí | false | PÚBLICO | Acepta permuta. |
| `video_url` | text | no |  | PÚBLICO | Video de YouTube opcional (solo youtube.com / youtu.be). |
| `status` | app.listing_status | sí | 'draft'::app.listing_status | PÚBLICO solo "published" | Máquina de estados validada por trigger (ver 120_reglas.sql). |
| `status_reason` | text | no |  | PROPIETARIO | Motivo de moderación visible al vendedor ("las fotos no muestran el vehículo"). |
| `status_changed_at` | timestamp with time zone | sí | now() | _PRIVADO_ |  |
| `submitted_at` | timestamp with time zone | no |  | _PRIVADO_ |  |
| `first_published_at` | timestamp with time zone | no |  | PÚBLICO | Primera publicación (base de "días hasta la venta"). |
| `published_at` | timestamp with time zone | no |  | PÚBLICO | Inicio del ciclo de publicación actual. |
| `expires_at` | timestamp with time zone | no |  | PROPIETARIO | published_at + duración configurada (60 días). Aviso 3 días antes. |
| `paused_at` | timestamp with time zone | no |  | _PRIVADO_ |  |
| `sold_at` | timestamp with time zone | no |  | _PRIVADO_ |  |
| `deleted_at` | timestamp with time zone | no |  | _PRIVADO_ |  |
| `renewal_count` | smallint | sí | 0 | _PRIVADO_ |  |
| `reviewed_by` | uuid | no |  | _PRIVADO_ | FK → app.users(id) |
| `reviewed_at` | timestamp with time zone | no |  | _PRIVADO_ |  |
| `duplicate_of_listing_id` | uuid | no |  | ADMIN | FK → app.listings(id) · Marca de posible duplicado para revisión. No bloquea automáticamente. |
| `search_vector` | tsvector | no |  | SISTEMA | generada · Índice de texto (título + descripción, español, sin tildes). |
| `created_at` | timestamp with time zone | sí | now() | _PRIVADO_ |  |
| `updated_at` | timestamp with time zone | sí | now() | _PRIVADO_ |  |

<details><summary>Restricciones</summary>

- `li_deleted_at`: `CHECK (((status = 'deleted'::app.listing_status) = (deleted_at IS NOT NULL)))`
- `li_desc_len`: `CHECK (((description IS NULL) OR (length(description) <= 5000)))`
- `li_km`: `CHECK (((km IS NULL) OR ((km >= 0) AND (km <= 2000000))))`
- `li_price`: `CHECK (((price_amount IS NULL) OR ((price_amount > (0)::numeric) AND (price_amount < ('100000000000'::bigint)::numeric))))`
- `li_publishable`: `CHECK (((status = ANY (ARRAY['draft'::app.listing_status, 'deleted'::app.listing_status])) OR ((geo_area_id IS NOT NULL) AND (price_amount IS NOT NULL) AND (km IS NOT NULL) AND (length(btrim(title)) >= 5))))`
- `li_published_dates`: `CHECK (((status <> 'published'::app.listing_status) OR ((published_at IS NOT NULL) AND (expires_at IS NOT NULL))))`
- `li_sold_at`: `CHECK (((status = 'sold'::app.listing_status) = (sold_at IS NOT NULL)))`
- `li_title_len`: `CHECK ((length(title) <= 90))`
- `li_video`: `CHECK (((video_url IS NULL) OR (video_url ~* '^https://(www\.)?(youtube\.com/(watch\?v=\|shorts/)\|youtu\.be/)[A-Za-z0-9_-]{6,}'::text)))`

</details>

<details><summary>Índices</summary>

- `USING btree (agency_id, status) WHERE (agency_id IS NOT NULL)` — listings_agency_idx
- `UNIQUE USING btree (public_code)` — listings_code_uq
- `USING btree (expires_at) WHERE (status = 'published'::app.listing_status)` — listings_expiry_idx
- `USING gin (search_vector)` — listings_fts_idx
- `USING btree (submitted_at) WHERE (status = 'pending'::app.listing_status)` — listings_moderation_idx
- `UNIQUE USING btree (vehicle_id) WHERE (status = ANY (ARRAY['draft'::app.listing_status, 'pending'::app.listing_status, 'published'::app.listing_status, 'paused'::app.listing_status, 'requires_changes'::app.listing_status, 'expired'::app.listing_status]))` — listings_one_open_per_vehicle_uq
- `USING btree (owner_user_id, status)` — listings_owner_idx
- `USING btree (geo_area_id) WHERE (status = 'published'::app.listing_status)` — listings_published_geo_idx
- `USING btree (km) WHERE (status = 'published'::app.listing_status)` — listings_published_km_idx
- `USING btree (currency, price_amount) WHERE (status = 'published'::app.listing_status)` — listings_published_price_idx
- `USING btree (published_at DESC) WHERE (status = 'published'::app.listing_status)` — listings_published_recent_idx

</details>

<details><summary>Políticas RLS</summary>

- `li_insert` (INSERT → girando_app)
- `li_select` (SELECT → girando_app)
- `li_update` (UPDATE → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## listing_images

Fotos de la publicación. Máx. 6 activas, JPG/PNG/WEBP, ≤10 MB. Solo referencias de Cloudinary.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _PRIVADO_ | **PK** |
| `listing_id` | uuid | sí |  | _PRIVADO_ | FK → app.listings(id) |
| `cloudinary_public_id` | text | sí |  | PÚBLICO | Identificador para construir URLs transformadas (thumb, card, detalle, srcset). |
| `cloudinary_version` | bigint | no |  | _PRIVADO_ |  |
| `cloudinary_asset_id` | text | no |  | _PRIVADO_ |  |
| `secure_url` | text | sí |  | PÚBLICO | URL original devuelta por Cloudinary (solo referencia; el frontend usa transformaciones). |
| `etag` | text | no |  | ADMIN | Hash del archivo (MD5 de Cloudinary) para detectar fotos repetidas entre publicaciones. |
| `format` | text | sí |  | PÚBLICO | jpg/png/webp. |
| `kind` | app.image_kind | sí | 'additional'::app.image_kind | PÚBLICO | Posición sugerida (frente, trasera, laterales, interior, adicional). No obligatoria. |
| `position` | smallint | sí |  | PÚBLICO | Orden 1..6 (reordenable sin tocar Cloudinary). |
| `is_cover` | boolean | sí | false | PÚBLICO | Portada. Exactamente una por publicación con fotos (índice parcial único). |
| `width` | integer | sí |  | PÚBLICO | Ancho en px (para layout/srcset). |
| `height` | integer | sí |  | PÚBLICO | Alto en px. |
| `bytes` | integer | sí |  | ADMIN | Tamaño (≤10 MB). |
| `status` | app.image_status | sí | 'active'::app.image_status | SISTEMA | uploading → active → replaced/deleted → purge_scheduled → purged (borrado real en Cloudinary). |
| `uploaded_by` | uuid | sí |  | _PRIVADO_ | FK → app.users(id) |
| `uploaded_at` | timestamp with time zone | sí | now() | _PRIVADO_ |  |
| `purge_after` | timestamp with time zone | no |  | SISTEMA | Cuándo borrar en Cloudinary según retention_policies (vendida: 7 días). |
| `purged_at` | timestamp with time zone | no |  | _PRIVADO_ |  |
| `updated_at` | timestamp with time zone | sí | now() | _PRIVADO_ |  |

<details><summary>Restricciones</summary>

- `lim_bytes`: `CHECK (((bytes >= 1) AND (bytes <= 10485760)))`
- `lim_cover_active`: `CHECK (((NOT is_cover) OR (status = 'active'::app.image_status)))`
- `lim_dims`: `CHECK ((((width >= 320) AND (width <= 12000)) AND ((height >= 240) AND (height <= 12000))))`
- `lim_format`: `CHECK ((format = ANY (ARRAY['jpg'::text, 'jpeg'::text, 'png'::text, 'webp'::text])))`
- `lim_position`: `CHECK ((("position" >= 1) AND ("position" <= 6)))`
- `lim_purged`: `CHECK (((status = 'purged'::app.image_status) = (purged_at IS NOT NULL)))`
- `lim_url`: `CHECK ((secure_url ~ '^https://res\.cloudinary\.com/'::text))`

</details>

<details><summary>Índices</summary>

- `USING btree (etag) WHERE ((etag IS NOT NULL) AND (status = 'active'::app.image_status))` — lim_etag_idx
- `UNIQUE USING btree (listing_id) WHERE (is_cover AND (status = 'active'::app.image_status))` — lim_one_cover_uq
- `UNIQUE USING btree (listing_id, "position") WHERE (status = 'active'::app.image_status)` — lim_position_uq
- `UNIQUE USING btree (cloudinary_public_id)` — lim_public_id_uq
- `USING btree (purge_after) WHERE (status = 'purge_scheduled'::app.image_status)` — lim_purge_idx

</details>

<details><summary>Políticas RLS</summary>

- `lim_insert` (INSERT → girando_app)
- `lim_select` (SELECT → girando_app)
- `lim_update` (UPDATE → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## listing_contacts

Canales de contacto de la publicación, separados de los datos personales. Teléfono/WhatsApp/email se revelan solo si show_*=true y a usuarios autenticados (evento listing_contact_reveal).

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `listing_id` | uuid | sí |  | _PRIVADO_ | **PK** · FK → app.listings(id) |
| `source` | app.contact_source | sí | 'user_profile'::app.contact_source | _PRIVADO_ |  |
| `phone_e164` | text | no |  | PRIVADO salvo show_phone | Copia editable del default del perfil o de la agencia. |
| `show_phone` | boolean | sí | false | _PRIVADO_ |  |
| `whatsapp_e164` | text | no |  | PRIVADO salvo show_whatsapp | . |
| `show_whatsapp` | boolean | sí | false | _PRIVADO_ |  |
| `email` | citext | no |  | PRIVADO salvo show_email | . |
| `show_email` | boolean | sí | false | _PRIVADO_ |  |
| `instagram_url` | text | no |  | PÚBLICO | Redes comerciales opcionales. |
| `tiktok_url` | text | no |  | _PRIVADO_ |  |
| `facebook_url` | text | no |  | _PRIVADO_ |  |
| `website_url` | text | no |  | _PRIVADO_ |  |
| `updated_at` | timestamp with time zone | sí | now() | _PRIVADO_ |  |

<details><summary>Restricciones</summary>

- `lc_email`: `CHECK (((email IS NULL) OR (email ~ '^[^@\s]+@[^@\s]+\.[^@\s]{2,}$'::citext)))`
- `lc_fb`: `CHECK (((facebook_url IS NULL) OR (facebook_url ~* '^https://(www\.\|m\.)?facebook\.com/\S+$'::text)))`
- `lc_ig`: `CHECK (((instagram_url IS NULL) OR (instagram_url ~* '^https://(www\.)?instagram\.com/\S+$'::text)))`
- `lc_phone`: `CHECK (((phone_e164 IS NULL) OR (phone_e164 ~ '^\+[1-9][0-9]{7,14}$'::text)))`
- `lc_show_needs_value`: `CHECK ((((NOT show_phone) OR (phone_e164 IS NOT NULL)) AND ((NOT show_whatsapp) OR (whatsapp_e164 IS NOT NULL)) AND ((NOT show_email) OR (email IS NOT NULL))))`
- `lc_tt`: `CHECK (((tiktok_url IS NULL) OR (tiktok_url ~* '^https://(www\.)?tiktok\.com/@\S+$'::text)))`
- `lc_wa`: `CHECK (((whatsapp_e164 IS NULL) OR (whatsapp_e164 ~ '^\+[1-9][0-9]{7,14}$'::text)))`
- `lc_web`: `CHECK (((website_url IS NULL) OR (website_url ~* '^https://\S+$'::text)))`

</details>

<details><summary>Políticas RLS</summary>

- `lc_select` (SELECT → girando_app)
- `lc_update` (UPDATE → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## listing_status_history

[PROPIETARIO] Cada transición de estado (la escribe el trigger). Base para "tiempo hasta venta", moderación e historial del vendedor.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | bigint | sí |  | _PROPIETARIO_ | **PK** |
| `listing_id` | uuid | sí |  | _PROPIETARIO_ | FK → app.listings(id) |
| `from_status` | app.listing_status | no |  | _PROPIETARIO_ |  |
| `to_status` | app.listing_status | sí |  | _PROPIETARIO_ |  |
| `reason` | text | no |  | _PROPIETARIO_ |  |
| `actor_user_id` | uuid | no |  | _PROPIETARIO_ | FK → app.users(id) |
| `actor_type` | app.actor_type | sí |  | _PROPIETARIO_ |  |
| `created_at` | timestamp with time zone | sí | now() | _PROPIETARIO_ |  |

<details><summary>Índices</summary>

- `USING btree (listing_id, created_at)` — lsh_listing_idx

</details>

<details><summary>Políticas RLS</summary>

- `lsh_select` (SELECT → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## listing_price_history

[PÚBLICO agregado] Cambios de precio. Alimenta "Bajó el precio de un favorito" y estadísticas precio publicado vs final.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | bigint | sí |  | _PRIVADO_ | **PK** |
| `listing_id` | uuid | sí |  | _PRIVADO_ | FK → app.listings(id) |
| `old_amount` | numeric(14,2) | no |  | _PRIVADO_ |  |
| `old_currency` | app.currency_code | no |  | _PRIVADO_ |  |
| `new_amount` | numeric(14,2) | sí |  | _PRIVADO_ |  |
| `new_currency` | app.currency_code | sí |  | _PRIVADO_ |  |
| `changed_by` | uuid | no |  | _PRIVADO_ | FK → app.users(id) |
| `created_at` | timestamp with time zone | sí | now() | _PRIVADO_ |  |

<details><summary>Índices</summary>

- `USING btree (listing_id, created_at)` — lph_listing_idx

</details>

<details><summary>Políticas RLS</summary>

- `lph_select` (SELECT → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## verification_products

[PÚBLICO si active] Productos de verificación (Identidad, Agencia verificada; a futuro documentación, existencia del vehículo, inspección física).

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _PÚBLICO_ | **PK** |
| `code` | text | sí |  | _PÚBLICO_ |  |
| `name` | text | sí |  | _PÚBLICO_ |  |
| `description` | text | sí |  | _PÚBLICO_ |  |
| `kind` | app.verification_kind | sí |  | _PÚBLICO_ |  |
| `subject` | app.verification_subject | sí |  | _PÚBLICO_ |  |
| `price_amount` | numeric(12,2) | sí | 0 | _PÚBLICO_ |  |
| `currency` | app.currency_code | sí | 'ARS'::app.currency_code | _PÚBLICO_ |  |
| `required_documents` | app.document_type[] | sí | '{}'::app.document_type[] | _PÚBLICO_ |  |
| `validity_days` | integer | no |  | _PÚBLICO_ |  |
| `includes_physical_inspection` | boolean | sí | false | PÚBLICO | Solo true para un producto de inspección física real. Ningún otro producto puede decir que Girando inspeccionó un vehículo. |
| `public_disclaimer` | text | sí |  | PÚBLICO | Qué certifica y qué NO (p.ej. "Agencia verificada certifica los datos de la empresa, no el estado de los vehículos"). |
| `status` | app.verification_product_status | sí | 'draft'::app.verification_product_status | _PÚBLICO_ |  |
| `created_at` | timestamp with time zone | sí | now() | _PÚBLICO_ |  |
| `updated_at` | timestamp with time zone | sí | now() | _PÚBLICO_ |  |

<details><summary>Restricciones</summary>

- `vp_code`: `CHECK ((code ~ '^[a-z][a-z0-9_]{2,40}$'::text))`
- `vp_inspection_kind`: `CHECK ((includes_physical_inspection = (kind = 'physical_inspection'::app.verification_kind)))`
- `vp_price`: `CHECK ((price_amount >= (0)::numeric))`
- `vp_validity`: `CHECK (((validity_days IS NULL) OR (validity_days > 0)))`

</details>

<details><summary>Índices</summary>

- `UNIQUE USING btree (code)` — verification_products_code_uq

</details>

<details><summary>Políticas RLS</summary>

- `vp_admin_i` (INSERT → girando_app)
- `vp_admin_u` (UPDATE → girando_app)
- `vp_read` (SELECT → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## verifications

Solicitud de verificación. Solo staff aprueba/rechaza/revoca; nunca el solicitante ni el sujeto (CHECK + RLS).

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _PRIVADO_ | **PK** |
| `product_id` | uuid | sí |  | _PRIVADO_ | FK → app.verification_products(id) |
| `subject_user_id` | uuid | no |  | _PRIVADO_ | FK → app.users(id) |
| `subject_agency_id` | uuid | no |  | _PRIVADO_ | FK → app.agencies(id) |
| `subject_vehicle_id` | uuid | no |  | _PRIVADO_ | FK → app.vehicles(id) |
| `subject_listing_id` | uuid | no |  | _PRIVADO_ | FK → app.listings(id) |
| `requested_by` | uuid | sí |  | _PRIVADO_ | FK → app.users(id) |
| `status` | app.verification_status | sí | 'pending'::app.verification_status | PÚBLICO como distintivo si approved | pending → review → approved \| rejected; approved → revoked. |
| `reviewer_id` | uuid | no |  | ADMIN | FK → app.users(id) · Staff que decidió. |
| `review_started_at` | timestamp with time zone | no |  | _PRIVADO_ |  |
| `decided_at` | timestamp with time zone | no |  | _PRIVADO_ |  |
| `decision_reason` | text | no |  | PROPIETARIO | Motivo visible al solicitante (obligatorio al rechazar o revocar). |
| `expires_at` | timestamp with time zone | no |  | _PRIVADO_ |  |
| `revoked_at` | timestamp with time zone | no |  | _PRIVADO_ |  |
| `payment_id` | uuid | no |  | _PRIVADO_ | FK → app.payments(id) |
| `created_at` | timestamp with time zone | sí | now() | _PRIVADO_ |  |
| `updated_at` | timestamp with time zone | sí | now() | _PRIVADO_ |  |

<details><summary>Restricciones</summary>

- `ver_decision`: `CHECK (((status <> ALL (ARRAY['approved'::app.verification_status, 'rejected'::app.verification_status, 'revoked'::app.verification_status])) OR ((decided_at IS NOT NULL) AND (reviewer_id IS NOT NULL))))`
- `ver_no_self_review`: `CHECK (((reviewer_id IS NULL) OR ((reviewer_id <> requested_by) AND (reviewer_id IS DISTINCT FROM subject_user_id))))`
- `ver_one_subject`: `CHECK ((num_nonnulls(subject_user_id, subject_agency_id, subject_vehicle_id, subject_listing_id) = 1))`
- `ver_reason`: `CHECK (((status <> ALL (ARRAY['rejected'::app.verification_status, 'revoked'::app.verification_status])) OR (decision_reason IS NOT NULL)))`
- `ver_revoked`: `CHECK (((status = 'revoked'::app.verification_status) = (revoked_at IS NOT NULL)))`

</details>

<details><summary>Índices</summary>

- `USING btree (subject_agency_id) WHERE (subject_agency_id IS NOT NULL)` — ver_agency_idx
- `UNIQUE USING btree (product_id, COALESCE(subject_user_id, subject_agency_id, subject_vehicle_id, subject_listing_id)) WHERE (status = ANY (ARRAY['pending'::app.verification_status, 'review'::app.verification_status]))` — ver_open_per_subject_uq
- `USING btree (created_at) WHERE (status = ANY (ARRAY['pending'::app.verification_status, 'review'::app.verification_status]))` — ver_queue_idx
- `USING btree (subject_user_id) WHERE (subject_user_id IS NOT NULL)` — ver_user_idx

</details>

<details><summary>Políticas RLS</summary>

- `ver_insert` (INSERT → girando_app)
- `ver_select` (SELECT → girando_app)
- `ver_update` (UPDATE → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## documents

[SENSIBLE] Documentos en bucket PRIVADO (S3/R2). Acceso solo con URL firmada de corta vida generada por el backend y auditada.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _SENSIBLE_ | **PK** |
| `uploaded_by` | uuid | sí |  | _SENSIBLE_ | FK → app.users(id) |
| `owner_user_id` | uuid | no |  | _SENSIBLE_ | FK → app.users(id) |
| `owner_agency_id` | uuid | no |  | _SENSIBLE_ | FK → app.agencies(id) |
| `owner_vehicle_id` | uuid | no |  | _SENSIBLE_ | FK → app.vehicles(id) |
| `verification_id` | uuid | no |  | PRIVADO | FK → app.verifications(id) · Si se presentó como parte de una verificación. |
| `type` | app.document_type | sí |  | _SENSIBLE_ |  |
| `storage_provider` | app.storage_provider | sí |  | _SENSIBLE_ |  |
| `storage_bucket` | text | sí |  | _SENSIBLE_ |  |
| `storage_key` | text | sí |  | SISTEMA | Ruta dentro del bucket privado. La "URL" se genera on-demand (firmada, 5 min); nunca se persiste. |
| `mime_type` | text | sí |  | _SENSIBLE_ |  |
| `bytes` | integer | sí |  | _SENSIBLE_ |  |
| `sha256` | bytea | sí |  | SISTEMA | Integridad y detección de reutilización de documentos entre cuentas. |
| `original_filename` | text | no |  | _SENSIBLE_ |  |
| `status` | app.document_status | sí | 'uploaded'::app.document_status | _SENSIBLE_ |  |
| `expires_on` | date | no |  | PRIVADO | Vencimiento del documento (p.ej. cédula, habilitación). Un job lo marca expired. |
| `reviewed_by` | uuid | no |  | _SENSIBLE_ | FK → app.users(id) |
| `reviewed_at` | timestamp with time zone | no |  | _SENSIBLE_ |  |
| `rejection_reason` | text | no |  | _SENSIBLE_ |  |
| `deleted_at` | timestamp with time zone | no |  | _SENSIBLE_ |  |
| `created_at` | timestamp with time zone | sí | now() | _SENSIBLE_ |  |
| `updated_at` | timestamp with time zone | sí | now() | _SENSIBLE_ |  |

<details><summary>Restricciones</summary>

- `doc_bytes`: `CHECK (((bytes >= 1) AND (bytes <= 15728640)))`
- `doc_deleted`: `CHECK (((status = 'deleted'::app.document_status) = (deleted_at IS NOT NULL)))`
- `doc_mime`: `CHECK ((mime_type = ANY (ARRAY['application/pdf'::text, 'image/jpeg'::text, 'image/png'::text, 'image/webp'::text])))`
- `doc_no_self_review`: `CHECK (((reviewed_by IS NULL) OR (reviewed_by <> uploaded_by)))`
- `doc_one_owner`: `CHECK ((num_nonnulls(owner_user_id, owner_agency_id, owner_vehicle_id) = 1))`
- `doc_reject_reason`: `CHECK (((status <> 'rejected'::app.document_status) OR (rejection_reason IS NOT NULL)))`
- `doc_review`: `CHECK (((status <> ALL (ARRAY['approved'::app.document_status, 'rejected'::app.document_status])) OR ((reviewed_by IS NOT NULL) AND (reviewed_at IS NOT NULL))))`

</details>

<details><summary>Índices</summary>

- `USING btree (owner_agency_id) WHERE (owner_agency_id IS NOT NULL)` — documents_agency_idx
- `USING btree (expires_on) WHERE ((status = 'approved'::app.document_status) AND (expires_on IS NOT NULL))` — documents_expiry_idx
- `UNIQUE USING btree (storage_provider, storage_bucket, storage_key)` — documents_key_uq
- `USING btree (sha256)` — documents_sha_idx
- `USING btree (owner_user_id) WHERE (owner_user_id IS NOT NULL)` — documents_user_idx
- `USING btree (owner_vehicle_id) WHERE (owner_vehicle_id IS NOT NULL)` — documents_vehicle_idx
- `USING btree (verification_id) WHERE (verification_id IS NOT NULL)` — documents_verification_idx

</details>

<details><summary>Políticas RLS</summary>

- `doc_insert` (INSERT → girando_app)
- `doc_select` (SELECT → girando_app)
- `doc_update` (UPDATE → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## reviews

Calificación entre usuarios/agencias atada a una conversación respondida o a una venta.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _PRIVADO_ | **PK** |
| `reviewer_user_id` | uuid | sí |  | PÚBLICO como display_name | FK → app.users(id) · Autor. |
| `reviewed_user_id` | uuid | no |  | _PRIVADO_ | FK → app.users(id) |
| `reviewed_agency_id` | uuid | no |  | _PRIVADO_ | FK → app.agencies(id) |
| `conversation_id` | uuid | no |  | _PRIVADO_ | FK → app.conversations(id) |
| `sale_id` | uuid | no |  | _PRIVADO_ | FK → app.sales(id) |
| `rating` | smallint | sí |  | PÚBLICO | 1 a 5. |
| `comment` | text | no |  | _PRIVADO_ |  |
| `status` | app.review_status | sí | 'published'::app.review_status | PÚBLICO solo published | hidden/removed por moderación (con motivo). |
| `status_reason` | text | no |  | _PRIVADO_ |  |
| `created_at` | timestamp with time zone | sí | now() | _PRIVADO_ |  |
| `updated_at` | timestamp with time zone | sí | now() | _PRIVADO_ |  |

<details><summary>Restricciones</summary>

- `rv_comment`: `CHECK (((comment IS NULL) OR (length(comment) <= 1000)))`
- `rv_not_self`: `CHECK ((reviewed_user_id IS DISTINCT FROM reviewer_user_id))`
- `rv_one_interaction`: `CHECK ((num_nonnulls(conversation_id, sale_id) = 1))`
- `rv_one_subject`: `CHECK ((num_nonnulls(reviewed_user_id, reviewed_agency_id) = 1))`
- `rv_rating`: `CHECK (((rating >= 1) AND (rating <= 5)))`

</details>

<details><summary>Índices</summary>

- `USING btree (reviewed_agency_id, created_at DESC) WHERE (status = 'published'::app.review_status)` — rv_agency_idx
- `UNIQUE USING btree (reviewer_user_id, conversation_id) WHERE (conversation_id IS NOT NULL)` — rv_once_per_conversation_uq
- `UNIQUE USING btree (reviewer_user_id, sale_id) WHERE (sale_id IS NOT NULL)` — rv_once_per_sale_uq
- `USING btree (reviewed_user_id, created_at DESC) WHERE (status = 'published'::app.review_status)` — rv_user_idx

</details>

<details><summary>Políticas RLS</summary>

- `rv_insert` (INSERT → girando_app)
- `rv_select` (SELECT → girando_app)
- `rv_update` (UPDATE → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## report_reasons

[PÚBLICO] Motivos configurables (precio falso, vehículo inexistente, información engañosa, duplicada, inapropiado, posible estafa, ya vendido, otro...).

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _PÚBLICO_ | **PK** |
| `code` | text | sí |  | _PÚBLICO_ |  |
| `label` | text | sí |  | _PÚBLICO_ |  |
| `applies_to` | app.report_target[] | sí |  | _PÚBLICO_ |  |
| `requires_description` | boolean | sí | false | _PÚBLICO_ |  |
| `is_active` | boolean | sí | true | _PÚBLICO_ |  |
| `sort_order` | smallint | sí | 0 | _PÚBLICO_ |  |

<details><summary>Restricciones</summary>

- `rr_code`: `CHECK ((code ~ '^[a-z][a-z0-9_]{2,40}$'::text))`
- `report_reasons_code_key`: `UNIQUE (code)`

</details>

<details><summary>Índices</summary>

- `UNIQUE USING btree (code)` — report_reasons_code_key

</details>

<details><summary>Políticas RLS</summary>

- `rr_admin_i` (INSERT → girando_app)
- `rr_admin_u` (UPDATE → girando_app)
- `rr_read` (SELECT → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## reports

"Denunciada" no es un estado de la publicación: es un reporte abierto sobre ella que se revisa en moderación.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _ADMIN_ | **PK** |
| `reporter_user_id` | uuid | no |  | ADMIN | FK → app.users(id) · Nunca se revela al reportado. |
| `reporter_anonymous_id` | uuid | no |  | _ADMIN_ |  |
| `target` | app.report_target | sí |  | _ADMIN_ |  |
| `listing_id` | uuid | no |  | _ADMIN_ | FK → app.listings(id) |
| `reported_user_id` | uuid | no |  | _ADMIN_ | FK → app.users(id) |
| `agency_id` | uuid | no |  | _ADMIN_ | FK → app.agencies(id) |
| `message_id` | uuid | no |  | _ADMIN_ | FK → app.messages(id) |
| `review_id` | uuid | no |  | _ADMIN_ | FK → app.reviews(id) |
| `reason_id` | uuid | sí |  | _ADMIN_ | FK → app.report_reasons(id) |
| `description` | text | no |  | ADMIN | Detalle opcional del reportante. |
| `status` | app.report_status | sí | 'pending'::app.report_status | _ADMIN_ |  |
| `assigned_to` | uuid | no |  | _ADMIN_ | FK → app.users(id) |
| `resolved_by` | uuid | no |  | _ADMIN_ | FK → app.users(id) |
| `resolved_at` | timestamp with time zone | no |  | _ADMIN_ |  |
| `resolution_note` | text | no |  | _ADMIN_ |  |
| `created_at` | timestamp with time zone | sí | now() | _ADMIN_ |  |
| `updated_at` | timestamp with time zone | sí | now() | _ADMIN_ |  |

<details><summary>Restricciones</summary>

- `rp_desc`: `CHECK (((description IS NULL) OR (length(description) <= 1000)))`
- `rp_one_target`: `CHECK ((num_nonnulls(listing_id, reported_user_id, agency_id, message_id, review_id) = 1))`
- `rp_reporter`: `CHECK ((num_nonnulls(reporter_user_id, reporter_anonymous_id) >= 1))`
- `rp_resolution`: `CHECK (((status <> ALL (ARRAY['resolved'::app.report_status, 'rejected'::app.report_status])) OR ((resolved_by IS NOT NULL) AND (resolved_at IS NOT NULL) AND (resolution_note IS NOT NULL))))`
- `rp_target_match`: `CHECK ((((target = 'listing'::app.report_target) AND (listing_id IS NOT NULL)) OR ((target = 'user'::app.report_target) AND (reported_user_id IS NOT NULL)) OR ((target = 'agency'::app.report_target) AND (agency_id IS NOT NULL)) OR ((target = 'message'::app.report_target) AND (message_id IS NOT NULL)) OR ((target = 'review'::app.report_target) AND (review_id IS NOT NULL))))`

</details>

<details><summary>Índices</summary>

- `USING btree (agency_id) WHERE (agency_id IS NOT NULL)` — reports_agency_idx
- `USING btree (listing_id) WHERE (listing_id IS NOT NULL)` — reports_listing_idx
- `UNIQUE USING btree (reporter_user_id, target, COALESCE(listing_id, reported_user_id, agency_id, message_id, review_id)) WHERE ((status = ANY (ARRAY['pending'::app.report_status, 'reviewing'::app.report_status])) AND (reporter_user_id IS NOT NULL))` — reports_no_dup_open_uq
- `USING btree (created_at) WHERE (status = ANY (ARRAY['pending'::app.report_status, 'reviewing'::app.report_status]))` — reports_queue_idx
- `USING btree (reported_user_id) WHERE (reported_user_id IS NOT NULL)` — reports_user_idx

</details>

<details><summary>Políticas RLS</summary>

- `rp_insert` (INSERT → girando_app)
- `rp_select` (SELECT → girando_app)
- `rp_update` (UPDATE → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## moderation_actions

[ADMIN] Toda acción de moderación con autor, rol y motivo (obligatorio si afecta a terceros). Append-only.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _ADMIN_ | **PK** |
| `actor_user_id` | uuid | sí |  | _ADMIN_ | FK → app.users(id) |
| `actor_role` | app.staff_role | sí |  | _ADMIN_ |  |
| `action` | app.moderation_action_type | sí |  | _ADMIN_ |  |
| `listing_id` | uuid | no |  | _ADMIN_ | FK → app.listings(id) |
| `target_user_id` | uuid | no |  | _ADMIN_ | FK → app.users(id) |
| `agency_id` | uuid | no |  | _ADMIN_ | FK → app.agencies(id) |
| `message_id` | uuid | no |  | _ADMIN_ | FK → app.messages(id) |
| `review_id` | uuid | no |  | _ADMIN_ | FK → app.reviews(id) |
| `verification_id` | uuid | no |  | _ADMIN_ | FK → app.verifications(id) |
| `report_id` | uuid | no |  | _ADMIN_ | FK → app.reports(id) |
| `previous_state` | text | no |  | _ADMIN_ |  |
| `new_state` | text | no |  | _ADMIN_ |  |
| `reason` | text | no |  | _ADMIN_ |  |
| `created_at` | timestamp with time zone | sí | now() | _ADMIN_ |  |

<details><summary>Restricciones</summary>

- `ma_one_target`: `CHECK (((num_nonnulls(listing_id, target_user_id, agency_id, message_id, review_id, verification_id) = 1) OR ((action = ANY (ARRAY['report_dismiss'::app.moderation_action_type, 'report_resolve'::app.moderation_action_type])) AND (report_id IS NOT NULL))))`
- `ma_reason_required`: `CHECK (((reason IS NOT NULL) OR (action = ANY (ARRAY['listing_approve'::app.moderation_action_type, 'listing_reactivate'::app.moderation_action_type, 'user_reactivate'::app.moderation_action_type, 'agency_verify'::app.moderation_action_type, 'agency_reactivate'::app.moderation_action_type, 'verification_approve'::app.moderation_action_type, 'review_restore'::app.moderation_action_type]))))`

</details>

<details><summary>Índices</summary>

- `USING btree (actor_user_id, created_at DESC)` — ma_actor_idx
- `USING btree (agency_id, created_at DESC) WHERE (agency_id IS NOT NULL)` — ma_agency_idx
- `USING btree (listing_id, created_at DESC) WHERE (listing_id IS NOT NULL)` — ma_listing_idx
- `USING btree (target_user_id, created_at DESC) WHERE (target_user_id IS NOT NULL)` — ma_user_idx

</details>

<details><summary>Políticas RLS</summary>

- `ma_insert` (INSERT → girando_app)
- `ma_select` (SELECT → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## favorites

[PROPIETARIO] Quién guardó qué. Al vendedor solo le llega el CONTEO (nunca quiénes). Métricas históricas vía analytics_events (listing_favorite/unfavorite).

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `user_id` | uuid | sí |  | _PROPIETARIO_ | **PK** · FK → app.users(id) ON DELETE CASCADE |
| `listing_id` | uuid | sí |  | _PROPIETARIO_ | **PK** · FK → app.listings(id) |
| `created_at` | timestamp with time zone | sí | now() | _PROPIETARIO_ |  |

<details><summary>Índices</summary>

- `USING btree (listing_id)` — favorites_listing_idx

</details>

<details><summary>Políticas RLS</summary>

- `fav_own` (ALL → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## saved_searches

[PROPIETARIO] Búsquedas guardadas. filters = el mismo DTO de búsqueda de la API (versionado y validado por Pydantic): marca(s), modelo(s), año min/max, precio min/max+moneda, km, ubicación, combustible, transmisión, carrocería, condición, tipo de vendedor, etc.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _PROPIETARIO_ | **PK** |
| `user_id` | uuid | sí |  | _PROPIETARIO_ | FK → app.users(id) ON DELETE CASCADE |
| `name` | text | sí |  | _PROPIETARIO_ |  |
| `filters` | jsonb | sí |  | _PROPIETARIO_ |  |
| `filters_version` | smallint | sí | 1 | _PROPIETARIO_ |  |
| `brand_id` | uuid | no |  | SISTEMA | FK → app.vehicle_brands(id) · Prefiltro extraído de filters para encontrar rápido qué búsquedas matchean una publicación nueva. |
| `model_id` | uuid | no |  | _PROPIETARIO_ | FK → app.vehicle_models(id) |
| `geo_area_id` | uuid | no |  | _PROPIETARIO_ | FK → app.geo_areas(id) |
| `notification_enabled` | boolean | sí | false | PROPIETARIO | "Avisarme cuando aparezca un vehículo que coincida". |
| `notify_frequency` | text | sí | 'daily'::text | _PROPIETARIO_ |  |
| `last_notified_at` | timestamp with time zone | no |  | _PROPIETARIO_ |  |
| `last_seen_listing_published_at` | timestamp with time zone | no |  | _PROPIETARIO_ |  |
| `created_at` | timestamp with time zone | sí | now() | _PROPIETARIO_ |  |
| `updated_at` | timestamp with time zone | sí | now() | _PROPIETARIO_ |  |

<details><summary>Restricciones</summary>

- `ss_filters_obj`: `CHECK ((jsonb_typeof(filters) = 'object'::text))`
- `ss_freq`: `CHECK ((notify_frequency = ANY (ARRAY['instant'::text, 'daily'::text, 'weekly'::text])))`
- `ss_name`: `CHECK (((length(btrim(name)) >= 1) AND (length(btrim(name)) <= 60)))`

</details>

<details><summary>Índices</summary>

- `USING btree (model_id, brand_id) WHERE notification_enabled` — ss_match_idx
- `USING btree (user_id)` — ss_user_idx

</details>

<details><summary>Políticas RLS</summary>

- `ss_own` (ALL → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## conversations

[PROPIETARIO de ambas partes] Conversación → publicación → vehículo. Si la publicación es de agencia, cualquier miembro activo responde por la agencia.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _PROPIETARIO_ | **PK** |
| `listing_id` | uuid | sí |  | _PROPIETARIO_ | FK → app.listings(id) |
| `buyer_user_id` | uuid | sí |  | _PROPIETARIO_ | FK → app.users(id) |
| `seller_user_id` | uuid | sí |  | PRIVADO | FK → app.users(id) · Dueño de la publicación al momento de iniciar. |
| `seller_agency_id` | uuid | no |  | _PROPIETARIO_ | FK → app.agencies(id) |
| `status` | app.conversation_status | sí | 'open'::app.conversation_status | _PROPIETARIO_ |  |
| `blocked_by_user_id` | uuid | no |  | _PROPIETARIO_ | FK → app.users(id) |
| `blocked_at` | timestamp with time zone | no |  | _PROPIETARIO_ |  |
| `seller_first_reply_at` | timestamp with time zone | no |  | SISTEMA | Habilita calificar ("consulta respondida") y mide tiempo de respuesta. |
| `last_message_at` | timestamp with time zone | no |  | _PROPIETARIO_ |  |
| `buyer_archived_at` | timestamp with time zone | no |  | _PROPIETARIO_ |  |
| `seller_archived_at` | timestamp with time zone | no |  | _PROPIETARIO_ |  |
| `created_at` | timestamp with time zone | sí | now() | _PROPIETARIO_ |  |
| `updated_at` | timestamp with time zone | sí | now() | _PROPIETARIO_ |  |

<details><summary>Restricciones</summary>

- `cv_blocked`: `CHECK (((status = 'blocked'::app.conversation_status) = ((blocked_at IS NOT NULL) AND (blocked_by_user_id IS NOT NULL))))`
- `cv_not_self`: `CHECK ((buyer_user_id <> seller_user_id))`

</details>

<details><summary>Índices</summary>

- `USING btree (seller_agency_id, last_message_at DESC) WHERE (seller_agency_id IS NOT NULL)` — cv_agency_idx
- `USING btree (buyer_user_id, created_at)` — cv_buyer_created_idx
- `USING btree (buyer_user_id, last_message_at DESC)` — cv_buyer_idx
- `UNIQUE USING btree (listing_id, buyer_user_id)` — cv_one_per_buyer_listing_uq
- `USING btree (seller_user_id, last_message_at DESC)` — cv_seller_idx

</details>

<details><summary>Políticas RLS</summary>

- `cv_insert` (INSERT → girando_app)
- `cv_select` (SELECT → girando_app)
- `cv_update` (UPDATE → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## messages

[PROPIETARIO de ambas partes] Mensajes. Borrado lógico por el autor (deleted_at). Staff solo accede ante un reporte (auditado).

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _PROPIETARIO_ | **PK** |
| `conversation_id` | uuid | sí |  | _PROPIETARIO_ | FK → app.conversations(id) |
| `sender_user_id` | uuid | sí |  | _PROPIETARIO_ | FK → app.users(id) |
| `sender_side` | app.participant_side | sí |  | _PROPIETARIO_ |  |
| `body` | text | sí |  | _PROPIETARIO_ |  |
| `body_hash` | bytea | no |  | SISTEMA | generada · Anti-spam: impide repetir el mismo mensaje seguido y detecta mensajes masivos idénticos. |
| `read_at` | timestamp with time zone | no |  | PROPIETARIO | Leído por la contraparte. |
| `deleted_at` | timestamp with time zone | no |  | _PROPIETARIO_ |  |
| `visibility` | app.message_visibility | sí | 'visible'::app.message_visibility | ADMIN | hidden_by_moderation tras un reporte resuelto. |
| `created_at` | timestamp with time zone | sí | now() | _PROPIETARIO_ |  |

<details><summary>Restricciones</summary>

- `msg_body`: `CHECK (((length(btrim(body)) >= 1) AND (length(btrim(body)) <= 2000)))`

</details>

<details><summary>Índices</summary>

- `USING btree (conversation_id, created_at)` — msg_conversation_idx
- `USING btree (sender_user_id, body_hash, created_at DESC)` — msg_hash_idx
- `USING btree (conversation_id) WHERE ((read_at IS NULL) AND (deleted_at IS NULL))` — msg_unread_idx

</details>

<details><summary>Políticas RLS</summary>

- `msg_insert` (INSERT → girando_app)
- `msg_select` (SELECT → girando_app)
- `msg_update` (UPDATE → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## plans

[PÚBLICO si is_public] Entitlements aplicados por el backend (columnas tipadas). features_display es solo texto de marketing y NO otorga permisos.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _PÚBLICO_ | **PK** |
| `code` | text | sí |  | _PÚBLICO_ |  |
| `name` | text | sí |  | _PÚBLICO_ |  |
| `description` | text | no |  | _PÚBLICO_ |  |
| `audience` | app.plan_audience | sí |  | _PÚBLICO_ |  |
| `price_amount` | numeric(12,2) | sí | 0 | _PÚBLICO_ |  |
| `currency` | app.currency_code | sí | 'ARS'::app.currency_code | _PÚBLICO_ |  |
| `billing_period` | app.billing_period | sí | 'month'::app.billing_period | _PÚBLICO_ |  |
| `max_active_listings` | integer | sí |  | PÚBLICO | Cuentan published + pending. Validado en servidor (409 LIMITE_ALCANZADO) y por trigger. |
| `included_featured_listings` | integer | sí | 0 | _PÚBLICO_ |  |
| `included_promotion_credits` | integer | sí | 0 | _PÚBLICO_ |  |
| `stats_level` | smallint | sí | 0 | PÚBLICO | 0 básicas · 1 por publicación · 2 avanzadas · 3 exportación/API. |
| `includes_verification` | boolean | sí | false | _PÚBLICO_ |  |
| `max_members` | integer | sí | 1 | _PÚBLICO_ |  |
| `search_priority_boost` | boolean | sí | false | _PÚBLICO_ |  |
| `features_display` | text[] | sí | '{}'::text[] | _PÚBLICO_ |  |
| `badge_label` | text | no |  | _PÚBLICO_ |  |
| `is_default_for_audience` | boolean | sí | false | ADMIN | Plan efectivo cuando no hay suscripción que otorgue permisos (Particular = 1 publicación). |
| `is_public` | boolean | sí | true | _PÚBLICO_ |  |
| `is_active` | boolean | sí | true | _PÚBLICO_ |  |
| `sort_order` | smallint | sí | 0 | _PÚBLICO_ |  |
| `mp_preapproval_plan_id` | text | no |  | ADMIN | ID del plan de suscripción en Mercado Pago. PENDIENTE DE INTEGRACIÓN REAL. |
| `created_at` | timestamp with time zone | sí | now() | _PÚBLICO_ |  |
| `updated_at` | timestamp with time zone | sí | now() | _PÚBLICO_ |  |

<details><summary>Restricciones</summary>

- `pl_code`: `CHECK ((code ~ '^[a-z][a-z0-9_-]{2,40}$'::text))`
- `pl_free_period`: `CHECK (((price_amount = (0)::numeric) = (billing_period = 'none'::app.billing_period)))`
- `pl_limits`: `CHECK (((max_active_listings >= 0) AND (included_featured_listings >= 0) AND (included_promotion_credits >= 0) AND (max_members >= 1)))`
- `pl_price`: `CHECK ((price_amount >= (0)::numeric))`
- `pl_stats`: `CHECK (((stats_level >= 0) AND (stats_level <= 3)))`
- `plans_code_key`: `UNIQUE (code)`

</details>

<details><summary>Índices</summary>

- `UNIQUE USING btree (code)` — plans_code_key
- `UNIQUE USING btree (audience) WHERE (is_default_for_audience AND is_active)` — plans_default_uq

</details>

<details><summary>Políticas RLS</summary>

- `pl_admin_i` (INSERT → girando_app)
- `pl_admin_u` (UPDATE → girando_app)
- `pl_read` (SELECT → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## subscriptions

Estado financiero del plan de un usuario o agencia. Determina permisos reales. Escritura: solo worker (webhook) y staff finance.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _PRIVADO_ | **PK** |
| `plan_id` | uuid | sí |  | _PRIVADO_ | FK → app.plans(id) |
| `user_id` | uuid | no |  | _PRIVADO_ | FK → app.users(id) |
| `agency_id` | uuid | no |  | _PRIVADO_ | FK → app.agencies(id) |
| `created_by` | uuid | sí |  | _PRIVADO_ | FK → app.users(id) |
| `provider` | app.payment_provider | sí |  | _PRIVADO_ |  |
| `external_customer_id` | text | no |  | _PRIVADO_ |  |
| `external_subscription_id` | text | no |  | ADMIN | ID de preapproval de Mercado Pago. |
| `status` | app.subscription_status | sí | 'pending'::app.subscription_status | PROPIETARIO | Otorgan el plan: active, payment_failed, grace_period, canceled (hasta current_period_end). |
| `price_amount` | numeric(12,2) | sí |  | PROPIETARIO | Precio congelado al suscribirse: editar el plan no cambia retroactivamente lo pactado. |
| `currency` | app.currency_code | sí |  | _PRIVADO_ |  |
| `billing_period` | app.billing_period | sí |  | _PRIVADO_ |  |
| `started_at` | timestamp with time zone | no |  | _PRIVADO_ |  |
| `current_period_start` | timestamp with time zone | no |  | _PRIVADO_ |  |
| `current_period_end` | timestamp with time zone | no |  | _PRIVADO_ |  |
| `next_renewal_at` | timestamp with time zone | no |  | _PRIVADO_ |  |
| `grace_until` | timestamp with time zone | no |  | _PRIVADO_ |  |
| `cancel_at_period_end` | boolean | sí | false | _PRIVADO_ |  |
| `canceled_at` | timestamp with time zone | no |  | _PRIVADO_ |  |
| `cancel_reason` | text | no |  | _PRIVADO_ |  |
| `ended_at` | timestamp with time zone | no |  | _PRIVADO_ |  |
| `pending_plan_id` | uuid | no |  | PROPIETARIO | FK → app.plans(id) · Cambio de plan esperando pago confirmado. |
| `created_at` | timestamp with time zone | sí | now() | _PRIVADO_ |  |
| `updated_at` | timestamp with time zone | sí | now() | _PRIVADO_ |  |

<details><summary>Restricciones</summary>

- `sub_active_dates`: `CHECK (((status <> ALL (ARRAY['active'::app.subscription_status, 'payment_failed'::app.subscription_status, 'grace_period'::app.subscription_status, 'canceled'::app.subscription_status])) OR ((started_at IS NOT NULL) AND (current_period_end IS NOT NULL))))`
- `sub_canceled`: `CHECK (((status = 'canceled'::app.subscription_status) <= (canceled_at IS NOT NULL)))`
- `sub_expired`: `CHECK (((status = 'expired'::app.subscription_status) <= (ended_at IS NOT NULL)))`
- `sub_grace`: `CHECK (((status = 'grace_period'::app.subscription_status) <= (grace_until IS NOT NULL)))`
- `sub_one_owner`: `CHECK ((num_nonnulls(user_id, agency_id) = 1))`
- `sub_price`: `CHECK ((price_amount >= (0)::numeric))`

</details>

<details><summary>Índices</summary>

- `UNIQUE USING btree (provider, external_subscription_id) WHERE (external_subscription_id IS NOT NULL)` — sub_external_uq
- `UNIQUE USING btree (agency_id) WHERE ((agency_id IS NOT NULL) AND (status = ANY (ARRAY['pending'::app.subscription_status, 'active'::app.subscription_status, 'payment_failed'::app.subscription_status, 'grace_period'::app.subscription_status, 'canceled'::app.subscription_status])))` — sub_one_open_agency_uq
- `UNIQUE USING btree (user_id) WHERE ((user_id IS NOT NULL) AND (status = ANY (ARRAY['pending'::app.subscription_status, 'active'::app.subscription_status, 'payment_failed'::app.subscription_status, 'grace_period'::app.subscription_status, 'canceled'::app.subscription_status])))` — sub_one_open_user_uq
- `USING btree (status, current_period_end)` — sub_renewal_idx

</details>

<details><summary>Políticas RLS</summary>

- `sub_insert` (INSERT → girando_app)
- `sub_select` (SELECT → girando_app)
- `sub_update` (UPDATE → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## payments

Cobros. Mercado Pago: el estado lo fija el webhook tras consultar la API. Transferencia: pending → submitted (usuario avisa) → approved\|rejected (solo staff finance).

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _PRIVADO_ | **PK** |
| `purpose` | app.payment_purpose | sí |  | _PRIVADO_ |  |
| `subscription_id` | uuid | no |  | _PRIVADO_ | FK → app.subscriptions(id) |
| `promotion_id` | uuid | no |  | _PRIVADO_ | FK → app.promotions(id) |
| `verification_id` | uuid | no |  | _PRIVADO_ | FK → app.verifications(id) |
| `payer_user_id` | uuid | sí |  | _PRIVADO_ | FK → app.users(id) |
| `agency_id` | uuid | no |  | _PRIVADO_ | FK → app.agencies(id) |
| `provider` | app.payment_provider | sí |  | _PRIVADO_ |  |
| `method_type` | text | no |  | PROPIETARIO | Tipo informado por MP (credit_card, account_money, ...). Nunca número de tarjeta. |
| `status` | app.payment_status | sí | 'pending'::app.payment_status | _PRIVADO_ |  |
| `status_detail` | text | no |  | _PRIVADO_ |  |
| `amount` | numeric(12,2) | sí |  | _PRIVADO_ |  |
| `currency` | app.currency_code | sí | 'ARS'::app.currency_code | _PRIVADO_ |  |
| `external_reference` | text | sí | (gen_random_uuid())::text | ADMIN | Referencia propia enviada a MP (external_reference) para conciliar. |
| `mp_payment_id` | text | no |  | ADMIN | ID de pago de MP (único). |
| `mp_preference_id` | text | no |  | _PRIVADO_ |  |
| `mp_preapproval_id` | text | no |  | _PRIVADO_ |  |
| `transfer_reference` | text | no |  | PROPIETARIO | Referencia a incluir en la transferencia (GIR-000123), generada por el backend. |
| `transfer_declared_at` | timestamp with time zone | no |  | _PRIVADO_ |  |
| `receipt_document_id` | uuid | no |  | _PRIVADO_ | FK → app.documents(id) |
| `reviewed_by` | uuid | no |  | _PRIVADO_ | FK → app.users(id) |
| `reviewed_at` | timestamp with time zone | no |  | _PRIVADO_ |  |
| `rejection_reason` | text | no |  | _PRIVADO_ |  |
| `paid_at` | timestamp with time zone | no |  | _PRIVADO_ |  |
| `provider_snapshot` | jsonb | no |  | ADMIN | Subconjunto relevante de la respuesta del proveedor (status, status_detail, payment_method_id, date_approved, transaction_amount). Sin datos personales del pagador ni de la tarjeta. |
| `created_at` | timestamp with time zone | sí | now() | _PRIVADO_ |  |
| `updated_at` | timestamp with time zone | sí | now() | _PRIVADO_ |  |

<details><summary>Restricciones</summary>

- `pay_amount`: `CHECK ((amount > (0)::numeric))`
- `pay_no_self_review`: `CHECK (((reviewed_by IS NULL) OR (reviewed_by <> payer_user_id)))`
- `pay_one_purpose`: `CHECK ((num_nonnulls(subscription_id, promotion_id, verification_id) = 1))`
- `pay_paid_at`: `CHECK (((status = 'approved'::app.payment_status) <= (paid_at IS NOT NULL)))`
- `pay_purpose_match`: `CHECK ((((purpose = 'subscription'::app.payment_purpose) = (subscription_id IS NOT NULL)) AND ((purpose = 'promotion'::app.payment_purpose) = (promotion_id IS NOT NULL)) AND ((purpose = 'verification'::app.payment_purpose) = (verification_id IS NOT NULL))))`
- `pay_reject_reason`: `CHECK (((provider <> 'bank_transfer'::app.payment_provider) OR (status <> 'rejected'::app.payment_status) OR (rejection_reason IS NOT NULL)))`
- `pay_snapshot_obj`: `CHECK (((provider_snapshot IS NULL) OR (jsonb_typeof(provider_snapshot) = 'object'::text)))`
- `pay_submitted_only_transfer`: `CHECK (((status <> 'submitted'::app.payment_status) OR (provider = 'bank_transfer'::app.payment_provider)))`
- `pay_transfer_ref`: `CHECK (((provider = 'bank_transfer'::app.payment_provider) = (transfer_reference IS NOT NULL)))`
- `pay_transfer_ref_fmt`: `CHECK (((transfer_reference IS NULL) OR (transfer_reference ~ '^GIR-[0-9]{6,}$'::text)))`
- `pay_transfer_review`: `CHECK (((provider <> 'bank_transfer'::app.payment_provider) OR (status <> ALL (ARRAY['approved'::app.payment_status, 'rejected'::app.payment_status])) OR ((reviewed_by IS NOT NULL) AND (reviewed_at IS NOT NULL))))`

</details>

<details><summary>Índices</summary>

- `USING btree (agency_id, created_at DESC) WHERE (agency_id IS NOT NULL)` — pay_agency_idx
- `UNIQUE USING btree (external_reference)` — pay_external_ref_uq
- `UNIQUE USING btree (mp_payment_id) WHERE (mp_payment_id IS NOT NULL)` — pay_mp_payment_uq
- `USING btree (payer_user_id, created_at DESC)` — pay_payer_idx
- `USING btree (transfer_declared_at) WHERE (status = 'submitted'::app.payment_status)` — pay_review_queue_idx
- `USING btree (status, created_at DESC)` — pay_status_idx
- `USING btree (subscription_id, created_at DESC) WHERE (subscription_id IS NOT NULL)` — pay_subscription_idx
- `UNIQUE USING btree (transfer_reference) WHERE (transfer_reference IS NOT NULL)` — pay_transfer_ref_uq

</details>

<details><summary>Políticas RLS</summary>

- `pay_insert` (INSERT → girando_app)
- `pay_select` (SELECT → girando_app)
- `pay_update` (UPDATE → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## payment_events

[ADMIN] Webhooks recibidos (Mercado Pago: payment, subscription_preapproval, subscription_authorized_payment) y resultado de procesarlos. Idempotencia por idempotency_key.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | bigint | sí |  | _ADMIN_ | **PK** |
| `provider` | app.payment_provider | sí |  | _ADMIN_ |  |
| `topic` | text | sí |  | _ADMIN_ |  |
| `action` | text | no |  | _ADMIN_ |  |
| `resource_id` | text | sí |  | _ADMIN_ |  |
| `request_id` | text | no |  | _ADMIN_ |  |
| `idempotency_key` | text | sí |  | _ADMIN_ |  |
| `signature_valid` | boolean | sí |  | ADMIN | Resultado de validar x-signature (HMAC). Si es false no se procesa. |
| `payment_id` | uuid | no |  | _ADMIN_ | FK → app.payments(id) |
| `subscription_id` | uuid | no |  | _ADMIN_ | FK → app.subscriptions(id) |
| `processing_status` | app.provider_event_status | sí | 'received'::app.provider_event_status | _ADMIN_ |  |
| `error` | text | no |  | _ADMIN_ |  |
| `payload` | jsonb | sí |  | _ADMIN_ |  |
| `resource_snapshot` | jsonb | no |  | ADMIN | Respuesta de GET al recurso en la API del proveedor (la verdad), filtrada. |
| `received_at` | timestamp with time zone | sí | now() | _ADMIN_ |  |
| `processed_at` | timestamp with time zone | no |  | _ADMIN_ |  |

<details><summary>Índices</summary>

- `UNIQUE USING btree (provider, idempotency_key)` — pe_idempotency_uq
- `USING btree (received_at) WHERE (processing_status = ANY (ARRAY['received'::app.provider_event_status, 'failed'::app.provider_event_status]))` — pe_pending_idx
- `USING btree (provider, resource_id)` — pe_resource_idx

</details>

<details><summary>Políticas RLS</summary>

- `pe_select` (SELECT → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## exchange_rates

[PÚBLICO] Reemplaza el USD_RATE=1250 hardcodeado. Fuente a definir (BCRA oficial u otra). PENDIENTE DE INTEGRACIÓN.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | bigint | sí |  | _PÚBLICO_ | **PK** |
| `currency` | app.currency_code | sí |  | _PÚBLICO_ |  |
| `rate_to_ars` | numeric(14,4) | sí |  | _PÚBLICO_ |  |
| `source` | text | sí |  | _PÚBLICO_ |  |
| `valid_on` | date | sí |  | _PÚBLICO_ |  |
| `created_at` | timestamp with time zone | sí | now() | _PÚBLICO_ |  |

<details><summary>Restricciones</summary>

- `fx_not_ars`: `CHECK ((currency <> 'ARS'::app.currency_code))`
- `fx_rate`: `CHECK ((rate_to_ars > (0)::numeric))`
- `exchange_rates_currency_source_valid_on_key`: `UNIQUE (currency, source, valid_on)`

</details>

<details><summary>Índices</summary>

- `UNIQUE USING btree (currency, source, valid_on)` — exchange_rates_currency_source_valid_on_key

</details>

<details><summary>Políticas RLS</summary>

- `fx_read` (SELECT → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## promotion_products

[PÚBLICO si activo] Publicación destacada, Posición promocionada, Agencia destacada, Banner. Precio y duración editables por el admin.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _PÚBLICO_ | **PK** |
| `code` | text | sí |  | _PÚBLICO_ |  |
| `name` | text | sí |  | _PÚBLICO_ |  |
| `description` | text | sí |  | _PÚBLICO_ |  |
| `type` | app.promotion_type | sí |  | _PÚBLICO_ |  |
| `placement` | app.promotion_placement | sí |  | _PÚBLICO_ |  |
| `price_amount` | numeric(12,2) | sí |  | _PÚBLICO_ |  |
| `currency` | app.currency_code | sí | 'ARS'::app.currency_code | _PÚBLICO_ |  |
| `duration_days` | smallint | sí |  | _PÚBLICO_ |  |
| `is_active` | boolean | sí | true | _PÚBLICO_ |  |
| `created_at` | timestamp with time zone | sí | now() | _PÚBLICO_ |  |
| `updated_at` | timestamp with time zone | sí | now() | _PÚBLICO_ |  |

<details><summary>Restricciones</summary>

- `pp_days`: `CHECK (((duration_days >= 1) AND (duration_days <= 365)))`
- `pp_price`: `CHECK ((price_amount >= (0)::numeric))`
- `promotion_products_code_key`: `UNIQUE (code)`

</details>

<details><summary>Índices</summary>

- `UNIQUE USING btree (code)` — promotion_products_code_key

</details>

<details><summary>Políticas RLS</summary>

- `pp_admin_i` (INSERT → girando_app)
- `pp_admin_u` (UPDATE → girando_app)
- `pp_read` (SELECT → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## promotions

Exposición pagada, SIEMPRE rotulada (disclosure_label). Se muestra en bloque aparte; nunca altera el orden orgánico.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _PRIVADO_ | **PK** |
| `product_id` | uuid | no |  | _PRIVADO_ | FK → app.promotion_products(id) |
| `type` | app.promotion_type | sí |  | _PRIVADO_ |  |
| `placement` | app.promotion_placement | sí |  | _PRIVADO_ |  |
| `listing_id` | uuid | no |  | _PRIVADO_ | FK → app.listings(id) |
| `target_agency_id` | uuid | no |  | _PRIVADO_ | FK → app.agencies(id) |
| `advertiser_name` | text | no |  | PÚBLICO | Para banners de anunciantes que no publican en Girando. Solo material propio, provisto o con licencia. |
| `creative_public_id` | text | no |  | _PRIVADO_ |  |
| `link_url` | text | no |  | _PRIVADO_ |  |
| `purchased_by` | uuid | no |  | _PRIVADO_ | FK → app.users(id) |
| `paying_agency_id` | uuid | no |  | _PRIVADO_ | FK → app.agencies(id) |
| `price_amount` | numeric(12,2) | sí |  | _PRIVADO_ |  |
| `currency` | app.currency_code | sí | 'ARS'::app.currency_code | _PRIVADO_ |  |
| `starts_at` | timestamp with time zone | sí |  | _PRIVADO_ |  |
| `ends_at` | timestamp with time zone | sí |  | _PRIVADO_ |  |
| `status` | app.promotion_status | sí | 'pending'::app.promotion_status | _PRIVADO_ |  |
| `priority` | smallint | sí | 0 | ADMIN | Orden entre promociones del mismo placement. |
| `target_brand_id` | uuid | no |  | _PRIVADO_ | FK → app.vehicle_brands(id) |
| `target_model_id` | uuid | no |  | _PRIVADO_ | FK → app.vehicle_models(id) |
| `target_geo_area_id` | uuid | no |  | _PRIVADO_ | FK → app.geo_areas(id) |
| `disclosure_label` | text | sí | 'Patrocinado'::text | _PRIVADO_ |  |
| `status_reason` | text | no |  | _PRIVADO_ |  |
| `approved_by` | uuid | no |  | _PRIVADO_ | FK → app.users(id) |
| `approved_at` | timestamp with time zone | no |  | _PRIVADO_ |  |
| `created_at` | timestamp with time zone | sí | now() | _PRIVADO_ |  |
| `updated_at` | timestamp with time zone | sí | now() | _PRIVADO_ |  |

<details><summary>Restricciones</summary>

- `pr_active_approved`: `CHECK (((status <> ALL (ARRAY['active'::app.promotion_status, 'paused'::app.promotion_status, 'finished'::app.promotion_status])) OR (approved_at IS NOT NULL)))`
- `pr_active_needs_creative`: `CHECK (((status <> 'active'::app.promotion_status) OR (type <> 'banner_campaign'::app.promotion_type) OR (creative_public_id IS NOT NULL)))`
- `pr_dates`: `CHECK ((ends_at > starts_at))`
- `pr_label`: `CHECK ((disclosure_label = ANY (ARRAY['Patrocinado'::text, 'Publicidad'::text])))`
- `pr_link`: `CHECK (((link_url IS NULL) OR (link_url ~* '^https://\S+$'::text)))`
- `pr_price`: `CHECK ((price_amount >= (0)::numeric))`
- `pr_target`: `CHECK ((((type = ANY (ARRAY['featured_listing'::app.promotion_type, 'promoted_position'::app.promotion_type])) AND (listing_id IS NOT NULL) AND (target_agency_id IS NULL) AND (advertiser_name IS NULL)) OR ((type = 'featured_agency'::app.promotion_type) AND (target_agency_id IS NOT NULL) AND (listing_id IS NULL)) OR ((type = 'banner_campaign'::app.promotion_type) AND (advertiser_name IS NOT NULL) AND (link_url IS NOT NULL) AND (listing_id IS NULL))))`

</details>

<details><summary>Índices</summary>

- `USING btree (placement, priority DESC, starts_at) WHERE (status = 'active'::app.promotion_status)` — pr_active_idx
- `USING btree (target_agency_id) WHERE (target_agency_id IS NOT NULL)` — pr_agency_idx
- `USING btree (purchased_by, created_at DESC)` — pr_buyer_idx
- `USING btree (listing_id) WHERE (listing_id IS NOT NULL)` — pr_listing_idx
- `USING btree (ends_at) WHERE (status = ANY (ARRAY['active'::app.promotion_status, 'paused'::app.promotion_status]))` — pr_schedule_idx

</details>

<details><summary>Políticas RLS</summary>

- `pr_insert` (INSERT → girando_app)
- `pr_select` (SELECT → girando_app)
- `pr_update` (UPDATE → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## promotion_events

[PROPIETARIO] Ciclo de vida de la promoción (creada, aprobada, pausada, finalizada, pago). Las MÉTRICAS (impresiones, vistas, clics, favoritos, contactos) salen de analytics_events con promotion_id — no se duplican acá.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | bigint | sí |  | _PROPIETARIO_ | **PK** |
| `promotion_id` | uuid | sí |  | _PROPIETARIO_ | FK → app.promotions(id) |
| `event` | app.promotion_event_type | sí |  | _PROPIETARIO_ |  |
| `from_status` | app.promotion_status | no |  | _PROPIETARIO_ |  |
| `to_status` | app.promotion_status | no |  | _PROPIETARIO_ |  |
| `actor_user_id` | uuid | no |  | _PROPIETARIO_ | FK → app.users(id) |
| `actor_type` | app.actor_type | sí |  | _PROPIETARIO_ |  |
| `reason` | text | no |  | _PROPIETARIO_ |  |
| `created_at` | timestamp with time zone | sí | now() | _PROPIETARIO_ |  |

<details><summary>Índices</summary>

- `USING btree (promotion_id, created_at)` — pev_promotion_idx

</details>

<details><summary>Políticas RLS</summary>

- `pev_insert` (INSERT → girando_app)
- `pev_select` (SELECT → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## sales

Venta histórica. Sobrevive a la eliminación de fotos, a la anonimización de la publicación y a la baja de la cuenta. No guarda datos personales del comprador.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _PRIVADO_ | **PK** |
| `public_code` | text | sí | app.gen_public_code('V'::text) | _PRIVADO_ |  |
| `listing_id` | uuid | sí |  | _PRIVADO_ | FK → app.listings(id) |
| `vehicle_id` | uuid | sí |  | _PRIVADO_ | FK → app.vehicles(id) |
| `seller_user_id` | uuid | sí |  | _PRIVADO_ | FK → app.users(id) |
| `agency_id` | uuid | no |  | _PRIVADO_ | FK → app.agencies(id) |
| `reported_by` | uuid | sí |  | _PRIVADO_ | FK → app.users(id) |
| `sold_on` | date | sí |  | _PRIVADO_ |  |
| `final_price` | numeric(14,2) | sí |  | _PRIVADO_ | [PROPIETARIO; PÚBLICO solo agregado con n≥3] Precio final declarado por el vendedor. |
| `currency` | app.currency_code | sí |  | _PRIVADO_ |  |
| `fx_rate_to_ars` | numeric(14,4) | no |  | SISTEMA | Cotización congelada a la fecha de venta (solo USD) para estadísticas en ARS. |
| `is_financed` | boolean | sí | false | _PRIVADO_ |  |
| `financing_type` | app.financing_type | no |  | _PRIVADO_ |  |
| `financed_amount` | numeric(14,2) | no |  | _PRIVADO_ |  |
| `installments` | smallint | no |  | _PRIVADO_ |  |
| `channel` | app.sale_channel | sí |  | PROPIETARIO | girando / buyer_from_girando / other_channel. |
| `attributed_to_girando` | boolean | no |  | PROPIETARIO | generada · Derivado del canal (columna generada, no editable). |
| `buyer_conversation_id` | uuid | no |  | PRIVADO | FK → app.conversations(id) · Evidencia opcional de atribución (conversación con el comprador). No se copia ningún dato del comprador. |
| `notes` | text | no |  | PROPIETARIO | Observaciones privadas. |
| `status` | app.sale_status | sí | 'reported'::app.sale_status | ADMIN | voided = anulada por soporte (error del vendedor); no se borra. |
| `voided_reason` | text | no |  | _PRIVADO_ |  |
| `created_at` | timestamp with time zone | sí | now() | _PRIVADO_ |  |
| `updated_at` | timestamp with time zone | sí | now() | _PRIVADO_ |  |

<details><summary>Restricciones</summary>

- `sa_fin_amount`: `CHECK (((financed_amount IS NULL) OR ((financed_amount > (0)::numeric) AND (financed_amount <= final_price))))`
- `sa_financing`: `CHECK ((is_financed OR ((financing_type IS NULL) AND (financed_amount IS NULL) AND (installments IS NULL))))`
- `sa_financing_type`: `CHECK (((NOT is_financed) OR (financing_type IS NOT NULL)))`
- `sa_fx`: `CHECK (((currency = 'ARS'::app.currency_code) = (fx_rate_to_ars IS NULL)))`
- `sa_installments`: `CHECK (((installments IS NULL) OR ((installments >= 1) AND (installments <= 120))))`
- `sa_notes`: `CHECK (((notes IS NULL) OR (length(notes) <= 1000)))`
- `sa_price`: `CHECK (((final_price > (0)::numeric) AND (final_price < ('100000000000'::bigint)::numeric)))`
- `sa_sold_on`: `CHECK ((sold_on >= '2025-01-01'::date))`
- `sa_voided`: `CHECK (((status = 'voided'::app.sale_status) = (voided_reason IS NOT NULL)))`

</details>

<details><summary>Índices</summary>

- `USING btree (agency_id, sold_on DESC) WHERE (agency_id IS NOT NULL)` — sales_agency_idx
- `UNIQUE USING btree (public_code)` — sales_code_uq
- `USING btree (sold_on) WHERE (status = 'reported'::app.sale_status)` — sales_date_idx
- `UNIQUE USING btree (listing_id) WHERE (status = 'reported'::app.sale_status)` — sales_listing_uq
- `USING btree (seller_user_id, sold_on DESC)` — sales_seller_idx

</details>

<details><summary>Políticas RLS</summary>

- `sa_insert` (INSERT → girando_app)
- `sa_select` (SELECT → girando_app)
- `sa_update` (UPDATE → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## email_templates

[ADMIN] Plantillas versionadas (bienvenida, verificar email, recuperar contraseña, publicación aprobada/rechazada, nueva consulta, pago aprobado/rechazado, suscripción renovada/cancelada, verificación aprobada...).

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _ADMIN_ | **PK** |
| `code` | text | sí |  | _ADMIN_ |  |
| `version` | integer | sí | 1 | _ADMIN_ |  |
| `locale` | text | sí | 'es-AR'::text | _ADMIN_ |  |
| `subject` | text | sí |  | _ADMIN_ |  |
| `body_html` | text | sí |  | _ADMIN_ |  |
| `body_text` | text | sí |  | _ADMIN_ |  |
| `variables` | text[] | sí | '{}'::text[] | _ADMIN_ |  |
| `is_commercial` | boolean | sí | false | _ADMIN_ |  |
| `status` | app.template_status | sí | 'draft'::app.template_status | _ADMIN_ |  |
| `updated_by` | uuid | no |  | _ADMIN_ | FK → app.users(id) |
| `created_at` | timestamp with time zone | sí | now() | _ADMIN_ |  |
| `updated_at` | timestamp with time zone | sí | now() | _ADMIN_ |  |

<details><summary>Restricciones</summary>

- `et_code`: `CHECK ((code ~ '^[a-z][a-z0-9_.]{2,60}$'::text))`
- `email_templates_code_locale_version_key`: `UNIQUE (code, locale, version)`

</details>

<details><summary>Índices</summary>

- `UNIQUE USING btree (code, locale, version)` — email_templates_code_locale_version_key
- `UNIQUE USING btree (code, locale) WHERE (status = 'active'::app.template_status)` — et_one_active_uq

</details>

<details><summary>Políticas RLS</summary>

- `et_admin_i` (INSERT → girando_app)
- `et_admin_u` (UPDATE → girando_app)
- `et_staff` (SELECT → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## notification_types

[ADMIN] Catálogo de eventos notificables y sus canales (panel Admin → Notificaciones). Operativas (seguridad, pagos, moderación) son obligatorias; comerciales requieren consentimiento.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `code` | text | sí |  | _ADMIN_ | **PK** |
| `category` | app.notification_category | sí |  | _ADMIN_ |  |
| `description` | text | sí |  | _ADMIN_ |  |
| `is_commercial` | boolean | sí | false | _ADMIN_ |  |
| `is_mandatory` | boolean | sí | false | _ADMIN_ |  |
| `in_app_enabled` | boolean | sí | true | _ADMIN_ |  |
| `email_enabled` | boolean | sí | false | _ADMIN_ |  |
| `push_enabled` | boolean | sí | false | _ADMIN_ |  |
| `email_template_code` | text | no |  | _ADMIN_ |  |
| `is_active` | boolean | sí | true | _ADMIN_ |  |
| `updated_by` | uuid | no |  | _ADMIN_ | FK → app.users(id) |
| `updated_at` | timestamp with time zone | sí | now() | _ADMIN_ |  |

<details><summary>Restricciones</summary>

- `nt_code`: `CHECK ((code ~ '^[a-z][a-z0-9_]*\.[a-z0-9_.]+$'::text))`
- `nt_email_template`: `CHECK (((NOT email_enabled) OR (email_template_code IS NOT NULL)))`
- `nt_mandatory_not_commercial`: `CHECK ((NOT (is_mandatory AND is_commercial)))`

</details>

<details><summary>Políticas RLS</summary>

- `nt_admin` (UPDATE → girando_app)
- `nt_read` (SELECT → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## notification_preferences

[PROPIETARIO] Preferencias por categoría/canal. Ausencia de fila = default del tipo. Categorías security/payments/moderation no se pueden apagar (lo valida el backend). marketing además requiere consents vigente.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `user_id` | uuid | sí |  | _PROPIETARIO_ | **PK** · FK → app.users(id) ON DELETE CASCADE |
| `category` | app.notification_category | sí |  | _PROPIETARIO_ | **PK** |
| `channel` | app.notification_channel | sí |  | _PROPIETARIO_ | **PK** |
| `enabled` | boolean | sí |  | _PROPIETARIO_ |  |
| `updated_at` | timestamp with time zone | sí | now() | _PROPIETARIO_ |  |

<details><summary>Políticas RLS</summary>

- `np_own` (ALL → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## notifications

[PROPIETARIO] Bandeja in-app. entity_type/entity_id es una referencia de navegación (no FK) porque la notificación debe sobrevivir aunque la entidad se anonimice.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _PROPIETARIO_ | **PK** |
| `user_id` | uuid | sí |  | _PROPIETARIO_ | FK → app.users(id) ON DELETE CASCADE |
| `type_code` | text | sí |  | _PROPIETARIO_ | FK → app.notification_types(code) |
| `category` | app.notification_category | sí |  | _PROPIETARIO_ |  |
| `title` | text | sí |  | _PROPIETARIO_ |  |
| `body` | text | sí |  | _PROPIETARIO_ |  |
| `entity_type` | text | no |  | _PROPIETARIO_ |  |
| `entity_id` | uuid | no |  | _PROPIETARIO_ |  |
| `action_path` | text | no |  | _PROPIETARIO_ |  |
| `read_at` | timestamp with time zone | no |  | _PROPIETARIO_ |  |
| `created_at` | timestamp with time zone | sí | now() | _PROPIETARIO_ |  |

<details><summary>Restricciones</summary>

- `nf_body`: `CHECK ((length(body) <= 500))`
- `nf_entity_pair`: `CHECK (((entity_type IS NULL) = (entity_id IS NULL)))`
- `nf_entity_type`: `CHECK (((entity_type IS NULL) OR (entity_type = ANY (ARRAY['listing'::text, 'conversation'::text, 'subscription'::text, 'payment'::text, 'verification'::text, 'agency'::text, 'sale'::text, 'promotion'::text, 'saved_search'::text, 'report'::text, 'user'::text]))))`
- `nf_path`: `CHECK (((action_path IS NULL) OR (action_path ~ '^/[A-Za-z0-9/_?=&.-]*$'::text)))`
- `nf_title`: `CHECK ((length(title) <= 120))`

</details>

<details><summary>Índices</summary>

- `USING btree (user_id) WHERE (read_at IS NULL)` — nf_unread_idx
- `USING btree (user_id, created_at DESC)` — nf_user_idx

</details>

<details><summary>Políticas RLS</summary>

- `nf_own` (SELECT → girando_app)
- `nf_read` (UPDATE → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## email_events

[ADMIN] Cola/registro de emails. "sent" exige provider_message_id (confirmación real del proveedor). PROVEEDOR PENDIENTE DE CONFIGURAR.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | uuid | sí | gen_random_uuid() | _ADMIN_ | **PK** |
| `template_id` | uuid | sí |  | _ADMIN_ | FK → app.email_templates(id) |
| `notification_id` | uuid | no |  | _ADMIN_ | FK → app.notifications(id) ON DELETE SET NULL |
| `to_user_id` | uuid | no |  | _ADMIN_ | FK → app.users(id) ON DELETE SET NULL |
| `to_email` | citext | sí |  | PRIVADO | Destinatario al momento del envío. Retención: operativos. |
| `event_code` | text | sí |  | _ADMIN_ |  |
| `variables` | jsonb | sí | '{}'::jsonb | PRIVADO | Variables de la plantilla. No incluir datos sensibles (DNI, documentos, identificadores del vehículo). |
| `status` | app.email_status | sí | 'pending'::app.email_status | _ADMIN_ |  |
| `provider` | text | no |  | _ADMIN_ |  |
| `provider_message_id` | text | no |  | _ADMIN_ |  |
| `attempts` | smallint | sí | 0 | _ADMIN_ |  |
| `last_error` | text | no |  | _ADMIN_ |  |
| `scheduled_at` | timestamp with time zone | sí | now() | _ADMIN_ |  |
| `sent_at` | timestamp with time zone | no |  | _ADMIN_ |  |
| `created_at` | timestamp with time zone | sí | now() | _ADMIN_ |  |
| `updated_at` | timestamp with time zone | sí | now() | _ADMIN_ |  |

<details><summary>Restricciones</summary>

- `ee_failed`: `CHECK (((status <> 'failed'::app.email_status) OR (last_error IS NOT NULL)))`
- `ee_sent`: `CHECK (((status = 'sent'::app.email_status) = ((sent_at IS NOT NULL) AND (provider_message_id IS NOT NULL))))`
- `ee_vars`: `CHECK ((jsonb_typeof(variables) = 'object'::text))`

</details>

<details><summary>Índices</summary>

- `UNIQUE USING btree (provider, provider_message_id) WHERE (provider_message_id IS NOT NULL)` — ee_provider_msg_uq
- `USING btree (scheduled_at) WHERE (status = 'pending'::app.email_status)` — ee_queue_idx
- `USING btree (to_user_id, created_at DESC)` — ee_user_idx

</details>

<details><summary>Políticas RLS</summary>

- `ee_staff` (SELECT → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## audit_logs

[ADMIN] Registro inmutable: quién, rol, acción, entidad, antes/después (solo campos cambiados, con datos sensibles redactados), IP, user agent, motivo. Retención 10 años.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | bigint | sí |  | _ADMIN_ | **PK** |
| `occurred_at` | timestamp with time zone | sí | now() | _ADMIN_ |  |
| `actor_type` | app.actor_type | sí |  | _ADMIN_ |  |
| `actor_user_id` | uuid | no |  | _ADMIN_ | FK → app.users(id) |
| `actor_role` | text | no |  | _ADMIN_ |  |
| `action` | text | sí |  | _ADMIN_ |  |
| `entity_type` | text | sí |  | _ADMIN_ |  |
| `entity_id` | uuid | no |  | _ADMIN_ |  |
| `before_data` | jsonb | no |  | ADMIN | Solo columnas modificadas. DNI, documentos, identificadores y tokens se guardan como "[REDACTED]". |
| `after_data` | jsonb | no |  | _ADMIN_ |  |
| `reason` | text | no |  | _ADMIN_ |  |
| `ip` | inet | no |  | _ADMIN_ |  |
| `user_agent` | text | no |  | _ADMIN_ |  |
| `request_id` | text | no |  | _ADMIN_ |  |

<details><summary>Restricciones</summary>

- `al_action`: `CHECK ((action ~ '^[a-z_]+\.[a-z_]+$'::text))`
- `al_actor`: `CHECK (((actor_type = ANY (ARRAY['system'::app.actor_type, 'provider'::app.actor_type])) OR (actor_user_id IS NOT NULL)))`

</details>

<details><summary>Índices</summary>

- `USING btree (actor_user_id, occurred_at DESC) WHERE (actor_user_id IS NOT NULL)` — al_actor_idx
- `USING btree (entity_type, entity_id, occurred_at DESC)` — al_entity_idx
- `USING brin (occurred_at)` — al_time_brin

</details>

<details><summary>Políticas RLS</summary>

- `al_insert` (INSERT → girando_app)
- `al_staff` (SELECT → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## analytics_events

[ADMIN] Eventos de producto. Sin FKs (volumen y retención independientes). Si el visitante no aceptó analítica, anonymous_id/session_id van NULL y solo se cuentan eventos agregables (vistas, contactos) para las estadísticas del vendedor.

_RLS activo · particionada por mes_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `id` | bigint | sí |  | _ADMIN_ | **PK** |
| `occurred_at` | timestamp with time zone | sí | now() | _ADMIN_ | **PK** |
| `event_name` | app.analytics_event_name | sí |  | _ADMIN_ |  |
| `user_id` | uuid | no |  | _ADMIN_ |  |
| `anonymous_id` | uuid | no |  | _ADMIN_ |  |
| `session_id` | uuid | no |  | _ADMIN_ |  |
| `platform` | app.client_platform | no |  | _ADMIN_ |  |
| `listing_id` | uuid | no |  | _ADMIN_ |  |
| `agency_id` | uuid | no |  | _ADMIN_ |  |
| `promotion_id` | uuid | no |  | _ADMIN_ |  |
| `geo_area_id` | uuid | no |  | _ADMIN_ |  |
| `properties` | jsonb | sí | '{}'::jsonb | ADMIN | Contexto del evento (filtros aplicados, placement, origen). Nunca PII. |
| `consent_analytics` | boolean | sí | false | _ADMIN_ |  |

<details><summary>Restricciones</summary>

- `ae_props`: `CHECK ((jsonb_typeof(properties) = 'object'::text))`

</details>

<details><summary>Índices</summary>

- `CREATE INDEX ae_listing_idx ON ONLY app.analytics_events USING btree (listing_id, event_name, occurred_at) WHERE (listing_id IS NOT NULL)` — ae_listing_idx
- `CREATE INDEX ae_name_time_idx ON ONLY app.analytics_events USING btree (event_name, occurred_at)` — ae_name_time_idx
- `CREATE INDEX ae_promotion_idx ON ONLY app.analytics_events USING btree (promotion_id, event_name, occurred_at) WHERE (promotion_id IS NOT NULL)` — ae_promotion_idx
- `CREATE INDEX ae_time_brin ON ONLY app.analytics_events USING brin (occurred_at)` — ae_time_brin

</details>

<details><summary>Políticas RLS</summary>

- `ae_insert` (INSERT → girando_app)
- `ae_staff` (SELECT → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## listing_stats_daily

[PROPIETARIO] Métricas por publicación y día. Dato DERIVADO (lo escribe un job idempotente); se puede recalcular desde analytics_events. Existe solo por performance del panel del vendedor.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `listing_id` | uuid | sí |  | _PROPIETARIO_ | **PK** · FK → app.listings(id) |
| `day` | date | sí |  | _PROPIETARIO_ | **PK** |
| `impressions` | integer | sí | 0 | _PROPIETARIO_ |  |
| `views` | integer | sí | 0 | _PROPIETARIO_ |  |
| `favorites` | integer | sí | 0 | _PROPIETARIO_ |  |
| `unfavorites` | integer | sí | 0 | _PROPIETARIO_ |  |
| `contacts` | integer | sí | 0 | _PROPIETARIO_ |  |
| `contact_reveals` | integer | sí | 0 | _PROPIETARIO_ |  |
| `shares` | integer | sí | 0 | _PROPIETARIO_ |  |
| `promotion_clicks` | integer | sí | 0 | _PROPIETARIO_ |  |

<details><summary>Índices</summary>

- `USING btree (day)` — lsd_day_idx

</details>

<details><summary>Políticas RLS</summary>

- `lsd_select` (SELECT → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## app_settings

[ADMIN] Parámetros: duración de publicación, aviso de vencimiento, máx. fotos, límites anti-spam, muestra mínima para promedios, días de gracia, datos bancarios para transferencias. is_public=true se expone al frontend.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `key` | text | sí |  | _ADMIN_ | **PK** |
| `value` | jsonb | sí |  | _ADMIN_ |  |
| `description` | text | sí |  | _ADMIN_ |  |
| `is_public` | boolean | sí | false | _ADMIN_ |  |
| `updated_by` | uuid | no |  | _ADMIN_ | FK → app.users(id) |
| `updated_at` | timestamp with time zone | sí | now() | _ADMIN_ |  |

<details><summary>Restricciones</summary>

- `as_key`: `CHECK ((key ~ '^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$'::text))`

</details>

<details><summary>Políticas RLS</summary>

- `as_admin_i` (INSERT → girando_app)
- `as_admin_u` (UPDATE → girando_app)
- `as_read` (SELECT → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## retention_policies

[ADMIN] Política de retención configurable. approved_for_production=false hasta revisión legal (Ley 25.326). Borrar multimedia u operativos nunca toca auditoría ni ventas.

_RLS activo_

| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |
|---|---|---|---|---|---|
| `code` | text | sí |  | _ADMIN_ | **PK** |
| `label` | text | sí |  | _ADMIN_ |  |
| `category` | app.retention_category | sí |  | _ADMIN_ |  |
| `duration` | interval | sí |  | _ADMIN_ |  |
| `starts_from` | text | sí |  | _ADMIN_ |  |
| `action` | app.retention_action | sí |  | _ADMIN_ |  |
| `is_active` | boolean | sí | true | _ADMIN_ |  |
| `approved_for_production` | boolean | sí | false | _ADMIN_ |  |
| `updated_by` | uuid | no |  | _ADMIN_ | FK → app.users(id) |
| `updated_at` | timestamp with time zone | sí | now() | _ADMIN_ |  |

<details><summary>Restricciones</summary>

- `rp_audit_min`: `CHECK (((category <> 'audit'::app.retention_category) OR (duration >= '5 years'::interval)))`

</details>

<details><summary>Políticas RLS</summary>

- `rpol_admin` (UPDATE → girando_app)
- `rpol_read` (SELECT → girando_app)
- `worker_all` (ALL → girando_worker)

</details>

---

## Enums

| Enum | Valores |
|---|---|
| `actor_type` | `user`, `staff`, `system`, `provider` |
| `agency_kind` | `agency`, `official_dealer` |
| `agency_member_role` | `owner`, `admin`, `seller` |
| `agency_status` | `pending`, `review`, `verified`, `rejected`, `suspended`, `revoked` |
| `analytics_event_name` | `page_view`, `search`, `filter_applied`, `listing_impression`, `listing_view`, `listing_favorite`, `listing_unfavorite`, `listing_contact`, `listing_contact_reveal`, `listing_share`, `listing_application`, `listing_created`, `listing_published`, `listing_sold`, `promotion_impression`, `promotion_view`, `promotion_click`, `agency_view` |
| `auth_token_purpose` | `email_verification`, `password_reset`, `phone_verification`, `email_change` |
| `billing_period` | `none`, `month`, `year` |
| `body_type` | `sedan`, `hatchback`, `suv`, `pickup`, `coupe`, `convertible`, `wagon`, `van`, `minivan`, `chassis`, `motorcycle`, `other` |
| `catalog_request_status` | `pending`, `added`, `rejected` |
| `catalog_status` | `active`, `inactive` |
| `client_platform` | `web`, `ios`, `android`, `admin`, `api` |
| `consent_state` | `granted`, `revoked` |
| `consent_type` | `terms`, `privacy_policy`, `cookies`, `marketing_communications` |
| `contact_source` | `user_profile`, `agency`, `custom` |
| `conversation_status` | `open`, `closed`, `blocked` |
| `currency_code` | `ARS`, `USD` |
| `document_status` | `uploaded`, `in_review`, `approved`, `rejected`, `expired`, `deleted` |
| `document_type` | `dni_front`, `dni_back`, `cuit`, `cuit_certificate`, `green_card`, `blue_card`, `title`, `domain_report`, `agency_license`, `agency_other`, `proof_of_address`, `payment_receipt`, `other` |
| `email_status` | `pending`, `sent`, `failed` |
| `engine_aspiration` | `natural`, `turbo`, `supercharged`, `electric` |
| `financing_type` | `bank_loan`, `pledge_loan`, `dealer_financing`, `savings_plan`, `other` |
| `fuel_type` | `gasoline`, `diesel`, `cng`, `gasoline_cng`, `hybrid`, `plugin_hybrid`, `electric`, `other` |
| `geo_level` | `country`, `province`, `department`, `locality` |
| `identifier_status` | `declared`, `pending`, `verified`, `rejected` |
| `identifier_type` | `plate`, `vin`, `chassis_number`, `engine_number` |
| `image_kind` | `front`, `rear`, `left`, `right`, `interior`, `additional` |
| `image_status` | `uploading`, `active`, `replaced`, `deleted`, `purge_scheduled`, `purged` |
| `listing_status` | `draft`, `pending`, `published`, `paused`, `requires_changes`, `rejected`, `sold`, `expired`, `deleted` |
| `member_status` | `invited`, `active`, `removed` |
| `message_visibility` | `visible`, `hidden_by_moderation` |
| `moderation_action_type` | `listing_approve`, `listing_request_changes`, `listing_pause`, `listing_reactivate`, `listing_reject`, `listing_delete`, `user_suspend`, `user_block`, `user_reactivate`, `agency_verify`, `agency_reject`, `agency_suspend`, `agency_reactivate`, `agency_revoke`, `verification_approve`, `verification_reject`, `verification_revoke`, `message_hide`, `review_hide`, `review_restore`, `report_dismiss`, `report_resolve` |
| `notification_category` | `security`, `account`, `listing`, `messages`, `favorites`, `applications`, `payments`, `subscriptions`, `verifications`, `moderation`, `marketing` |
| `notification_channel` | `in_app`, `email`, `push` |
| `participant_side` | `buyer`, `seller` |
| `payment_provider` | `mercadopago`, `bank_transfer`, `manual` |
| `payment_purpose` | `subscription`, `promotion`, `verification` |
| `payment_status` | `pending`, `submitted`, `in_process`, `approved`, `rejected`, `canceled`, `refunded`, `charged_back` |
| `plan_audience` | `particular`, `agency` |
| `policy_doc_type` | `terms`, `privacy_policy`, `cookies_policy` |
| `promotion_event_type` | `created`, `submitted`, `approved`, `activated`, `paused`, `resumed`, `finished`, `canceled`, `payment_approved`, `payment_failed` |
| `promotion_placement` | `home_featured`, `home_banner`, `search_top`, `search_brand_model`, `agency_directory` |
| `promotion_status` | `pending`, `active`, `paused`, `finished`, `canceled` |
| `promotion_type` | `featured_listing`, `promoted_position`, `featured_agency`, `banner_campaign` |
| `provider_event_status` | `received`, `processed`, `ignored`, `failed` |
| `report_status` | `pending`, `reviewing`, `resolved`, `rejected` |
| `report_target` | `listing`, `user`, `agency`, `message`, `review` |
| `retention_action` | `delete`, `anonymize`, `aggregate_then_delete`, `keep` |
| `retention_category` | `media`, `operational`, `historical`, `audit` |
| `review_status` | `published`, `hidden`, `removed` |
| `sale_channel` | `girando`, `buyer_from_girando`, `other_channel` |
| `sale_status` | `reported`, `voided` |
| `session_end_reason` | `logout`, `logout_others`, `password_change`, `admin_revoked`, `expired`, `suspicious` |
| `staff_role` | `superadmin`, `admin`, `moderator`, `finance`, `support`, `catalog_editor` |
| `storage_provider` | `s3`, `r2`, `gcs`, `cloudinary_private` |
| `subscription_status` | `pending`, `active`, `payment_failed`, `grace_period`, `canceled`, `expired` |
| `tax_condition` | `responsable_inscripto`, `monotributo`, `exento` |
| `template_status` | `draft`, `active`, `archived` |
| `traction_type` | `front`, `rear`, `4x2`, `4x4`, `awd` |
| `transmission_type` | `manual`, `automatic`, `cvt`, `automated_manual`, `other` |
| `user_status` | `pending`, `active`, `suspended`, `blocked`, `deleted` |
| `vehicle_condition` | `new`, `used` |
| `vehicle_type` | `car`, `light_truck`, `van`, `truck`, `motorcycle`, `atv`, `other` |
| `verification_kind` | `identity`, `agency`, `documentation`, `vehicle_existence`, `vehicle_data`, `physical_inspection` |
| `verification_product_status` | `draft`, `active`, `inactive` |
| `verification_status` | `pending`, `review`, `approved`, `rejected`, `revoked` |
| `verification_subject` | `user`, `agency`, `vehicle`, `listing` |

## Vistas

| Vista | Descripción |
|---|---|
| `api_public.agencies` | Perfil público de agencias (no suspendidas/revocadas). Reputación Girando y Google en columnas separadas; nunca se combinan. |
| `api_public.catalog_versions` |  |
| `api_public.geo_areas` |  |
| `api_public.listing_contact` |  |
| `api_public.listings` | Publicaciones visibles para cualquiera. El contacto NO está acá: se pide autenticado a api_public.listing_contact. |
| `api_public.plans` |  |
| `api_public.report_reasons` |  |
| `api_public.reviews` |  |
| `api_public.settings` |  |
| `api_public.sponsored` |  |
| `api_public.user_profiles` |  |
| `api_public.verification_products` |  |
| `app.v_catalog_versions` |  |
| `app.v_promotion_metrics` |  |
| `app.v_sales_base` |  |
| `app.v_sales_by_brand_month` |  |
| `app.v_sales_by_model` |  |
| `app.v_sales_by_year` |  |
| `app.v_seller_kpis` |  |
