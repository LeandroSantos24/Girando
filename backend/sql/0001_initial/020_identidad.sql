-- =====================================================================
-- 020 · Identidad: usuarios, datos personales, perfil público, staff,
--       sesiones, tokens, intentos de login, bloqueos, consentimientos.
-- Convención de visibilidad en COMMENT ON COLUMN:
--   [PÚBLICO]     puede salir por api_public
--   [PRIVADO]     titular + staff autorizado (nunca público)
--   [PROPIETARIO] solo el titular (staff solo vía soporte auditado)
--   [ADMIN]       solo staff
--   [SENSIBLE]    dato personal sensible: cifrado o acceso restringido + auditado
--   [SISTEMA]     secreto técnico: nunca sale del backend
-- =====================================================================
SET search_path = app, public;

-- ---------------------------------------------------------------------
-- users: SOLO autenticación y estado de la cuenta
-- ---------------------------------------------------------------------
CREATE TABLE users (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email                 citext NOT NULL,
  phone_e164            text,
  password_hash         text,
  status                user_status NOT NULL DEFAULT 'pending',
  status_reason         text,
  email_verified_at     timestamptz,
  phone_verified_at     timestamptz,
  identity_verified_at  timestamptz,
  failed_login_count    smallint NOT NULL DEFAULT 0,
  locked_until          timestamptz,
  password_changed_at   timestamptz,
  mfa_enabled           boolean NOT NULL DEFAULT false,
  mfa_secret_encrypted  bytea,
  last_login_at         timestamptz,
  deleted_at            timestamptz,
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT users_email_format CHECK (email ~ '^[^@\s]+@[^@\s]+\.[^@\s]{2,}$' AND length(email) <= 254),
  CONSTRAINT users_phone_e164   CHECK (phone_e164 IS NULL OR phone_e164 ~ '^\+[1-9][0-9]{7,14}$'),
  CONSTRAINT users_deleted_consistency CHECK ((status = 'deleted') = (deleted_at IS NOT NULL))
);
COMMENT ON TABLE users IS 'Cuenta de acceso. Solo autenticación y estado. Sin datos personales ni de perfil.';
COMMENT ON COLUMN users.email IS '[PRIVADO] Login. Único (case-insensitive). Se reemplaza por alias anónimo al eliminar la cuenta.';
COMMENT ON COLUMN users.phone_e164 IS '[PRIVADO] Teléfono de la cuenta (recuperación/2FA), E.164. No es el teléfono de contacto de publicaciones.';
COMMENT ON COLUMN users.password_hash IS '[SISTEMA] Argon2id/PBKDF2. NULL si la cuenta usa solo proveedor externo (futuro).';
COMMENT ON COLUMN users.status IS '[ADMIN] pending→active→suspended/blocked→deleted. Solo staff o sistema lo cambian.';
COMMENT ON COLUMN users.status_reason IS '[ADMIN] Motivo del último cambio de estado.';
COMMENT ON COLUMN users.email_verified_at IS '[PRIVADO] Lo setea el sistema al consumir un auth_token email_verification.';
COMMENT ON COLUMN users.phone_verified_at IS '[PRIVADO] Lo setea el sistema al verificar OTP.';
COMMENT ON COLUMN users.identity_verified_at IS '[PÚBLICO como booleano] Caché mantenida SOLO por trigger desde verifications (identity aprobada). Nunca editable por el usuario.';
COMMENT ON COLUMN users.failed_login_count IS '[SISTEMA] Contador para bloqueo temporal.';
COMMENT ON COLUMN users.locked_until IS '[SISTEMA] Bloqueo temporal por intentos fallidos.';
COMMENT ON COLUMN users.mfa_secret_encrypted IS '[SISTEMA] Preparado para 2FA TOTP (cifrado a nivel aplicación). No usado en v1.';
COMMENT ON COLUMN users.last_login_at IS '[PRIVADO] Último acceso exitoso.';

CREATE UNIQUE INDEX users_email_uq ON users (email);
CREATE UNIQUE INDEX users_phone_verified_uq ON users (phone_e164) WHERE phone_verified_at IS NOT NULL;
CREATE INDEX users_status_idx ON users (status) WHERE status <> 'active';
CREATE TRIGGER users_updated BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();

-- ---------------------------------------------------------------------
-- user_personal_data: datos personales (1:1). Nunca públicos.
-- ---------------------------------------------------------------------
CREATE TABLE user_personal_data (
  user_id               uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  first_name            text,
  last_name             text,
  dni_encrypted         bytea,
  dni_hash              bytea,
  dni_last3             char(3),
  birth_date            date,
  home_location_id      uuid,   -- FK agregada en 030 (locations)
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT upd_names_len CHECK (coalesce(length(first_name),0) <= 80 AND coalesce(length(last_name),0) <= 80),
  CONSTRAINT upd_birth_date CHECK (birth_date IS NULL OR birth_date >= DATE '1900-01-01'),  -- edad mínima (18) se valida en backend
  CONSTRAINT upd_dni_pair CHECK ((dni_encrypted IS NULL) = (dni_hash IS NULL))
);
COMMENT ON TABLE user_personal_data IS 'Información personal (1:1 con users). Separada del perfil público y de la autenticación.';
COMMENT ON COLUMN user_personal_data.first_name IS '[PRIVADO] Nombre legal. El nombre visible está en user_profiles.display_name.';
COMMENT ON COLUMN user_personal_data.last_name IS '[PRIVADO] Apellido legal.';
COMMENT ON COLUMN user_personal_data.dni_encrypted IS '[SENSIBLE] DNI cifrado a nivel aplicación (AES-GCM/Fernet, clave fuera de la DB). Validación backend: ^[0-9]{7,8}$.';
COMMENT ON COLUMN user_personal_data.dni_hash IS '[SISTEMA] HMAC-SHA256(DNI, pepper) para detectar duplicados sin descifrar.';
COMMENT ON COLUMN user_personal_data.dni_last3 IS '[PRIVADO] Últimos 3 dígitos para mostrar al titular (***.***.123).';
COMMENT ON COLUMN user_personal_data.birth_date IS '[SENSIBLE] Opcional. Solo si un producto lo requiere (p.ej. verificación de identidad).';
COMMENT ON COLUMN user_personal_data.home_location_id IS '[SENSIBLE] Domicilio exacto (locations). Solo para verificaciones que lo exijan.';
CREATE UNIQUE INDEX upd_dni_hash_uq ON user_personal_data (dni_hash) WHERE dni_hash IS NOT NULL;
CREATE TRIGGER upd_updated BEFORE UPDATE ON user_personal_data FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();

-- ---------------------------------------------------------------------
-- user_profiles: perfil público (1:1)
-- ---------------------------------------------------------------------
CREATE TABLE user_profiles (
  user_id               uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  display_name          text NOT NULL,
  avatar_public_id      text,
  bio                   text,
  geo_area_id           uuid,   -- FK agregada en 030 (geo_areas): ciudad/departamento público
  contact_whatsapp_e164 text,
  contact_phone_e164    text,
  contact_email         citext,
  instagram_url         text,
  tiktok_url            text,
  facebook_url          text,
  x_url                 text,
  youtube_url           text,
  website_url           text,
  is_public             boolean NOT NULL DEFAULT true,
  show_phone_default    boolean NOT NULL DEFAULT false,
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT up_display_name CHECK (length(btrim(display_name)) BETWEEN 2 AND 60),
  CONSTRAINT up_bio_len CHECK (bio IS NULL OR length(bio) <= 500),
  CONSTRAINT up_wa   CHECK (contact_whatsapp_e164 IS NULL OR contact_whatsapp_e164 ~ '^\+[1-9][0-9]{7,14}$'),
  CONSTRAINT up_ph   CHECK (contact_phone_e164 IS NULL OR contact_phone_e164 ~ '^\+[1-9][0-9]{7,14}$'),
  CONSTRAINT up_ig   CHECK (instagram_url IS NULL OR instagram_url ~* '^https://(www\.)?instagram\.com/[A-Za-z0-9_.]{1,30}/?$'),
  CONSTRAINT up_tt   CHECK (tiktok_url IS NULL OR tiktok_url ~* '^https://(www\.)?tiktok\.com/@[A-Za-z0-9_.]{2,24}/?$'),
  CONSTRAINT up_fb   CHECK (facebook_url IS NULL OR facebook_url ~* '^https://(www\.|m\.)?facebook\.com/\S+$'),
  CONSTRAINT up_x    CHECK (x_url IS NULL OR x_url ~* '^https://(www\.)?(x|twitter)\.com/[A-Za-z0-9_]{1,15}/?$'),
  CONSTRAINT up_yt   CHECK (youtube_url IS NULL OR youtube_url ~* '^https://(www\.)?youtube\.com/\S+$'),
  CONSTRAINT up_web  CHECK (website_url IS NULL OR website_url ~* '^https://[^\s/$.?#].[^\s]*$')
);
COMMENT ON TABLE user_profiles IS 'Perfil público del usuario (1:1). Todo lo público de una persona sale de acá y solo si is_public.';
COMMENT ON COLUMN user_profiles.display_name IS '[PÚBLICO] Nombre visible (p.ej. "Juan M."). Independiente del nombre legal.';
COMMENT ON COLUMN user_profiles.avatar_public_id IS '[PÚBLICO] public_id de Cloudinary.';
COMMENT ON COLUMN user_profiles.geo_area_id IS '[PÚBLICO] Ciudad/departamento aproximado. Nunca dirección.';
COMMENT ON COLUMN user_profiles.contact_whatsapp_e164 IS '[PRIVADO] Valor por defecto para listing_contacts. Solo se publica vía listing_contacts con show_whatsapp=true.';
COMMENT ON COLUMN user_profiles.contact_phone_e164 IS '[PRIVADO] Idem teléfono.';
COMMENT ON COLUMN user_profiles.contact_email IS '[PRIVADO] Email de contacto comercial (puede diferir del email de login).';
COMMENT ON COLUMN user_profiles.instagram_url IS '[PÚBLICO] Opcional. Validado por dominio.';
COMMENT ON COLUMN user_profiles.is_public IS '[PROPIETARIO] "Perfil público visible". Si es false, api_public no expone el perfil (las publicaciones muestran solo "Particular").';
COMMENT ON COLUMN user_profiles.show_phone_default IS '[PROPIETARIO] "Mostrar mi teléfono en publicaciones" (default para nuevas publicaciones).';
CREATE TRIGGER up_updated BEFORE UPDATE ON user_profiles FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();

-- ---------------------------------------------------------------------
-- staff_roles: roles administrativos (N:N usuario-rol, con historial)
-- ---------------------------------------------------------------------
CREATE TABLE staff_roles (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      uuid NOT NULL REFERENCES users(id),
  role         staff_role NOT NULL,
  granted_by   uuid REFERENCES users(id),
  granted_at   timestamptz NOT NULL DEFAULT now(),
  revoked_by   uuid REFERENCES users(id),
  revoked_at   timestamptz,
  CONSTRAINT sr_no_self_grant CHECK (granted_by IS NULL OR granted_by <> user_id)
);
COMMENT ON TABLE staff_roles IS '[ADMIN] Roles del panel de administración. Fuente de verdad de permisos de staff (no el JWT).';
CREATE UNIQUE INDEX staff_roles_active_uq ON staff_roles (user_id, role) WHERE revoked_at IS NULL;

CREATE OR REPLACE FUNCTION app.app_has_staff_role(VARIADIC roles staff_role[]) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, public AS $$
  SELECT EXISTS (
    SELECT 1 FROM app.staff_roles s
    JOIN app.users u ON u.id = s.user_id AND u.status = 'active'
    WHERE s.user_id = app.app_current_user_id()
      AND s.revoked_at IS NULL
      AND (s.role = 'superadmin' OR s.role = ANY (roles)))
$$;
CREATE OR REPLACE FUNCTION app.app_is_staff() RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, public AS $$
  SELECT EXISTS (SELECT 1 FROM app.staff_roles s WHERE s.user_id = app.app_current_user_id() AND s.revoked_at IS NULL)
$$;

-- ---------------------------------------------------------------------
-- sessions / auth_tokens / login_attempts
-- ---------------------------------------------------------------------
CREATE TABLE sessions (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id             uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  refresh_token_hash  bytea NOT NULL,
  platform            client_platform NOT NULL,
  device_label        text,
  user_agent          text,
  ip                  inet,
  ip_city             text,
  mfa_passed          boolean NOT NULL DEFAULT false,
  created_at          timestamptz NOT NULL DEFAULT now(),
  last_seen_at        timestamptz NOT NULL DEFAULT now(),
  expires_at          timestamptz NOT NULL,
  ended_at            timestamptz,
  end_reason          session_end_reason,
  CONSTRAINT sessions_end_pair CHECK ((ended_at IS NULL) = (end_reason IS NULL))
);
COMMENT ON TABLE sessions IS '[PROPIETARIO] Sesiones/dispositivos. Permite "cerrar las demás sesiones" revocando en backend.';
COMMENT ON COLUMN sessions.refresh_token_hash IS '[SISTEMA] SHA-256 del refresh token (nunca el token).';
COMMENT ON COLUMN sessions.ip IS '[PRIVADO] Retención: logs técnicos (90 días) — se anonimiza luego.';
CREATE UNIQUE INDEX sessions_token_uq ON sessions (refresh_token_hash);
CREATE INDEX sessions_user_active_idx ON sessions (user_id, last_seen_at DESC) WHERE ended_at IS NULL;

CREATE TABLE auth_tokens (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  purpose      auth_token_purpose NOT NULL,
  token_hash   bytea NOT NULL,
  new_value    text,
  expires_at   timestamptz NOT NULL,
  used_at      timestamptz,
  created_at   timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE auth_tokens IS '[SISTEMA] Tokens de un solo uso (verificar email, recuperar contraseña, OTP teléfono, cambio de email).';
CREATE UNIQUE INDEX auth_tokens_hash_uq ON auth_tokens (token_hash);
CREATE INDEX auth_tokens_user_idx ON auth_tokens (user_id, purpose) WHERE used_at IS NULL;

CREATE TABLE login_attempts (
  id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  email          citext NOT NULL,
  user_id        uuid REFERENCES users(id) ON DELETE SET NULL,
  ip             inet,
  user_agent     text,
  success        boolean NOT NULL,
  failure_reason text,
  created_at     timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE login_attempts IS '[ADMIN] Intentos de login para bloqueo y detección de abuso. Retención corta (logs técnicos).';
CREATE INDEX login_attempts_email_idx ON login_attempts (email, created_at DESC);
CREATE INDEX login_attempts_ip_idx ON login_attempts (ip, created_at DESC);

-- ---------------------------------------------------------------------
-- user_blocks: un usuario bloquea a otro (mensajería)
-- ---------------------------------------------------------------------
CREATE TABLE user_blocks (
  blocker_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  blocked_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  reason          text,
  created_at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (blocker_user_id, blocked_user_id),
  CONSTRAINT ub_not_self CHECK (blocker_user_id <> blocked_user_id)
);
COMMENT ON TABLE user_blocks IS '[PROPIETARIO] Bloqueos entre usuarios. El bloqueado no puede iniciar ni continuar conversaciones.';
CREATE INDEX user_blocks_blocked_idx ON user_blocks (blocked_user_id);

-- ---------------------------------------------------------------------
-- policy_versions + consents (historial, no un booleano)
-- ---------------------------------------------------------------------
CREATE TABLE policy_versions (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  doc_type      policy_doc_type NOT NULL,
  version       text NOT NULL,
  content_url   text NOT NULL,
  content_sha256 bytea NOT NULL,
  published_at  timestamptz NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (doc_type, version)
);
COMMENT ON TABLE policy_versions IS '[PÚBLICO] Versiones de Términos, Privacidad y Cookies. El hash prueba qué texto se aceptó.';

CREATE TABLE consents (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           uuid REFERENCES users(id) ON DELETE SET NULL,
  anonymous_id      uuid,
  consent_type      consent_type NOT NULL,
  policy_version_id uuid NOT NULL REFERENCES policy_versions(id),
  state             consent_state NOT NULL,
  necessary         boolean NOT NULL DEFAULT true,
  preferences       boolean,
  analytics         boolean,
  marketing         boolean,
  channel           client_platform NOT NULL,
  user_agent        text,
  created_at        timestamptz NOT NULL DEFAULT now(),
  superseded_at     timestamptz,
  CONSTRAINT consents_subject CHECK (num_nonnulls(user_id, anonymous_id) >= 1),
  CONSTRAINT consents_necessary CHECK (necessary),
  CONSTRAINT consents_cookie_fields CHECK (
    (consent_type = 'cookies') = (preferences IS NOT NULL AND analytics IS NOT NULL AND marketing IS NOT NULL))
);
COMMENT ON TABLE consents IS '[PROPIETARIO] Registro append-only. Cada cambio inserta una fila nueva y marca superseded_at en la anterior (= fecha de actualización).';
COMMENT ON COLUMN consents.anonymous_id IS '[PRIVADO] ID de dispositivo para visitantes sin cuenta (cookie de primera parte). Se vincula a user_id al registrarse.';
CREATE UNIQUE INDEX consents_current_user_uq ON consents (user_id, consent_type) WHERE superseded_at IS NULL AND user_id IS NOT NULL;
CREATE UNIQUE INDEX consents_current_anon_uq ON consents (anonymous_id, consent_type) WHERE superseded_at IS NULL AND user_id IS NULL;
