// Girando Admin — lógica conectada a /api/admin (misma API y misma base que la App).
// Los permisos los decide el backend (staff_roles en PostgreSQL). Esta pantalla solo muestra
// lo que la API devuelve y pide acciones; si el rol no alcanza, la API responde 403.
const API = window.GirandoAPI;
const L = (g, v) => API.label(g, v);
const B = { ok: 'tg tg-ok', warn: 'tg tg-warn', bad: 'tg tg-bad', info: 'tg tg-info', muted: 'tg tg-muted' };
const CHIP = (on) => on ? 'border:1px solid #14171f;background:#14171f;color:#fff;' : 'border:1px solid #dde1e8;background:#fff;color:#14171f;';
const BTN = { primary: 'border:0;background:#1652f0;color:#fff;', danger: 'border:1px solid #f1c4c4;background:#fff;color:#a32020;', plain: 'border:1px solid #dde1e8;background:#fff;color:#14171f;' };
const PAGE = 25;
const errMsg = (e) => (e && e.message) || 'Ocurrió un error.';
const safeImg = (u) => (typeof u === 'string' && (/^\/media\/[A-Za-z0-9/_\-.]+$/.test(u) || /^https:\/\/res\.cloudinary\.com\/[A-Za-z0-9/_\-.,:]+$/.test(u))) ? u : '';
const d = (s) => s ? API.date(s) : '—';
const dt = (s) => s ? API.dateTime(s) : '—';
const vname = (i) => [i.brand, i.model, i.version, i.year].filter(Boolean).join(' ') || i.title || 'Sin datos';

const LISTING_ST = { draft: ['Borrador', B.muted], pending: ['Pendiente', B.warn], published: ['Publicada', B.ok], paused: ['Pausada', B.muted], requires_changes: ['Requiere cambios', B.warn], rejected: ['Rechazada', B.bad], sold: ['Vendida', B.info], expired: ['Expirada', B.bad], deleted: ['Eliminada', B.bad] };
const USER_ST = { active: ['Activo', B.ok], pending: ['Pendiente', B.warn], suspended: ['Suspendido', B.bad], blocked: ['Bloqueado', B.bad], deleted: ['Eliminado', B.muted] };
const AGENCY_ST = { pending: ['Sin verificar', B.muted], review: ['Verificación en revisión', B.warn], verified: ['Verificada', B.ok], rejected: ['Rechazada', B.bad], suspended: ['Suspendida', B.bad], revoked: ['Revocada', B.muted] };
const VER_ST = { pending: ['Pendiente', B.warn], review: ['En revisión', B.warn], approved: ['Aprobada', B.ok], rejected: ['Rechazada', B.bad], revoked: ['Revocada', B.muted] };
const REP_ST = { pending: ['Pendiente', B.warn], reviewing: ['En revisión', B.warn], resolved: ['Resuelto', B.ok], rejected: ['Descartado', B.muted] };
const SUB_ST = { pending: ['Pendiente', B.warn], active: ['Activa', B.ok], payment_failed: ['Pago rechazado', B.bad], grace_period: ['En período de gracia', B.warn], canceled: ['Cancelada', B.muted], expired: ['Expirada', B.bad] };
const PAY_ST = { pending: ['Pendiente', B.warn], submitted: ['Informado', B.warn], in_process: ['En proceso', B.warn], approved: ['Aprobado', B.ok], rejected: ['Rechazado', B.bad], canceled: ['Cancelado', B.muted], refunded: ['Reintegrado', B.muted], charged_back: ['Contracargo', B.bad] };
const MAIL_ST = { pending: ['Pendiente', B.warn], sent: ['Enviado', B.ok], failed: ['Fallido', B.bad], skipped: ['Omitido', B.muted] };
const chips = (m) => [['Todos', null], ...Object.entries(m).map(([k, v]) => [v[0], k])];

const PROMO_ST = { pending: ['Pendiente', B.warn], active: ['Activa', B.ok], paused: ['Pausada', B.muted], finished: ['Finalizada', B.info], canceled: ['Cancelada', B.bad] };
const HB_ST = { draft: ['Borrador', B.muted], active: ['Activo', B.ok], archived: ['Archivado', B.muted] };
const PROMO_TYPE = { featured_listing: 'Publicación destacada', promoted_position: 'Posición promocionada', featured_agency: 'Agencia destacada', banner_campaign: 'Banner (Publicidad)' };
const PLACEMENT = { home_featured: 'Home · Destacados', home_banner: 'Home · Banner', search_top: 'Búsqueda · Arriba', search_brand_model: 'Búsqueda por marca/modelo', agency_directory: 'Directorio de agencias' };
const HB_KIND = { hero: 'Portada (hero)', announcement: 'Aviso', cta: 'Llamado a la acción' };
const HB_TARGET = { listado: 'Ver vehículos', publicar: 'Publicar', planes: 'Planes', registro: 'Crear cuenta' };
const PROVIDER = { mercadopago: 'Mercado Pago', manual: 'Asignado por Girando', bank_transfer: 'Transferencia' };
const VSTATE = { none: ['Sin solicitud', B.muted], pending: ['Solicitud pendiente', B.warn], review: ['En revisión', B.warn], verified: ['Verificada', B.ok], rejected: ['Rechazada', B.bad], suspended: ['Suspendida', B.bad], revoked: ['Revocada', B.muted] };
const EVENT_ES = { page_view: 'Páginas vistas', search: 'Búsquedas', filter_applied: 'Filtros aplicados', listing_impression: 'Impresiones de publicaciones', listing_view: 'Vistas de publicaciones',
  listing_favorite: 'Favoritos agregados', listing_unfavorite: 'Favoritos quitados', listing_contact: 'Consultas a vendedores', listing_contact_reveal: 'Datos de contacto vistos', listing_share: 'Compartidas',
  listing_application: 'Postulaciones', listing_created: 'Publicaciones creadas', listing_published: 'Publicaciones aprobadas', listing_sold: 'Ventas informadas',
  promotion_impression: 'Impresiones de promociones', promotion_view: 'Vistas de promociones', promotion_click: 'Clics en promociones', agency_view: 'Visitas a perfiles de agencia',
  external_click: 'Clics a webs/redes de agencias', message_sent: 'Mensajes enviados', subscription_activated: 'Suscripciones activadas', payment_approved: 'Pagos aprobados' };
const money = (n) => API.money(n || 0, 'ARS');
const isoDay = (v, end) => v ? v + (end ? 'T23:59:59-03:00' : 'T00:00:00-03:00') : null;
const S2 = (c, k, dflt) => (c.state[k] == null ? dflt : c.state[k]);
const dayVal = (s) => s ? String(s).slice(0, 10) : '';

// Secciones: columnas, filtros y acciones. `server: true` → la API filtra y pagina.
const SECTIONS = {
  dashboard: { title: 'Resumen', columns: ['Publicación', 'Código', 'Enviada', 'Estado'] },
  usuarios: { title: 'Usuarios', columns: ['Usuario', 'Email', 'Rol', 'Alta', 'Estado'], statuses: chips(USER_ST).filter(c => c[1] !== 'deleted'), server: true, url: '/admin/users' },
  agencias: { title: 'Agencias', columns: ['Agencia', 'CUIT', 'Plan', 'Publicadas / inventario', 'Solicitud', 'Estado'], statuses: chips({ pending: AGENCY_ST.pending, verified: AGENCY_ST.verified, rejected: AGENCY_ST.rejected, suspended: AGENCY_ST.suspended, revoked: AGENCY_ST.revoked }), server: true, url: '/admin/agencies' },
  publicaciones: { title: 'Publicaciones', columns: ['Publicación', 'Vendedor', 'Precio', 'Fecha', 'Alertas', 'Estado'], statuses: chips(LISTING_ST), server: true, url: '/admin/listings' },
  catalogo: { title: 'Catálogo de vehículos' },
  negocio: { title: 'Negocio' },
  finanzas: { title: 'Finanzas' },
  ventas: { title: 'Ventas y estadísticas' },
  planes: { title: 'Planes' },
  suscripciones: { title: 'Suscripciones', columns: ['Agencia', 'Plan', 'Estado', 'Alta', 'Fin del período', 'Monto', 'Método'], statuses: chips(SUB_ST), url: '/admin/subscriptions', statusCol: 2 },
  pagos: { title: 'Pagos', columns: ['Agencia', 'Concepto', 'Monto', 'Método', 'Fecha', 'Estado'], statuses: chips(PAY_ST), url: '/admin/payments' },
  promociones: { title: 'Promociones', columns: ['Tipo', 'Destino', 'Ubicación', 'Vigencia', 'Precio', 'Pago', 'Estado'], statuses: chips(PROMO_ST), url: '/admin/promotions' },
  home: { title: 'Contenido de la Home', columns: ['Tipo', 'Título', 'Botón', 'Vigencia', 'Orden', 'Estado'], statuses: chips({ draft: HB_ST.draft, active: HB_ST.active }), url: '/admin/home-blocks' },
  verificaciones: { title: 'Verificaciones', columns: ['Solicitante', 'Tipo', 'Revisión', 'Fecha', 'Estado'], statuses: chips(VER_ST), url: '/admin/verifications' },
  reportes: { title: 'Reportes y denuncias', columns: ['Motivo', 'Publicación', 'Detalle', 'Fecha', 'Estado'], statuses: chips(REP_ST), url: '/admin/reports' },
  envios: { title: 'Cola de envíos', columns: ['Plantilla', 'Destinatario', 'Evento', 'Fecha', 'Estado'], statuses: chips(MAIL_ST), url: '/admin/emails' },
  auditoria: { title: 'Auditoría', columns: ['Actor', 'Acción', 'Entidad', 'Motivo', 'Fecha y hora'], server: true, url: '/admin/audit', page: 50 },
  retencion: { title: 'Retención de datos' },
  configuracion: { title: 'Integraciones' },
};
// Quién ve cada sección. Es solo para no mostrar lo que el backend igual rechazaría (403):
// la validación real está en require_roles() de cada endpoint y en RLS. Superadmin entra a todo.
const OPS = ['moderator', 'admin'];
const FIN = ['finance'];
const SUP = [];
const ACCESS = { dashboard: null, publicaciones: OPS, agencias: OPS, verificaciones: OPS, reportes: OPS, usuarios: ['admin', 'support'], catalogo: ['catalog_editor', 'admin'],
  negocio: FIN, finanzas: FIN, ventas: FIN, planes: FIN, suscripciones: FIN, pagos: FIN,
  promociones: SUP, home: SUP, envios: SUP, auditoria: SUP, retencion: SUP, configuracion: SUP };
const NAV_GROUPS = [['Operación', [['dashboard', 'Resumen'], ['publicaciones', 'Publicaciones'], ['agencias', 'Agencias'], ['usuarios', 'Usuarios'], ['catalogo', 'Catálogo']]],
  ['Confianza', [['verificaciones', 'Verificaciones'], ['reportes', 'Reportes']]],
  ['Negocio', [['negocio', 'Visión general'], ['finanzas', 'Finanzas'], ['planes', 'Planes'], ['suscripciones', 'Suscripciones'], ['pagos', 'Pagos'], ['promociones', 'Promociones'], ['ventas', 'Ventas']]],
  ['Contenido', [['home', 'Home'], ['envios', 'Cola de envíos']]],
  ['Sistema', [['auditoria', 'Auditoría'], ['retencion', 'Retención de datos'], ['configuracion', 'Integraciones']]]];
const PERIODS = [['dia', 'Día', 1], ['semana', 'Semana', 7], ['mes', 'Mes', 30], ['trimestre', 'Trimestre', 90], ['año', 'Año', 365]];
const VT = [['car', 'Auto'], ['light_truck', 'Camioneta'], ['van', 'Utilitario'], ['truck', 'Camión'], ['motorcycle', 'Moto'], ['atv', 'Cuatriciclo']];
const BODY = ['sedan', 'hatchback', 'suv', 'pickup', 'coupe', 'convertible', 'wagon', 'van', 'minivan', 'chassis', 'motorcycle', 'other'];
const TRANS = ['manual', 'automatic', 'cvt', 'automated_manual', 'other'];
const TRACTION = ['front', 'rear', '4x2', '4x4', 'awd'];
const FUELS = ['gasoline', 'diesel', 'cng', 'gasoline_cng', 'hybrid', 'plugin_hybrid', 'electric', 'other'];
const UNIT_ES = { day: 'días', days: 'días', mon: 'meses', mons: 'meses', year: 'años', years: 'años' };
const UNIT_API = { day: 'days', days: 'days', mon: 'months', mons: 'months', year: 'years', years: 'years' };

class Component extends DCLogic {
  state = { authChecked: false, me: null, loginEmail: '', loginPass: '', loginError: null, loginBusy: false,
    section: 'dashboard', statusFilter: {}, query: '', page: {}, data: {}, dash: null, toast: null, pending: null, pendingReason: '', detail: null,
    period: 'mes', sales: null, business: null, finance: null, finMonths: 6, promoProducts: [], agencyPlans: [], pendingChoice: '',
    pf: { type: 'featured_listing', placement: 'home_featured', listing_code: '', agency_id: '', advertiser_name: '', link_url: '', start: '', end: '', price: '0', priority: '0', label: 'Patrocinado', notes: '' }, pfError: null,
    hf: { id: null, kind: 'announcement', title: '', body: '', cta_label: '', cta_target: '', sort_order: '0', start: '', end: '', status: 'draft' }, hfError: null, plans: [], plansDirty: {}, retention: [], retentionDirty: {}, mediaQueue: [], integrations: null,
    cat: { brands: [], models: [], gens: [], versions: {}, engines: [] }, selBrand: null, selModel: null, selGen: '',
    nf: { brand: '', model: '', modelType: 'car', gen: '', genFrom: '', ver: '', verBody: 'sedan', verTrans: 'manual', verTraction: 'front', verDoors: '4', verEngine: '', engine: '', engineFuel: 'gasoline' } };

  componentDidMount() {
    this.checkSession();
    // Enter/Espacio activan elementos no nativos con role=button; Escape cierra el menú lateral en mobile
    this._key = (e) => {
      if (e.key === 'Escape' && this.state.navOpen) { this.setState({ navOpen: false }); return; }
      if (e.key !== 'Enter' && e.key !== ' ') return;
      const el = e.target; if (!el || !el.getAttribute || el.getAttribute('role') !== 'button' || /^(BUTTON|A|INPUT|SELECT|TEXTAREA)$/.test(el.tagName)) return;
      e.preventDefault(); el.click();
    };
    document.addEventListener('keydown', this._key);
  }
  componentWillUnmount() { document.removeEventListener('keydown', this._key); }
  showToast(m) { clearTimeout(this._t); this.setState({ toast: m }); this._t = setTimeout(() => this.setState({ toast: null }), 2600); }
  async checkSession() {
    try { const me = await API.get('/me/profile'); this.setState({ me, authChecked: true }); if ((me.staff_roles || []).length) this.open(this.can(this.state.section) ? this.state.section : 'dashboard'); }
    catch (e) { this.setState({ me: null, authChecked: true }); }
  }
  async login() {
    const S = this.state;
    this.setState({ loginBusy: true, loginError: null });
    try { await API.post('/auth/login', { email: S.loginEmail.trim().toLowerCase(), password: S.loginPass }); this.setState({ loginPass: '' }); await this.checkSession(); }
    catch (e) { this.setState({ loginError: errMsg(e) }); } finally { this.setState({ loginBusy: false }); }
  }
  async logout() { try { await API.post('/auth/logout'); } catch (e) { /* noop */ } this.setState({ me: null, data: {}, dash: null }); }
  handle(e) { if (e && e.status === 401) { this.setState({ me: null }); return; } this.showToast(errMsg(e)); }

  // ------------------------------------------------------------------ carga de datos
  roles() { return (this.state.me && this.state.me.staff_roles) || []; }
  hasRole(...r) { const mine = this.roles(); return mine.includes('superadmin') || r.some(x => mine.includes(x)); }
  can(section) { const need = ACCESS[section]; return need === null || need === undefined ? true : this.hasRole(...need); }
  open(section) { if (!this.can(section)) { this.showToast('Tu rol no tiene acceso a esta sección'); return; } this.setState({ section, query: '', navOpen: false }, () => this.load(section)); try { window.scrollTo(0, 0); } catch (e) { /* noop */ } }
  async load(section) {
    const S = this.state; const sec = SECTIONS[section];
    if (!sec) return;
    try {
      if (section === 'dashboard') { this.setState({ dash: await API.get('/admin/dashboard') }); return; }
      if (section === 'catalogo') { await Promise.all([this.loadBrands(), this.loadEngines()]); return; }
      if (section === 'ventas') { const days = (PERIODS.find(p => p[0] === S.period) || PERIODS[2])[2]; this.setState({ sales: await API.get('/admin/sales-stats', { days }) }); return; }
      if (section === 'planes') { const r = await API.get('/admin/plans'); this.setState({ plans: r.items, plansDirty: {} }); return; }
      if (section === 'retencion') { const [r, m] = await Promise.all([API.get('/admin/retention'), API.get('/admin/media-queue')]); this.setState({ retention: r.items, retentionDirty: {}, mediaQueue: m.items }); return; }
      if (section === 'configuracion') { this.setState({ integrations: await API.get('/integrations/status') }); return; }
      if (section === 'negocio') { this.setState({ business: await API.get('/admin/business') }); return; }
      if (section === 'finanzas') { this.setState({ finance: await API.get('/admin/finance/summary', { months: S.finMonths }) }); return; }
      if (section === 'promociones') { const [r, ags] = await Promise.all([API.get('/admin/promotions'), API.get('/admin/agencies', { page_size: 100 })]); this.setState(s => ({ promoProducts: r.products || [], data: { ...s.data, promociones: r, agencias: ags } })); return; }
      if (!sec.url) return;
      const params = {};
      if (sec.server) {
        const size = sec.page || PAGE; params.page = S.page[section] || 1; params.page_size = size;
        const f = S.statusFilter[section]; if (f) params.status = f;
        if (S.query.trim() && section !== 'auditoria') params.q = S.query.trim();
      }
      const r = await API.get(sec.url, params);
      this.setState(s => ({ data: { ...s.data, [section]: r } }));
    } catch (e) { this.handle(e); }
  }
  async act(fn, okMsg, reload) {
    try { await fn(); if (okMsg) this.showToast(okMsg); } catch (e) { this.handle(e); }
    this.setState({ pending: null, pendingReason: '' });
    await this.load(reload || this.state.section);
    // Detalle con recarga (publicación, verificación) se refresca; el resto se cierra para no mostrar datos viejos
    if (this.state.detail) { if (this.state.detail.reload) this.state.detail.reload(); else this.setState({ detail: null }); }
    if (this.state.section !== 'dashboard') API.get('/admin/dashboard').then(dash => this.setState({ dash })).catch(() => {});
  }
  ask(title, run, opts) { this.setState({ pending: { title, run, label: 'Motivo', hint: 'Queda registrado en Auditoría con tu usuario, la fecha y el motivo. El usuario lo ve en su notificación.', cta: 'Confirmar', options: null, ...(opts || {}) }, pendingReason: (opts && opts.initial) || '', pendingChoice: (opts && opts.options && opts.options[0] && opts.options[0].value) || '' }); }

  // ------------------------------------------------------------------ acciones por entidad
  listingActs(l) {
    const post = (a, reason) => this.act(() => API.post('/admin/listings/' + l.id + '/' + a, reason ? { reason } : {}), 'Listo: ' + vname(l));
    const withReason = (label, a, danger) => ({ label, danger, onRun: () => this.ask(label + ': ' + vname(l), (r) => post(a, r)) });
    const direct = (label, a) => ({ label, primary: true, onRun: () => post(a) });
    return ({ pending: [direct('Aprobar', 'approve'), withReason('Solicitar cambios', 'request_changes'), withReason('Rechazar', 'reject', true)],
      published: [withReason('Solicitar cambios', 'request_changes'), withReason('Pausar', 'pause'), withReason('Eliminar', 'delete', true)],
      paused: [direct('Reactivar', 'reactivate'), withReason('Eliminar', 'delete', true)], rejected: [withReason('Eliminar', 'delete', true)] })[l.status] || [];
  }
  userActs(u) {
    const post = (a, reason) => this.act(() => API.post('/admin/users/' + u.id + '/' + a, reason ? { reason } : {}), 'Listo: ' + (u.display_name || u.email));
    const withReason = (label, a) => ({ label, danger: true, onRun: () => this.ask(label + ': ' + (u.display_name || u.email), (r) => post(a, r)) });
    if (this.state.me && u.id === this.state.me.id) return [];
    const roleAct = this.hasRole('superadmin') ? [{ label: 'Roles de staff', onRun: () => this.manageRoles(u) }] : [];
    return (({ active: [withReason('Suspender', 'suspend'), withReason('Bloquear', 'block')], pending: [withReason('Suspender', 'suspend')],
      suspended: [{ label: 'Reactivar', primary: true, onRun: () => post('reactivate') }, withReason('Bloquear', 'block')], blocked: [{ label: 'Reactivar', primary: true, onRun: () => post('reactivate') }] })[u.status] || []).concat(roleAct);
  }
  manageRoles(u) {
    const ROLE_ES = { admin: 'Admin (operación)', moderator: 'Moderación', support: 'Soporte', finance: 'Finanzas (solo lectura comercial)', catalog_editor: 'Catálogo' };
    const has = String(u.staff_roles || '').split(',').filter(Boolean);
    const options = Object.entries(ROLE_ES).map(([r, l]) => has.includes(r) ? { value: 'revoke:' + r, label: 'Quitar: ' + l } : { value: 'grant:' + r, label: 'Dar: ' + l });
    this.ask('Roles de staff: ' + (u.display_name || u.email), (reason, choice) => { const [op, role] = String(choice).split(':');
      this.act(() => API.post('/admin/users/' + u.id + '/roles', { role, grant: op === 'grant' }), (op === 'grant' ? 'Rol asignado: ' : 'Rol quitado: ') + ROLE_ES[role]); },
    { options, optionLabel: 'Cambio', label: 'Motivo', cta: 'Aplicar', tone: 'primary', hint: 'Super Admin no se asigna desde el panel (se crea por consola). El cambio rige desde el próximo pedido del usuario y queda en Auditoría.' });
  }
  agencyStatus(a) { return (a.status === 'pending' && ['pending', 'review'].includes(a.verification_status)) ? 'review' : a.status; }
  agencyActs(a, withPlan) {
    const post = (x, reason) => this.act(() => API.post('/admin/agencies/' + a.id + '/' + x, reason ? { reason } : {}), 'Listo: ' + a.trade_name);
    const withReason = (label, x) => ({ label, danger: true, onRun: () => this.ask(label + ': ' + a.trade_name, (r) => post(x, r)) });
    const open = ['pending', 'review'].includes(a.verification_status);
    const acts = [];
    // Verificar/rechazar: moderación o admin. Suspender, revocar y reactivar: solo admin (el backend lo exige igual).
    if (open) acts.push({ label: 'Verificar', primary: true, onRun: () => this.ask('Aprobar verificación: ' + a.trade_name, (r) => post('verify', r), { label: 'Nota de aprobación', cta: 'Aprobar', tone: 'primary', hint: 'Con esta aprobación la App muestra el sello "Verificada". Revisá antes el checklist y dejá la evidencia. Queda en Auditoría con tu usuario.' }) }, withReason('Rechazar', 'reject'));
    if (this.hasRole('admin')) {
      if (a.status === 'verified') acts.push(withReason('Suspender', 'suspend'), withReason('Revocar verificación', 'revoke'));
      else if (a.status === 'pending' && !open) acts.push(withReason('Suspender', 'suspend'));
      if (a.status === 'suspended') acts.push({ label: 'Reactivar', primary: true, onRun: () => post('reactivate') });
    }
    if (withPlan && this.hasRole('superadmin')) {
      acts.push({ label: 'Asignar plan', onRun: () => this.grantPlan(a) });
      if (a.plan_provider === 'manual') acts.push({ label: 'Terminar plan asignado', danger: true, onRun: () => this.ask('Terminar plan: ' + a.trade_name, (r) => this.act(() => API.post('/admin/agencies/' + a.id + '/plan/end', { reason: r }), 'Plan terminado. Lo que excede el plan gratuito quedó pausado.'), { hint: 'La agencia vuelve al plan gratuito. Las publicaciones que excedan el límite pasan a inventario (pausadas). Queda en Auditoría.' }) });
    }
    return acts;
  }
  async grantPlan(a) {
    try {
      const r = await API.get('/admin/plans');
      const opts = r.items.filter(p => p.audience === 'agency' && p.is_active).map(p => ({ value: p.id, label: p.name + ' · hasta ' + p.max_active_listings + ' publicadas' }));
      if (!opts.length) { this.showToast('No hay planes de agencia activos'); return; }
      this.ask('Asignar plan: ' + a.trade_name, (notes, planId) => this.act(() => API.post('/admin/agencies/' + a.id + '/plan', { plan_id: planId, notes }), 'Plan asignado a ' + a.trade_name),
        { label: 'Motivo (convenio, cortesía, prueba)', cta: 'Asignar', tone: 'primary', options: opts, optionLabel: 'Plan',
          hint: 'Sin cobro y sin Mercado Pago: dura un mes calendario y no se renueva solo. No reemplaza una suscripción paga vigente. Queda en Auditoría.' });
    } catch (e) { this.handle(e); }
  }
  openAgency(a) {
    const st = AGENCY_ST[this.agencyStatus(a)] || [a.status, B.muted];
    const vs = VSTATE[a.verification_state] || [a.verification_state || '—'];
    const acts = this.agencyActs(a, true);
    if (a.verification_id) acts.push({ label: 'Ver verificación', onRun: () => this.openVerification(a.verification_id) });
    this.openKV(a.trade_name, st[0], st[1], [['Razón social', a.legal_name], ['CUIT', a.cuit], ['Ubicación', a.locality], ['Responsable', a.owner_name],
      ['Plan vigente', (a.plan_name || 'Gratuito') + (a.plan_provider ? ' · ' + (PROVIDER[a.plan_provider] || a.plan_provider) : '')],
      ['Publicadas', a.published], ['Inventario (incluye pausadas y borradores)', a.inventory], ['Estado de verificación', vs[0]],
      ['Verificada el', dt(a.verified_at)], ['Motivo de estado', a.status_reason], ['Alta', dt(a.created_at)], ['Página pública', a.slug ? '/#a/' + a.slug : '—']], acts);
  }
  async openVerification(id) {
    const reload = async () => {
      try {
        const v = await API.get('/admin/verifications/' + id);
        const st = VER_ST[v.status] || [v.status, B.muted];
        const openV = ['pending', 'review'].includes(v.status);
        const patch = (body, msg) => this.act(() => API.patch('/admin/verifications/' + id, body), msg, 'verificaciones');
        const acts = [];
        if (v.status === 'pending') acts.push({ label: 'Tomar revisión', primary: true, onRun: () => patch({ start_review: true, assign_to_me: true }, 'Revisión iniciada y asignada a vos') });
        if (openV && v.agency_id) acts.push(...this.agencyActs({ id: v.agency_id, trade_name: v.trade_name, status: 'pending', verification_status: v.status }));
        this.setState(s => ({ detail: { reload, code: v.product, title: v.trade_name || 'Verificación', status: st[0], statusClass: st[1], reason: v.decision_reason, images: [], description: '',
          rows: [['Razón social', v.legal_name], ['CUIT', v.cuit], ['Localidad', v.locality], ['Sitio web', v.website_url], ['Teléfono', v.phone_e164], ['Email', v.agency_email],
            ['Estado de la agencia', (VSTATE[v.agency_state] || [v.agency_state])[0]], ['Solicitó', v.requested_by_name], ['Asignada a', v.assigned_to_name], ['Revisó', v.reviewer_name],
            ['Solicitada', dt(v.created_at)], ['Revisión iniciada', dt(v.review_started_at)], ['Decisión', dt(v.decided_at)], ['Vence', d(v.expires_at)]].map(([k, x]) => ({ k, v: x == null || x === '' ? '—' : String(x) })),
          history: (v.history || []).map(h => ({ when: dt(h.at), what: h.action + (h.actor_role ? ' · ' + h.actor_role : '') + (h.reason ? ' · ' + h.reason : '') })), acts,
          checklist: (v.items || []).map(it => ({ label: it.label, mark: it.done ? '✓' : '', checked: it.done ? 'true' : 'false', style: it.done ? 'background:#e6f4ec;border-color:#9fd3b4;color:#14532d;' : '',
            onToggle: openV ? () => patch({ checklist: (v.items || []).map(x => ({ key: x.key, done: x.key === it.key ? !x.done : x.done, note: x.note || null })) }, it.done ? 'Desmarcado' : 'Marcado como revisado') : () => this.showToast('La verificación ya tiene una decisión') })),
          checklistNote: v.public_disclaimer || 'Criterios preliminares: la regla final de verificación todavía no está definida. El sello solo aparece con una aprobación real.',
          canEvidence: openV, evidence: S2(this, 'evidenceDraft', v.evidence_notes || ''),
          saveEvidence: () => patch({ evidence_notes: (this.state.evidenceDraft || '').trim() || null }, 'Notas de evidencia guardadas') } }));
      } catch (e) { this.handle(e); }
    };
    this.setState({ evidenceDraft: null });
    reload();
  }
  promoActs(p) {
    const post = (a, reason) => this.act(() => API.post('/admin/promotions/' + p.id + '/' + a, reason ? { reason } : {}), 'Promoción actualizada');
    const withReason = (label, a, danger) => ({ label, danger, onRun: () => this.ask(label + ' promoción', (r) => post(a, r)) });
    return ({ pending: [{ label: 'Activar', primary: true, onRun: () => post('activate') }, withReason('Cancelar', 'cancel', true)],
      active: [withReason('Pausar', 'pause'), { label: 'Finalizar', onRun: () => post('finish') }, withReason('Cancelar', 'cancel', true)],
      paused: [{ label: 'Reanudar', primary: true, onRun: () => post('resume') }, { label: 'Finalizar', onRun: () => post('finish') }, withReason('Cancelar', 'cancel', true)] })[p.status] || [];
  }
  homeBody(h, status) {
    return { kind: h.kind, title: h.title, body: h.body || null, image_public_id: h.image_public_id || null, cta_label: h.cta_label || null, cta_target: h.cta_target || null,
      sort_order: Number(h.sort_order || 0), starts_at: h.starts_at || null, ends_at: h.ends_at || null, status: status || h.status };
  }
  homeActs(h) {
    const put = (status, msg) => this.act(() => API.put('/admin/home-blocks/' + h.id, this.homeBody(h, status)), msg);
    const acts = [{ label: 'Editar', onRun: () => this.setState({ hf: { id: h.id, kind: h.kind, title: h.title, body: h.body || '', cta_label: h.cta_label || '', cta_target: h.cta_target || '', sort_order: String(h.sort_order || 0), start: dayVal(h.starts_at), end: dayVal(h.ends_at), status: h.status }, hfError: null }, () => { try { window.scrollTo({ top: 0, behavior: 'smooth' }); } catch (e) { /* noop */ } }) }];
    if (h.status !== 'active') acts.push({ label: 'Activar', primary: true, onRun: () => put('active', 'Bloque activo en la Home') });
    if (h.status === 'active') acts.push({ label: 'Pasar a borrador', onRun: () => put('draft', 'Bloque fuera de la Home') });
    acts.push({ label: 'Archivar', danger: true, onRun: () => put('archived', 'Bloque archivado') });
    return acts;
  }
  async openListing(l) {
    const reload = async () => {
      try {
        const x = await API.get('/admin/listings/' + l.id);
        const st = LISTING_ST[x.status] || [x.status, B.muted];
        this.setState({ detail: { reload, code: x.public_code, title: vname(x), status: st[0], statusClass: st[1], reason: x.status_reason,
          images: (x.images || []).map(i => ({ url: safeImg(i.url) })).filter(i => i.url), description: x.description || 'Sin descripción.',
          rows: [['Título del vendedor', x.title || '—'], ['Precio', API.money(x.price_amount, x.currency)], ['Kilómetros', API.km(x.km)], ['Motor', x.engine || '—'], ['Combustible', L('fuel', x.fuel)],
            ['Transmisión', L('transmission', x.transmission)], ['Ubicación', [x.locality, x.province].filter(Boolean).join(', ') || '—'], ['Vendedor', x.agency_name || (x.owner && (x.owner.display_name + ' · ' + x.owner.email)) || '—'],
            ['Estado del usuario', x.owner ? L('user_status', x.owner.status) : '—'], ['Financiable', x.is_financeable ? 'Sí' : 'No'], ['Video', x.video_url || '—'], ['Enviada', dt(x.submitted_at)], ['Publicada', dt(x.published_at)], ['Vence', d(x.expires_at)]].map(([k, v]) => ({ k, v })),
          history: [...(x.moderation || []).map(m => ({ when: dt(m.created_at), what: 'Moderación: ' + m.action + (m.reason ? ' · ' + m.reason : '') })), ...(x.history || []).slice().reverse().map(h => ({ when: dt(h.created_at), what: (L('status', h.from_status) || '—') + ' → ' + L('status', h.to_status) + (h.reason ? ' · ' + h.reason : '') }))],
          acts: this.listingActs(x) } });
      } catch (e) { this.handle(e); }
    };
    reload();
  }
  openKV(title, status, statusClass, rows, acts) { this.setState({ detail: { title, code: '', status, statusClass, reason: null, images: [], description: '', rows: rows.map(([k, v]) => ({ k, v: v == null || v === '' ? '—' : String(v) })), history: [], acts: acts || [] } }); }

  // ------------------------------------------------------------------ catálogo
  async loadBrands() { const r = await API.get('/admin/catalog/brands'); this.setState(s => ({ cat: { ...s.cat, brands: r.items } })); const b = this.state.selBrand || (r.items[0] && r.items[0].id); if (b) await this.selectBrand(b); }
  async loadEngines() { const r = await API.get('/admin/catalog/engines'); this.setState(s => ({ cat: { ...s.cat, engines: r.items }, nf: { ...s.nf, verEngine: s.nf.verEngine || (r.items[0] && r.items[0].id) || '' } })); }
  async selectBrand(id) {
    const r = await API.get('/admin/catalog/models', { parent_id: id });
    this.setState(s => ({ selBrand: id, cat: { ...s.cat, models: r.items } }));
    const m = r.items.find(x => x.id === this.state.selModel) || r.items[0];
    if (m) await this.selectModel(m.id); else this.setState(s => ({ selModel: null, cat: { ...s.cat, gens: [], versions: {} } }));
  }
  async selectModel(id) {
    const r = await API.get('/admin/catalog/generations', { parent_id: id });
    const vs = await Promise.all(r.items.map(g => API.get('/admin/catalog/versions', { parent_id: g.id })));
    const versions = {}; r.items.forEach((g, i) => { versions[g.id] = vs[i].items; });
    this.setState(s => ({ selModel: id, selGen: r.items.some(g => g.id === s.selGen) ? s.selGen : ((r.items[0] || {}).id || ''), cat: { ...s.cat, gens: r.items, versions } }));
  }
  async catReload() { if (this.state.selModel) await this.selectModel(this.state.selModel); }
  catToggle(level, it, after) { return (e) => { if (e) e.stopPropagation(); this.act(() => API.patch('/admin/catalog/' + level + '/' + it.id, { status: it.status === 'active' ? 'inactive' : 'active' }), (it.status === 'active' ? 'Desactivado: ' : 'Activado: ') + it.name, 'none').then(after); }; }
  catRename(level, it, after) { return (e) => { if (e) e.stopPropagation(); this.ask('Editar nombre: ' + it.name, (name) => this.act(() => API.patch('/admin/catalog/' + level + '/' + it.id, { name }), 'Nombre actualizado', 'none').then(after), { label: 'Nombre', hint: 'Se actualiza en la App y en las publicaciones que lo usan. Queda en Auditoría.', cta: 'Guardar', initial: it.name }); }; }

  // ================================================================== render
  renderVals() {
    const S = this.state; const me = S.me; const isStaff = !!(me && (me.staff_roles || []).length);
    const section = S.section; const sec = SECTIONS[section] || SECTIONS.dashboard;
    const filt = S.statusFilter[section] || null; const q = S.query.trim().toLowerCase();
    const setNf = (k) => (e) => { const v = e.target.value; this.setState(s => ({ nf: { ...s.nf, [k]: v } })); };

    // ---- filas de la tabla
    let rows = []; let total = 0;
    const raw = S.data[section] || { items: [], total: 0 };
    const mk = (id, vals, st, acts, onView) => ({ id, vals, st, acts: acts || [], onView });
    if (section === 'dashboard') {
      rows = ((S.dash && S.dash.moderation_queue) || []).map(l => mk(l.id, [vname(l), l.public_code, dt(l.submitted_at)], LISTING_ST.pending, this.listingActs({ ...l, status: 'pending' }), () => this.openListing(l)));
    } else if (section === 'usuarios') {
      rows = raw.items.map(u => mk(u.id, [u.display_name || '—', u.email, u.staff_roles ? 'Staff: ' + u.staff_roles : (u.agencies > 0 ? 'Agencia' : 'Usuario'), d(u.created_at)], USER_ST[u.status] || [u.status, B.muted], this.userActs(u),
        () => this.openKV(u.display_name || u.email, (USER_ST[u.status] || [u.status])[0], (USER_ST[u.status] || [0, B.muted])[1], [['Email', u.email], ['Email verificado', u.email_verified ? 'Sí' : 'No'], ['Identidad verificada', u.identity_verified ? 'Sí' : 'No'], ['Roles de staff', u.staff_roles || 'Ninguno'], ['Agencias', u.agencies], ['Publicaciones activas', u.active_listings], ['Alta', dt(u.created_at)], ['Último ingreso', dt(u.last_login_at)], ['Motivo de estado', u.status_reason]], this.userActs(u))));
    } else if (section === 'agencias') {
      rows = raw.items.map(a => { const st = AGENCY_ST[this.agencyStatus(a)] || [a.status, B.muted];
        return mk(a.id, [a.trade_name, a.cuit ? a.cuit.replace(/^(\d{2})(\d{8})(\d)$/, '$1-$2-$3') : '—', (a.plan_name || 'Gratuito') + (a.plan_provider === 'manual' ? ' · asignado' : ''), a.published + ' / ' + a.inventory, d(a.verification_requested_at)], st, this.agencyActs(a), () => this.openAgency(a)); });
    } else if (section === 'publicaciones') {
      rows = raw.items.map(l => { const alerts = [l.open_reports > 0 && (l.open_reports + ' reporte' + (l.open_reports > 1 ? 's' : '')), l.possible_duplicates > 0 && 'Posible duplicado', !l.photos && l.status !== 'draft' && 'Sin fotos'].filter(Boolean).join(' · ') || '—';
        return mk(l.id, [vname(l), l.seller || '—', l.price_amount ? API.money(l.price_amount, l.currency) : '—', d(l.submitted_at || l.updated_at), alerts], LISTING_ST[l.status] || [l.status, B.muted], this.listingActs(l), () => this.openListing(l)); });
    } else if (section === 'suscripciones') {
      rows = raw.items.map(s => mk(s.id, [s.agency || '—', s.plan_name, (SUB_ST[s.status] || [s.status])[0], d(s.created_at), d(s.current_period_end), API.money(s.price_amount, s.currency), s.provider === 'mercadopago' ? 'Mercado Pago' : s.provider], SUB_ST[s.status] || [s.status, B.muted]));
    } else if (section === 'pagos') {
      rows = raw.items.map(p => mk(p.id, [p.agency || '—', p.plan ? 'Suscripción ' + p.plan : 'Pago', API.money(p.amount, p.currency), p.provider === 'mercadopago' ? 'Mercado Pago' + (p.mp_payment_id ? ' #' + p.mp_payment_id : '') : p.provider, d(p.paid_at || p.created_at)], PAY_ST[p.status] || [p.status, B.muted]));
    } else if (section === 'verificaciones') {
      rows = raw.items.map(v => { const acts = v.agency_id && ['pending', 'review'].includes(v.status) ? this.agencyActs({ id: v.agency_id, trade_name: v.agency, status: 'pending', verification_status: v.status }) : [];
        return mk(v.id, [v.agency || v.user_name || '—', v.product, v.decision_reason || (v.agency ? 'Checklist preliminar' : '—'), d(v.created_at)], VER_ST[v.status] || [v.status, B.muted], acts, () => this.openVerification(v.id)); });
    } else if (section === 'promociones') {
      rows = raw.items.map(p => mk(p.id, [PROMO_TYPE[p.type] || p.type, p.listing_title ? p.listing_title + ' · ' + p.listing_code : (p.agency_name || p.advertiser_name || '—'), PLACEMENT[p.placement] || p.placement,
        d(p.starts_at) + ' → ' + d(p.ends_at), Number(p.price_amount) > 0 ? money(p.price_amount) : 'Cortesía', p.payment_status ? (PAY_ST[p.payment_status] || [p.payment_status])[0] : (Number(p.price_amount) > 0 ? 'Sin pago' : '—')],
        PROMO_ST[p.status] || [p.status, B.muted], this.promoActs(p),
        () => this.openKV(PROMO_TYPE[p.type] || 'Promoción', (PROMO_ST[p.status] || [p.status])[0], (PROMO_ST[p.status] || [0, B.muted])[1], [['Etiqueta visible', p.disclosure_label], ['Ubicación', PLACEMENT[p.placement]], ['Publicación', p.listing_code ? p.listing_title + ' (' + p.listing_code + ')' : null], ['Agencia', p.agency_name], ['Anunciante', p.advertiser_name], ['Enlace', p.link_url], ['Imagen', p.creative_public_id || (p.type === 'banner_campaign' ? 'Falta subir la imagen' : null)], ['Prioridad', p.priority], ['Desde', dt(p.starts_at)], ['Hasta', dt(p.ends_at)], ['Precio', Number(p.price_amount) > 0 ? money(p.price_amount) : 'Cortesía (sin cobro)'], ['Pago', p.payment_status ? (PAY_ST[p.payment_status] || [p.payment_status])[0] : '—'], ['Aprobada', dt(p.approved_at)], ['Motivo de estado', p.status_reason], ['Alta', dt(p.created_at)]], this.promoActs(p))));
    } else if (section === 'home') {
      rows = raw.items.map(h => mk(h.id, [HB_KIND[h.kind] || h.kind, h.title, h.cta_label ? h.cta_label + ' → ' + (HB_TARGET[h.cta_target] || h.cta_target) : '—', (h.starts_at || h.ends_at) ? d(h.starts_at) + ' → ' + d(h.ends_at) : 'Sin fechas', String(h.sort_order)],
        HB_ST[h.status] || [h.status, B.muted], this.homeActs(h),
        () => this.openKV(h.title, (HB_ST[h.status] || [h.status])[0], (HB_ST[h.status] || [0, B.muted])[1], [['Tipo', HB_KIND[h.kind]], ['Texto', h.body], ['Botón', h.cta_label], ['Destino', HB_TARGET[h.cta_target] || h.cta_target], ['Orden', h.sort_order], ['Desde', dt(h.starts_at)], ['Hasta', dt(h.ends_at)], ['Creado', dt(h.created_at)], ['Actualizado', dt(h.updated_at)]], this.homeActs(h))));
    } else if (section === 'reportes') {
      rows = raw.items.map(r => { const post = (res, note) => this.act(() => API.post('/admin/reports/' + r.id + '/resolve', { resolution: res, note }), 'Reporte actualizado');
        const acts = ['pending', 'reviewing'].includes(r.status) ? [{ label: 'Resolver', primary: true, onRun: () => this.ask('Resolver reporte: ' + r.reason, (n) => post('resolved', n), { label: 'Qué se hizo' }) }, { label: 'Descartar', onRun: () => this.ask('Descartar reporte: ' + r.reason, (n) => post('rejected', n)) }] : [];
        return mk(r.id, [r.reason, r.listing_title || r.public_code || '—', r.description || '—', d(r.created_at)], REP_ST[r.status] || [r.status, B.muted], acts, r.public_code ? () => window.open('/#v/' + encodeURIComponent(r.public_code), '_blank', 'noopener') : null); });
    } else if (section === 'envios') {
      rows = raw.items.map(e => mk(e.id, [e.template_name || e.template_code, e.to_email_masked, e.event_code, dt(e.created_at)], e.last_error === 'provider_not_configured' ? ['Sin proveedor', B.muted] : (MAIL_ST[e.status] || [e.status, B.muted])));
    } else if (section === 'auditoria') {
      rows = raw.items.map(a => mk(a.id, [(a.actor_name || a.actor_type) + (a.actor_role ? ' · ' + a.actor_role : ''), a.action, a.entity_type + (a.entity_id ? ' · ' + String(a.entity_id).slice(0, 8) : ''), a.reason || '—', dt(a.occurred_at)], null, [],
        () => this.openKV('Registro de auditoría #' + a.id, a.action, B.info, [['Actor', a.actor_name || a.actor_type], ['Rol', a.actor_role], ['Entidad', a.entity_type + ' ' + (a.entity_id || '')], ['Motivo', a.reason], ['IP', a.ip], ['Fecha', dt(a.occurred_at)], ['Antes', a.before_data ? JSON.stringify(a.before_data) : '—'], ['Después', a.after_data ? JSON.stringify(a.after_data) : '—']])));
    }
    total = sec.server ? (raw.total || 0) : rows.length;
    if (!sec.server && filt) rows = rows.filter(r => r.st && r.st[0] === (sec.statuses.find(c => c[1] === filt) || [])[0]);
    if (!sec.server && q) rows = rows.filter(r => r.vals.join(' ').toLowerCase().includes(q));
    const pageN = S.page[section] || 1; const size = sec.page || PAGE;
    const setPage = (n) => this.setState(s => ({ page: { ...s.page, [section]: n } }), () => this.load(section));

    // ---- dashboard
    const D = S.dash || { users: {}, agencies: {}, listings: {}, weekly_published: [] };
    const sum = (o) => Object.values(o || {}).reduce((n, v) => n + Number(v || 0), 0);
    const bars = (D.weekly_published || []).map(w => { const x = new Date(String(w.week).slice(0, 10) + 'T12:00:00'); return { label: x.getDate() + '/' + (x.getMonth() + 1), value: Number(w.n) }; });
    const maxBar = Math.max(1, ...bars.map(b => b.value));
    const attention = [
      (D.listings.pending || 0) > 0 && { title: D.listings.pending + ' publicaci' + (D.listings.pending > 1 ? 'ones esperan' : 'ón espera') + ' moderación', meta: 'Revisá fotos, precio y datos antes de aprobar', cta: 'Revisar', onClick: () => this.setState(s => ({ statusFilter: { ...s.statusFilter, publicaciones: 'pending' } }), () => this.open('publicaciones')) },
      D.verifications_open > 0 && { title: D.verifications_open + ' verificaci' + (D.verifications_open > 1 ? 'ones pendientes' : 'ón pendiente'), meta: 'Agencias que pidieron el sello', cta: 'Verificar', onClick: () => this.open('verificaciones') },
      D.reports_open > 0 && { title: D.reports_open + ' reporte' + (D.reports_open > 1 ? 's' : '') + ' sin resolver', meta: 'Denuncias de usuarios', cta: 'Ver reportes', onClick: () => this.open('reportes') },
    ].filter(Boolean);
    if (!attention.length) attention.push({ title: 'Todo al día', meta: 'No hay publicaciones, verificaciones ni reportes pendientes', cta: 'Ver publicaciones', onClick: () => this.open('publicaciones') });
    const kpi = (label, value, delta, sec2) => ({ label, value: String(value == null ? 0 : value), delta, deltaStyle: 'color:#5c6370;', onClick: () => sec2 && this.open(sec2) });

    // ---- ventas
    const SV = S.sales || { kpis: {}, models: [], brands: [], min_sample: 3 };
    const K = SV.kpis || {}; const nMin = SV.min_sample || 3;
    const maxBrand = Math.max(1, ...SV.brands.map(b => Number(b.n)));

    // ---- catálogo
    const C = S.cat;
    const stt = (a) => ({ statusText: a ? 'Activa' : 'Inactiva', statusClass: a ? B.ok : B.muted, toggleLabel: a ? 'Desactivar' : 'Activar', nameStyle: a ? '' : 'color:#9aa0ab;' });
    const selBrand = C.brands.find(b => b.id === S.selBrand); const selModel = C.models.find(m => m.id === S.selModel);
    const catQ = (list) => list.filter(x => !q || x.name.toLowerCase().includes(q));

    const listLabel = (group, v) => ({ value: v, label: L(group, v) });
    const isSuper = this.hasRole('superadmin');

    // ---- Negocio y Finanzas: tarjetas + tablas simples. Todo sale de la API; vacío = "Sin datos".
    const tbl = (title, columns, rowsIn, empty, note) => ({ title, columns, note: note || '', rows: rowsIn.map(r => ({ cells: r.map(t => ({ t: t == null || t === '' ? '—' : String(t) })) })), empty: rowsIn.length ? '' : (empty || 'Sin datos todavía.') });
    let panelKpis = []; let panels = [];
    if (section === 'negocio' && S.business) {
      const Bz = S.business; const ag = Bz.agencies || {}; const li = Bz.listings || {}; const pay = Bz.payments || {};
      const subs = Bz.subscriptions || []; const mrr = subs.reduce((n, x) => n + Number(x.mrr_ars || 0), 0); const paidSubs = subs.filter(x => x.provider !== 'manual').reduce((n, x) => n + Number(x.n), 0);
      const comp = subs.filter(x => x.provider === 'manual').reduce((n, x) => n + Number(x.n), 0);
      const ev = Bz.events_30d || {};
      panelKpis = [['Usuarios activos', (Bz.users || {}).active, ((Bz.users || {}).new_30d || 0) + ' altas en 30 días'], ['Agencias verificadas', ag.verified || 0, ((ag.pending || 0) + (ag.review || 0)) + ' con solicitud abierta · ' + (ag.none || 0) + ' sin solicitar'],
        ['Publicadas', li.published || 0, (li.inventory || 0) + ' en inventario · ' + (li.pending || 0) + ' en moderación'], ['Suscripciones pagas', paidSubs, comp + ' planes asignados sin cobro'],
        ['Ingreso mensual recurrente', money(mrr), 'Solo suscripciones con cobro'], ['Cobrado este mes', money(pay.collected_month_ars), 'Pagos aprobados (ARS)'],
        ['Pagos pendientes', pay.pending || 0, (pay.transfers_to_review || 0) + ' transferencias por verificar'], ['Promociones vigentes', (Bz.promotions || []).filter(x => x.status === 'active').length, (Bz.home_blocks || []).length + ' bloques activos en la Home']]
        .map(([label, value, hint]) => ({ label, value: String(value == null ? 0 : value), hint }));
      panels = [tbl('Planes', ['Plan', 'Para', 'Precio', 'Límite publicadas', 'Con plan vigente'], (Bz.plans || []).map(x => [x.name + (x.is_active ? '' : ' (inactivo)'), x.audience === 'agency' ? 'Agencias' : 'Particulares', Number(x.price_amount) > 0 ? money(x.price_amount) : 'Gratis', x.max_active_listings, x.audience === 'agency' ? x.active_subscriptions : '—'])),
        tbl('Vencen en los próximos 15 días', ['Agencia', 'Plan', 'Método', 'Fin del período'], (Bz.expiring || []).map(x => [x.trade_name, x.plan, PROVIDER[x.provider] || x.provider, d(x.current_period_end)]), 'Ningún plan vence en los próximos 15 días.'),
        tbl('Promociones vigentes y pendientes', ['Tipo', 'Destino', 'Estado', 'Hasta'], (Bz.promotions || []).map(x => [PROMO_TYPE[x.type] || x.type, x.target, (PROMO_ST[x.status] || [x.status])[0], d(x.ends_at)]), 'No hay promociones vigentes.'),
        tbl('Actividad real (últimos 30 días)', ['Evento', 'Cantidad'], Object.entries(ev).sort((a, b) => b[1] - a[1]).map(([k, n]) => [EVENT_ES[k] || k, n]), 'Sin datos suficientes: todavía no hay eventos registrados.', 'Conteo de eventos registrados por el servidor. No se estima ni se extrapola.')];
    } else if (section === 'finanzas' && S.finance) {
      const F = S.finance; const tot = (k) => (F.by_month || []).reduce((n, m) => n + Number(m[k] || 0), 0);
      panelKpis = [['Facturado', money(tot('billed')), 'Pagos emitidos en ' + F.months + ' meses'], ['Cobrado', money(tot('collected')), 'Aprobados por fecha de cobro'], ['Pendiente', money(tot('pending')), 'Esperando al proveedor'],
        ['Transferencias por verificar', money(tot('to_verify')), (F.transfers_to_review || []).length + ' informadas'], ['Rechazado', money(tot('rejected')), 'Rechazos y contracargos'], ['Planes asignados sin cobro', F.manual_active || 0, 'Convenios y cortesías vigentes']]
        .map(([label, value, hint]) => ({ label, value: String(value), hint }));
      const PURPOSE = { subscription: 'Suscripción', promotion: 'Promoción', verification: 'Verificación' };
      panels = [tbl('Por mes', ['Mes', 'Facturado', 'Cobrado', 'Pendiente', 'Por verificar', 'Rechazado'], (F.by_month || []).slice().reverse().map(m => { const x = new Date(String(m.month).slice(0, 10) + 'T12:00:00'); return [x.toLocaleDateString('es-AR', { month: 'long', year: 'numeric' }), money(m.billed), money(m.collected), money(m.pending), money(m.to_verify), money(m.rejected)]; })),
        tbl('Desglose por concepto y medio', ['Concepto', 'Medio', 'Estado', 'Cantidad', 'Monto'], (F.breakdown || []).map(x => [PURPOSE[x.purpose] || x.purpose, PROVIDER[x.provider] || x.provider, (PAY_ST[x.status] || [x.status])[0], x.n, money(x.amount)]), 'Todavía no hay pagos registrados.'),
        tbl('Transferencias informadas por verificar', ['Agencia', 'Referencia', 'Monto', 'Informada'], (F.transfers_to_review || []).map(x => [x.trade_name, x.transfer_reference, money(x.amount), dt(x.transfer_declared_at)]), 'No hay transferencias por verificar.', 'Transferencia bancaria: deshabilitada hasta cargar los datos bancarios reales.'),
        tbl('Suscripciones vigentes y vencimientos', ['Agencia', 'Plan', 'Método', 'Estado', 'Monto', 'Fin del período'], (F.subscriptions || []).map(x => [x.trade_name, x.plan, PROVIDER[x.provider] || x.provider, (SUB_ST[x.status] || [x.status])[0] + (x.cancel_at_period_end ? ' · no renueva' : ''), x.provider === 'manual' ? 'Sin cobro' : money(x.price_amount), d(x.current_period_end)]), 'No hay suscripciones vigentes.', 'Los períodos son meses calendario (zona horaria Argentina). Con Mercado Pago, la renovación la confirma el webhook; nunca una fecha calculada en el navegador.')];
    }

    // ---- formularios de Promociones y Home
    const fld = (label, key, val, on, type, options, hint) => ({ label, key, value: val, onChange: on, isText: !type || type === 'text', isDate: type === 'date', isNum: type === 'num', isSelect: type === 'select', isArea: type === 'area', options: options || [], hint: hint || '' });
    const setPf = (k) => (e) => { const v = e.target.value; this.setState(s2 => ({ pf: { ...s2.pf, [k]: v }, pfError: null })); };
    const setHf = (k) => (e) => { const v = e.target.value; this.setState(s2 => ({ hf: { ...s2.hf, [k]: v }, hfError: null })); };
    const opt = (m) => Object.entries(m).map(([value, label]) => ({ value, label }));
    let form = null;
    if (section === 'promociones') {
      const P = S.pf; const fields = [fld('Tipo', 'type', P.type, setPf('type'), 'select', opt(PROMO_TYPE)), fld('Ubicación', 'placement', P.placement, setPf('placement'), 'select', opt(PLACEMENT))];
      if (P.type === 'featured_listing' || P.type === 'promoted_position') fields.push(fld('Código de la publicación', 'listing_code', P.listing_code, setPf('listing_code'), 'text', null, 'P-XXXXXXXX, tiene que estar publicada'));
      if (P.type === 'featured_agency') fields.push(fld('Agencia', 'agency_id', P.agency_id, setPf('agency_id'), 'select', [{ value: '', label: 'Elegí…' }, ...((S.data.agencias || { items: [] }).items.map(a => ({ value: a.id, label: a.trade_name })))], 'Se listan las agencias cargadas en la sección Agencias'));
      if (P.type === 'banner_campaign') fields.push(fld('Anunciante', 'advertiser_name', P.advertiser_name, setPf('advertiser_name')), fld('Enlace', 'link_url', P.link_url, setPf('link_url'), 'text', null, 'https://…'));
      fields.push(fld('Desde', 'start', P.start, setPf('start'), 'date'), fld('Hasta', 'end', P.end, setPf('end'), 'date'), fld('Precio ($)', 'price', P.price, setPf('price'), 'num', null, '0 = cortesía. Si tiene precio, se activa recién con el pago aprobado.'),
        fld('Prioridad', 'priority', P.priority, setPf('priority'), 'num', null, '0 a 100'), fld('Etiqueta visible', 'label', P.label, setPf('label'), 'select', [{ value: 'Patrocinado', label: 'Patrocinado' }, { value: 'Publicidad', label: 'Publicidad' }]), fld('Nota interna', 'notes', P.notes, setPf('notes')));
      form = { title: 'Nueva promoción', fields, error: S.pfError, cta: 'Crear (queda pendiente)', note: 'Toda promoción se muestra con su etiqueta "Patrocinado" o "Publicidad". El estado lo decide la base de datos, no el navegador. Banners: la carga de imagen requiere Cloudinary (pendiente); sin imagen no se pueden activar.',
        onSubmit: async () => {
          const body = { type: P.type, placement: P.placement, starts_at: isoDay(P.start), ends_at: isoDay(P.end, true), price_amount: Number(P.price || 0), priority: Number(P.priority || 0), disclosure_label: P.label, notes: P.notes.trim() || null,
            listing_code: P.listing_code.trim().toUpperCase() || null, agency_id: P.agency_id || null, advertiser_name: P.advertiser_name.trim() || null, link_url: P.link_url.trim() || null };
          if (!body.starts_at || !body.ends_at) { this.setState({ pfError: 'Completá las fechas de inicio y fin' }); return; }
          try { await API.post('/admin/promotions', body); this.showToast('Promoción creada como pendiente'); this.setState(s2 => ({ pf: { ...s2.pf, listing_code: '', advertiser_name: '', link_url: '', notes: '' } })); this.load('promociones'); }
          catch (e) { if (e && e.status === 401) this.handle(e); else this.setState({ pfError: errMsg(e) }); }
        }, onCancel: null };
    } else if (section === 'home') {
      const H = S.hf;
      const fields = [fld('Tipo', 'kind', H.kind, setHf('kind'), 'select', opt(HB_KIND)), fld('Título', 'title', H.title, setHf('title'), 'text', null, '3 a 90 caracteres'), fld('Texto', 'body', H.body, setHf('body'), 'area', null, 'Hasta 280 caracteres'),
        fld('Texto del botón', 'cta_label', H.cta_label, setHf('cta_label'), 'text', null, 'Opcional'), fld('Destino del botón', 'cta_target', H.cta_target, setHf('cta_target'), 'select', [{ value: '', label: 'Sin botón' }, ...opt(HB_TARGET)]),
        fld('Orden', 'sort_order', H.sort_order, setHf('sort_order'), 'num', null, 'Menor = primero'), fld('Desde', 'start', H.start, setHf('start'), 'date', null, 'Opcional'), fld('Hasta', 'end', H.end, setHf('end'), 'date', null, 'Opcional'),
        fld('Estado', 'status', H.status, setHf('status'), 'select', [{ value: 'draft', label: 'Borrador' }, { value: 'active', label: 'Activo (se ve en la Home)' }])];
      form = { title: H.id ? 'Editar bloque' : 'Nuevo bloque de la Home', fields, error: S.hfError, cta: H.id ? 'Guardar cambios' : 'Crear bloque',
        note: 'Bloques simples (portada, aviso o llamado a la acción) con fechas. Las publicaciones y agencias destacadas se manejan desde Promociones. No es un editor de páginas.',
        onSubmit: async () => {
          const body = this.homeBody({ kind: H.kind, title: H.title.trim(), body: H.body.trim(), cta_label: H.cta_target ? H.cta_label.trim() : '', cta_target: H.cta_target, sort_order: H.sort_order, starts_at: isoDay(H.start), ends_at: isoDay(H.end, true) }, H.status);
          try { if (H.id) await API.put('/admin/home-blocks/' + H.id, body); else await API.post('/admin/home-blocks', body);
            this.showToast(H.id ? 'Bloque actualizado' : 'Bloque creado'); this.setState({ hf: { id: null, kind: 'announcement', title: '', body: '', cta_label: '', cta_target: '', sort_order: '0', start: '', end: '', status: 'draft' } }); this.load('home'); }
          catch (e) { if (e && e.status === 401) this.handle(e); else this.setState({ hfError: errMsg(e) }); }
        }, onCancel: H.id ? () => this.setState({ hf: { id: null, kind: 'announcement', title: '', body: '', cta_label: '', cta_target: '', sort_order: '0', start: '', end: '', status: 'draft' }, hfError: null }) : null };
    }
    const out = {
      // sesión
      needLogin: S.authChecked && !me, notStaff: S.authChecked && !!me && !isStaff, checking: !S.authChecked,
      loginEmail: S.loginEmail, loginPass: S.loginPass, loginError: S.loginError, loginBtn: S.loginBusy ? 'Ingresando…' : 'Ingresar',
      onLoginEmail: (e) => this.setState({ loginEmail: e.target.value, loginError: null }), onLoginPass: (e) => this.setState({ loginPass: e.target.value, loginError: null }),
      onLoginKey: (e) => { if (e.key === 'Enter') this.login(); }, submitLogin: () => this.login(), logout: () => this.logout(), resetDemo: () => this.logout(),
      adminName: me ? (me.display_name || me.email) : '', adminRoles: me ? (me.staff_roles || []).map(r => ({ superadmin: 'Superadmin', admin: 'Admin', moderator: 'Moderación', catalog_editor: 'Catálogo', support: 'Soporte', finance: 'Finanzas' })[r] || r).join(' · ') : '',
      toast: S.toast, query: S.query, stop: (e) => e.stopPropagation(),
      onQuery: (e) => { const v = e.target.value; this.setState(s => ({ query: v, page: { ...s.page, [section]: 1 } })); if (sec.server) { clearTimeout(this._qt); this._qt = setTimeout(() => this.load(this.state.section), 350); } },
      // modal de confirmación
      pendingOpen: !!S.pending, pendingTitle: S.pending ? S.pending.title : '', pendingLabel: S.pending ? S.pending.label : 'Motivo', pendingHint: S.pending ? S.pending.hint : '', pendingCta: S.pending ? S.pending.cta : 'Confirmar', pendingCtaStyle: S.pending && S.pending.tone === 'primary' ? 'background:#1652f0;' : 'background:#a32020;',
      pendingReason: S.pendingReason, pendingNoReason: S.pendingReason.trim().length < 3, onPendingReason: (e) => this.setState({ pendingReason: e.target.value }),
      cancelPending: () => this.setState({ pending: null }), confirmPending: () => { const p = S.pending; if (p && S.pendingReason.trim().length >= 3) p.run(S.pendingReason.trim(), S.pendingChoice); },
      pendingHasOptions: !!(S.pending && S.pending.options), pendingOptions: (S.pending && S.pending.options) || [], pendingOptionLabel: (S.pending && S.pending.optionLabel) || 'Opción',
      pendingChoice: S.pendingChoice, onPendingChoice: (e) => this.setState({ pendingChoice: e.target.value }),
      // detalle
      detailOpen: !!S.detail, closeDetail: () => this.setState({ detail: null }),
      dt: S.detail ? { ...S.detail, noImages: !S.detail.images.length && !!S.detail.code && !S.detail.checklist, hasHistory: S.detail.history.length > 0, hasDescription: !!S.detail.description,
        hasChecklist: !!S.detail.checklist, checklist: S.detail.checklist || [], checklistNote: S.detail.checklistNote || '', canEvidence: !!S.detail.canEvidence,
        evidence: S.evidenceDraft == null ? (S.detail.evidence || '') : S.evidenceDraft, onEvidence: (e) => this.setState({ evidenceDraft: e.target.value }), saveEvidence: S.detail.saveEvidence || (() => {}),
        acts: S.detail.acts.map(a => ({ label: a.label, style: a.primary ? BTN.primary : (a.danger ? BTN.danger : BTN.plain), onClick: () => a.onRun() })) } : { rows: [], images: [], history: [], acts: [] },
      // encabezado
      sectionTitle: sec.title, dataLabel: 'Datos en vivo · PostgreSQL',
      isPanels: section === 'negocio' || section === 'finanzas', panelKpis, panels, showMonths: section === 'finanzas',
      monthChips: [3, 6, 12].map(n => ({ label: n + ' meses', selected: S.finMonths === n, style: CHIP(S.finMonths === n), onClick: () => this.setState({ finMonths: n }, () => this.load('finanzas')) })),
      hasForm: !!form, form: form || { fields: [], title: '', cta: '', note: '', error: null }, formSubmit: () => form && form.onSubmit(), formCancel: () => form && form.onCancel && form.onCancel(), formHasCancel: !!(form && form.onCancel),
      isDashboard: section === 'dashboard', isConfig: section === 'configuracion', isSubs: section === 'suscripciones', isCatalogo: section === 'catalogo', isPlanesAdm: section === 'planes',
      isVentasAdm: section === 'ventas', isRetencion: section === 'retencion',
      hasTable: !['configuracion', 'catalogo', 'planes', 'ventas', 'retencion', 'negocio', 'finanzas'].includes(section),
      showPeriod: section === 'ventas',
      periodChips: PERIODS.map(([k, l]) => ({ label: l, selected: S.period === k, style: CHIP(S.period === k), onClick: () => this.setState({ period: k }, () => this.load('ventas')) })),
      // navegación lateral: fija en desktop, cajón (drawer) en tablet y mobile
      navOpen: S.navOpen ? 'true' : 'false', navToggleLabel: S.navOpen ? 'Cerrar menú' : 'Abrir menú',
      toggleNav: () => this.setState(s => ({ navOpen: !s.navOpen })), closeNav: () => this.setState({ navOpen: false }),
      navItems: NAV_GROUPS.map(([gl, items]) => [gl, items.filter(([k]) => this.can(k))]).filter(([, items]) => items.length).flatMap(([gl, items]) => [{ isHeader: true, isItem: false, label: gl }, ...items.map(([k, l]) => {
        const n = k === 'publicaciones' ? D.listings.pending || 0 : k === 'verificaciones' ? D.verifications_open || 0 : k === 'reportes' ? D.reports_open || 0 : 0;
        return { isHeader: false, isItem: true, label: l, count: n > 0 ? String(n) : null, current: k === section ? 'page' : 'false', style: k === section ? 'background:#e9eefe;color:#0d3399;font-weight:700;' : 'background:transparent;color:#14171f;font-weight:500;', onClick: () => this.open(k) };
      })]),
      kpis: [kpi('Usuarios', sum(D.users), (D.signups_last_7d || 0) + ' altas en 7 días', 'usuarios'), kpi('Agencias', sum(D.agencies), (D.agencies.verified || 0) + ' verificadas', 'agencias'),
        kpi('Publicaciones activas', D.listings.published || 0, (D.published_last_7d || 0) + ' aprobadas en 7 días', 'publicaciones'), kpi('Pendientes de moderación', D.listings.pending || 0, 'Esperan revisión', 'publicaciones'),
        ...(D.can_business ? [kpi('Ventas registradas', D.sales_total, (D.sales_attributed || 0) + ' atribuidas a Girando', 'ventas'), kpi('Suscripciones vigentes', D.subscriptions_active, 'Mercado Pago y planes asignados', 'suscripciones')] : []),
        kpi('Reportes pendientes', D.reports_open, 'Para revisar', 'reportes'), kpi('Verificaciones pendientes', D.verifications_open, 'Agencias', 'verificaciones')],
      bars: bars.map((b, i) => ({ ...b, style: 'height:' + Math.max(3, Math.round(b.value / maxBar * 130)) + 'px;background:' + (i === bars.length - 1 ? '#1652f0' : '#c9d6fb') + ';' })),
      attention,
      subKpis: [['Activas', (S.data.suscripciones || { items: [] }).items.filter(s => s.status === 'active').length, ''], ['Pendientes de pago', (S.data.suscripciones || { items: [] }).items.filter(s => s.status === 'pending').length, 'color:#8c560a;'],
        ['Pago rechazado', (S.data.suscripciones || { items: [] }).items.filter(s => s.status === 'payment_failed').length, 'color:#a32020;'], ['Canceladas', (S.data.suscripciones || { items: [] }).items.filter(s => s.status === 'canceled').length, '']].map(([label, value, style]) => ({ label, value: String(value), style })),
      // tabla genérica
      statusChips: (sec.statuses || []).map(([label, v]) => ({ label, selected: filt === v, style: CHIP(filt === v), onClick: () => this.setState(s => ({ statusFilter: { ...s.statusFilter, [section]: v }, page: { ...s.page, [section]: 1 } }), () => sec.server && this.load(section)) })),
      columns: sec.columns || [],
      rows: rows.map(r => ({ acts: r.acts.map(a => ({ label: a.label, style: a.primary ? BTN.primary : (a.danger ? BTN.danger : BTN.plain), onClick: () => a.onRun() })),
        cells: [...r.vals.map((v, i) => ({ text: v, label: sec.columns[i] || '', badge: (section === 'suscripciones' && i === 2) ? r.st[1] : (sec.columns[i] === 'Alertas' && v !== '—' ? B.warn : null), plain: !((section === 'suscripciones' && i === 2) || (sec.columns[i] === 'Alertas' && v !== '—')), style: i === 0 ? 'font-weight:600;' : 'color:#454b56;' })),
          ...(r.st && section !== 'suscripciones' ? [{ text: r.st[0], badge: r.st[1], plain: false, style: '' }] : [])],
        onSecondary: () => r.onView ? r.onView() : this.showToast('Sin más detalle para mostrar') })),
      noRows: rows.length === 0, resultLabel: (sec.server ? total : rows.length) + ' resultados',
      pageLabel: sec.server ? ('Página ' + pageN + ' de ' + Math.max(1, Math.ceil(total / size)) + ' · ' + total + ' en total') : ('Mostrando ' + rows.length),
      noPrev: !sec.server || pageN <= 1, noNext: !sec.server || pageN * size >= total, prevPage: () => pageN > 1 && setPage(pageN - 1), nextPage: () => pageN * size < total && setPage(pageN + 1),
      // catálogo
      selBrand: selBrand ? selBrand.name : '—', selModel: selModel ? selModel.name : '—', nf: S.nf, nfOn: Object.keys(S.nf).reduce((o, k) => { o[k] = setNf(k); return o; }, {}),
      newBrand: S.nf.brand, newModel: S.nf.model, newVersion: S.nf.ver, onNewBrand: setNf('brand'), onNewModel: setNf('model'), onNewVersion: setNf('ver'),
      vtOpts: VT.map(([value, label]) => ({ value, label })), bodyOpts: BODY.map(v => listLabel('body_type', v)), transOpts: TRANS.map(v => listLabel('transmission', v)), tractionOpts: TRACTION.map(v => listLabel('traction', v)), fuelOpts: FUELS.map(v => listLabel('fuel', v)),
      selGenValue: S.selGen, onSelGen: (e) => this.setState({ selGen: e.target.value }),
      engineOpts: C.engines.filter(e => e.status === 'active').map(e => ({ value: e.id, label: e.name + ' · ' + L('fuel', e.fuel) })), genOpts: C.gens.map(g => ({ value: g.id, label: g.name })),
      addBrand: () => { const n = S.nf.brand.trim(); if (!n) return; this.act(() => API.post('/admin/catalog/brands', { name: n }), 'Marca agregada: ' + n, 'none').then(() => { this.setState(s => ({ nf: { ...s.nf, brand: '' } })); this.loadBrands(); }); },
      addModel: () => { const n = S.nf.model.trim(); if (!n || !S.selBrand) return; this.act(() => API.post('/admin/catalog/models', { brand_id: S.selBrand, name: n, vehicle_type: S.nf.modelType }), 'Modelo agregado: ' + n, 'none').then(() => { this.setState(s => ({ nf: { ...s.nf, model: '' } })); this.selectBrand(S.selBrand); }); },
      addGen: () => { const n = S.nf.gen.trim(); const y = +S.nf.genFrom; if (!n || !S.selModel || !(y >= 1900 && y <= 2100)) { this.showToast('Completá nombre y año de inicio de la generación'); return; } this.act(() => API.post('/admin/catalog/generations', { model_id: S.selModel, name: n, year_from: y }), 'Generación agregada: ' + n, 'none').then(() => { this.setState(s => ({ nf: { ...s.nf, gen: '', genFrom: '' } })); this.catReload(); }); },
      addVersion: () => { const n = S.nf.ver.trim(); if (!n || !S.selGen) { this.showToast('Elegí la generación y escribí el nombre de la versión'); return; } if (!S.nf.verEngine) { this.showToast('Primero cargá un motor'); return; }
        this.act(() => API.post('/admin/catalog/versions', { generation_id: S.selGen, name: n, body_type: S.nf.verBody, transmission: S.nf.verTrans, traction: S.nf.verTraction, doors: +S.nf.verDoors || null, engine_ids: [S.nf.verEngine] }), 'Versión agregada: ' + n, 'none').then(() => { this.setState(s => ({ nf: { ...s.nf, ver: '' } })); this.catReload(); }); },
      addEngine: () => { const n = S.nf.engine.trim(); if (!n) return; this.act(() => API.post('/admin/catalog/engines', { name: n, fuel: S.nf.engineFuel }), 'Motor agregado: ' + n, 'none').then(() => { this.setState(s => ({ nf: { ...s.nf, engine: '' } })); this.loadEngines(); }); },
      catBrands: catQ(C.brands).map(b => ({ name: b.name, meta: b.vehicles_count + ' vehículos cargados', ...stt(b.status === 'active'), rowStyle: b.id === S.selBrand ? 'background:#e9eefe;' : '', onSelect: () => this.selectBrand(b.id), onToggle: this.catToggle('brands', b, () => this.loadBrands()), onRename: this.catRename('brands', b, () => this.loadBrands()) })),
      catModels: C.models.map(m => ({ name: m.name, meta: L('vehicle_type', m.vehicle_type) + ' · ' + m.vehicles_count + ' vehículos', ...stt(m.status === 'active'), rowStyle: m.id === S.selModel ? 'background:#e9eefe;' : '', onSelect: () => this.selectModel(m.id), onToggle: this.catToggle('models', m, () => this.selectBrand(S.selBrand)), onRename: this.catRename('models', m, () => this.selectBrand(S.selBrand)) })),
      catGens: C.gens.map(g => ({ name: g.name, years: g.year_from + '–' + (g.year_to || 'hoy'), toggleLabel: g.status === 'active' ? 'Desactivar' : 'Activar', statusText: g.status === 'active' ? 'Activa' : 'Inactiva', statusClass: g.status === 'active' ? B.ok : B.muted,
        onToggle: this.catToggle('generations', g, () => this.catReload()), onRename: this.catRename('generations', g, () => this.catReload()),
        versions: (C.versions[g.id] || []).map(v => ({ name: v.name, meta: [((v.engines || []).find(e => e.is_default) || (v.engines || [])[0] || {}).name || 'Sin motor', L('transmission', v.transmission), L('traction', v.traction), L('body_type', v.body_type)].filter(x => x && x !== '—').join(' · ') + ' · ' + v.vehicles_count + ' vehículos',
          ...stt(v.status === 'active' && g.status === 'active'), onToggle: this.catToggle('versions', v, () => this.catReload()), onRename: this.catRename('versions', v, () => this.catReload()) })) })),
      catEngines: C.engines.filter(e => !q || e.name.toLowerCase().includes(q)).map(e => ({ name: e.name, meta: L('fuel', e.fuel) + ' · ' + e.vehicles_count + ' vehículos', ...stt(e.status === 'active'), onToggle: this.catToggle('engines', e, () => this.loadEngines()), onRename: this.catRename('engines', e, () => this.loadEngines()) })),
      // planes
      planRows: S.plans.map((p, i) => { const upd = (f, num) => (e) => { const v = num ? e.target.value.replace(/\D/g, '') : e.target.value; this.setState(s => { const plans = s.plans.slice(); plans[i] = { ...plans[i], [f]: num ? Number(v || 0) : v }; return { plans, plansDirty: { ...s.plansDirty, [p.id]: true } }; }); };
        return { name: p.name, price: String(Math.round(+p.price_amount)), limit: String(p.max_active_listings), audienceLabel: p.audience === 'agency' ? 'Agencias' : 'Particulares', periodLabel: ({ none: 'Sin cobro', month: 'Mensual', year: 'Anual' })[p.billing_period] || p.billing_period,
          featured: String(p.included_featured_listings || 0), members: String(p.max_members || 1), onFeatured: upd('included_featured_listings', true), onMembers: upd('max_members', true), readonly: !isSuper,
          onName: upd('name'), onPrice: upd('price_amount', true), onLimit: upd('max_active_listings', true), statusText: p.is_active ? 'Activo' : 'Inactivo', statusClass: p.is_active ? B.ok : B.muted,
          onToggle: () => isSuper && this.setState(s => { const plans = s.plans.slice(); plans[i] = { ...plans[i], is_active: !plans[i].is_active }; return { plans, plansDirty: { ...s.plansDirty, [p.id]: true } }; }) }; }),
      savePlans: async () => { const dirty = S.plans.filter(p => S.plansDirty[p.id]); if (!dirty.length) { this.showToast('No hay cambios'); return; }
        try { for (const p of dirty) await API.patch('/admin/plans/' + p.id, { name: p.name, price_amount: +p.price_amount, max_active_listings: +p.max_active_listings, included_featured_listings: +p.included_featured_listings || 0, max_members: Math.max(1, +p.max_members || 1), is_active: p.is_active }); this.showToast('Planes guardados. La App ya usa los nuevos valores.'); } catch (e) { this.handle(e); }
        this.load('planes'); },
      canEditPlans: isSuper, plansNote: isSuper ? 'La App lee los planes desde PostgreSQL: nombre, precio, límite de publicadas, destacadas incluidas, miembros y estado se cambian acá sin tocar el frontend. Los cambios de precio aplican a las suscripciones nuevas; las vigentes conservan su precio.' : 'Solo lectura: los planes y precios los modifica el Super Admin.',
      // ventas
      salesKpisAdm: [['Publicaciones creadas', K.created, 'En el período'], ['Publicaciones activas', K.published, 'Hoy'], ['Ventas reportadas', K.sold, 'Informadas por vendedores'], ['Atribuidas a Girando', K.attributed, 'Canal Girando o cliente de Girando'],
        ['Volumen reportado', K.volume_ars != null ? API.money(K.volume_ars, 'ARS') : 'Sin datos', 'Ventas en pesos'], ['Precio promedio', K.avg_ars != null ? API.money(K.avg_ars, 'ARS') : 'Sin datos suficientes', 'Mínimo ' + nMin + ' ventas en pesos']].map(([label, value, hint]) => ({ label, value: String(value == null ? 0 : value), hint })),
      modelStats: SV.models.map(m => { const ok = m.avg_sold != null; return { name: m.name, pub: m.published, sold: m.sold, avgPub: ok && m.avg_listed != null ? API.money(m.avg_listed, 'ARS') : 'Datos insuficientes', avgSold: ok ? API.money(m.avg_sold, 'ARS') : '—', days: ok && m.avg_days != null ? Math.round(m.avg_days) + ' días' : '—', avgStyle: ok ? '' : 'color:#9aa0ab;' }; }),
      noModelStats: SV.models.length === 0, noBrandStats: SV.brands.length === 0,
      brandStats: SV.brands.map(b => ({ name: b.name, value: b.n, bar: 'width:' + Math.round(Number(b.n) / maxBrand * 100) + '%;' })),
      // retención
      retentionRows: S.retention.map((r, i) => { const m = String(r.duration).match(/^(\d+)\s+(\w+)/) || [null, r.duration, 'days'];
        return { label: r.label, cat: ({ media: 'Multimedia', operational: 'Operativos', historical: 'Históricos', audit: 'Auditoría', security: 'Seguridad', legal: 'Legal' })[r.category] || r.category, catClass: ({ media: B.warn, operational: B.muted, historical: B.info, audit: B.ok, security: B.info, legal: B.info })[r.category] || B.muted, value: String(r._value != null ? r._value : m[1]), unit: UNIT_ES[m[2]] || m[2],
          from: r.starts_from || '—', then: (({ delete: 'Se borra', anonymize: 'Se anonimiza', aggregate_then_delete: 'Se agrega y se borra', keep: 'Se conserva' })[r.action] || r.action || '—') + (r.approved_for_production ? '' : ' · pendiente de validación legal'),
          onValue: (e) => { const v = e.target.value.replace(/\D/g, '').slice(0, 4); this.setState(s => { const ret = s.retention.slice(); ret[i] = { ...ret[i], _value: v, _unit: UNIT_API[m[2]] || 'days' }; return { retention: ret, retentionDirty: { ...s.retentionDirty, [r.code]: true } }; }); } }; }),
      saveRetention: async () => { const dirty = S.retention.filter(r => S.retentionDirty[r.code] && r._value); if (!dirty.length) { this.showToast('No hay cambios'); return; }
        try { for (const r of dirty) await API.patch('/admin/retention/' + encodeURIComponent(r.code), { value: +r._value, unit: r._unit }); this.showToast('Política guardada. Queda en Auditoría.'); } catch (e) { this.handle(e); } this.load('retencion'); },
      mediaQueue: S.mediaQueue.map(m => ({ title: m.title, reason: L('status', m.reason), photos: m.photos, scheduled: d(m.scheduled), status: m.status === 'purged' ? 'Eliminadas' : 'Programada', statusClass: m.status === 'purged' ? B.muted : B.warn, canDelete: false, onDelete: () => {} })),
      noMedia: S.mediaQueue.length === 0,
      mediaNote: 'El worker borra las fotos al vencer el plazo (local en desarrollo, Cloudinary en producción) y lo registra en Auditoría.',
      // integraciones
      emailSenders: S.integrations && S.integrations.email_senders ? [['Avisos (transaccional)', S.integrations.email_senders.transactional], ['Comunicaciones oficiales', S.integrations.email_senders.official], ['Contacto (responder a)', S.integrations.email_senders.contact]].map(([k, v]) => ({ k, v })) : [],
      integrations: S.integrations ? [['Fotos', S.integrations.images, 'local_dev = disco local solo para desarrollo'], ['Mercado Pago', S.integrations.mercadopago, 'Suscripciones: preapproval + webhook firmado'], ['Email', S.integrations.email, 'Sin proveedor los emails quedan en la cola, sin enviarse'],
        ['Google Places', S.integrations.google_places, 'Sin API key no se muestra ninguna calificación de Google'], ['Documentos privados (R2)', S.integrations.documents_bucket, 'Bucket privado con URLs firmadas'], ['Cotización USD', S.integrations.exchange_rate, 'BCRA · Comunicación A 3500'],
        ['Email de marketing', S.integrations.email_senders && S.integrations.email_senders.marketing !== 'not_configured' ? 'configured' : 'not_configured', 'Separado de los avisos; solo a quien dio consentimiento']].map(([name, st, hint]) => ({ name, hint, status: st === 'configured' || st === 'bcra' || st === 'cloudinary' || st === 'resend' ? 'Conectado' : (st === 'local_dev' ? 'Desarrollo' : 'No configurado'), cls: st === 'configured' || st === 'bcra' || st === 'cloudinary' || st === 'resend' ? B.ok : (st === 'local_dev' ? B.warn : B.muted) })) : [],
    };
    if (window.__GR_CHECK) window.__GR_KEYS = Object.keys(out);
    return out;
  }
}
