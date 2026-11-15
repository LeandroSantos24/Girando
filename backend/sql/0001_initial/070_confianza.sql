-- =====================================================================
-- 070 · Confianza: documentos, verificaciones, reseñas, reportes,
--       acciones de moderación.
-- Relaciones "polimórficas" resueltas con ARCOS EXCLUSIVOS: varias FKs
-- nulas + CHECK num_nonnulls(...) = 1. Así la integridad la garantiza la
-- base (no hay subject_id sin FK).
-- =====================================================================
SET search_path = app, public;

-- ---------------------------------------------------------------------
-- verification_products (configurable por el admin)
-- ---------------------------------------------------------------------
CREATE TABLE verification_products (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code                 text NOT NULL,
  name                 text NOT NULL,
  description          text NOT NULL,
  kind                 verification_kind NOT NULL,
  subject              verification_subject NOT NULL,
  price_amount         numeric(12,2) NOT NULL DEFAULT 0,
  currency             currency_code NOT NULL DEFAULT 'ARS',
  required_documents   document_type[] NOT NULL DEFAULT '{}',
  validity_days        integer,
  includes_physical_inspection boolean NOT NULL DEFAULT false,
  public_disclaimer    text NOT NULL,
  status               verification_product_status NOT NULL DEFAULT 'draft',
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT vp_code CHECK (code ~ '^[a-z][a-z0-9_]{2,40}$'),
  CONSTRAINT vp_price CHECK (price_amount >= 0),
  CONSTRAINT vp_validity CHECK (validity_days IS NULL OR validity_days > 0),
  CONSTRAINT vp_inspection_kind CHECK (includes_physical_inspection = (kind = 'physical_inspection'))
);
COMMENT ON TABLE verification_products IS '[PÚBLICO si active] Productos de verificación (Identidad, Agencia verificada; a futuro documentación, existencia del vehículo, inspección física).';
COMMENT ON COLUMN verification_products.public_disclaimer IS '[PÚBLICO] Qué certifica y qué NO (p.ej. "Agencia verificada certifica los datos de la empresa, no el estado de los vehículos").';
COMMENT ON COLUMN verification_products.includes_physical_inspection IS '[PÚBLICO] Solo true para un producto de inspección física real. Ningún otro producto puede decir que Girando inspeccionó un vehículo.';
CREATE UNIQUE INDEX verification_products_code_uq ON verification_products (code);
CREATE TRIGGER vp_updated BEFORE UPDATE ON verification_products FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();

-- ---------------------------------------------------------------------
-- verifications (una solicitud concreta)
-- ---------------------------------------------------------------------
CREATE TABLE verifications (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id         uuid NOT NULL REFERENCES verification_products(id),
  subject_user_id    uuid REFERENCES users(id),
  subject_agency_id  uuid REFERENCES agencies(id),
  subject_vehicle_id uuid REFERENCES vehicles(id),
  subject_listing_id uuid REFERENCES listings(id),
  requested_by       uuid NOT NULL REFERENCES users(id),
  status             verification_status NOT NULL DEFAULT 'pending',
  reviewer_id        uuid REFERENCES users(id),
  review_started_at  timestamptz,
  decided_at         timestamptz,
  decision_reason    text,
  expires_at         timestamptz,
  revoked_at         timestamptz,
  payment_id         uuid,   -- FK agregada en 090 (payments)
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ver_one_subject CHECK (num_nonnulls(subject_user_id, subject_agency_id, subject_vehicle_id, subject_listing_id) = 1),
  CONSTRAINT ver_no_self_review CHECK (reviewer_id IS NULL OR (reviewer_id <> requested_by AND reviewer_id IS DISTINCT FROM subject_user_id)),
  CONSTRAINT ver_decision CHECK (status NOT IN ('approved','rejected','revoked') OR (decided_at IS NOT NULL AND reviewer_id IS NOT NULL)),
  CONSTRAINT ver_reason CHECK (status NOT IN ('rejected','revoked') OR decision_reason IS NOT NULL),
  CONSTRAINT ver_revoked CHECK ((status = 'revoked') = (revoked_at IS NOT NULL))
);
COMMENT ON TABLE verifications IS 'Solicitud de verificación. Solo staff aprueba/rechaza/revoca; nunca el solicitante ni el sujeto (CHECK + RLS).';
COMMENT ON COLUMN verifications.status IS '[PÚBLICO como distintivo si approved] pending → review → approved | rejected; approved → revoked.';
COMMENT ON COLUMN verifications.decision_reason IS '[PROPIETARIO] Motivo visible al solicitante (obligatorio al rechazar o revocar).';
COMMENT ON COLUMN verifications.reviewer_id IS '[ADMIN] Staff que decidió.';
CREATE UNIQUE INDEX ver_open_per_subject_uq ON verifications
  (product_id, coalesce(subject_user_id, subject_agency_id, subject_vehicle_id, subject_listing_id))
  WHERE status IN ('pending','review');
CREATE INDEX ver_queue_idx ON verifications (created_at) WHERE status IN ('pending','review');
CREATE INDEX ver_user_idx ON verifications (subject_user_id) WHERE subject_user_id IS NOT NULL;
CREATE INDEX ver_agency_idx ON verifications (subject_agency_id) WHERE subject_agency_id IS NOT NULL;
CREATE TRIGGER ver_updated BEFORE UPDATE ON verifications FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();

-- ---------------------------------------------------------------------
-- documents (archivo privado + metadatos). NO se guarda URL pública.
-- ---------------------------------------------------------------------
CREATE TABLE documents (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  uploaded_by        uuid NOT NULL REFERENCES users(id),
  owner_user_id      uuid REFERENCES users(id),
  owner_agency_id    uuid REFERENCES agencies(id),
  owner_vehicle_id   uuid REFERENCES vehicles(id),
  verification_id    uuid REFERENCES verifications(id),
  type               document_type NOT NULL,
  storage_provider   storage_provider NOT NULL,
  storage_bucket     text NOT NULL,
  storage_key        text NOT NULL,
  mime_type          text NOT NULL,
  bytes              integer NOT NULL,
  sha256             bytea NOT NULL,
  original_filename  text,
  status             document_status NOT NULL DEFAULT 'uploaded',
  expires_on         date,
  reviewed_by        uuid REFERENCES users(id),
  reviewed_at        timestamptz,
  rejection_reason   text,
  deleted_at         timestamptz,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT doc_one_owner CHECK (num_nonnulls(owner_user_id, owner_agency_id, owner_vehicle_id) = 1),
  CONSTRAINT doc_mime CHECK (mime_type IN ('application/pdf','image/jpeg','image/png','image/webp')),
  CONSTRAINT doc_bytes CHECK (bytes BETWEEN 1 AND 15728640),
  CONSTRAINT doc_review CHECK (status NOT IN ('approved','rejected') OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)),
  CONSTRAINT doc_reject_reason CHECK (status <> 'rejected' OR rejection_reason IS NOT NULL),
  CONSTRAINT doc_no_self_review CHECK (reviewed_by IS NULL OR reviewed_by <> uploaded_by),
  CONSTRAINT doc_deleted CHECK ((status = 'deleted') = (deleted_at IS NOT NULL))
);
COMMENT ON TABLE documents IS '[SENSIBLE] Documentos en bucket PRIVADO (S3/R2). Acceso solo con URL firmada de corta vida generada por el backend y auditada.';
COMMENT ON COLUMN documents.storage_key IS '[SISTEMA] Ruta dentro del bucket privado. La "URL" se genera on-demand (firmada, 5 min); nunca se persiste.';
COMMENT ON COLUMN documents.sha256 IS '[SISTEMA] Integridad y detección de reutilización de documentos entre cuentas.';
COMMENT ON COLUMN documents.expires_on IS '[PRIVADO] Vencimiento del documento (p.ej. cédula, habilitación). Un job lo marca expired.';
COMMENT ON COLUMN documents.verification_id IS '[PRIVADO] Si se presentó como parte de una verificación.';
CREATE UNIQUE INDEX documents_key_uq ON documents (storage_provider, storage_bucket, storage_key);
CREATE INDEX documents_user_idx ON documents (owner_user_id) WHERE owner_user_id IS NOT NULL;
CREATE INDEX documents_agency_idx ON documents (owner_agency_id) WHERE owner_agency_id IS NOT NULL;
CREATE INDEX documents_vehicle_idx ON documents (owner_vehicle_id) WHERE owner_vehicle_id IS NOT NULL;
CREATE INDEX documents_verification_idx ON documents (verification_id) WHERE verification_id IS NOT NULL;
CREATE INDEX documents_expiry_idx ON documents (expires_on) WHERE status = 'approved' AND expires_on IS NOT NULL;
CREATE INDEX documents_sha_idx ON documents (sha256);
CREATE TRIGGER documents_updated BEFORE UPDATE ON documents FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();

-- ---------------------------------------------------------------------
-- reviews (reputación Girando). Requieren interacción válida y una sola
-- por interacción. La de Google vive aparte (external_ratings).
-- ---------------------------------------------------------------------
CREATE TABLE reviews (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  reviewer_user_id    uuid NOT NULL REFERENCES users(id),
  reviewed_user_id    uuid REFERENCES users(id),
  reviewed_agency_id  uuid REFERENCES agencies(id),
  conversation_id     uuid,  -- FK agregada en 080
  sale_id             uuid,  -- FK agregada en 090
  rating              smallint NOT NULL,
  comment             text,
  status              review_status NOT NULL DEFAULT 'published',
  status_reason       text,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT rv_one_subject CHECK (num_nonnulls(reviewed_user_id, reviewed_agency_id) = 1),
  CONSTRAINT rv_one_interaction CHECK (num_nonnulls(conversation_id, sale_id) = 1),
  CONSTRAINT rv_rating CHECK (rating BETWEEN 1 AND 5),
  CONSTRAINT rv_comment CHECK (comment IS NULL OR length(comment) <= 1000),
  CONSTRAINT rv_not_self CHECK (reviewed_user_id IS DISTINCT FROM reviewer_user_id)
);
COMMENT ON TABLE reviews IS 'Calificación entre usuarios/agencias atada a una conversación respondida o a una venta.';
COMMENT ON COLUMN reviews.reviewer_user_id IS '[PÚBLICO como display_name] Autor.';
COMMENT ON COLUMN reviews.rating IS '[PÚBLICO] 1 a 5.';
COMMENT ON COLUMN reviews.status IS '[PÚBLICO solo published] hidden/removed por moderación (con motivo).';
CREATE UNIQUE INDEX rv_once_per_conversation_uq ON reviews (reviewer_user_id, conversation_id) WHERE conversation_id IS NOT NULL;
CREATE UNIQUE INDEX rv_once_per_sale_uq ON reviews (reviewer_user_id, sale_id) WHERE sale_id IS NOT NULL;
CREATE INDEX rv_user_idx ON reviews (reviewed_user_id, created_at DESC) WHERE status = 'published';
CREATE INDEX rv_agency_idx ON reviews (reviewed_agency_id, created_at DESC) WHERE status = 'published';
CREATE TRIGGER rv_updated BEFORE UPDATE ON reviews FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();

-- ---------------------------------------------------------------------
-- report_reasons (configurables) + reports
-- ---------------------------------------------------------------------
CREATE TABLE report_reasons (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code        text NOT NULL UNIQUE,
  label       text NOT NULL,
  applies_to  report_target[] NOT NULL,
  requires_description boolean NOT NULL DEFAULT false,
  is_active   boolean NOT NULL DEFAULT true,
  sort_order  smallint NOT NULL DEFAULT 0,
  CONSTRAINT rr_code CHECK (code ~ '^[a-z][a-z0-9_]{2,40}$')
);
COMMENT ON TABLE report_reasons IS '[PÚBLICO] Motivos configurables (precio falso, vehículo inexistente, información engañosa, duplicada, inapropiado, posible estafa, ya vendido, otro...).';

CREATE TABLE reports (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  reporter_user_id   uuid REFERENCES users(id),
  reporter_anonymous_id uuid,
  target             report_target NOT NULL,
  listing_id         uuid REFERENCES listings(id),
  reported_user_id   uuid REFERENCES users(id),
  agency_id          uuid REFERENCES agencies(id),
  message_id         uuid,   -- FK agregada en 080
  review_id          uuid REFERENCES reviews(id),
  reason_id          uuid NOT NULL REFERENCES report_reasons(id),
  description        text,
  status             report_status NOT NULL DEFAULT 'pending',
  assigned_to        uuid REFERENCES users(id),
  resolved_by        uuid REFERENCES users(id),
  resolved_at        timestamptz,
  resolution_note    text,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT rp_reporter CHECK (num_nonnulls(reporter_user_id, reporter_anonymous_id) >= 1),
  CONSTRAINT rp_one_target CHECK (num_nonnulls(listing_id, reported_user_id, agency_id, message_id, review_id) = 1),
  CONSTRAINT rp_target_match CHECK (
       (target = 'listing' AND listing_id IS NOT NULL) OR (target = 'user' AND reported_user_id IS NOT NULL)
    OR (target = 'agency' AND agency_id IS NOT NULL)  OR (target = 'message' AND message_id IS NOT NULL)
    OR (target = 'review' AND review_id IS NOT NULL)),
  CONSTRAINT rp_desc CHECK (description IS NULL OR length(description) <= 1000),
  CONSTRAINT rp_resolution CHECK (status NOT IN ('resolved','rejected') OR (resolved_by IS NOT NULL AND resolved_at IS NOT NULL AND resolution_note IS NOT NULL))
);
COMMENT ON TABLE reports IS '"Denunciada" no es un estado de la publicación: es un reporte abierto sobre ella que se revisa en moderación.';
COMMENT ON COLUMN reports.reporter_user_id IS '[ADMIN] Nunca se revela al reportado.';
COMMENT ON COLUMN reports.description IS '[ADMIN] Detalle opcional del reportante.';
CREATE INDEX reports_queue_idx ON reports (created_at) WHERE status IN ('pending','reviewing');
CREATE INDEX reports_listing_idx ON reports (listing_id) WHERE listing_id IS NOT NULL;
CREATE INDEX reports_user_idx ON reports (reported_user_id) WHERE reported_user_id IS NOT NULL;
CREATE INDEX reports_agency_idx ON reports (agency_id) WHERE agency_id IS NOT NULL;
CREATE UNIQUE INDEX reports_no_dup_open_uq ON reports (reporter_user_id, target, coalesce(listing_id, reported_user_id, agency_id, message_id, review_id))
  WHERE status IN ('pending','reviewing') AND reporter_user_id IS NOT NULL;
CREATE TRIGGER reports_updated BEFORE UPDATE ON reports FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();

-- ---------------------------------------------------------------------
-- moderation_actions (registro de dominio: quién, qué, sobre qué, por qué)
-- ---------------------------------------------------------------------
CREATE TABLE moderation_actions (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_user_id    uuid NOT NULL REFERENCES users(id),
  actor_role       staff_role NOT NULL,
  action           moderation_action_type NOT NULL,
  listing_id       uuid REFERENCES listings(id),
  target_user_id   uuid REFERENCES users(id),
  agency_id        uuid REFERENCES agencies(id),
  message_id       uuid,   -- FK agregada en 080
  review_id        uuid REFERENCES reviews(id),
  verification_id  uuid REFERENCES verifications(id),
  report_id        uuid REFERENCES reports(id),
  previous_state   text,
  new_state        text,
  reason           text,
  created_at       timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ma_one_target CHECK (num_nonnulls(listing_id, target_user_id, agency_id, message_id, review_id, verification_id) = 1
                                  OR (action IN ('report_dismiss','report_resolve') AND report_id IS NOT NULL)),
  CONSTRAINT ma_reason_required CHECK (reason IS NOT NULL OR action IN ('listing_approve','listing_reactivate','user_reactivate','agency_verify','agency_reactivate','verification_approve','review_restore'))
);
COMMENT ON TABLE moderation_actions IS '[ADMIN] Toda acción de moderación con autor, rol y motivo (obligatorio si afecta a terceros). Append-only.';
CREATE INDEX ma_listing_idx ON moderation_actions (listing_id, created_at DESC) WHERE listing_id IS NOT NULL;
CREATE INDEX ma_user_idx ON moderation_actions (target_user_id, created_at DESC) WHERE target_user_id IS NOT NULL;
CREATE INDEX ma_agency_idx ON moderation_actions (agency_id, created_at DESC) WHERE agency_id IS NOT NULL;
CREATE INDEX ma_actor_idx ON moderation_actions (actor_user_id, created_at DESC);
