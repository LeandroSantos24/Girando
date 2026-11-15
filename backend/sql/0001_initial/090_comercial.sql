-- =====================================================================
-- 090 · Comercial: planes, suscripciones, pagos, eventos de proveedor,
--       cotizaciones, promociones, ventas.
-- Fuente de verdad de permisos = subscriptions (escrita solo por el
-- worker de webhooks o por staff finance). Nunca el frontend.
-- =====================================================================
SET search_path = app, public;

-- ---------------------------------------------------------------------
-- plans (editables por el admin sin tocar código)
-- ---------------------------------------------------------------------
CREATE TABLE plans (
  id                        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code                      text NOT NULL UNIQUE,
  name                      text NOT NULL,
  description               text,
  audience                  plan_audience NOT NULL,
  price_amount              numeric(12,2) NOT NULL DEFAULT 0,
  currency                  currency_code NOT NULL DEFAULT 'ARS',
  billing_period            billing_period NOT NULL DEFAULT 'month',
  max_active_listings       integer NOT NULL,
  included_featured_listings integer NOT NULL DEFAULT 0,
  included_promotion_credits integer NOT NULL DEFAULT 0,
  stats_level               smallint NOT NULL DEFAULT 0,
  includes_verification     boolean NOT NULL DEFAULT false,
  max_members               integer NOT NULL DEFAULT 1,
  search_priority_boost     boolean NOT NULL DEFAULT false,
  features_display          text[] NOT NULL DEFAULT '{}',
  badge_label               text,
  is_default_for_audience   boolean NOT NULL DEFAULT false,
  is_public                 boolean NOT NULL DEFAULT true,
  is_active                 boolean NOT NULL DEFAULT true,
  sort_order                smallint NOT NULL DEFAULT 0,
  mp_preapproval_plan_id    text,
  created_at                timestamptz NOT NULL DEFAULT now(),
  updated_at                timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pl_code CHECK (code ~ '^[a-z][a-z0-9_-]{2,40}$'),
  CONSTRAINT pl_price CHECK (price_amount >= 0),
  CONSTRAINT pl_free_period CHECK ((price_amount = 0) = (billing_period = 'none')),
  CONSTRAINT pl_limits CHECK (max_active_listings >= 0 AND included_featured_listings >= 0 AND included_promotion_credits >= 0 AND max_members >= 1),
  CONSTRAINT pl_stats CHECK (stats_level BETWEEN 0 AND 3)
);
COMMENT ON TABLE plans IS '[PÚBLICO si is_public] Entitlements aplicados por el backend (columnas tipadas). features_display es solo texto de marketing y NO otorga permisos.';
COMMENT ON COLUMN plans.max_active_listings IS '[PÚBLICO] Cuentan published + pending. Validado en servidor (409 LIMITE_ALCANZADO) y por trigger.';
COMMENT ON COLUMN plans.stats_level IS '[PÚBLICO] 0 básicas · 1 por publicación · 2 avanzadas · 3 exportación/API.';
COMMENT ON COLUMN plans.is_default_for_audience IS '[ADMIN] Plan efectivo cuando no hay suscripción que otorgue permisos (Particular = 1 publicación).';
COMMENT ON COLUMN plans.mp_preapproval_plan_id IS '[ADMIN] ID del plan de suscripción en Mercado Pago. PENDIENTE DE INTEGRACIÓN REAL.';
CREATE UNIQUE INDEX plans_default_uq ON plans (audience) WHERE is_default_for_audience AND is_active;
CREATE TRIGGER plans_updated BEFORE UPDATE ON plans FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();

-- ---------------------------------------------------------------------
-- subscriptions
-- ---------------------------------------------------------------------
CREATE TABLE subscriptions (
  id                        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  plan_id                   uuid NOT NULL REFERENCES plans(id),
  user_id                   uuid REFERENCES users(id),
  agency_id                 uuid REFERENCES agencies(id),
  created_by                uuid NOT NULL REFERENCES users(id),
  provider                  payment_provider NOT NULL,
  external_customer_id      text,
  external_subscription_id  text,
  status                    subscription_status NOT NULL DEFAULT 'pending',
  price_amount              numeric(12,2) NOT NULL,
  currency                  currency_code NOT NULL,
  billing_period            billing_period NOT NULL,
  started_at                timestamptz,
  current_period_start      timestamptz,
  current_period_end        timestamptz,
  next_renewal_at           timestamptz,
  grace_until               timestamptz,
  cancel_at_period_end      boolean NOT NULL DEFAULT false,
  canceled_at               timestamptz,
  cancel_reason             text,
  ended_at                  timestamptz,
  pending_plan_id           uuid REFERENCES plans(id),
  created_at                timestamptz NOT NULL DEFAULT now(),
  updated_at                timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT sub_one_owner CHECK (num_nonnulls(user_id, agency_id) = 1),
  CONSTRAINT sub_price CHECK (price_amount >= 0),
  CONSTRAINT sub_active_dates CHECK (status NOT IN ('active','payment_failed','grace_period','canceled') OR (started_at IS NOT NULL AND current_period_end IS NOT NULL)),
  CONSTRAINT sub_grace CHECK ((status = 'grace_period') <= (grace_until IS NOT NULL)),
  CONSTRAINT sub_canceled CHECK ((status = 'canceled') <= (canceled_at IS NOT NULL)),
  CONSTRAINT sub_expired CHECK ((status = 'expired') <= (ended_at IS NOT NULL))
);
COMMENT ON TABLE subscriptions IS 'Estado financiero del plan de un usuario o agencia. Determina permisos reales. Escritura: solo worker (webhook) y staff finance.';
COMMENT ON COLUMN subscriptions.price_amount IS '[PROPIETARIO] Precio congelado al suscribirse: editar el plan no cambia retroactivamente lo pactado.';
COMMENT ON COLUMN subscriptions.external_subscription_id IS '[ADMIN] ID de preapproval de Mercado Pago.';
COMMENT ON COLUMN subscriptions.status IS '[PROPIETARIO] Otorgan el plan: active, payment_failed, grace_period, canceled (hasta current_period_end).';
COMMENT ON COLUMN subscriptions.pending_plan_id IS '[PROPIETARIO] Cambio de plan esperando pago confirmado.';
CREATE UNIQUE INDEX sub_one_open_agency_uq ON subscriptions (agency_id) WHERE agency_id IS NOT NULL AND status IN ('pending','active','payment_failed','grace_period','canceled');
CREATE UNIQUE INDEX sub_one_open_user_uq ON subscriptions (user_id) WHERE user_id IS NOT NULL AND status IN ('pending','active','payment_failed','grace_period','canceled');
CREATE UNIQUE INDEX sub_external_uq ON subscriptions (provider, external_subscription_id) WHERE external_subscription_id IS NOT NULL;
CREATE INDEX sub_renewal_idx ON subscriptions (status, current_period_end);
CREATE TRIGGER sub_updated BEFORE UPDATE ON subscriptions FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();

-- ---------------------------------------------------------------------
-- payments (Mercado Pago o transferencia). Sin datos de tarjeta.
-- ---------------------------------------------------------------------
CREATE SEQUENCE transfer_reference_seq START 1;
CREATE TABLE payments (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  purpose               payment_purpose NOT NULL,
  subscription_id       uuid REFERENCES subscriptions(id),
  promotion_id          uuid,  -- FK más abajo
  verification_id       uuid REFERENCES verifications(id),
  payer_user_id         uuid NOT NULL REFERENCES users(id),
  agency_id             uuid REFERENCES agencies(id),
  provider              payment_provider NOT NULL,
  method_type           text,
  status                payment_status NOT NULL DEFAULT 'pending',
  status_detail         text,
  amount                numeric(12,2) NOT NULL,
  currency              currency_code NOT NULL DEFAULT 'ARS',
  external_reference    text NOT NULL DEFAULT gen_random_uuid()::text,
  mp_payment_id         text,
  mp_preference_id      text,
  mp_preapproval_id     text,
  transfer_reference    text,
  transfer_declared_at  timestamptz,
  receipt_document_id   uuid REFERENCES documents(id),
  reviewed_by           uuid REFERENCES users(id),
  reviewed_at           timestamptz,
  rejection_reason      text,
  paid_at               timestamptz,
  provider_snapshot     jsonb,
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pay_one_purpose CHECK (num_nonnulls(subscription_id, promotion_id, verification_id) = 1),
  CONSTRAINT pay_purpose_match CHECK ((purpose = 'subscription') = (subscription_id IS NOT NULL)
                                  AND (purpose = 'promotion') = (promotion_id IS NOT NULL)
                                  AND (purpose = 'verification') = (verification_id IS NOT NULL)),
  CONSTRAINT pay_amount CHECK (amount > 0),
  CONSTRAINT pay_transfer_ref CHECK ((provider = 'bank_transfer') = (transfer_reference IS NOT NULL)),
  CONSTRAINT pay_transfer_ref_fmt CHECK (transfer_reference IS NULL OR transfer_reference ~ '^GIR-[0-9]{6,}$'),
  CONSTRAINT pay_submitted_only_transfer CHECK (status <> 'submitted' OR provider = 'bank_transfer'),
  CONSTRAINT pay_transfer_review CHECK (provider <> 'bank_transfer' OR status NOT IN ('approved','rejected') OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)),
  CONSTRAINT pay_no_self_review CHECK (reviewed_by IS NULL OR reviewed_by <> payer_user_id),
  CONSTRAINT pay_reject_reason CHECK (provider <> 'bank_transfer' OR status <> 'rejected' OR rejection_reason IS NOT NULL),
  CONSTRAINT pay_paid_at CHECK ((status = 'approved') <= (paid_at IS NOT NULL)),
  CONSTRAINT pay_snapshot_obj CHECK (provider_snapshot IS NULL OR jsonb_typeof(provider_snapshot) = 'object')
);
COMMENT ON TABLE payments IS 'Cobros. Mercado Pago: el estado lo fija el webhook tras consultar la API. Transferencia: pending → submitted (usuario avisa) → approved|rejected (solo staff finance).';
COMMENT ON COLUMN payments.external_reference IS '[ADMIN] Referencia propia enviada a MP (external_reference) para conciliar.';
COMMENT ON COLUMN payments.mp_payment_id IS '[ADMIN] ID de pago de MP (único).';
COMMENT ON COLUMN payments.method_type IS '[PROPIETARIO] Tipo informado por MP (credit_card, account_money, ...). Nunca número de tarjeta.';
COMMENT ON COLUMN payments.transfer_reference IS '[PROPIETARIO] Referencia a incluir en la transferencia (GIR-000123), generada por el backend.';
COMMENT ON COLUMN payments.provider_snapshot IS '[ADMIN] Subconjunto relevante de la respuesta del proveedor (status, status_detail, payment_method_id, date_approved, transaction_amount). Sin datos personales del pagador ni de la tarjeta.';
CREATE UNIQUE INDEX pay_external_ref_uq ON payments (external_reference);
CREATE UNIQUE INDEX pay_mp_payment_uq ON payments (mp_payment_id) WHERE mp_payment_id IS NOT NULL;
CREATE UNIQUE INDEX pay_transfer_ref_uq ON payments (transfer_reference) WHERE transfer_reference IS NOT NULL;
CREATE INDEX pay_subscription_idx ON payments (subscription_id, created_at DESC) WHERE subscription_id IS NOT NULL;
CREATE INDEX pay_payer_idx ON payments (payer_user_id, created_at DESC);
CREATE INDEX pay_agency_idx ON payments (agency_id, created_at DESC) WHERE agency_id IS NOT NULL;
CREATE INDEX pay_review_queue_idx ON payments (transfer_declared_at) WHERE status = 'submitted';
CREATE INDEX pay_status_idx ON payments (status, created_at DESC);
CREATE TRIGGER pay_updated BEFORE UPDATE ON payments FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();

ALTER TABLE verifications ADD CONSTRAINT ver_payment_fk FOREIGN KEY (payment_id) REFERENCES payments(id);

-- ---------------------------------------------------------------------
-- payment_events: cada notificación del proveedor (idempotente)
-- ---------------------------------------------------------------------
CREATE TABLE payment_events (
  id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  provider           payment_provider NOT NULL,
  topic              text NOT NULL,
  action             text,
  resource_id        text NOT NULL,
  request_id         text,
  idempotency_key    text NOT NULL,
  signature_valid    boolean NOT NULL,
  payment_id         uuid REFERENCES payments(id),
  subscription_id    uuid REFERENCES subscriptions(id),
  processing_status  provider_event_status NOT NULL DEFAULT 'received',
  error              text,
  payload            jsonb NOT NULL,
  resource_snapshot  jsonb,
  received_at        timestamptz NOT NULL DEFAULT now(),
  processed_at       timestamptz
);
COMMENT ON TABLE payment_events IS '[ADMIN] Webhooks recibidos (Mercado Pago: payment, subscription_preapproval, subscription_authorized_payment) y resultado de procesarlos. Idempotencia por idempotency_key.';
COMMENT ON COLUMN payment_events.signature_valid IS '[ADMIN] Resultado de validar x-signature (HMAC). Si es false no se procesa.';
COMMENT ON COLUMN payment_events.resource_snapshot IS '[ADMIN] Respuesta de GET al recurso en la API del proveedor (la verdad), filtrada.';
CREATE UNIQUE INDEX pe_idempotency_uq ON payment_events (provider, idempotency_key);
CREATE INDEX pe_pending_idx ON payment_events (received_at) WHERE processing_status IN ('received','failed');
CREATE INDEX pe_resource_idx ON payment_events (provider, resource_id);

-- ---------------------------------------------------------------------
-- exchange_rates: cotización para normalizar ARS/USD en búsquedas y estadísticas
-- ---------------------------------------------------------------------
CREATE TABLE exchange_rates (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  currency    currency_code NOT NULL,
  rate_to_ars numeric(14,4) NOT NULL,
  source      text NOT NULL,
  valid_on    date NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT fx_rate CHECK (rate_to_ars > 0),
  CONSTRAINT fx_not_ars CHECK (currency <> 'ARS'),
  UNIQUE (currency, source, valid_on)
);
COMMENT ON TABLE exchange_rates IS '[PÚBLICO] Reemplaza el USD_RATE=1250 hardcodeado. Fuente a definir (BCRA oficial u otra). PENDIENTE DE INTEGRACIÓN.';

-- ---------------------------------------------------------------------
-- promotion_products (catálogo de productos pagos de exposición)
-- ---------------------------------------------------------------------
CREATE TABLE promotion_products (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code           text NOT NULL UNIQUE,
  name           text NOT NULL,
  description    text NOT NULL,
  type           promotion_type NOT NULL,
  placement      promotion_placement NOT NULL,
  price_amount   numeric(12,2) NOT NULL,
  currency       currency_code NOT NULL DEFAULT 'ARS',
  duration_days  smallint NOT NULL,
  is_active      boolean NOT NULL DEFAULT true,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pp_price CHECK (price_amount >= 0),
  CONSTRAINT pp_days CHECK (duration_days BETWEEN 1 AND 365)
);
COMMENT ON TABLE promotion_products IS '[PÚBLICO si activo] Publicación destacada, Posición promocionada, Agencia destacada, Banner. Precio y duración editables por el admin.';
CREATE TRIGGER pp_updated BEFORE UPDATE ON promotion_products FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();

-- ---------------------------------------------------------------------
-- promotions (una compra/campaña concreta)
-- ---------------------------------------------------------------------
CREATE TABLE promotions (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id         uuid REFERENCES promotion_products(id),
  type               promotion_type NOT NULL,
  placement          promotion_placement NOT NULL,
  listing_id         uuid REFERENCES listings(id),
  target_agency_id   uuid REFERENCES agencies(id),
  advertiser_name    text,
  creative_public_id text,
  link_url           text,
  purchased_by       uuid REFERENCES users(id),
  paying_agency_id   uuid REFERENCES agencies(id),
  price_amount       numeric(12,2) NOT NULL,
  currency           currency_code NOT NULL DEFAULT 'ARS',
  starts_at          timestamptz NOT NULL,
  ends_at            timestamptz NOT NULL,
  status             promotion_status NOT NULL DEFAULT 'pending',
  priority           smallint NOT NULL DEFAULT 0,
  target_brand_id    uuid REFERENCES vehicle_brands(id),
  target_model_id    uuid REFERENCES vehicle_models(id),
  target_geo_area_id uuid REFERENCES geo_areas(id),
  disclosure_label   text NOT NULL DEFAULT 'Patrocinado',
  status_reason      text,
  approved_by        uuid REFERENCES users(id),
  approved_at        timestamptz,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pr_target CHECK (
       (type IN ('featured_listing','promoted_position') AND listing_id IS NOT NULL AND target_agency_id IS NULL AND advertiser_name IS NULL)
    OR (type = 'featured_agency' AND target_agency_id IS NOT NULL AND listing_id IS NULL)
    OR (type = 'banner_campaign' AND advertiser_name IS NOT NULL AND link_url IS NOT NULL AND listing_id IS NULL)),
  CONSTRAINT pr_dates CHECK (ends_at > starts_at),
  CONSTRAINT pr_price CHECK (price_amount >= 0),
  CONSTRAINT pr_label CHECK (disclosure_label IN ('Patrocinado','Publicidad')),
  CONSTRAINT pr_link CHECK (link_url IS NULL OR link_url ~* '^https://\S+$'),
  CONSTRAINT pr_active_needs_creative CHECK (status <> 'active' OR type <> 'banner_campaign' OR creative_public_id IS NOT NULL),
  CONSTRAINT pr_active_approved CHECK (status NOT IN ('active','paused','finished') OR approved_at IS NOT NULL)
);
COMMENT ON TABLE promotions IS 'Exposición pagada, SIEMPRE rotulada (disclosure_label). Se muestra en bloque aparte; nunca altera el orden orgánico.';
COMMENT ON COLUMN promotions.advertiser_name IS '[PÚBLICO] Para banners de anunciantes que no publican en Girando. Solo material propio, provisto o con licencia.';
COMMENT ON COLUMN promotions.priority IS '[ADMIN] Orden entre promociones del mismo placement.';
CREATE INDEX pr_active_idx ON promotions (placement, priority DESC, starts_at) WHERE status = 'active';
CREATE INDEX pr_listing_idx ON promotions (listing_id) WHERE listing_id IS NOT NULL;
CREATE INDEX pr_agency_idx ON promotions (target_agency_id) WHERE target_agency_id IS NOT NULL;
CREATE INDEX pr_buyer_idx ON promotions (purchased_by, created_at DESC);
CREATE INDEX pr_schedule_idx ON promotions (ends_at) WHERE status IN ('active','paused');
CREATE TRIGGER pr_updated BEFORE UPDATE ON promotions FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();

ALTER TABLE payments ADD CONSTRAINT pay_promotion_fk FOREIGN KEY (promotion_id) REFERENCES promotions(id);

CREATE TABLE promotion_events (
  id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  promotion_id   uuid NOT NULL REFERENCES promotions(id),
  event          promotion_event_type NOT NULL,
  from_status    promotion_status,
  to_status      promotion_status,
  actor_user_id  uuid REFERENCES users(id),
  actor_type     actor_type NOT NULL,
  reason         text,
  created_at     timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE promotion_events IS '[PROPIETARIO] Ciclo de vida de la promoción (creada, aprobada, pausada, finalizada, pago). Las MÉTRICAS (impresiones, vistas, clics, favoritos, contactos) salen de analytics_events con promotion_id — no se duplican acá.';
CREATE INDEX pev_promotion_idx ON promotion_events (promotion_id, created_at);

-- ---------------------------------------------------------------------
-- sales: registro histórico de "Vendí este vehículo"
-- ---------------------------------------------------------------------
CREATE TABLE sales (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  public_code         text NOT NULL DEFAULT app.gen_public_code('V'),
  listing_id          uuid NOT NULL REFERENCES listings(id),
  vehicle_id          uuid NOT NULL REFERENCES vehicles(id),
  seller_user_id      uuid NOT NULL REFERENCES users(id),
  agency_id           uuid REFERENCES agencies(id),
  reported_by         uuid NOT NULL REFERENCES users(id),
  sold_on             date NOT NULL,
  final_price         numeric(14,2) NOT NULL,
  currency            currency_code NOT NULL,
  fx_rate_to_ars      numeric(14,4),
  is_financed         boolean NOT NULL DEFAULT false,
  financing_type      financing_type,
  financed_amount     numeric(14,2),
  installments        smallint,
  channel             sale_channel NOT NULL,
  attributed_to_girando boolean GENERATED ALWAYS AS (channel <> 'other_channel') STORED,
  buyer_conversation_id uuid REFERENCES conversations(id),
  notes               text,
  status              sale_status NOT NULL DEFAULT 'reported',
  voided_reason       text,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT sa_price CHECK (final_price > 0 AND final_price < 100000000000),
  CONSTRAINT sa_fx CHECK ((currency = 'ARS') = (fx_rate_to_ars IS NULL)),
  CONSTRAINT sa_financing CHECK (is_financed OR (financing_type IS NULL AND financed_amount IS NULL AND installments IS NULL)),
  CONSTRAINT sa_financing_type CHECK (NOT is_financed OR financing_type IS NOT NULL),
  CONSTRAINT sa_fin_amount CHECK (financed_amount IS NULL OR (financed_amount > 0 AND financed_amount <= final_price)),
  CONSTRAINT sa_installments CHECK (installments IS NULL OR installments BETWEEN 1 AND 120),
  CONSTRAINT sa_sold_on CHECK (sold_on >= DATE '2025-01-01'),
  CONSTRAINT sa_notes CHECK (notes IS NULL OR length(notes) <= 1000),
  CONSTRAINT sa_voided CHECK ((status = 'voided') = (voided_reason IS NOT NULL))
);
COMMENT ON TABLE sales IS 'Venta histórica. Sobrevive a la eliminación de fotos, a la anonimización de la publicación y a la baja de la cuenta. No guarda datos personales del comprador.';
COMMENT ON COLUMN sales.final_price IS '[PROPIETARIO; PÚBLICO solo agregado con n≥3] Precio final declarado por el vendedor.';
COMMENT ON COLUMN sales.fx_rate_to_ars IS '[SISTEMA] Cotización congelada a la fecha de venta (solo USD) para estadísticas en ARS.';
COMMENT ON COLUMN sales.channel IS '[PROPIETARIO] girando / buyer_from_girando / other_channel.';
COMMENT ON COLUMN sales.attributed_to_girando IS '[PROPIETARIO] Derivado del canal (columna generada, no editable).';
COMMENT ON COLUMN sales.buyer_conversation_id IS '[PRIVADO] Evidencia opcional de atribución (conversación con el comprador). No se copia ningún dato del comprador.';
COMMENT ON COLUMN sales.notes IS '[PROPIETARIO] Observaciones privadas.';
COMMENT ON COLUMN sales.status IS '[ADMIN] voided = anulada por soporte (error del vendedor); no se borra.';
CREATE UNIQUE INDEX sales_listing_uq ON sales (listing_id) WHERE status = 'reported';
CREATE UNIQUE INDEX sales_code_uq ON sales (public_code);
CREATE INDEX sales_seller_idx ON sales (seller_user_id, sold_on DESC);
CREATE INDEX sales_agency_idx ON sales (agency_id, sold_on DESC) WHERE agency_id IS NOT NULL;
CREATE INDEX sales_date_idx ON sales (sold_on) WHERE status = 'reported';
CREATE TRIGGER sales_updated BEFORE UPDATE ON sales FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();

ALTER TABLE reviews ADD CONSTRAINT rv_sale_fk FOREIGN KEY (sale_id) REFERENCES sales(id);
