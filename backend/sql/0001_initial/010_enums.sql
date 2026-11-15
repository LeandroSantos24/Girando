-- =====================================================================
-- 010 · Enums (estados y vocabularios técnicos estables)
-- Regla: ENUM para estados y códigos que el código del backend conoce.
-- Tablas para listas que el administrador edita (motivos de reporte,
-- productos de promoción, planes, productos de verificación).
-- Las etiquetas en español viven en el frontend / i18n, no en la base.
-- =====================================================================
SET search_path = app, public;

-- Cuentas
CREATE TYPE user_status        AS ENUM ('pending','active','suspended','blocked','deleted');
CREATE TYPE staff_role         AS ENUM ('superadmin','admin','moderator','finance','support','catalog_editor');
CREATE TYPE agency_status      AS ENUM ('pending','review','verified','rejected','suspended','revoked');
CREATE TYPE agency_kind        AS ENUM ('agency','official_dealer');         -- Agencia / Concesionaria oficial
CREATE TYPE agency_member_role AS ENUM ('owner','admin','seller');
CREATE TYPE member_status      AS ENUM ('invited','active','removed');
CREATE TYPE tax_condition      AS ENUM ('responsable_inscripto','monotributo','exento');
CREATE TYPE auth_token_purpose AS ENUM ('email_verification','password_reset','phone_verification','email_change');
CREATE TYPE session_end_reason AS ENUM ('logout','logout_others','password_change','admin_revoked','expired','suspicious');
CREATE TYPE client_platform    AS ENUM ('web','ios','android','admin','api');

-- Ubicación
CREATE TYPE geo_level          AS ENUM ('country','province','department','locality');

-- Catálogo
CREATE TYPE catalog_status     AS ENUM ('active','inactive');
CREATE TYPE vehicle_type       AS ENUM ('car','light_truck','van','truck','motorcycle','atv','other');
                               -- Auto, Camioneta, Utilitario, Camión, Moto, Cuatriciclo, Otro
CREATE TYPE body_type          AS ENUM ('sedan','hatchback','suv','pickup','coupe','convertible','wagon','van','minivan','chassis','motorcycle','other');
CREATE TYPE fuel_type          AS ENUM ('gasoline','diesel','cng','gasoline_cng','hybrid','plugin_hybrid','electric','other');
CREATE TYPE transmission_type  AS ENUM ('manual','automatic','cvt','automated_manual','other');
CREATE TYPE traction_type      AS ENUM ('front','rear','4x2','4x4','awd');
CREATE TYPE engine_aspiration  AS ENUM ('natural','turbo','supercharged','electric');

-- Vehículo / publicación
CREATE TYPE vehicle_condition  AS ENUM ('new','used');
CREATE TYPE currency_code      AS ENUM ('ARS','USD');
CREATE TYPE identifier_type    AS ENUM ('plate','vin','chassis_number','engine_number');
CREATE TYPE identifier_status  AS ENUM ('declared','pending','verified','rejected');
CREATE TYPE listing_status     AS ENUM ('draft','pending','published','paused','requires_changes','rejected','sold','expired','deleted');
CREATE TYPE image_kind         AS ENUM ('front','rear','left','right','interior','additional');
CREATE TYPE image_storage_provider AS ENUM ('cloudinary','local_dev');
CREATE TYPE image_status       AS ENUM ('uploading','active','replaced','deleted','purge_scheduled','purged');
CREATE TYPE contact_source     AS ENUM ('user_profile','agency','custom');
CREATE TYPE catalog_request_status AS ENUM ('pending','added','rejected');

-- Confianza
CREATE TYPE document_type      AS ENUM ('dni_front','dni_back','cuit','cuit_certificate','green_card','blue_card','title','domain_report','agency_license','agency_other','proof_of_address','payment_receipt','other');
                               -- cédula verde / cédula azul / título / informe de dominio / habilitación comercial ...
CREATE TYPE document_status    AS ENUM ('uploaded','in_review','approved','rejected','expired','deleted');
CREATE TYPE storage_provider   AS ENUM ('s3','r2','gcs','cloudinary_private');
CREATE TYPE verification_subject AS ENUM ('user','agency','vehicle','listing');
CREATE TYPE verification_kind  AS ENUM ('identity','agency','documentation','vehicle_existence','vehicle_data','physical_inspection');
CREATE TYPE verification_product_status AS ENUM ('draft','active','inactive');
CREATE TYPE verification_status AS ENUM ('pending','review','approved','rejected','revoked');
CREATE TYPE review_status      AS ENUM ('published','hidden','removed');
CREATE TYPE report_target      AS ENUM ('listing','user','agency','message','review');
CREATE TYPE report_status      AS ENUM ('pending','reviewing','resolved','rejected');
CREATE TYPE moderation_action_type AS ENUM (
  'listing_approve','listing_request_changes','listing_pause','listing_reactivate','listing_reject','listing_delete',
  'user_suspend','user_block','user_reactivate',
  'agency_verify','agency_reject','agency_suspend','agency_reactivate','agency_revoke',
  'verification_approve','verification_reject','verification_revoke',
  'message_hide','review_hide','review_restore','report_dismiss','report_resolve');

-- Mensajería
CREATE TYPE conversation_status AS ENUM ('open','closed','blocked');
CREATE TYPE participant_side   AS ENUM ('buyer','seller');
CREATE TYPE message_visibility AS ENUM ('visible','hidden_by_moderation');

-- Comercial
CREATE TYPE plan_audience      AS ENUM ('particular','agency');
CREATE TYPE billing_period     AS ENUM ('none','month','year');
CREATE TYPE subscription_status AS ENUM ('pending','active','payment_failed','grace_period','canceled','expired');
CREATE TYPE payment_provider   AS ENUM ('mercadopago','bank_transfer','manual');
CREATE TYPE payment_status     AS ENUM ('pending','submitted','in_process','approved','rejected','canceled','refunded','charged_back');
CREATE TYPE payment_purpose    AS ENUM ('subscription','promotion','verification');
CREATE TYPE provider_event_status AS ENUM ('received','processed','ignored','failed');
CREATE TYPE promotion_type     AS ENUM ('featured_listing','promoted_position','featured_agency','banner_campaign');
CREATE TYPE promotion_status   AS ENUM ('pending','active','paused','finished','canceled');
CREATE TYPE promotion_placement AS ENUM ('home_featured','home_banner','search_top','search_brand_model','agency_directory');
CREATE TYPE promotion_event_type AS ENUM ('created','submitted','approved','activated','paused','resumed','finished','canceled','payment_approved','payment_failed');
CREATE TYPE sale_channel       AS ENUM ('girando','buyer_from_girando','other_channel');
CREATE TYPE financing_type     AS ENUM ('bank_loan','pledge_loan','dealer_financing','savings_plan','other');
                               -- crédito bancario / crédito prendario / financiación propia / plan de ahorro / otro
CREATE TYPE sale_status        AS ENUM ('reported','voided');

-- Comunicación
CREATE TYPE notification_category AS ENUM ('security','account','listing','messages','favorites','applications','payments','subscriptions','verifications','moderation','marketing');
CREATE TYPE notification_channel  AS ENUM ('in_app','email','push');
CREATE TYPE template_status    AS ENUM ('draft','active','archived');
CREATE TYPE email_status       AS ENUM ('pending','sent','failed');

-- Cumplimiento / plataforma
CREATE TYPE consent_type       AS ENUM ('terms','privacy_policy','cookies','marketing_communications');
CREATE TYPE consent_state      AS ENUM ('granted','revoked');
CREATE TYPE policy_doc_type    AS ENUM ('terms','privacy_policy','cookies_policy');
CREATE TYPE actor_type         AS ENUM ('user','staff','system','provider');
CREATE TYPE retention_category AS ENUM ('media','operational','historical','audit');
CREATE TYPE retention_action   AS ENUM ('delete','anonymize','aggregate_then_delete','keep');
CREATE TYPE analytics_event_name AS ENUM (
  'page_view','search','filter_applied',
  'listing_impression','listing_view','listing_favorite','listing_unfavorite','listing_contact','listing_contact_reveal','listing_share',
  'listing_application','listing_created','listing_published','listing_sold',
  'promotion_impression','promotion_view','promotion_click',
  'agency_view');
