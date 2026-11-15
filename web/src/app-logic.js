// Girando App — lógica conectada a la API (reemplaza girando-data.js / girando-store.js).
// Todo dato sale del backend (PostgreSQL). Lo que todavía no existe en el backend se muestra
// como "Próximamente" o vacío: nunca con datos inventados.
const API = window.GirandoAPI;
const L = (g, v) => API.label(g, v);
const CHIP_SEL = 'display:inline-flex;background:var(--color-accent-700);color:#fff;border:1px solid var(--color-accent-700);';
const CHIP_UNSEL = 'display:inline-flex;background:transparent;color:var(--color-text);border:1px solid var(--color-neutral-300);';
const DOT_ON = 'width:14px;height:5px;border-radius:3px;background:var(--color-text);display:inline-block;';
const DOT_OFF = 'width:5px;height:5px;border-radius:3px;background:var(--color-neutral-300);display:inline-block;';
const RADIO = (on) => 'width:20px;height:20px;border-radius:50%;flex-shrink:0;' + (on ? 'border:6px solid var(--color-accent);' : 'border:2px solid var(--color-neutral-300);');
const SEG = (on) => on ? 'background:var(--color-text);color:#fff;font-weight:700;' : 'color:var(--color-muted);font-weight:600;';

const VEHICLE_TYPES = [['Todos', null], ['Auto', 'car'], ['Camioneta', 'light_truck'], ['Moto', 'motorcycle'], ['Camión', 'truck'], ['Utilitario', 'van'], ['Cuatriciclo', 'atv']];
const WZ_TYPES = [['Auto', 'car'], ['Camioneta', 'light_truck'], ['Moto', 'motorcycle'], ['Camión', 'truck'], ['Utilitario', 'van']];
const CONDITIONS = [['Todos', null], ['Nuevo', 'new'], ['Usado', 'used']];
const SELLER_TYPES = [['Todos', null], ['Concesionaria oficial', 'official_dealer'], ['Agencia', 'agency'], ['Particular', 'particular']];
const FUELS = [['Nafta', 'gasoline'], ['Diésel', 'diesel'], ['GNC', 'cng'], ['Nafta/GNC', 'gasoline_cng'], ['Híbrido', 'hybrid'], ['Eléctrico', 'electric'], ['Otro', 'other']];
const SORTS = { 'relevancia': 'relevancia', 'recientes': 'recientes', 'precio-asc': 'precio_asc', 'precio-desc': 'precio_desc', 'km-asc': 'km_asc', 'km-desc': 'km_desc' };
const STATUS_CLASS = { published: 'tag tag-success', pending: 'tag tag-accent-2', paused: 'tag tag-muted', draft: 'tag tag-outline', requires_changes: 'tag tag-accent-2', rejected: 'tag tag-danger', sold: 'tag tag-accent', expired: 'tag tag-danger', deleted: 'tag tag-muted' };
const MY_FILTERS = { 'Activas': ['draft', 'pending', 'published', 'paused', 'requires_changes'], 'Finalizadas': ['sold', 'expired', 'rejected'], 'Todas': null };
const CATALOG_EDITABLE = ['draft', 'requires_changes', 'rejected'];
const NOTE_STYLE = { warn: 'background:#fbeedc;color:#8c560a;', bad: 'background:var(--color-danger-100);color:var(--color-danger);', info: 'background:var(--color-accent-100);color:var(--color-accent-700);' };
const SUB_STATUS = { pending: ['Pendiente', 'tag tag-accent-2'], active: ['Activa', 'tag tag-success'], payment_failed: ['Pago rechazado', 'tag tag-danger'], grace_period: ['En período de gracia', 'tag tag-accent-2'], canceled: ['Cancelada', 'tag tag-muted'], expired: ['Expirada', 'tag tag-danger'] };
const PAY_STATUS = { pending: ['Pendiente', 'tag tag-accent-2'], approved: ['Aprobado', 'tag tag-success'], rejected: ['Rechazado', 'tag tag-danger'], cancelled: ['Cancelado', 'tag tag-muted'], refunded: ['Reintegrado', 'tag tag-muted'], in_process: ['En proceso', 'tag tag-accent-2'] };
const PHOTO_SLOTS = [['Frente', 'Vista delantera completa', 'front'], ['Trasera', 'Parte trasera completa', 'rear'], ['Lateral izquierdo', 'De punta a punta', 'left'], ['Lateral derecho', 'De punta a punta', 'right'], ['Interior', 'Tablero y asientos', 'interior'], ['Adicional', 'Motor, baúl o detalle', 'additional']];
const DESC_TIPS = [['Estado', 'Estado general: '], ['Mantenimiento', 'Mantenimiento: '], ['Dueños', 'Cantidad de dueños: '], ['Equipamiento', 'Equipamiento: '], ['Documentación', 'Documentación: '], ['Detalles', 'Detalles a tener en cuenta: ']];
const SALE_CHANNELS = [['girando', 'A través de Girando', 'El comprador te contactó y cerraron la operación por Girando.'], ['buyer_from_girando', 'Cliente proveniente de Girando', 'Te conoció por Girando y cerraron por otro medio.'], ['other_channel', 'Otro canal', 'La venta no vino de Girando.']];
const FIN_TYPES = [['pledge_loan', 'Crédito prendario'], ['bank_loan', 'Crédito bancario'], ['dealer_financing', 'Financiación propia'], ['savings_plan', 'Plan de ahorro'], ['other', 'Otra']];
const AUTH_GATES = {
  fav: { title: 'Guardá tus favoritos', body: 'Creá una cuenta para guardar esta publicación y volver a verla cuando quieras.', line: 'Ingresá para guardar la publicación que estabas viendo.' },
  contact: { title: 'Contactá al vendedor', body: 'Necesitás una cuenta para ver los datos de contacto del vendedor.', line: 'Ingresá para contactar al vendedor.' },
  publish: { title: 'Publicá en Girando', body: 'Creá tu cuenta gratis para publicar tu vehículo y gestionar tus avisos.', line: 'Ingresá para publicar.' },
  report: { title: 'Reportá la publicación', body: 'Necesitás una cuenta para enviar un reporte. Así evitamos reportes automáticos.', line: 'Ingresá para reportar.' },
  account: { title: 'Ingresá a tu cuenta', body: 'Tus notificaciones están guardadas en tu cuenta.', line: 'Ingresá para ver tus notificaciones.' },
};
const PUBLISH_OPTIONS = [
  { key: 'vehiculo', icon: '🚗', label: 'Vehículo', hint: 'Auto, moto, camioneta o camión' },
  { key: 'servicio', icon: '🔧', label: 'Servicio', hint: 'Próximamente' },
  { key: 'empleo', icon: '💼', label: 'Empleo', hint: 'Próximamente' },
  { key: 'repuesto', icon: '🔩', label: 'Repuesto / comercio', hint: 'Próximamente' },
];
const NOTIF_FILTERS = [['Todas', null], ['Publicaciones', 'listing'], ['Cuenta', 'account'], ['Suscripción', 'billing'], ['Verificación', 'verification']];
const COOKIE_KEY = 'girando-cookie-consent';
const EMPTY_WZ = { type: 'car', brandId: '', modelId: '', genId: '', versionId: '', year: '', km: '', fuel: '', color: '', price: '', currency: 'ARS', provinceId: '', deptId: '', title: '', desc: '', yt: '', financiable: false, permuta: false, condition: 'used' };
const EMPTY_FILTERS = { vehicleType: null, conditionFilter: null, sellerTypeFilter: null, financiableOnly: false, verifiedOnly: false, marcaSel: [], modelSel: [], yearFrom: '', yearTo: '', priceFrom: '', priceTo: '', kmFrom: '', kmTo: '', fuelSel: [], transSel: [], bodySel: [], tractionSel: [], searchText: '' };

const uniq = (a) => Array.from(new Set(a.filter(Boolean)));
const digits = (v) => String(v || '').replace(/\D/g, '');
const errMsg = (e) => (e && e.message) || 'Ocurrió un error. Probá de nuevo.';
const initials = (s) => String(s || '?').trim().split(/\s+/).slice(0, 2).map(w => w[0] || '').join('').toUpperCase() || '?';
// Solo URLs de imagen que el backend pudo haber generado (almacenamiento local de desarrollo o Cloudinary)
const safeImg = (u) => (typeof u === 'string' && (/^\/media\/[A-Za-z0-9/_\-.]+$/.test(u) || /^https:\/\/res\.cloudinary\.com\/[A-Za-z0-9/_\-.,:]+$/.test(u))) ? u : '';
const ytId = (u) => { const m = String(u || '').match(/(?:v=|youtu\.be\/|shorts\/)([A-Za-z0-9_-]{6,})/); return m ? m[1] : null; };
const vehicleName = (i) => [i.brand, i.model, i.version].filter(Boolean).join(' ');
const today = () => { const d = new Date(); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); };
const fmtDate = (s) => { if (!s) return '—'; const [y, m, d] = String(s).slice(0, 10).split('-'); return d + '/' + m + '/' + y; };
const hashRoute = () => { const h = (location.hash || '').replace(/^#\/?/, ''); const [path, q] = h.split('?'); return { path, params: new URLSearchParams(q || '') }; };
const setHash = (h) => { try { history.replaceState(null, '', h ? '#' + h : location.pathname + location.search); } catch (e) { /* noop */ } };

function carFromPublic(i) {
  return { id: i.id, code: i.public_code, title: vehicleName(i) || i.title, sellerTitle: i.title, brand: i.brand, model: i.model, version: i.version,
    year: i.year ? String(i.year) : '—', km: API.km(i.km), price: API.money(i.price_amount, i.currency), location: [i.locality, i.province].filter(Boolean).join(', '),
    cover: safeImg(i.cover_url), featured: false, seller: i.agency_name || 'Particular', agencySlug: i.agency_slug,
    // Señales reales del backend (nunca se infieren en el navegador)
    verified: !!(i.agency_verified || i.seller_identity_verified), verifiedLabel: i.agency_verified ? 'Agencia verificada' : (i.seller_identity_verified ? 'Identidad verificada' : '') };
}
// Pantallas que viven dentro de "Mi Girando" (en desktop comparten la navegación lateral)
// Perfil público de la agencia (editable por dueño/admin de la agencia). Las URL se validan en el backend.
const AG_FIELDS = [['trade_name', 'Nombre comercial', 'text', ''], ['description', 'Descripción', 'area', 'Qué vendés, desde cuándo, qué te diferencia'], ['phone_e164', 'Teléfono', 'tel', '+5426140000000'],
  ['whatsapp_e164', 'WhatsApp', 'tel', '+5492614000000'], ['email', 'Email de contacto', 'email', 'ventas@tuagencia.com'], ['website_url', 'Sitio web', 'url', 'https://'],
  ['store_url', 'Tienda online (Tienda Nube u otra)', 'url', 'https://tutienda.mitiendanube.com'], ['instagram_url', 'Instagram', 'url', 'https://instagram.com/…'], ['facebook_url', 'Facebook', 'url', 'https://facebook.com/…'],
  ['tiktok_url', 'TikTok', 'url', 'https://tiktok.com/@…'], ['youtube_url', 'YouTube', 'url', 'https://youtube.com/…']];
const AG_CHANNELS = [['website', 'website_url', 'Sitio web'], ['store', 'store_url', 'Tienda online'], ['whatsapp', 'whatsapp_e164', 'WhatsApp'], ['instagram', 'instagram_url', 'Instagram'], ['facebook', 'facebook_url', 'Facebook'], ['tiktok', 'tiktok_url', 'TikTok'], ['youtube', 'youtube_url', 'YouTube']];
const VSTATE_LABEL = { none: 'Sin verificar', pending: 'Verificación en revisión', review: 'Verificación en revisión', verified: 'Verificada', rejected: 'Rechazada', suspended: 'Suspendida', revoked: 'Revocada' };
const ACCOUNT_SCREENS = ['miAgencia', 'perfil', 'misPublicaciones', 'favoritos', 'mensajes', 'notificaciones', 'postulaciones', 'suscripcion', 'ventas', 'ventaDetalle', 'configuracion', 'estadisticas', 'verificacion', 'calificaciones'];
// Activa con Enter/Espacio los elementos no nativos marcados como botón o enlace (cards, filas, chips).
function keyActivate(e) {
  if (e.key !== 'Enter' && e.key !== ' ') return;
  const el = e.target;
  if (!el || !el.getAttribute) return;
  const role = el.getAttribute('role');
  if (!(role === 'button' || role === 'link' || role === 'radio' || role === 'checkbox')) return;
  if (/^(BUTTON|A|INPUT|SELECT|TEXTAREA|LABEL)$/.test(el.tagName)) return;
  e.preventDefault();
  el.click();
}

class Component extends DCLogic {
  state = { screen: 'home', booting: true, me: null, authed: false, isStaff: false,
    provinces: [], depts: {}, provinceId: null, provinceName: 'Todo el país', deptId: null, deptName: 'Todos', locationSheetOpen: false,
    homeCars: [], banners: [], sponsored: [], adIndex: 0, homeBlocks: [], agStats: null, agProfile: null, agForm: null, agFormError: null, agSaving: false,
    ...EMPTY_FILTERS, sortBy: 'relevancia', sheetOpen: false, results: null, facets: null,
    selectedCode: null, detail: null, photoIdx: 0, similar: [], contactOpen: false, contact: null, contactLoading: false,
    favIds: [], favItems: [], authGate: null, authReason: null, returnScreen: 'home', publishChooserOpen: false,
    reportOpen: false, reportReasonsApi: [], reportReason: null, reportDesc: '', reportSent: false, toast: null,
    loginEmail: '', loginPass: '', showPass: false, loginError: null, loginNotice: null, authLoading: false,
    regName: '', regLast: '', regEmail: '', regPass: '', regPass2: '', regError: null, recoverStep: 1, resetToken: null,
    myListings: [], myFilter: 'Activas', limitHit: false,
    wz: { ...EMPTY_WZ }, wzStep: 1, wzId: null, wzStatus: null, wzBusy: false, cat: { brands: {}, models: {}, gens: {}, versions: {} }, photos: [],
    plans: [], planTab: 'particular', ckPlanId: null, ckStep: 'metodo', ckError: null, ckBusy: false,
    ckAg: { trade: '', legal: '', cuit: '', tax: 'responsable_inscripto', provinceId: '', deptId: '' },
    manageOpen: false, manageConfirm: false, billing: null,
    notifs: [], notifFilter: 'Todas', notifReturn: 'home',
    stats: null, statsPeriod: '30',
    sales: null, saleSel: null, sale: null, lastSale: null, ventasTab: 'resumen', salesFilter: { month: 'Todos', brand: 'Todas', model: 'Todos', price: 'Todos', fin: 'Todas' },
    agencySlug: null, agencyData: null, agencyReturn: 'detalle',
    cfg: { name: '', phone: '', showPhone: false, isPublic: true }, sessions: [],
    cookieConsent: (() => { try { return JSON.parse(localStorage.getItem(COOKIE_KEY)); } catch (e) { return null; } })(),
    cookieSettingsOpen: false, cookieCats: { preferencias: false, analitica: false, marketing: false } };

  // ------------------------------------------------------------------ ciclo de vida
  componentDidMount() {
    this.boot();
    this._onHash = () => this.applyHash();
    window.addEventListener('hashchange', this._onHash);
    document.addEventListener('keydown', keyActivate);
    // Escape cierra la hoja o modal abierto (filtros, ubicación, contacto, reporte, etc.)
    this._onEsc = (e) => {
      if (e.key !== 'Escape') return;
      const S = this.state;
      if (S.sheetOpen || S.locationSheetOpen || S.publishChooserOpen || S.reportOpen || S.contactOpen || S.cookieSettingsOpen || S.manageOpen || S.authGate) {
        if (S.authGate) this._after = null;
        this.setState({ sheetOpen: false, locationSheetOpen: false, publishChooserOpen: false, reportOpen: false, contactOpen: false, cookieSettingsOpen: false, manageOpen: false, authGate: null });
      }
    };
    document.addEventListener('keydown', this._onEsc);
  }
  componentWillUnmount() { window.removeEventListener('hashchange', this._onHash); document.removeEventListener('keydown', keyActivate); document.removeEventListener('keydown', this._onEsc); clearTimeout(this._st); clearTimeout(this._tt); }
  componentDidUpdate(prevProps, prevState) {
    const k = this.searchKey();
    if (k !== this._lastKey) { this._lastKey = k; clearTimeout(this._st); this._st = setTimeout(() => this.runSearch(), prevState && prevState.searchText !== this.state.searchText ? 350 : 60); }
  }
  async boot() {
    await Promise.all([this.loadMe(true), this.loadGeo(), this.loadHome(), this.loadPlans()]);
    this.setState({ booting: false });
    this.applyHash();
  }
  applyHash() {
    const { path, params } = hashRoute();
    if (path.startsWith('v/')) this.openDetail(decodeURIComponent(path.slice(2)));
    else if (path === 'recuperar' && params.get('token')) { this.setState({ screen: 'recuperar', recoverStep: 3, resetToken: params.get('token'), regPass: '', regPass2: '', regError: null }); setHash(''); }
    else if (path === 'verificar-email' && params.get('token')) {
      API.post('/auth/email/verify', { token: params.get('token') }).then(() => { this.showToast('¡Listo! Verificaste tu email'); this.loadMe(); }).catch(e => this.showToast(errMsg(e)));
      setHash('');
    } else if (path === 'mis-publicaciones') this.requireAuth('publish', () => this.go('misPublicaciones'));
    else if (path === 'notificaciones') this.requireAuth('account', () => this.go('notificaciones'));
  }
  showToast(msg) { clearTimeout(this._tt); this.setState({ toast: msg }); this._tt = setTimeout(() => this.setState({ toast: null }), 2600); }
  go(screen, extra) {
    this.setState({ screen, limitHit: false, ...(extra || {}) });
    if (screen !== 'detalle' && (location.hash || '').startsWith('#v/')) setHash('');
    const loaders = { misPublicaciones: () => this.loadMyListings(), perfil: () => this.state.authed && this.refreshAccount(), favoritos: () => this.state.authed && this.loadFavs(),
      notificaciones: () => this.loadNotifs(), estadisticas: () => { this.loadStats(); this.loadAgencyStats(); }, miAgencia: () => this.loadAgencyProfile(), ventas: () => this.loadSales(), ventaDetalle: () => this.loadSales(),
      suscripcion: () => this.loadBilling(), configuracion: () => this.loadConfig(), planes: () => this.loadPlans(), limite: () => this.loadMyListings() };
    if (loaders[screen]) loaders[screen]();
    try { window.scrollTo(0, 0); } catch (e) { /* noop */ }
  }

  // ------------------------------------------------------------------ sesión
  async loadMe(silent) {
    try {
      const me = await API.get('/me/profile');
      this.setState({ me, authed: true, isStaff: (me.staff_roles || []).length > 0, cfg: { name: me.display_name || '', phone: me.contact_phone_e164 || '', showPhone: !!me.show_phone_default, isPublic: me.is_public !== false } });
      await Promise.all([this.loadFavs(), this.loadMyListings(), this.loadNotifs()]);
      return me;
    } catch (e) {
      if (!silent && e.status !== 401) this.showToast(errMsg(e));
      this.setState({ me: null, authed: false, isStaff: false, favIds: [], favItems: [], myListings: [], notifs: [] });
      return null;
    }
  }
  async refreshAccount() { try { const me = await API.get('/me/profile'); this.setState({ me }); } catch (e) { if (e.status === 401) this.sessionExpired(); } this.loadMyListings(); }
  sessionExpired() { this.setState({ me: null, authed: false, screen: 'login', returnScreen: 'perfil', loginNotice: 'Tu sesión expiró. Volvé a ingresar para seguir donde estabas.' }); }
  requireAuth(reason, after) {
    if (this.state.authed) { if (after) after(); return; }
    this._after = after;
    this.setState({ authGate: reason, authReason: reason, returnScreen: this.state.screen });
  }
  async completeLogin() {
    const after = this._after; this._after = null;
    await this.loadMe();
    this.setState({ authGate: null, authLoading: false, loginError: null, regError: null, loginNotice: null, loginPass: '', regPass: '', regPass2: '' });
    this.go(this.state.returnScreen || 'home');
    if (after) after();
  }
  myAgency() { const a = (this.state.me && this.state.me.agencies) || []; return a[0] || null; }
  usage() {
    const ag = this.myAgency();
    if (ag && this.state.billing && this.state.billing.usage) return this.state.billing.usage;
    return (this.state.me && this.state.me.particular_usage) || { plan: { name: 'Particular' }, used: 0, limit: 1, at_limit: false };
  }

  // ------------------------------------------------------------------ datos públicos
  async loadGeo() {
    try { const r = await API.get('/geo', { level: 'province' }); this.setState({ provinces: r.items }); } catch (e) { /* sin ubicaciones */ }
  }
  async loadDepts(provinceId) {
    if (!provinceId || this.state.depts[provinceId]) return;
    try { const r = await API.get('/geo', { parent_id: provinceId }); this.setState(s => ({ depts: { ...s.depts, [provinceId]: r.items } })); } catch (e) { /* noop */ }
  }
  async loadHome() {
    try {
      const [recent, banners, sponsored, home] = await Promise.all([API.get('/listings', { sort: 'recientes', page_size: 8 }), API.get('/sponsored', { placement: 'home_banner' }), API.get('/sponsored', { placement: 'home_featured' }),
        API.get('/home').catch(() => ({ blocks: [] }))]);
      this.setState({ homeCars: recent.items.map(carFromPublic), banners: banners.items, sponsored: sponsored.items, homeBlocks: home.blocks || [] });
    } catch (e) { /* home vacío */ }
  }
  async loadPlans() { try { const r = await API.get('/plans'); this.setState({ plans: r.items }); } catch (e) { /* noop */ } }
  searchParams() {
    const S = this.state;
    const num = (v) => { const n = digits(v); return n ? n : undefined; };
    return { q: S.searchText.trim() || undefined, vehicle_type: S.vehicleType || undefined, brand_id: S.marcaSel, model_id: S.modelSel,
      year_min: S.yearFrom.length === 4 ? S.yearFrom : undefined, year_max: S.yearTo.length === 4 ? S.yearTo : undefined,
      price_min: num(S.priceFrom), price_max: num(S.priceTo), currency: (num(S.priceFrom) || num(S.priceTo)) ? 'ARS' : undefined,
      km_min: num(S.kmFrom), km_max: num(S.kmTo), fuel: S.fuelSel, transmission: S.transSel, body_type: S.bodySel, traction: S.tractionSel,
      condition: S.conditionFilter || undefined, seller_type: S.sellerTypeFilter || undefined, verified: S.verifiedOnly || undefined,
      financeable: S.financiableOnly || undefined, geo_area_id: S.deptId || S.provinceId || undefined };
  }
  searchKey() { return JSON.stringify([this.searchParams(), this.state.sortBy]); }
  async runSearch() {
    const p = this.searchParams(); const seq = (this._seq = (this._seq || 0) + 1);
    try {
      const [results, facets] = await Promise.all([API.get('/listings', { ...p, sort: SORTS[this.state.sortBy] || 'relevancia', page_size: 48 }), API.get('/listings/facets', p)]);
      if (seq === this._seq) this.setState({ results, facets });
    } catch (e) { if (seq === this._seq) { this.setState({ results: { items: [], total: 0 } }); if (e.status === 429) this.showToast(e.message); } }
  }
  // Carga progresiva: agrega la página siguiente a los resultados actuales (mismos filtros y orden).
  async loadMoreResults() {
    const R = this.state.results;
    if (!R || this.state.loadingMore || R.items.length >= R.total) return;
    const seq = this._seq;
    this.setState({ loadingMore: true });
    try {
      const more = await API.get('/listings', { ...this.searchParams(), sort: SORTS[this.state.sortBy] || 'relevancia', page_size: 48, page: (R.page || 1) + 1 });
      if (seq === this._seq) this.setState(s => ({ results: { ...more, items: [...s.results.items, ...more.items.filter(i => !s.results.items.some(x => x.id === i.id))] } }));
    } catch (e) { this.showToast(errMsg(e)); }
    this.setState({ loadingMore: false });
  }
  async openDetail(code) {
    if (!code) return;
    this.setState({ screen: 'detalle', selectedCode: code, detail: null, photoIdx: 0, similar: [], contact: null, contactOpen: false });
    setHash('v/' + encodeURIComponent(code));
    try { window.scrollTo(0, 0); } catch (e) { /* noop */ }
    try {
      const d = await API.get('/listings/' + encodeURIComponent(code));
      if (this.state.selectedCode !== code) return;
      this.setState({ detail: d });
      const sim = await API.get('/listings', { model_id: [d.model_id], page_size: 4 });
      this.setState({ similar: sim.items.filter(i => i.id !== d.id).slice(0, 3).map(carFromPublic) });
    } catch (e) {
      this.showToast(e.status === 404 ? 'La publicación ya no está disponible' : errMsg(e));
      this.go('listado');
    }
  }
  async openAgency(slug) {
    this.setState({ screen: 'agencia', agencySlug: slug, agencyData: null, agencyReturn: this.state.screen });
    try { this.setState({ agencyData: await API.get('/agencies/' + encodeURIComponent(slug)) }); } catch (e) { this.showToast(errMsg(e)); this.go(this.state.agencyReturn || 'listado'); }
  }

  // ------------------------------------------------------------------ usuario
  async loadFavs() { try { const r = await API.get('/me/favorites'); this.setState({ favItems: r.items, favIds: r.items.map(f => f.listing_id) }); } catch (e) { /* noop */ } }
  async toggleFav(id) {
    this.requireAuth('fav', async () => {
      const has = this.state.favIds.includes(id);
      this.setState(s => ({ favIds: has ? s.favIds.filter(f => f !== id) : [...s.favIds, id] }));
      try { if (has) await API.del('/me/favorites/' + id); else await API.put('/me/favorites/' + id); this.showToast(has ? 'Quitado de favoritos' : 'Guardado en favoritos'); }
      catch (e) { this.showToast(errMsg(e)); }
      this.loadFavs();
    });
  }
  async loadMyListings() {
    if (!this.state.authed && !this.state.me) return;
    try {
      const reqs = [API.get('/me/listings', { group: 'todas' })];
      const ag = this.myAgency(); if (ag) reqs.push(API.get('/me/listings', { group: 'todas', agency_id: ag.id }));
      const res = await Promise.all(reqs);
      const items = res.flatMap(r => r.items).sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at)));
      this.setState({ myListings: items });
      if (ag) this.loadBilling();
    } catch (e) { if (e.status === 401) this.sessionExpired(); }
  }
  async loadNotifs() { if (!this.state.authed && !this.state.me) return; try { const r = await API.get('/me/notifications'); this.setState({ notifs: r.items }); } catch (e) { /* noop */ } }
  homeCta(target) {
    const t = target || '';
    if (t.startsWith('https://')) { window.open(t, '_blank', 'noopener'); return; }
    ({ listado: () => this.go('listado'), publicar: () => this.requireAuth('publish', () => this.goPublishVehicle()), planes: () => this.go('planes'), registro: () => this.go(this.state.authed ? 'perfil' : 'registro') })[t]?.();
  }
  async loadAgencyStats() {
    const ag = this.myAgency(); if (!ag) { this.setState({ agStats: null }); return; }
    try { this.setState({ agStats: await API.get('/me/agencies/' + ag.id + '/stats', { days: Number(this.state.statsPeriod) || 30 }) }); } catch (e) { this.setState({ agStats: null }); }
  }
  async loadAgencyProfile() {
    const ag = this.myAgency(); if (!ag) { this.go('perfil'); return; }
    try {
      const a = await API.get('/me/agencies/' + ag.id);
      const f = {}; AG_FIELDS.forEach(([k]) => { f[k] = a[k] || ''; });
      this.setState({ agProfile: a, agForm: f, agFormError: null });
    } catch (e) { this.showToast(errMsg(e)); }
  }
  async saveAgencyProfile() {
    const ag = this.myAgency(); const S = this.state; if (!ag || !S.agForm || S.agSaving) return;
    const body = {}; AG_FIELDS.forEach(([k]) => { const v = String(S.agForm[k] || '').trim(); const old = (S.agProfile && S.agProfile[k]) || ''; if (v !== old) body[k] = v; });
    if (!Object.keys(body).length) { this.showToast('No hay cambios'); return; }
    this.setState({ agSaving: true, agFormError: null });
    try { const a = await API.patch('/me/agencies/' + ag.id, body); const f = {}; AG_FIELDS.forEach(([k]) => { f[k] = a[k] || ''; }); this.setState({ agProfile: a, agForm: f }); this.showToast('Perfil de la agencia actualizado'); this.loadMe(); }
    catch (e) { this.setState({ agFormError: errMsg(e) }); } finally { this.setState({ agSaving: false }); }
  }
  async loadStats() { try { this.setState({ stats: await API.get('/me/stats', { days: this.state.statsPeriod }) }); } catch (e) { this.showToast(errMsg(e)); } }
  async loadSales() { try { this.setState({ sales: await API.get('/me/sales') }); } catch (e) { this.showToast(errMsg(e)); } }
  async loadBilling() {
    const ag = this.myAgency(); if (!ag) { this.setState({ billing: null }); return; }
    try { this.setState({ billing: await API.get('/me/agencies/' + ag.id + '/billing') }); } catch (e) { /* noop */ }
  }
  async loadConfig() { try { const r = await API.get('/auth/sessions'); this.setState({ sessions: r.items }); } catch (e) { /* noop */ } }
  async transition(l, to, okMsg) {
    try { await API.post('/me/listings/' + l.id + '/transition', { to }); this.showToast(okMsg); }
    catch (e) { if (e.code === 'LIMITE_ALCANZADO') { this.go('limite'); return; } this.showToast(errMsg(e)); }
    this.loadMyListings(); this.refreshAccount();
  }

  // ------------------------------------------------------------------ asistente de publicación
  async loadCat(level, key, url, params) {
    if (!key || this.state.cat[level][key]) return;
    try { const r = await API.get(url, params); this.setState(s => ({ cat: { ...s.cat, [level]: { ...s.cat[level], [key]: r.items } } })); } catch (e) { this.showToast(errMsg(e)); }
  }
  loadBrands(type) { return this.loadCat('brands', type, '/catalog/brands', { vehicle_type: type }); }
  loadModels(brandId, type) { return this.loadCat('models', brandId + ':' + type, '/catalog/brands/' + brandId + '/models', { vehicle_type: type }); }
  loadGens(modelId) { return this.loadCat('gens', modelId, '/catalog/models/' + modelId + '/generations'); }
  loadVersions(genId) { return this.loadCat('versions', genId, '/catalog/generations/' + genId + '/versions'); }
  wzVersion() { const w = this.state.wz; return ((this.state.cat.versions[w.genId]) || []).find(v => v.id === w.versionId) || null; }
  wzGen() { const w = this.state.wz; return ((this.state.cat.gens[w.modelId]) || []).find(g => g.id === w.genId) || null; }
  setWz(f, val) {
    this.setState(s => {
      const w = { ...s.wz, [f]: val };
      if (f === 'type') { w.brandId = ''; w.modelId = ''; w.genId = ''; w.versionId = ''; }
      if (f === 'brandId') { w.modelId = ''; w.genId = ''; w.versionId = ''; }
      if (f === 'modelId') { w.genId = ''; w.versionId = ''; }
      if (f === 'genId') { w.versionId = ''; w.year = ''; }
      if (f === 'versionId') { w.fuel = ''; }
      if (f === 'provinceId') w.deptId = '';
      return { wz: w };
    }, () => {
      const w = this.state.wz;
      if (f === 'type') this.loadBrands(w.type);
      if (f === 'brandId' && w.brandId) this.loadModels(w.brandId, w.type);
      if (f === 'modelId' && w.modelId) this.loadGens(w.modelId);
      if (f === 'genId' && w.genId) this.loadVersions(w.genId);
      if (f === 'provinceId' && w.provinceId) this.loadDepts(w.provinceId);
    });
  }
  goPublishVehicle() {
    const u = this.usage();
    this.setState({ publishChooserOpen: false });
    if (u.at_limit) { this.go('limite'); return; }
    const mza = this.state.provinces.find(p => p.name === 'Mendoza');
    this.setState({ screen: 'publicar', wzStep: 1, wzId: null, wzStatus: null, wz: { ...EMPTY_WZ, provinceId: mza ? mza.id : '' }, photos: [], limitHit: false });
    this.loadBrands('car'); if (mza) this.loadDepts(mza.id);
  }
  async openEdit(l) {
    try {
      const d = await API.get('/me/listings/' + l.id);
      const prov = this.state.provinces.find(p => p.name === d.province);
      const w = { ...EMPTY_WZ, type: d.vehicle_type || 'car', brandId: d.brand_id || '', modelId: d.model_id || '', genId: d.generation_id || '', versionId: d.version_id || '',
        year: d.year ? String(d.year) : '', km: d.km != null ? String(d.km) : '', fuel: d.fuel_override || '', color: d.color || '', price: d.price_amount ? String(Math.round(+d.price_amount)) : '',
        currency: d.currency || 'ARS', provinceId: prov ? prov.id : '', deptId: d.geo_area_id || '', title: d.title || '', desc: d.description || '', yt: d.video_url || '',
        financiable: !!d.is_financeable, permuta: !!d.accepts_trade_in, condition: d.condition || 'used' };
      this.setState({ screen: 'publicar', wzStep: 1, wzId: d.id, wzStatus: d.status, wz: w, photos: d.images || [] });
      this.loadBrands(w.type); if (w.brandId) this.loadModels(w.brandId, w.type); if (w.modelId) this.loadGens(w.modelId); if (w.genId) this.loadVersions(w.genId); if (w.provinceId) this.loadDepts(w.provinceId);
    } catch (e) { this.showToast(errMsg(e)); }
  }
  wzPayload() {
    const w = this.state.wz; const v = this.wzVersion(); const locked = this.state.wzId && !CATALOG_EDITABLE.includes(this.state.wzStatus);
    const p = { km: w.km ? +w.km : null, price_amount: w.price ? w.price : null, currency: w.currency, condition: w.condition, geo_area_id: w.deptId || null,
      title: w.title.trim() || null, description: w.desc.trim() || null, is_financeable: w.financiable, accepts_trade_in: w.permuta, video_url: w.yt.trim() || null, color: w.color.trim() || null };
    if (!locked) {
      p.version_id = w.versionId || null; p.year = w.year ? +w.year : null;
      const def = v && (v.engines || []).find(e => e.is_default) || (v && (v.engines || [])[0]);
      p.fuel_override = (w.fuel && def && w.fuel !== def.fuel) ? w.fuel : null;
    }
    return p;
  }
  async wzSave() {
    const payload = this.wzPayload();
    if (!this.state.wzId) {
      const ag = this.myAgency();
      const d = await API.post('/me/listings', { ...payload, ...(ag ? { agency_id: ag.id } : {}) });
      this.setState({ wzId: d.id, wzStatus: d.status, photos: d.images || [] });
      return d;
    }
    const d = await API.patch('/me/listings/' + this.state.wzId, payload);
    this.setState({ wzStatus: d.status, photos: d.images || [] });
    return d;
  }
  async wzAdvance() {
    const S = this.state;
    this.setState({ wzBusy: true });
    try {
      await this.wzSave();
      if (S.wzStep < 5) { this.setState({ wzStep: S.wzStep + 1 }); return; }
      if (['draft', 'requires_changes', 'rejected'].includes(this.state.wzStatus)) {
        await API.post('/me/listings/' + this.state.wzId + '/transition', { to: 'pending' });
        this.showToast('Enviamos tu publicación a revisión');
      } else this.showToast('Cambios guardados');
      this.setState({ myFilter: 'Activas' });
      this.go('misPublicaciones'); this.refreshAccount();
    } catch (e) {
      if (e.code === 'LIMITE_ALCANZADO') { this.showToast('Guardamos tu borrador. ' + e.message); this.go('limite'); }
      else this.showToast(errMsg(e));
    } finally { this.setState({ wzBusy: false }); }
  }
  async wzSaveDraft() {
    const w = this.state.wz;
    if (!w.versionId && !this.state.wzId && !w.title.trim()) { this.showToast('Elegí al menos la versión o escribí un título para guardar el borrador'); return; }
    this.setState({ wzBusy: true });
    try { await this.wzSave(); this.showToast(this.state.wzStatus === 'draft' ? 'Guardamos tu borrador' : 'Cambios guardados'); this.setState({ myFilter: 'Activas' }); this.go('misPublicaciones'); }
    catch (e) { this.showToast(errMsg(e)); } finally { this.setState({ wzBusy: false }); }
  }
  // Fotos: el servidor valida formato real, tamaño y cantidad. Acá solo se evita subir algo claramente inválido.
  async uploadPhoto(file, slotIdx) {
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) { this.setPhotoErr(slotIdx, 'Formato no válido. Usá JPG, PNG o WEBP.'); return; }
    if (file.size > 10 * 1024 * 1024) { this.setPhotoErr(slotIdx, 'La foto pesa más de 10 MB.'); return; }
    if (!this.state.wzId) { try { await this.wzSave(); } catch (e) { this.showToast(errMsg(e)); return; } }
    const kind = (PHOTO_SLOTS[slotIdx] || PHOTO_SLOTS[5])[2];
    this.setState(s => ({ uploading: { ...(s.uploading || {}), [slotIdx]: true }, photoErrors: { ...(s.photoErrors || {}), [slotIdx]: null } }));
    try {
      let d;
      try { d = await API.upload('/me/listings/' + this.state.wzId + '/images', file, { kind }); }
      catch (e) { if (e.code !== 'USAR_SUBIDA_DIRECTA') throw e; d = await this.uploadCloudinary(file, kind); }
      this.setState({ photos: d.images || [] });
    } catch (e) { this.setPhotoErr(slotIdx, errMsg(e)); }
    finally { this.setState(s => ({ uploading: { ...(s.uploading || {}), [slotIdx]: false } })); }
  }
  async uploadCloudinary(file, kind) {
    const sig = await API.post('/me/listings/' + this.state.wzId + '/images/upload-signature');
    const f = new FormData(); f.append('file', file); f.append('api_key', sig.api_key); f.append('signature', sig.signature);
    Object.entries(sig.params).forEach(([k, v]) => f.append(k, v));
    const r = await fetch(sig.upload_url, { method: 'POST', body: f });
    if (!r.ok) throw new Error('Cloudinary rechazó la foto. Probá con otra.');
    const up = await r.json();
    return API.post('/me/listings/' + this.state.wzId + '/images/confirm', { public_id: up.public_id, version: up.version, signature: up.signature, kind });
  }
  setPhotoErr(i, msg) { this.setState(s => ({ photoErrors: { ...(s.photoErrors || {}), [i]: msg } })); }
  async photoOp(fn, okMsg) {
    try { const d = await fn(); this.setState({ photos: d.images || [] }); if (okMsg) this.showToast(okMsg); } catch (e) { this.showToast(errMsg(e)); }
  }
  movePhoto(i, dir) {
    const imgs = this.state.photos.slice(); const j = i + dir; if (j < 0 || j >= imgs.length) return;
    [imgs[i], imgs[j]] = [imgs[j], imgs[i]];
    this.photoOp(() => API.post('/me/listings/' + this.state.wzId + '/images/reorder', { image_ids: imgs.map(x => x.id) }));
  }

  // ------------------------------------------------------------------ venta
  async openSale(l) {
    try {
      const d = await API.get('/me/listings/' + l.id);
      this.setState({ screen: 'venta', sale: { listing: d, step: 1, channel: '', date: today(), price: d.price_amount ? String(Math.round(+d.price_amount)) : '', currency: d.currency || 'ARS', patente: '', financed: false, finType: '', cuotas: '', finAmount: '', notes: '', busy: false } });
    } catch (e) { this.showToast(errMsg(e)); }
  }
  async commitSale() {
    const s = this.state.sale;
    this.setState(st => ({ sale: { ...st.sale, busy: true } }));
    try {
      const body = { sold_on: s.date, final_price: s.price, currency: s.currency, channel: s.channel, is_financed: !!s.financed,
        financing_type: s.financed ? s.finType || null : null, installments: s.financed && s.cuotas ? +s.cuotas : null,
        financed_amount: s.financed && s.finAmount ? s.finAmount : null, plate: s.patente.trim() ? s.patente.trim().toUpperCase() : null, notes: s.notes.trim() || null };
      const res = await API.post('/me/listings/' + s.listing.id + '/sale', body);
      this.setState(st => ({ lastSale: { ...res, listing: s.listing, body }, sale: { ...st.sale, step: 3, busy: false } }));
      this.loadMyListings(); this.loadSales(); this.refreshAccount();
    } catch (e) { this.setState(st => ({ sale: { ...st.sale, busy: false } })); this.showToast(errMsg(e)); }
  }

  // ------------------------------------------------------------------ suscripción / agencia
  async createAgencyAndContinue() {
    const a = this.state.ckAg;
    if (a.trade.trim().length < 2 || a.legal.trim().length < 2) { this.setState({ ckError: 'Completá el nombre comercial y la razón social.' }); return; }
    if (!/^\d{2}-?\d{8}-?\d$/.test(a.cuit.trim())) { this.setState({ ckError: 'Revisá el CUIT: son 11 números (ej: 30-12345678-9).' }); return; }
    if (!a.deptId) { this.setState({ ckError: 'Elegí la provincia y el departamento de la agencia.' }); return; }
    this.setState({ ckBusy: true, ckError: null });
    try {
      await API.post('/me/agencies', { trade_name: a.trade.trim(), legal_name: a.legal.trim(), cuit: a.cuit.trim(), tax_condition: a.tax, geo_area_id: a.deptId });
      await this.loadMe(); await this.loadBilling();
      this.setState({ ckStep: 'metodo' });
      this.showToast('Creamos tu agencia. Podés pedir la verificación desde Mi Girando.');
    } catch (e) { this.setState({ ckError: errMsg(e) }); } finally { this.setState({ ckBusy: false }); }
  }
  async startMercadoPago() {
    const ag = this.myAgency(); if (!ag) { this.setState({ ckStep: 'agencia' }); return; }
    this.setState({ ckStep: 'procesando', ckError: null });
    try {
      const r = await API.post('/me/agencies/' + ag.id + '/subscription', { plan_id: this.state.ckPlanId });
      if (r.init_point && /^https:\/\/(www\.)?mercadopago\.com(\.ar)?\//.test(r.init_point)) { window.location.assign(r.init_point); return; }
      this.setState({ ckStep: 'pendiente' });
    } catch (e) { this.setState({ ckStep: e.code === 'PAGOS_NO_CONFIGURADOS' ? 'nodisponible' : 'mp', ckError: errMsg(e) }); }
  }
  async cancelSubscription() {
    const ag = this.myAgency(); if (!ag) return;
    try { await API.post('/me/agencies/' + ag.id + '/subscription/cancel', {}); this.showToast('Cancelaste tu suscripción'); } catch (e) { this.showToast(errMsg(e)); }
    this.setState({ manageOpen: false, manageConfirm: false }); this.loadBilling();
  }

  // ------------------------------------------------------------------ cookies
  saveCookieConsent(cats) { const c = { cats, date: new Date().toISOString(), version: '2026-09' }; try { localStorage.setItem(COOKIE_KEY, JSON.stringify(c)); } catch (e) { /* noop */ } this.setState({ cookieConsent: c, cookieSettingsOpen: false, cookieCats: { preferencias: !!cats.preferencias, analitica: !!cats.analitica, marketing: !!cats.marketing } }); this.showToast('Guardamos tus preferencias de cookies'); }

  // ================================================================== render
  renderVals() {
    const S = this.state;
    const stop = (e) => e.stopPropagation();
    const screen = S.screen, authed = S.authed, me = S.me || {};
    const favDecorate = (c) => { const isFav = authed && S.favIds.includes(c.id); return { ...c, isFav, notFav: !isFav, favLabel: isFav ? 'Quitar de favoritos' : 'Guardar en favoritos', onFav: (e) => { e.stopPropagation(); this.toggleFav(c.id); }, onClick: () => this.openDetail(c.code) }; };
    const gate = AUTH_GATES[S.authGate] || AUTH_GATES.fav;
    const usage = this.usage();
    const planName = (usage.plan && usage.plan.name) || 'Particular';
    const atLimit = !!usage.at_limit;
    const userName = me.display_name || [me.first_name, me.last_name].filter(Boolean).join(' ') || 'Mi cuenta';
    const ag = this.myAgency();
    const isAg = !!ag;

    // ---- ubicación
    const provinceChips = [{ id: null, name: 'Todo el país' }, ...S.provinces].map(p => ({ name: p.name, style: (p.id || null) === S.provinceId ? CHIP_SEL : CHIP_UNSEL,
      onClick: () => { this.setState({ provinceId: p.id || null, provinceName: p.name, deptId: null, deptName: 'Todos' }); if (p.id) this.loadDepts(p.id); } }));
    const departmentChips = S.provinceId ? [{ id: null, name: 'Todos' }, ...(S.depts[S.provinceId] || [])].map(d => ({ name: d.name, style: (d.id || null) === S.deptId ? CHIP_SEL : CHIP_UNSEL,
      onClick: () => this.setState({ deptId: d.id || null, deptName: d.name }) })) : [];
    const locationLabel = S.provinceName + (S.deptId ? ', ' + S.deptName : '');

    const heroBlock = (S.homeBlocks || []).find(b => b.kind === 'hero') || null;
    // ---- banners y patrocinados (solo promociones reales, siempre rotuladas)
    const ADSX = S.banners;
    const cur = ADSX.length ? ADSX[S.adIndex % ADSX.length] : null;
    const currentAd = cur ? { id: cur.promotion_id, title: cur.advertiser_name || 'Publicidad', subtitle: cur.disclosure_label || 'Publicidad' } : { id: 'none', title: '', subtitle: '' };
    const adDots = ADSX.map((ad, i) => ({ style: i === S.adIndex % Math.max(1, ADSX.length) ? DOT_ON : DOT_OFF, label: 'Ver anuncio de ' + (ad.advertiser_name || ''), current: i === S.adIndex % Math.max(1, ADSX.length) ? 'true' : 'false', onClick: () => this.setState({ adIndex: i }) }));
    const sponsoredHome = S.sponsored.filter(s => s.public_code).map(s => ({ ...carFromPublic({ ...s, id: s.public_code }), featured: true }));

    // ---- búsqueda
    const R = S.results || { items: [], total: 0 }; const F = S.facets || {};
    const interp = R.interpretation || {};
    const interpParts = [interp.brand && ('Marca ' + interp.brand), interp.model && ('Modelo ' + interp.model), interp.year && ('Año ' + interp.year), interp.text && ('“' + interp.text + '”')].filter(Boolean);
    const cars = R.items.map(carFromPublic);
    const facetLabel = { fuel: 'fuel', transmission: 'transmission', body_type: 'body_type', traction: 'traction' };
    const tog = (key, val) => () => this.setState(s => { const arr = s[key]; const next = arr.includes(val) ? arr.filter(x => x !== val) : [...arr, val]; const patch = { [key]: next }; if (key === 'marcaSel' && !next.length) patch.modelSel = []; return patch; });
    const facetChips = (key, facet, group) => {
      const opts = (F[facet] || []).map(o => ({ value: o.value, label: group ? L(group, o.value) : o.label, count: o.count }));
      S[key].forEach(v => { if (!opts.some(o => o.value === v)) opts.push({ value: v, label: group ? L(group, v) : (this._labels && this._labels[v]) || v }); });
      this._labels = this._labels || {}; opts.forEach(o => { this._labels[o.value] = o.label; });
      return opts.map(o => { const sel = S[key].includes(o.value); return { name: o.label + (o.count != null ? ' (' + o.count + ')' : ''), selected: sel, style: sel ? CHIP_SEL : CHIP_UNSEL, onClick: tog(key, o.value) }; });
    };
    const lbl = (v) => (this._labels && this._labels[v]) || v;
    const act = [];
    S.marcaSel.forEach(m => act.push({ label: lbl(m), onRemove: tog('marcaSel', m) }));
    S.modelSel.forEach(m => act.push({ label: lbl(m), onRemove: tog('modelSel', m) }));
    if (S.yearFrom || S.yearTo) act.push({ label: 'Año ' + (S.yearFrom || '…') + '–' + (S.yearTo || '…'), onRemove: () => this.setState({ yearFrom: '', yearTo: '' }) });
    if (S.priceFrom || S.priceTo) act.push({ label: 'Precio $ ' + (S.priceFrom || '…') + '–' + (S.priceTo || '…'), onRemove: () => this.setState({ priceFrom: '', priceTo: '' }) });
    if (S.kmFrom || S.kmTo) act.push({ label: 'Km ' + (S.kmFrom || '…') + '–' + (S.kmTo || '…'), onRemove: () => this.setState({ kmFrom: '', kmTo: '' }) });
    [['fuelSel', 'fuel'], ['transSel', 'transmission'], ['bodySel', 'body_type'], ['tractionSel', 'traction']].forEach(([k, g]) => S[k].forEach(v => act.push({ label: L(g, v), onRemove: tog(k, v) })));
    if (S.conditionFilter) act.push({ label: L('condition', S.conditionFilter), onRemove: () => this.setState({ conditionFilter: null }) });
    if (S.sellerTypeFilter) act.push({ label: L('seller_type', S.sellerTypeFilter), onRemove: () => this.setState({ sellerTypeFilter: null }) });
    if (S.verifiedOnly) act.push({ label: 'Verificado', onRemove: () => this.setState({ verifiedOnly: false }) });
    if (S.financiableOnly) act.push({ label: 'Financiable', onRemove: () => this.setState({ financiableOnly: false }) });
    const single = (list, key) => list.map(([name, v]) => ({ name, selected: S[key] === v, style: S[key] === v ? CHIP_SEL : CHIP_UNSEL, onClick: () => this.setState({ [key]: v }) }));
    const pubChips = [
      { name: 'Verificado', selected: S.verifiedOnly, style: S.verifiedOnly ? CHIP_SEL : CHIP_UNSEL, onClick: () => this.setState(s => ({ verifiedOnly: !s.verifiedOnly })) },
      { name: 'Financiable', selected: S.financiableOnly, style: S.financiableOnly ? CHIP_SEL : CHIP_UNSEL, onClick: () => this.setState(s => ({ financiableOnly: !s.financiableOnly })) },
    ];
    const modelChips = facetChips('modelSel', 'model');

    // ---- detalle
    const d = S.detail;
    const selectedCar = d ? { ...carFromPublic(d), id: d.id, color: d.color || '—', fuel: L('fuel', d.fuel), transmission: L('transmission', d.transmission), doors: d.doors || '—', engine: d.engine || '—',
      bodyType: L('body_type', d.body_type), traction: L('traction', d.traction), description: d.description || 'El vendedor no agregó una descripción.',
      youtubeId: ytId(d.video_url), youtubeEmbed: ytId(d.video_url) ? 'https://www.youtube-nocookie.com/embed/' + ytId(d.video_url) : '',
      seller: d.agency ? d.agency.trade_name : ((d.seller && d.seller.display_name) || d.seller_display_name || 'Particular') }
      : { id: '', title: 'Cargando…', year: '', km: '', price: '', location: '', brand: '', model: '', version: '', description: '', seller: '' };
    const imgs = (d && d.images) || [];
    const photo = imgs.length ? imgs[S.photoIdx % imgs.length] : null;
    const sellerVerified = d ? (d.agency ? !!d.agency.is_verified : !!(d.seller && d.seller.identity_verified)) : false;
    const rating = d ? (d.agency ? [d.agency.girando_rating, d.agency.girando_review_count] : d.seller ? [d.seller.girando_rating, d.seller.girando_review_count] : [null, 0]) : [null, 0];
    const ratingText = rating[0] ? '★ ' + String(rating[0]).replace('.', ',') + ' (' + rating[1] + ')' : 'Sin calificaciones todavía';
    const since = d ? (d.agency ? d.agency.member_since : d.seller && d.seller.member_since) : null;
    const isFavSel = !!(d && authed && S.favIds.includes(d.id));
    const trustSignals = (() => {
      if (!d) return [];
      const ok = 'background:var(--color-success-100);color:var(--color-success);', mu = 'background:var(--color-neutral-200);color:#454b56;';
      const items = [d.agency ? (d.agency.is_verified ? ['✓', ok, 'Agencia verificada', 'Verificamos los datos de la empresa. Girando no inspecciona el vehículo.'] : ['!', mu, 'Agencia sin verificar', 'La agencia todavía no tiene la verificación vigente.'])
        : (sellerVerified ? ['✓', ok, 'Identidad verificada', 'El vendedor validó su identidad.'] : ['!', mu, 'Identidad sin verificar', 'El vendedor todavía no validó su identidad.']),
        ['⌖', mu, 'Ubicación', d.agency && d.agency.street ? (d.agency.street + ' ' + (d.agency.street_number || '') + ', ' + (d.agency.locality || '')) : ([d.locality, d.province].filter(Boolean).join(', ') + ' · zona aproximada. La dirección exacta se coordina con el vendedor.')],
        ['★', mu, 'Calificación Girando', rating[0] ? ratingText + ' opiniones' : 'Todavía no tiene calificaciones en Girando.']];
      if (d.agency && d.agency.google_rating != null) items.push(['G', mu, 'Google · opiniones externas', '★ ' + String(d.agency.google_rating).replace('.', ',') + ' · ' + d.agency.google_review_count + ' reseñas. Fuente externa (actualizado ' + API.date(d.agency.google_synced_at) + '), no se promedia con Girando.']);
      if (d.seller_active_listings != null) items.push(['#', mu, 'Publicaciones activas', String(d.seller_active_listings)]);
      items.push(['✓', ok, 'Datos del vehículo', 'Marca, modelo y versión elegidos del catálogo Girando.']);
      return items.map(([icon, iconStyle, title, body]) => ({ icon, iconStyle, title, body }));
    })();
    const contact = S.contact;
    const contactRows = contact ? [contact.whatsapp && { label: 'WhatsApp', value: contact.whatsapp, href: 'https://wa.me/' + digits(contact.whatsapp) }, contact.phone && { label: 'Teléfono', value: contact.phone, href: 'tel:' + contact.phone },
      contact.email && { label: 'Email', value: contact.email, href: 'mailto:' + contact.email }].filter(Boolean) : [];

    // ---- mis publicaciones
    const noteFor = (l) => {
      if (l.status === 'pending') return ['La revisamos en menos de 24 h', 'info'];
      if (l.status === 'rejected') return ['Rechazada: ' + (l.status_reason || 'revisá los datos y volvé a enviarla'), 'bad'];
      if (l.status === 'requires_changes') return ['Requiere cambios: ' + (l.status_reason || ''), 'warn'];
      if (l.status === 'paused' && l.status_reason) return ['Pausada: ' + l.status_reason, 'warn'];
      if (l.status === 'published' && l.expires_at && (new Date(l.expires_at) - Date.now()) < 5 * 864e5) return ['Tu publicación vence el ' + API.date(l.expires_at), 'warn'];
      if (l.status === 'expired') return ['Tu publicación expiró el ' + API.date(l.expires_at), 'bad'];
      if (l.status === 'sold' && l.photos_purge_after) return ['Las fotos se eliminan el ' + API.date(l.photos_purge_after), 'info'];
      if (l.status === 'draft') { const miss = [!l.version_id && 'versión', !l.price_amount && 'precio', !l.km && l.km !== 0 && 'km', !l.geo_area_id && 'ubicación', !(l.photo_count > 0) && 'fotos'].filter(Boolean); return miss.length ? ['Falta: ' + miss.join(', '), 'warn'] : null; }
      return null;
    };
    const actionsFor = (l) => {
      const P = 'btn btn-secondary btn-sm', G = 'btn btn-ghost btn-sm';
      const sale = { label: 'Vendí este vehículo', cls: G, onClick: () => this.openSale(l) };
      switch (l.status) {
        case 'published': return [{ label: 'Editar', cls: P, onClick: () => this.openEdit(l) }, { label: 'Pausar', cls: P, onClick: () => this.transition(l, 'paused', 'Publicación pausada') }, sale];
        case 'pending': return [{ label: 'Retirar de revisión', cls: P, onClick: () => this.transition(l, 'draft', 'Volvió a borrador. Podés editarla.') }];
        case 'paused': return [{ label: 'Reactivar', cls: P, onClick: () => this.transition(l, 'pending', 'Enviamos tu publicación a revisión') }, { label: 'Editar', cls: P, onClick: () => this.openEdit(l) }, sale, { label: 'Eliminar', cls: G, onClick: () => this.transition(l, 'deleted', 'Publicación eliminada. Queda en tu historial.') }];
        case 'expired': return [{ label: 'Renovar publicación', cls: P, onClick: () => this.transition(l, 'pending', 'Enviamos tu publicación a revisión') }, sale, { label: 'Eliminar', cls: G, onClick: () => this.transition(l, 'deleted', 'Publicación eliminada') }];
        case 'draft': return [{ label: 'Continuar borrador', cls: P, onClick: () => this.openEdit(l) }, { label: 'Eliminar', cls: G, onClick: () => this.transition(l, 'deleted', 'Borrador eliminado') }];
        case 'rejected': case 'requires_changes': return [{ label: 'Corregir y reenviar', cls: P, onClick: () => this.openEdit(l) }];
        case 'sold': return l.sale_id ? [{ label: 'Ver venta', cls: P, onClick: () => this.go('ventaDetalle', { saleSel: l.sale_id }) }] : [];
        default: return [];
      }
    };
    const listingsAll = S.myListings.map(l => { const n = noteFor(l); return { ...l, title: vehicleName(l) || l.title || 'Publicación sin completar', status: L('status', l.status), statusCode: l.status, statusClass: STATUS_CLASS[l.status],
      meta: [l.year, l.km != null ? API.km(l.km) : null].filter(Boolean).join(' · ') || 'Sin datos todavía', price: l.price_amount ? API.money(l.price_amount, l.currency) : 'Sin precio',
      cover: safeImg(l.cover_url), hasPhotos: !l.photos_purged, noPhotos: !!l.photos_purged, mediaLabel: 'Fotos eliminadas',
      note: n ? n[0] : null, noteStyle: NOTE_STYLE[n ? n[1] : 'info'], showStats: ['published', 'paused', 'sold', 'expired'].includes(l.status),
      visits: String(l.stats ? l.stats.views : 0), leads: String(l.stats ? l.stats.contacts : 0), saves: String(l.stats ? l.stats.favorites || 0 : 0), actions: actionsFor(l) }; });
    const myFilterSet = MY_FILTERS[S.myFilter];
    const listingsView = listingsAll.filter(l => !myFilterSet || myFilterSet.includes(l.statusCode));
    const usageLabel = usage.used + ' de ' + usage.limit + (usage.limit === 1 ? ' publicación activa' : ' publicaciones activas') + (isAg && ag.inventory_total != null ? ' · ' + ag.inventory_total + ' en inventario' : '');
    const usageBarStyle = 'width:' + Math.min(100, Math.round(usage.used / Math.max(1, usage.limit) * 100)) + '%;background:' + (atLimit ? '#d08a12' : 'var(--color-accent)') + ';';
    const activeCount = listingsAll.filter(l => l.statusCode === 'published').length;

    // ---- asistente
    const wz = S.wz; const wzV = this.wzVersion(); const wzG = this.wzGen();
    const catLocked = !!(S.wzId && !CATALOG_EDITABLE.includes(S.wzStatus));
    const brands = S.cat.brands[wz.type] || []; const models = S.cat.models[wz.brandId + ':' + wz.type] || []; const gens = S.cat.gens[wz.modelId] || []; const versions = S.cat.versions[wz.genId] || [];
    const nameOf = (list, id) => (list.find(x => x.id === id) || {}).name || '';
    const wzVehicleName = [nameOf(brands, wz.brandId), nameOf(models, wz.modelId), nameOf(versions, wz.versionId)].filter(Boolean).join(' ');
    const defEngine = wzV ? ((wzV.engines || []).find(e => e.is_default) || (wzV.engines || [])[0]) : null;
    const fuelCode = wz.fuel || (defEngine && defEngine.fuel) || '';
    const yNow = new Date().getFullYear() + 1;
    const yFrom = wzV && wzV.year_from ? wzV.year_from : (wzG ? wzG.year_from : yNow - 40); const yTo = wzV && wzV.year_to ? wzV.year_to : (wzG && wzG.year_to_raw < 2100 ? wzG.year_to_raw : yNow);
    const yearOpts = Array.from({ length: Math.max(0, yTo - yFrom + 1) }, (_, i) => String(yTo - i));
    const photos = S.photos || [];
    const slots = PHOTO_SLOTS.map((meta, i) => {
      const p = photos[i]; const up = S.uploading && S.uploading[i]; const er = S.photoErrors && S.photoErrors[i];
      const st = p ? 'ok' : up ? 'loading' : er ? 'error' : 'empty';
      const url = p ? safeImg(p.url) : '';
      return { label: meta[0], hint: meta[1], isEmpty: st === 'empty', isLoading: st === 'loading', isError: st === 'error', isOk: st === 'ok', error: er, isCover: !!(p && p.is_cover),
        imgStyle: url ? 'background-image:url("' + url + '");' : '', boxStyle: st === 'empty' ? 'border:1.5px dashed var(--color-neutral-300);background:#fff;' : (st === 'error' ? 'border:1.5px solid var(--color-danger);' : (p && p.is_cover ? 'outline:2px solid var(--color-text);outline-offset:1px;' : '')),
        onFile: (e) => { const f = e.target.files && e.target.files[0]; e.target.value = ''; if (f) this.uploadPhoto(f, photos.length > i ? i : photos.length); },
        onLeft: () => this.movePhoto(i, -1), onRight: () => this.movePhoto(i, 1),
        onRemove: () => p && this.photoOp(() => API.del('/me/listings/' + S.wzId + '/images/' + p.id), 'Foto eliminada'),
        onCover: () => p && this.photoOp(() => API.patch('/me/listings/' + S.wzId + '/images/' + p.id, { is_cover: true }), 'Esta foto es la portada') };
    });
    const okCount = photos.length;
    const checks = [['Marca, modelo y versión', !!wzV || catLocked, 'Obligatorio'], ['Año', !!wz.year, 'Obligatorio'], ['Kilometraje', wz.km !== '', 'Obligatorio'], ['Precio', !!wz.price, 'Obligatorio'], ['Ubicación', !!wz.deptId, 'Obligatorio'], ['Título', !!wz.title.trim(), 'Obligatorio'], ['Fotografías (' + okCount + ' de 6)', okCount >= 6, 'Recomendado'], ['Descripción', wz.desc.trim().length >= 40, 'Recomendado']];
    const pct = Math.round(checks.filter(c => c[1]).length / checks.length * 100);
    const wzValid = { 1: !!wzV || catLocked, 2: !!(wz.year && wz.km !== ''), 3: !!(wz.price && wz.deptId), 4: !!wz.title.trim(), 5: checks.slice(0, 6).every(c => c[1]) };
    const wzChip = (field, opts, locked) => opts.map(([name, v]) => ({ name, selected: wz[field] === v, style: wz[field] === v ? CHIP_SEL : CHIP_UNSEL, onClick: () => { if (locked) { this.showToast('Ese dato no se puede cambiar en una publicación activa'); return; } this.setWz(field, v); } }));
    const fixedChip = (label) => label ? [{ name: label, selected: true, style: CHIP_SEL, onClick: () => this.showToast('Dato del catálogo: se toma de la versión elegida') }] : [];
    const isSubmitStatus = !S.wzId || ['draft', 'requires_changes', 'rejected'].includes(S.wzStatus);

    // ---- planes y suscripción
    const bill = S.billing; const sub = bill && bill.subscription;
    const plansCfg = S.plans;
    const ckPlan = plansCfg.find(p => p.id === S.ckPlanId) || { name: '', price_amount: 0, max_active_listings: 0 };
    const subInfo = sub ? SUB_STATUS[sub.status] || [sub.status, 'tag tag-outline'] : null;

    // ---- verificación
    const agVer = ag ? (bill && bill.agency ? bill.agency.verification_status : null) : null;
    const verif = isAg ? (ag.verification_state ? VSTATE_LABEL[ag.verification_state] || ag.verification_state : (ag.status === 'verified' ? 'Verificada' : agVer === 'pending' || agVer === 'review' ? 'Verificación en revisión' : agVer === 'rejected' ? 'Rechazada' : L('agency_status', ag.status))) : (me.identity_verified ? 'Aprobada' : 'No verificada');
    const VERIF_CLASS = { 'Sin verificar': 'tag tag-outline', 'Pendiente': 'tag tag-outline', 'No verificada': 'tag tag-outline', 'Verificación en revisión': 'tag tag-accent-2', 'Verificada': 'tag tag-success', 'Aprobada': 'tag tag-success', 'Rechazada': 'tag tag-danger', 'Suspendida': 'tag tag-danger', 'Revocada': 'tag tag-danger' };

    // ---- notificaciones
    const notifCat = NOTIF_FILTERS.find(n => n[0] === S.notifFilter);
    const notifsFiltered = S.notifs.filter(n => !notifCat || !notifCat[1] || n.category === notifCat[1]);
    const unreadNotifs = S.notifs.filter(n => !n.read_at).length;
    const pathToScreen = (p) => ({ '/mis-publicaciones': 'misPublicaciones', '/mi-girando': 'perfil', '/suscripcion': 'suscripcion', '/verificacion': 'verificacion', '/ventas': 'ventas' })[p] || null;

    // ---- estadísticas
    const st = S.stats; const tot = (st && st.totals) || {};

    // ---- ventas
    const salesData = S.sales || { summary: { count: 0, by_model: [] }, items: [] };
    const sItems = salesData.items || []; const sum = salesData.summary || {};
    const SF = S.salesFilter;
    const priceRange = { '0-10': [0, 10e6], '10-20': [10e6, 20e6], '20-999': [20e6, 1e15] }[SF.price];
    const monthOf = (s) => String(s.sold_on).slice(0, 7);
    const sList = sItems.filter(s => (SF.month === 'Todos' || monthOf(s) === SF.month) && (SF.brand === 'Todas' || s.brand === SF.brand) && (SF.model === 'Todos' || s.model === SF.model)
      && (SF.fin === 'Todas' || (SF.fin === 'Financiadas' ? s.is_financed : !s.is_financed)) && (!priceRange || (s.currency === 'ARS' && +s.final_price >= priceRange[0] && +s.final_price < priceRange[1])));
    const saleView = sItems.find(s => s.id === S.saleSel);
    const recRows = (s) => [['Vehículo', [s.brand, s.model].filter(Boolean).join(' ')], ['Versión', s.version], ['Año', s.year], ['Kilómetros', API.km(s.km)], ['Precio publicado', API.money(s.listed_price, s.currency)],
      ['Precio final', API.money(s.final_price, s.currency)], ['Vendida el', fmtDate(s.sold_on)], ['Días hasta la venta', s.days_to_sell != null ? String(s.days_to_sell) : '—'],
      ['Financiada', s.is_financed ? ('Sí · ' + L('financing', s.financing_type) + (s.installments ? ' · ' + s.installments + ' cuotas' : '')) : 'No'], ['Canal', L('channel', s.channel)], ['Publicación originaria', s.listing_code || '—']].map(([k, v]) => ({ k, v: v || '—' }));
    const monthLabel = (m) => { const [y, mm] = m.split('-'); return new Date(+y, +mm - 1, 1).toLocaleDateString('es-AR', { month: 'long', year: 'numeric' }); };
    const nowMonth = today().slice(0, 7);
    const curMonth = sItems.filter(s => monthOf(s) === nowMonth);
    const sale = S.sale || {};
    const sl = sale.listing;
    const setF = (k) => (e) => { const v = e.target.value; this.setState(s2 => ({ salesFilter: { ...s2.salesFilter, [k]: v, ...(k === 'brand' ? { model: 'Todos' } : {}) } })); };
    const minN = sum.min_sample || 3;

    // ---- navegación
    const onNav = ['login', 'registro', 'recuperar', 'publicar', 'checkout'].indexOf(screen) === -1;
    const anySheet = S.sheetOpen || S.locationSheetOpen || !!S.authGate || S.publishChooserOpen || S.reportOpen || S.manageOpen || S.cookieSettingsOpen || S.contactOpen;
    const navDef = [
      { label: 'Inicio', key: 'home', match: ['home'] },
      { label: 'Buscar', key: 'buscar', match: ['buscar', 'listado', 'detalle', 'servicios', 'empleos', 'repuestos', 'agencia'] },
      { label: 'Publicar', key: 'publish', match: [] },
      { label: 'Favoritos', key: 'favoritos', match: ['favoritos'] },
      { label: authed ? 'Mi Girando' : 'Ingresar', key: 'perfil', match: ['perfil', 'planes', 'misPublicaciones', 'postulaciones', 'calificaciones', 'perfilPublico', 'configuracion', 'suscripcion', 'limite', 'mensajes', 'estadisticas', 'verificacion', 'notificaciones', 'ventas', 'ventaDetalle', 'venta'] },
    ];
    const toggleRow = (meta, on, locked, onChange) => ({ label: meta[0], hint: meta[1], on, locked, onChange: onChange || (() => {}) });
    const agData = S.agencyData;

    const out = {
      // pantallas
      isHome: screen === 'home', isListado: screen === 'listado', isDetalle: screen === 'detalle', isEmpleos: screen === 'empleos', isEmpleoDetalle: false, isRepuestos: screen === 'repuestos', isRepuestoDetalle: false,
      isServicios: screen === 'servicios', isServicioDetalle: false, isPerfil: screen === 'perfil' && authed, isPerfilGuest: screen === 'perfil' && !authed, isFavoritos: screen === 'favoritos', isBuscar: screen === 'buscar',
      isPlanes: screen === 'planes', isPublicar: screen === 'publicar', isLogin: screen === 'login', isRegistro: screen === 'registro', isRecuperar: screen === 'recuperar',
      isMisPublicaciones: screen === 'misPublicaciones', isPostulaciones: screen === 'postulaciones', isCalificaciones: screen === 'calificaciones', isPerfilPublico: screen === 'perfilPublico', isConfiguracion: screen === 'configuracion',
      isLimite: screen === 'limite', isCheckout: screen === 'checkout', isSuscripcion: screen === 'suscripcion', isAgencia: screen === 'agencia',
      isMensajes: screen === 'mensajes', isChat: false, isNotificaciones: screen === 'notificaciones', isEstadisticas: screen === 'estadisticas', isVerificacion: screen === 'verificacion',
      isVenta: screen === 'venta', isVentas: screen === 'ventas', isVentaDetalle: screen === 'ventaDetalle',
      authed, guest: !authed, stop, toast: S.toast, booting: S.booting,
      userName, userInitials: initials(userName), userLocality: me.locality || 'Sin ubicación', isStaff: S.isStaff, memberSince: me.created_at ? new Date(me.created_at).toLocaleDateString('es-AR', { month: 'long', year: 'numeric' }) : '',
      emailUnverified: authed && me.email_verified === false, resendVerification: () => API.post('/auth/email/resend').then(() => this.showToast('Te enviamos el email de verificación')).catch(e => this.showToast(errMsg(e))),

      // home
      currentAd, adDots, nextAd: () => this.setState(s => ({ adIndex: s.adIndex + 1 })), hasAds: ADSX.length > 0, noAds: !S.booting && ADSX.length === 0, adHasImage: false, adNoImage: true, adImageStyle: '',
      featuredCars: (sponsoredHome.length ? sponsoredHome : S.homeCars).map(favDecorate),
      // Home: destacados (solo promociones reales) y recientes, por separado
      homeFeatured: sponsoredHome.map(favDecorate), hasHomeFeatured: sponsoredHome.length > 0,
      heroTitle: heroBlock ? heroBlock.title : 'Encontrá tu próximo vehículo en Girando',
      heroLead: heroBlock ? (heroBlock.body || '') : 'Autos, camionetas, motos y utilitarios de particulares y agencias. Publicá gratis y gestioná tus avisos desde un solo lugar.',
      hasHeroCta: !!(heroBlock && heroBlock.cta_label), heroCtaLabel: heroBlock && heroBlock.cta_label, heroCta: () => heroBlock && this.homeCta(heroBlock.cta_target),
      // En mobile no hay portada grande: el bloque "hero" se muestra como aviso destacado (solo < 768 px)
      homeNotices: (S.homeBlocks || []).filter(b => b.kind !== 'hero' || b === heroBlock).map(b => ({ title: b.title, body: b.body || '', hasCta: !!b.cta_label, ctaLabel: b.cta_label || '', onCta: () => this.homeCta(b.cta_target),
        cls: b.kind === 'hero' ? 'gr-notice gr-notice--cta gr-hide-md' : (b.kind === 'cta' ? 'gr-notice gr-notice--cta' : 'gr-notice') })),
      hasHomeNotices: (S.homeBlocks || []).length > 0,
      homeRecent: S.homeCars.map(favDecorate), hasHomeRecent: S.homeCars.length > 0, noHomeRecent: !S.booting && S.homeCars.length === 0, homeLoading: S.booting,
      homeTypeChips: VEHICLE_TYPES.filter(([, v]) => v).map(([name, v]) => ({ name, onClick: () => { this.setState({ ...EMPTY_FILTERS, searchText: S.searchText, vehicleType: v }); this.go('listado'); } })), homeListTitle: sponsoredHome.length ? 'Destacados' : 'Recién publicados', hasHomeCars: sponsoredHome.length + S.homeCars.length > 0, noHomeCars: !S.booting && sponsoredHome.length + S.homeCars.length === 0,
      locationLabel, locationSheetOpen: S.locationSheetOpen, provinceChips, departmentChips,
      openLocationSheet: () => this.setState({ locationSheetOpen: true }), closeLocationSheet: () => this.setState({ locationSheetOpen: false }),
      jobs: [], jobsPreview: [], hasJobs: false, shops: [], shopCount: 0, brandChips: [], isEspecialistas: false, subBrandChips: [], services: [], serviceCount: 0, serviceChips: [],
      selectedShop: {}, selectedService: {}, selectedJob: {}, requestSheetOpen: false, requested: false, notRequested: true, applySheetOpen: false, applied: false, notApplied: true,
      openRequestSheet: () => {}, closeRequestSheet: () => {}, submitRequest: () => {}, openApplySheet: () => {}, closeApplySheet: () => {}, submitApply: () => {},

      // favoritos
      favCars: S.favItems.map(f => ({ ...favDecorate({ ...carFromPublic({ ...f, id: f.listing_id }), id: f.listing_id }), available: f.available, availLabel: f.available ? 'Disponible' : 'No disponible', availClass: f.available ? 'tag tag-success' : 'tag tag-muted', savedLabel: 'Guardado el ' + API.date(f.saved_at), onClick: () => f.available ? this.openDetail(f.public_code) : this.showToast('Esta publicación ya no está disponible') })),
      favCount: authed ? S.favIds.length : 0, hasFavs: authed && S.favItems.length > 0, authedNoFavs: authed && S.favItems.length === 0,

      // detalle
      selectedCar, selectedCarIsFav: isFavSel, selectedCarNotFav: !isFavSel, selectedCarFavLabel: isFavSel ? 'Quitar de favoritos' : 'Guardar en favoritos',
      detailCover: photo ? safeImg(photo.url) : '', photoCounter: imgs.length ? ((S.photoIdx % imgs.length) + 1) + ' / ' + imgs.length : 'Sin fotos',
      nextPhoto: () => imgs.length > 1 && this.setState(s => ({ photoIdx: (s.photoIdx + 1) % imgs.length })),
      prevPhoto: () => imgs.length > 1 && this.setState(s => ({ photoIdx: (s.photoIdx - 1 + imgs.length) % imgs.length })),
      hasManyPhotos: imgs.length > 1,
      detailThumbs: imgs.length > 1 ? imgs.map((im, i) => ({ id: im.id || String(i), url: safeImg(im.url), current: i === S.photoIdx % imgs.length ? 'true' : 'false',
        label: 'Ver foto ' + (i + 1) + ' de ' + imgs.length, onClick: () => this.setState({ photoIdx: i }) })) : [],
      publishedAgo: d && d.published_at ? 'Publicado ' + (API.ago(d.published_at).match(/^\d/) ? 'hace ' : '') + API.ago(d.published_at).toLowerCase() : '',
      toggleFavoriteCar: () => d && this.toggleFav(d.id),
      shareCar: () => { if (!d) return; const url = location.origin + '/#v/' + d.public_code; if (navigator.share) navigator.share({ title: 'Girando · ' + selectedCar.title, url }).catch(() => {}); else { try { navigator.clipboard.writeText(url); } catch (e) { /* noop */ } this.showToast('Enlace copiado'); } },
      contactSeller: () => this.requireAuth('contact', async () => {
        if (!d) return; this.setState({ contactOpen: true, contactLoading: true });
        try { this.setState({ contact: await API.get('/listings/' + encodeURIComponent(d.public_code) + '/contact') }); } catch (e) { this.setState({ contactOpen: false }); this.showToast(errMsg(e)); } finally { this.setState({ contactLoading: false }); }
      }),
      contactOpen: S.contactOpen, closeContact: () => this.setState({ contactOpen: false }), contactRows, contactLoading: S.contactLoading, contactEmpty: !S.contactLoading && !!contact && contactRows.length === 0,
      seoTitle: d ? [selectedCar.brand, selectedCar.model, selectedCar.version, selectedCar.year].filter(Boolean).join(' ') + (d.locality ? ' en ' + d.locality : '') : '',
      breadcrumb: d ? ['Vehículos', selectedCar.brand, selectedCar.model, selectedCar.year].filter(Boolean).join(' › ') : '',
      breadcrumbTail: d ? [selectedCar.brand, selectedCar.model, selectedCar.year].filter(Boolean).join(' › ') : '',
      publishedBy: d ? 'Publicado por ' + L('seller_type', d.seller_type) : '',
      sellerBadge: sellerVerified ? (d && d.agency ? '✓ Agencia verificada' : '✓ Identidad verificada') : (d && d.agency ? 'Agencia sin verificar' : 'Sin verificar'), sellerBadgeClass: sellerVerified ? 'tag tag-success' : 'tag tag-muted',
      trustRows: d ? [['Calificación', ratingText], ['En Girando desde', since ? String(since) : '—'], ['Publicaciones activas', d.seller_active_listings != null ? String(d.seller_active_listings) : '—']].map(([k, v]) => ({ k, v })) : [],
      trustSignals, sellerLine: d && d.agency ? 'Ver perfil de la agencia ›' : 'Contactalo desde Girando',
      openSellerProfile: () => { if (d && d.agency) this.openAgency(d.agency.slug); },
      similarCars: S.similar.map(favDecorate), hasSimilar: S.similar.length > 0, noSimilar: !!d && S.similar.length === 0,
      openReportSheet: () => this.requireAuth('report', async () => {
        this.setState({ reportOpen: true, reportSent: false, reportReason: null, reportDesc: '' });
        if (!S.reportReasonsApi.length) { try { const r = await API.get('/report-reasons', { target: 'listing' }); this.setState({ reportReasonsApi: r.items }); } catch (e) { this.showToast(errMsg(e)); } }
      }),
      closeReport: () => this.setState({ reportOpen: false }), reportSent: S.reportSent, reportNotSent: !S.reportSent, reportDisabled: !S.reportReason,
      reportReasons: S.reportReasonsApi.map(r => ({ label: r.label, selected: r.id === S.reportReason, onClick: () => this.setState({ reportReason: r.id }), dotStyle: RADIO(r.id === S.reportReason) })),
      reportDesc: S.reportDesc, onReportDesc: (e) => this.setState({ reportDesc: e.target.value }),
      submitReport: async () => { try { await API.post('/reports', { target: 'listing', code: d.public_code, reason_id: S.reportReason, description: S.reportDesc.trim() || null }); this.setState({ reportSent: true }); } catch (e) { this.showToast(errMsg(e)); } },

      // agencia pública
      agency: agData ? { id: agData.id, name: agData.trade_name, kind: L('seller_type', agData.kind === 'official_dealer' ? 'official_dealer' : 'agency'), address: [agData.street && (agData.street + ' ' + (agData.street_number || '')), agData.locality].filter(Boolean).join(', '),
        rating: agData.girando_rating ? String(agData.girando_rating).replace('.', ',') : '—', reviews: String(agData.girando_review_count || 0), since: String(agData.member_since || '—'), desc: agData.description || '',
        googleRating: agData.google_rating != null ? String(agData.google_rating).replace('.', ',') : '—', googleCount: agData.google_rating != null ? String(agData.google_review_count) : 'Sin datos' } : { id: '', name: 'Cargando…', kind: '', address: '', rating: '—', reviews: '0', since: '', desc: '', googleRating: '—', googleCount: '' },
      hasGoogle: !!(agData && agData.google_rating != null),
      agencyBadge: agData && agData.is_verified ? '✓ Agencia verificada' : 'Agencia sin verificar', agencyBadgeClass: agData && agData.is_verified ? 'tag tag-success' : 'tag tag-muted',
      agencyCars: agData ? (agData.listings || []).map(carFromPublic).map(favDecorate) : [], agencyCarCount: agData ? (agData.listings || []).length : 0, agencyNoCars: !!agData && !(agData.listings || []).length,
      goBackFromAgency: () => this.go(S.agencyReturn || 'listado'),
      // Canales externos de la agencia: pasan por /api/out (registra el clic sin datos personales y redirige)
      agencyChannels: agData ? AG_CHANNELS.filter(([, col]) => agData[col]).map(([k, , label]) => ({ label, href: '/api/out/agency/' + encodeURIComponent(agData.slug) + '/' + k })) : [],
      hasAgencyChannels: !!agData && AG_CHANNELS.some(([, col]) => agData[col]),
      contactAgency: () => this.requireAuth('contact', () => { if (!agData) return; this.setState({ contactOpen: true, contactLoading: false, contact: { phone: agData.phone_e164, whatsapp: agData.whatsapp_e164, email: agData.email } }); }),

      // búsqueda
      cars: cars.map(favDecorate), carCount: R.total, resultsLabel: S.results ? (R.total === 1 ? '1 vehículo' : R.total + ' vehículos') : 'Buscando…',
      hasMoreResults: !!S.results && R.items.length < R.total, loadMoreResults: () => this.loadMoreResults(), loadMoreLabel: S.loadingMore ? 'Cargando…' : 'Ver más resultados', loadingMore: !!S.loadingMore,
      shownLabel: S.results && R.total > R.items.length ? 'Mostrando ' + R.items.length + ' de ' + R.total : '', noResults: !!S.results && R.total === 0,
      hasSponsored: false, sponsoredCars: [],
      vehicleTypeChips: VEHICLE_TYPES.map(([name, v]) => ({ name, style: S.vehicleType === v ? CHIP_SEL : CHIP_UNSEL, onClick: () => this.setState({ vehicleType: v, marcaSel: [], modelSel: [] }) })),
      conditionChips: single(CONDITIONS, 'conditionFilter'), sellerTypeChips: single(SELLER_TYPES, 'sellerTypeFilter'),
      marcaChips: facetChips('marcaSel', 'brand'), modelChips, hasModelChips: S.marcaSel.length > 0 && modelChips.length > 0, noBrandForModels: S.marcaSel.length === 0,
      fuelChips: facetChips('fuelSel', 'fuel', 'fuel'), transChips: facetChips('transSel', 'transmission', 'transmission'), bodyChips: facetChips('bodySel', 'body_type', 'body_type'), tractionChips: facetChips('tractionSel', 'traction', 'traction'),
      pubChips, activeFilterChips: act, hasActiveFilters: act.length > 0, filtersBtnLabel: act.length ? 'Filtros · ' + act.length : 'Filtros',
      searchText: S.searchText, onSearch: (e) => this.setState({ searchText: e.target.value.slice(0, 100) }), onSearchKey: (e) => { if (e.key === 'Enter') this.go('listado'); },
      hasInterp: interpParts.length > 0, searchInterp: interpParts.join(' · '), sortBy: S.sortBy, onSort: (e) => this.setState({ sortBy: e.target.value }),
      yearFrom: S.yearFrom, yearTo: S.yearTo, priceFrom: S.priceFrom, priceTo: S.priceTo, kmFrom: S.kmFrom, kmTo: S.kmTo,
      on: { yearFrom: (e) => this.setState({ yearFrom: digits(e.target.value).slice(0, 4) }), yearTo: (e) => this.setState({ yearTo: digits(e.target.value).slice(0, 4) }), priceFrom: (e) => this.setState({ priceFrom: digits(e.target.value).slice(0, 12) }), priceTo: (e) => this.setState({ priceTo: digits(e.target.value).slice(0, 12) }), kmFrom: (e) => this.setState({ kmFrom: digits(e.target.value).slice(0, 7) }), kmTo: (e) => this.setState({ kmTo: digits(e.target.value).slice(0, 7) }) },
      sheetOpen: S.sheetOpen, reportOpen: S.reportOpen, toggleSheet: () => this.setState(s => ({ sheetOpen: !s.sheetOpen })), closeSheet: () => this.setState({ sheetOpen: false }),
      toggleFinanciable: () => this.setState(s => ({ financiableOnly: !s.financiableOnly })), togglePlanAhorro: () => {},
      clearFilters: () => this.setState({ ...EMPTY_FILTERS }),

      // auth
      authGateOpen: !!S.authGate, authGateTitle: gate.title, authGateBody: gate.body,
      closeAuthGate: () => { this._after = null; this.setState({ authGate: null }); },
      authContextLine: S.authReason ? (AUTH_GATES[S.authReason] || {}).line : 'Guardá favoritos, publicá y gestioná tus avisos.',
      loginEmail: S.loginEmail, loginPass: S.loginPass, loginError: S.loginError, loginNotice: S.loginNotice, authLoading: S.authLoading,
      regName: S.regName, regLast: S.regLast, regEmail: S.regEmail, regPass: S.regPass, regPass2: S.regPass2, regError: S.regError,
      passType: S.showPass ? 'text' : 'password', passToggleLabel: S.showPass ? 'Ocultar' : 'Mostrar', togglePass: () => this.setState(s => ({ showPass: !s.showPass })),
      onLoginEmail: (e) => this.setState({ loginEmail: e.target.value, loginError: null }), onLoginPass: (e) => this.setState({ loginPass: e.target.value, loginError: null }),
      onLoginKey: (e) => { if (e.key === 'Enter') this.renderVals().submitLogin(); },
      onRegName: (e) => this.setState({ regName: e.target.value, regError: null }), onRegLast: (e) => this.setState({ regLast: e.target.value, regError: null }),
      onRegEmail: (e) => this.setState({ regEmail: e.target.value, regError: null }), onRegPass: (e) => this.setState({ regPass: e.target.value, regError: null }), onRegPass2: (e) => this.setState({ regPass2: e.target.value, regError: null }),
      loginBtnLabel: S.authLoading ? 'Ingresando…' : 'Iniciar sesión', regBtnLabel: S.authLoading ? 'Creando tu cuenta…' : 'Crear cuenta',
      submitLogin: async () => {
        const em = S.loginEmail.trim().toLowerCase();
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(em)) return this.setState({ loginError: 'Revisá el email: el formato no es válido.' });
        if (!S.loginPass) return this.setState({ loginError: 'Ingresá tu contraseña.' });
        this.setState({ authLoading: true, loginError: null });
        try { await API.post('/auth/login', { email: em, password: S.loginPass }); await this.completeLogin(); }
        catch (e) { this.setState({ authLoading: false, loginError: errMsg(e) }); }
      },
      submitRegistro: async () => {
        const em = S.regEmail.trim().toLowerCase(); const name = [S.regName.trim(), S.regLast.trim()].filter(Boolean).join(' ');
        if (name.length < 2) return this.setState({ regError: 'Ingresá tu nombre.' });
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(em)) return this.setState({ regError: 'Ingresá un email válido.' });
        if (S.regPass.length < 8) return this.setState({ regError: 'La contraseña tiene que tener al menos 8 caracteres.' });
        if (S.regPass !== S.regPass2) return this.setState({ regError: 'Las contraseñas no coinciden.' });
        this.setState({ authLoading: true, regError: null });
        try { await API.post('/auth/register', { email: em, password: S.regPass, display_name: name, accept_terms: true }); await this.completeLogin(); this.showToast('¡Bienvenido a Girando!'); }
        catch (e) { this.setState({ authLoading: false, regError: errMsg(e) }); }
      },
      recoverStep: S.recoverStep, isRec1: S.recoverStep === 1, isRec2: S.recoverStep === 2, isRec3: S.recoverStep === 3, isRec4: S.recoverStep === 4,
      recoverNext: async () => {
        if (S.recoverStep === 1) {
          const em = S.loginEmail.trim().toLowerCase();
          if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(em)) { this.showToast('Ingresá un email válido'); return; }
          try { await API.post('/auth/password/forgot', { email: em }); this.setState({ recoverStep: 2 }); } catch (e) { this.showToast(errMsg(e)); }
        } else if (S.recoverStep === 2) { this.go('login'); }
        else if (S.recoverStep === 3) {
          if (S.regPass.length < 8) return this.setState({ regError: 'Usá al menos 8 caracteres.' });
          if (S.regPass !== S.regPass2) return this.setState({ regError: 'Las contraseñas no coinciden.' });
          try { await API.post('/auth/password/reset', { token: S.resetToken, password: S.regPass }); this.setState({ recoverStep: 4, regError: null, regPass: '', regPass2: '', resetToken: null }); }
          catch (e) { this.setState({ regError: errMsg(e) }); }
        }
      },
      resendRecover: () => API.post('/auth/password/forgot', { email: S.loginEmail.trim().toLowerCase() }).then(() => this.showToast('Si el email existe, te reenviamos el enlace')).catch(e => this.showToast(errMsg(e))),
      goLogin: () => this.setState(s => ({ screen: 'login', authGate: null, recoverStep: 1, returnScreen: s.authGate ? s.returnScreen : (['login', 'registro', 'recuperar'].includes(s.screen) ? s.returnScreen : s.screen) })),
      goRegistro: () => this.setState(s => ({ screen: 'registro', authGate: null, returnScreen: s.authGate ? s.returnScreen : (['login', 'registro', 'recuperar'].includes(s.screen) ? s.returnScreen : s.screen) })),
      goRecuperar: () => this.setState({ screen: 'recuperar', recoverStep: 1, regPass: '', regPass2: '', regError: null }),
      cancelAuth: () => { this._after = null; this.setState({ loginError: null, regError: null, authReason: null }); this.go(S.returnScreen || 'home'); },
      logout: async () => { try { await API.post('/auth/logout'); } catch (e) { /* la sesión igual se descarta */ } this.setState({ me: null, authed: false, isStaff: false, favIds: [], favItems: [], myListings: [], notifs: [], billing: null, authReason: null }); this.go('home'); this.showToast('Cerraste sesión'); },

      // publicar
      publishChooserOpen: S.publishChooserOpen, closePublishChooser: () => this.setState({ publishChooserOpen: false }),
      publishOptions: PUBLISH_OPTIONS.map(o => ({ ...o, onClick: () => { this.setState({ publishChooserOpen: false }); if (o.key === 'vehiculo') this.requireAuth('publish', () => this.goPublishVehicle()); else this.showToast('Muy pronto vas a poder publicar ' + o.label.toLowerCase() + 's'); } })),
      publishTitle: S.wzId && S.wzStatus !== 'draft' ? 'Editar publicación' : 'Publicar vehículo', goPublicarVehiculo: () => this.requireAuth('publish', () => this.goPublishVehicle()), goPublicar: () => this.requireAuth('publish', () => this.goPublishVehicle()), limitHit: S.limitHit,
      myListings: listingsView, myActiveListings: listingsAll.filter(l => l.statusCode === 'published'), myListingsCount: listingsAll.length, noListings: listingsView.length === 0,
      myActiveLabel: activeCount === 1 ? '1 publicación activa' : activeCount + ' publicaciones activas',
      myFilterChips: Object.keys(MY_FILTERS).map(n => ({ name: n, style: n === S.myFilter ? CHIP_SEL : CHIP_UNSEL, onClick: () => this.setState({ myFilter: n }) })),
      countedListings: listingsAll.filter(l => ['published', 'pending'].includes(l.statusCode)),
      effectivePlanName: planName, usageLabel, usageBarStyle, accountLabel: isAg ? 'Agencia · ' + ag.trade_name : 'Particular',
      limitTitle: usage.limit <= 1 ? 'Ya tenés una publicación activa' : 'Llegaste al límite de tu plan',
      limitBody: usage.limit <= 1 ? 'Con la cuenta Particular podés tener 1 publicación activa a la vez (publicada o en revisión). Para publicar otro vehículo, pausá o marcá como vendida la actual, o pasá a una cuenta Agencia.' : ('Tu plan ' + planName + ' incluye ' + usage.limit + ' publicaciones activas. Pasá a un plan superior o pausá alguna publicación.'),
      limitPrimaryLabel: isAg ? 'Ver planes' : 'Pasar a cuenta Agencia', onLimitPrimary: () => this.go('planes', { planTab: 'agencia', limitHit: true }),

      // asistente
      wz, wzStep: S.wzStep, isWz1: S.wzStep === 1, isWz2: S.wzStep === 2, isWz3: S.wzStep === 3, isWz4: S.wzStep === 4, isWz5: S.wzStep === 5,
      wzStepName: ['', 'Vehículo', 'Datos', 'Precio y ubicación', 'Fotos y descripción', 'Revisión'][S.wzStep],
      wzBars: [1, 2, 3, 4, 5].map(n => ({ style: 'background:' + (n <= S.wzStep ? 'var(--color-accent)' : 'var(--color-neutral-300)') + ';' })),
      // mismos pasos, en lista (sidebar de desktop). Solo muestra el avance: validar sigue siendo del backend.
      wzSteps: ['Vehículo', 'Datos', 'Precio y ubicación', 'Fotos y descripción', 'Revisión'].map((name, i) => ({ n: i + 1, name,
        state: i + 1 < S.wzStep ? 'done' : (i + 1 === S.wzStep ? 'current' : 'todo'), mark: i + 1 < S.wzStep ? '✓' : String(i + 1), current: i + 1 === S.wzStep ? 'step' : 'false' })),
      wzChips: { type: wzChip('type', WZ_TYPES, catLocked), fuel: wzChip('fuel', FUELS), trans: fixedChip(wzV && L('transmission', wzV.transmission)), doors: fixedChip(wzV && wzV.doors ? String(wzV.doors) : ''), traction: fixedChip(wzV && L('traction', wzV.traction)), condition: wzChip('condition', [['Usado', 'used'], ['Nuevo', 'new']]),
        extras: [{ name: 'Financiable', selected: wz.financiable, style: wz.financiable ? CHIP_SEL : CHIP_UNSEL, onClick: () => this.setWz('financiable', !wz.financiable) }, { name: 'Acepta permuta', selected: wz.permuta, style: wz.permuta ? CHIP_SEL : CHIP_UNSEL, onClick: () => this.setWz('permuta', !wz.permuta) }] },
      wzFuelShown: fuelCode, wzFuelIsCatalog: !wz.fuel,
      wzOn: { brand: (e) => this.setWz('brandId', e.target.value), model: (e) => this.setWz('modelId', e.target.value), gen: (e) => this.setWz('genId', e.target.value), version: (e) => this.setWz('versionId', e.target.value),
        year: (e) => this.setWz('year', e.target.value), km: (e) => this.setWz('km', digits(e.target.value).slice(0, 7)), color: (e) => this.setWz('color', e.target.value.slice(0, 40)), price: (e) => this.setWz('price', digits(e.target.value).slice(0, 12)),
        currency: (e) => this.setWz('currency', e.target.value), province: (e) => this.setWz('provinceId', e.target.value), dept: (e) => this.setWz('deptId', e.target.value), body: () => {}, zone: () => {},
        title: (e) => this.setWz('title', e.target.value.slice(0, 70)), desc: (e) => this.setWz('desc', e.target.value.slice(0, 5000)), yt: (e) => this.setWz('yt', e.target.value.trim().slice(0, 200)) },
      brandOpts: brands.map(b => ({ value: b.id, label: b.name })), modelOpts: models.map(m => ({ value: m.id, label: m.name })), genOpts: gens.map(g => ({ value: g.id, label: g.name })), versionOpts: versions.map(v => ({ value: v.id, label: v.name })),
      wzNoBrand: !wz.brandId || catLocked, wzNoModel: !wz.modelId || catLocked, wzNoGen: !wz.genId || catLocked, wzCatLocked: catLocked, wzNoBrandsForType: !!S.cat.brands[wz.type] && brands.length === 0,
      wzVersionObj: wzV ? { engine: defEngine ? defEngine.name : '—', trans: L('transmission', wzV.transmission), traction: L('traction', wzV.traction) } : null, wzVehicleName,
      yearOpts, bodyOpts: wzV ? [{ value: wzV.body_type, label: L('body_type', wzV.body_type) }] : [], wzBody: wzV ? wzV.body_type : '',
      provinceOpts: S.provinces.map(p => ({ value: p.id, label: p.name })), deptOpts: (S.depts[wz.provinceId] || []).map(x => ({ value: x.id, label: x.name })),
      wzCantNext: !wzValid[S.wzStep] || S.wzBusy, wzNextLabel: S.wzBusy ? 'Guardando…' : (S.wzStep === 5 ? (isSubmitStatus ? 'Enviar a revisión' : 'Guardar cambios') : 'Continuar'),
      wzNext: () => { if (!wzValid[S.wzStep] || S.wzBusy) return; this.wzAdvance(); },
      wzBack: () => { if (S.wzStep > 1) this.setState({ wzStep: S.wzStep - 1 }); else this.go('misPublicaciones'); },
      wzBusy: S.wzBusy, wzSaveDraft: () => this.wzSaveDraft(),wzShowSaveDraft: !S.wzId || S.wzStatus === 'draft', wzDraftLabel: S.wzBusy ? 'Guardando…' : 'Guardar borrador y salir',
      requestCatalog: () => this.showToast('Escribinos a soporte con la marca, modelo y versión. Lo sumamos al catálogo.'),
      wzSummary: [['Marca', nameOf(brands, wz.brandId)], ['Modelo', nameOf(models, wz.modelId)], ['Generación', nameOf(gens, wz.genId)], ['Versión', nameOf(versions, wz.versionId)], ['Motor', defEngine ? defEngine.name : '—'], ['Año', wz.year],
        ['Kilómetros', wz.km !== '' ? API.km(+wz.km) : '—'], ['Combustible', fuelCode ? L('fuel', fuelCode) : '—'], ['Transmisión', wzV ? L('transmission', wzV.transmission) : '—'], ['Carrocería', wzV ? L('body_type', wzV.body_type) : '—'], ['Tracción', wzV ? L('traction', wzV.traction) : '—'],
        ['Ubicación', [nameOf(S.depts[wz.provinceId] || [], wz.deptId), nameOf(S.provinces, wz.provinceId)].filter(Boolean).join(', ')], ['Precio', wz.price ? API.money(wz.price, wz.currency) : '—']].map(([k, v]) => ({ k, v: v || '—' })),
      wzTitleShown: wz.title.trim() || 'Todavía no escribiste un título',
      photoSlots: slots, photoCountLabel: okCount + ' de 6 fotos', photosFull: okCount >= 6,
      onMultiFiles: (e) => { const files = Array.from(e.target.files || []); e.target.value = ''; const free = 6 - photos.length; files.slice(0, free).forEach((f, k) => this.uploadPhoto(f, photos.length + k)); if (files.length > free) this.showToast('Máximo 6 fotos por publicación'); },
      descTips: DESC_TIPS.map(([label, pre]) => ({ label, onClick: () => this.setWz('desc', (wz.desc ? wz.desc.replace(/\s*$/, '') + '\n' : '') + pre) })),
      checklist: checks.map(([label, done, tag]) => ({ label, tag, icon: done ? '✓' : '', iconStyle: done ? 'background:var(--color-success-100);color:var(--color-success);' : 'border:1.5px solid var(--color-neutral-300);' })),
      completenessLabel: 'Tu publicación está ' + pct + '% completa', completenessBar: 'width:' + pct + '%;background:' + (pct === 100 ? 'var(--color-success)' : 'var(--color-accent)') + ';',
      urlBoxOpen: false, urlDraft: '', toggleUrlBox: () => {}, onUrlDraft: () => {}, urlIsLoading: false, urlIsError: false, urlIsOk: false, urlError: '', urlPreviewStyle: '', previewUrl: () => {}, addUrlPhoto: () => {},

      // planes / checkout / suscripción
      planTabs: [['particular', 'Particular'], ['agencia', 'Agencias']].map(([k, l]) => ({ label: l, selected: S.planTab === k, onClick: () => this.setState({ planTab: k }), style: SEG(S.planTab === k) })),
      plansView: plansCfg.filter(p => (S.planTab === 'agencia' ? p.audience === 'agency' : p.audience === 'particular')).map(p => {
        const isCur = usage.plan && usage.plan.id === p.id; const free = +p.price_amount === 0;
        return { ...p, badge: p.badge_label || null, tagline: p.description || '', features: Array.isArray(p.features_display) ? p.features_display : [], priceLabel: free ? 'Gratis' : API.money(p.price_amount, p.currency), periodLabel: free ? '' : ' /mes',
          limitLabel: 'Hasta ' + p.max_active_listings + (p.max_active_listings === 1 ? ' publicación activa' : ' publicaciones activas'), isCurrent: isCur,
          cta: isCur ? 'Tu plan actual' : (free ? 'Plan gratuito' : 'Elegir ' + p.name), btnClass: isCur || free ? 'btn btn-secondary' : (p.badge_label ? 'btn btn-primary' : 'btn btn-secondary'),
          cardStyle: isCur ? 'border:2px solid var(--color-text);' : (p.badge_label ? 'border:2px solid var(--color-accent);' : 'border:1px solid var(--color-neutral-300);'),
          onChoose: () => { if (free) { this.showToast('Es el plan gratuito de toda cuenta Particular'); return; } this.requireAuth('publish', () => { this.setState({ screen: 'checkout', ckPlanId: p.id, ckStep: this.myAgency() ? 'metodo' : 'agencia', ckError: null }); if (!S.provinces.length) this.loadGeo(); }); } };
      }),
      goPlanes: () => this.go('planes'), goPlanesAgencia: () => this.go('planes', { planTab: 'agencia' }), goSuscripcion: () => this.requireAuth('account', () => this.go('suscripcion')),
      ckTitle: S.ckStep === 'pendiente' ? 'Suscripción' : 'Suscribirte', ckPlan: { ...ckPlan }, ckPlanPrice: API.money(ckPlan.price_amount, ckPlan.currency || 'ARS'), ckPlanLimit: 'Hasta ' + ckPlan.max_active_listings + ' publicaciones activas',
      isCkAgencia: S.ckStep === 'agencia', isCkMetodo: S.ckStep === 'metodo', isCkMp: S.ckStep === 'mp', isCkProcesando: S.ckStep === 'procesando', isCkAprobado: false, isCkTransfer: false, isCkPendiente: S.ckStep === 'pendiente', isCkNoDisponible: S.ckStep === 'nodisponible',
      ckError: S.ckError, ckBusy: S.ckBusy, ckAg: S.ckAg,
      ckAgOn: ['trade', 'legal', 'cuit', 'tax', 'provinceId', 'deptId'].reduce((o, f) => { o[f] = (e) => { const v = e.target.value; this.setState(s => ({ ckAg: { ...s.ckAg, [f]: v, ...(f === 'provinceId' ? { deptId: '' } : {}) }, ckError: null })); if (f === 'provinceId') this.loadDepts(v); }; return o; }, {}),
      ckDeptOpts: (S.depts[S.ckAg.provinceId] || []).map(x => ({ value: x.id, label: x.name })),
      ckMethods: [['mp', 'Mercado Pago', 'Tarjeta, dinero en cuenta y otros medios. Débito automático mensual.']].map(([k, l, hnt]) => ({ label: l, hint: hnt, selected: true, onClick: () => {}, dotStyle: RADIO(true) })),
      ckNext: () => { if (S.ckStep === 'agencia') this.createAgencyAndContinue(); else if (S.ckStep === 'metodo') this.setState({ ckStep: 'mp' }); },
      ckBack: () => { const back = { metodo: this.myAgency() ? null : 'agencia', mp: 'metodo', nodisponible: 'metodo' }[S.ckStep]; if (back) this.setState({ ckStep: back, ckError: null }); else this.go('planes'); },
      goMercadoPago: () => this.startMercadoPago(), bankRows: [], confirmTransfer: () => {},
      hasSubscription: !!sub, subPlanName: sub ? sub.plan_name : planName, subStatusLabel: subInfo ? subInfo[0] : 'Gratis', subStatusClass: subInfo ? subInfo[1] : 'tag tag-outline',
      subRows: sub ? [{ k: sub.status === 'canceled' ? 'Finaliza' : 'Próximo cobro', v: sub.current_period_end ? API.date(sub.current_period_end) : 'Al acreditarse el pago' }, { k: 'Monto', v: API.money(sub.price_amount, sub.currency) + ' /mes' }, { k: 'Medio de pago', v: sub.provider === 'mercadopago' ? 'Mercado Pago' : (sub.provider || '—') }]
        : [{ k: 'Precio', v: 'Gratis' }, { k: 'Incluye', v: usage.limit + (usage.limit === 1 ? ' publicación activa' : ' publicaciones activas') }],
      subBanner: sub ? ({ pending: 'Estamos esperando la confirmación de Mercado Pago. Tu plan se activa cuando se acredite el pago, no antes.', payment_failed: 'Mercado Pago rechazó el último cobro. Actualizá tu medio de pago en Mercado Pago para evitar interrupciones.', grace_period: 'No pudimos cobrar tu plan. Tenés hasta el ' + API.date(sub.grace_until) + ' para regularizar.', canceled: 'Cancelaste tu suscripción. El plan sigue activo hasta el ' + API.date(sub.current_period_end) + '.', expired: 'Tu suscripción expiró. Volviste al límite Particular. No se borró nada.' })[sub.status] || null : null,
      subBannerStyle: sub && ['payment_failed', 'expired'].includes(sub.status) ? NOTE_STYLE.bad : NOTE_STYLE.warn,
      payHistoryView: ((bill && bill.payments) || []).map(p => { const ps = PAY_STATUS[p.status] || [p.status, 'tag tag-muted']; return { concept: p.concept || 'Suscripción', date: API.date(p.paid_at || p.created_at), method: p.provider === 'mercadopago' ? 'Mercado Pago' : p.provider, amount: API.money(p.amount, p.currency), status: ps[0], statusClass: ps[1] }; }),
      noPayments: !((bill && bill.payments) || []).length,
      manageOpen: S.manageOpen, manageConfirm: S.manageConfirm, manageMenu: !S.manageConfirm,
      openManage: () => this.setState({ manageOpen: true, manageConfirm: false }), closeManage: () => this.setState({ manageOpen: false }), backManage: () => this.setState({ manageConfirm: false }),
      manageOptions: [{ label: 'Cambiar de plan', style: '', onClick: () => { this.setState({ manageOpen: false }); this.go('planes', { planTab: 'agencia' }); } },
        { label: 'Actualizar medio de pago', style: '', onClick: () => { this.setState({ manageOpen: false }); this.showToast('El medio de pago se cambia desde tu cuenta de Mercado Pago'); } },
        ...(sub && ['active', 'pending', 'payment_failed', 'grace_period'].includes(sub.status) ? [{ label: 'Cancelar suscripción', style: 'color:var(--color-danger);', onClick: () => this.setState({ manageConfirm: true }) }] : [])],
      subCancelUntil: sub && sub.current_period_end ? API.date(sub.current_period_end) : 'el fin del período pagado',
      confirmCancel: () => this.cancelSubscription(),

      // mi girando
      goHome: () => this.go('home'), goListado: () => this.go('listado'), goBuscar: () => this.go('buscar'), goEmpleos: () => this.go('empleos'), goRepuestos: () => this.go('repuestos'), goServicios: () => this.go('servicios'),
      goPerfil: () => this.go('perfil'), goMisPublicaciones: () => this.requireAuth('publish', () => this.go('misPublicaciones')), goPostulaciones: () => this.go('postulaciones'), goCalificaciones: () => this.go('calificaciones'),
      goPerfilPublico: () => this.go('perfilPublico'), goConfiguracion: () => this.go('configuracion'), goFavoritos: () => this.go('favoritos'),
      goMensajes: () => this.showToast('Los mensajes llegan muy pronto. Mientras tanto, contactá al vendedor por sus datos de contacto.'),
      goNotificaciones: () => this.requireAuth('account', () => this.go('notificaciones', { notifReturn: S.screen === 'notificaciones' ? S.notifReturn : S.screen })),
      goBackNotifs: () => this.go(S.notifReturn || 'home'), goEstadisticas: () => this.go('estadisticas'), goVerificacion: () => this.go('verificacion'),
      goVentas: () => this.go('ventas', { ventasTab: 'resumen' }), goVentasHistorial: () => this.go('ventas', { ventasTab: 'historial' }),
      hasUnreadMsgs: false, hasUnreadNotifs: authed && unreadNotifs > 0, unreadMsgsLabel: 'Próximamente', unreadNotifsLabel: unreadNotifs ? (unreadNotifs === 1 ? '1 sin leer' : unreadNotifs + ' sin leer') : 'Estás al día',
      applicationsLabel: 'Próximamente', applicationsList: [], noApplications: true, appFilterChips: [],
      reviewTabs: [], reviewsList: [], rateOpen: false, rateSent: false, rateNotSent: true, rateDisabled: true, openRate: () => {}, rateBtnLabel: 'Calificar a un usuario', closeRate: () => {}, submitRate: () => {}, rateStarButtons: [],
      myRatingLabel: me.girando_rating ? String(me.girando_rating).replace('.', ',') : '—',
      saveConfig: async () => {
        const c = S.cfg; const body = { display_name: c.name.trim(), is_public: c.isPublic, show_phone_default: c.showPhone };
        const ph = c.phone.trim(); if (ph) { const n = digits(ph); body.contact_phone_e164 = ph.startsWith('+') ? '+' + n : '+54' + n; body.contact_whatsapp_e164 = body.contact_phone_e164; }
        try { const me2 = await API.patch('/me/profile', body); this.setState({ me: me2 }); this.showToast('Cambios guardados'); this.go('perfil'); } catch (e) { this.showToast(errMsg(e)); }
      },
      cfg: S.cfg, userEmail: me.email || '',
      cfgOn: { name: (e) => { const v = e.target.value.slice(0, 60); this.setState(s => ({ cfg: { ...s.cfg, name: v } })); }, phone: (e) => { const v = e.target.value.slice(0, 20); this.setState(s => ({ cfg: { ...s.cfg, phone: v } })); },
        showPhone: () => this.setState(s => ({ cfg: { ...s.cfg, showPhone: !s.cfg.showPhone } })), isPublic: () => this.setState(s => ({ cfg: { ...s.cfg, isPublic: !s.cfg.isPublic } })) },
      commPrefs: [toggleRow(['Emails de tu cuenta', 'Seguridad y avisos necesarios para operar. No se pueden desactivar.'], true, true), toggleRow(['Promociones y novedades', 'Próximamente vas a poder elegirlo. Hoy no te enviamos comunicaciones comerciales.'], false, true)],
      marketingConsentLine: null,
      sessionsView: S.sessions.map(se => ({ device: se.device_label || (se.platform === 'web' ? 'Navegador web' : se.platform || 'Dispositivo'), meta: (se.ip ? se.ip + ' · ' : '') + 'Último uso ' + API.dateTime(se.last_seen_at || se.created_at), current: !!se.current })),
      hasOtherSessions: S.sessions.filter(se => !se.current).length > 0,
      closeOtherSessions: async () => { try { await API.post('/auth/logout-others'); this.showToast('Cerramos las demás sesiones'); this.loadConfig(); } catch (e) { this.showToast(errMsg(e)); } },
      accountEvents: [],
      openLegal: (doc) => () => window.open('/api/legal/' + doc, '_blank', 'noopener'),
      openTerms: () => window.open('/api/legal/terminos', '_blank', 'noopener'), openPrivacy: () => window.open('/api/legal/privacidad', '_blank', 'noopener'), openCookiesDoc: () => window.open('/api/legal/cookies', '_blank', 'noopener'),

      // mensajes (próximamente)
      noConvos: true, convosView: [], chat: { with: '', withType: '', carTitle: '', carPrice: '' }, chatMessages: [], chatTyping: false, chatBlocked: false, chatCanSend: false, chatEmpty: false, chatDraft: '', chatDraftEmpty: true,
      onChatDraft: () => {}, onChatKey: () => {}, sendChat: () => {}, quickReplies: [], chatMenuOpen: false, openChatMenu: () => {}, closeChatMenu: () => {}, reportChat: () => {}, blockChat: () => {},

      // notificaciones
      notifChips: NOTIF_FILTERS.map(([n]) => ({ name: n, style: n === S.notifFilter ? CHIP_SEL : CHIP_UNSEL, onClick: () => this.setState({ notifFilter: n }) })),
      notifsView: notifsFiltered.map(n => ({ ...n, type: ({ listing: 'Publicaciones', account: 'Cuenta', billing: 'Suscripción', verification: 'Verificación', security: 'Seguridad' })[n.category] || 'Girando', time: API.ago(n.created_at),
        dotStyle: !n.read_at ? 'background:var(--color-accent);' : 'background:transparent;', rowStyle: !n.read_at ? 'background:var(--color-accent-100);' : '',
        onClick: async () => { if (!n.read_at) { try { await API.post('/me/notifications/' + n.id + '/read'); } catch (e) { /* noop */ } this.loadNotifs(); } const sc = pathToScreen(n.action_path); if (sc) this.go(sc); } })),
      noNotifs: notifsFiltered.length === 0,
      markAllRead: async () => { try { await API.post('/me/notifications/read-all'); } catch (e) { /* noop */ } this.loadNotifs(); },

      // estadísticas de la agencia (eventos reales: perfil y clics a sus canales)
      hasAgStats: isAg && !!S.agStats, agStatsEmpty: isAg && !!S.agStats && !(S.agStats.totals.profile_views || S.agStats.totals.external_clicks),
      agStatsKpis: S.agStats ? [['Visitas al perfil', S.agStats.totals.profile_views], ['Clics a tus canales', S.agStats.totals.external_clicks]].map(([label, v]) => ({ label, value: String(v || 0) })) : [],
      agStatsChannels: S.agStats ? AG_CHANNELS.map(([k, , label]) => ({ label, value: String((S.agStats.external_clicks || {})[k] || 0) })).filter(c => c.value !== '0') : [],
      // perfil de la agencia
      isMiAgencia: screen === 'miAgencia' && isAg, goMiAgencia: () => this.requireAuth('account', () => this.go('miAgencia')),
      miAgenciaSub: isAg ? (usage.used + ' de ' + usage.limit + ' publicadas · ' + (ag.inventory_total || 0) + ' en inventario') : '',
      agFields: AG_FIELDS.map(([k, label, type, ph]) => ({ id: 'ag-' + k, label, placeholder: ph, value: (S.agForm && S.agForm[k]) || '', isArea: type === 'area', isInput: type !== 'area', type: type === 'area' ? 'text' : type,
        onChange: (e) => { const v = e.target.value; this.setState(s2 => ({ agForm: { ...(s2.agForm || {}), [k]: v }, agFormError: null })); } })),
      agFormError: S.agFormError, agSaveLabel: S.agSaving ? 'Guardando…' : 'Guardar perfil', saveAgency: () => this.saveAgencyProfile(),
      agCounters: (() => { const P = S.agProfile; const inv = (P && P.inventory) || {}; const invTotal = Object.entries(inv).filter(([k]) => k !== 'sold').reduce((n, [, v]) => n + Number(v), 0);
        return [['Publicadas', (P && P.usage ? P.usage.used : usage.used) + ' de ' + (P && P.usage ? P.usage.limit : usage.limit), 'Cuentan para tu plan (publicadas y en revisión)'],
          ['Inventario', String(invTotal), [inv.draft && inv.draft + ' borradores', inv.paused && inv.paused + ' pausadas', inv.requires_changes && inv.requires_changes + ' con cambios pedidos', inv.expired && inv.expired + ' vencidas'].filter(Boolean).join(' · ') || 'Todo lo cargado y no vendido'],
          ['Plan', (P && P.usage && P.usage.plan && P.usage.plan.name) || planName, P && P.usage && P.usage.subscription && P.usage.subscription.current_period_end ? 'Vigente hasta ' + fmtDate(P.usage.subscription.current_period_end) : ''],
          ['Verificación', VSTATE_LABEL[(P && P.verification_state) || ag && ag.verification_state] || '—', 'El sello aparece solo con aprobación de Girando']].map(([k, v, h]) => ({ k, v, h })); })(),
      agPublicUrl: isAg && ag.slug ? '#a/' + ag.slug : '', openMyAgencyPage: () => { if (isAg && ag.slug) this.openAgency(ag.slug); },
      // estadísticas
      statsScope: isAg ? 'Tus publicaciones y las de tu agencia' : 'Tus publicaciones',
      statsPeriods: [['7', 'Últimos 7 días'], ['30', 'Últimos 30 días']].map(([k, l]) => ({ label: l, selected: S.statsPeriod === k, onClick: () => { this.setState({ statsPeriod: k }, () => { this.loadStats(); this.loadAgencyStats(); }); }, style: SEG(S.statsPeriod === k) })),
      statsKpis: st ? [['Visitas', tot.views], ['Favoritos', tot.favorites], ['Consultas', tot.contacts], ['Compartidas', tot.shares]].map(([label, v]) => ({ label, value: String(v || 0) })) : [],
      statsRows: st ? st.listings.map(r => ({ title: r.title || 'Publicación', visits: r.views, saves: r.favorites, leads: r.contacts })) : [],
      statsEmpty: !!st && !st.has_data, statsNote: st ? (st.has_data ? st.note : 'Todavía no hay datos suficientes. Las métricas aparecen cuando tus publicaciones reciben visitas.') : 'Cargando…',
      promosView: [], noPromos: true, promoOpen: false, closePromo: () => {}, promoTargetTitle: '', promoProducts: [], confirmPromo: () => {},

      // verificación
      isAgencyAccount: isAg, isParticularAccount: !isAg,
      verifRowTitle: isAg ? 'Verificación de agencia' : 'Verificación de identidad', verifRowSub: isAg ? 'Mostrá el distintivo “Agencia verificada”' : 'Aumenta la confianza en tus publicaciones',
      verifStatus: verif, verifStatusClass: VERIF_CLASS[verif] || 'tag tag-outline',
      verifIntro: isAg ? ({ 'Verificada': 'Tu agencia muestra el distintivo “Agencia verificada” en su perfil y publicaciones.', 'Verificación en revisión': 'Recibimos tu solicitud. El equipo de Girando la revisa y te avisamos por notificación. El distintivo no significa que Girando inspeccionó los vehículos.', 'Rechazada': 'No pudimos validar los datos. Revisalos y enviá la solicitud de nuevo.' })[verif] || 'Tu agencia todavía no está verificada. Revisamos los datos de la empresa, la información fiscal y el responsable. El distintivo no significa que Girando inspeccionó los vehículos.'
        : (me.identity_verified ? 'Tu identidad está verificada. Tus publicaciones lo muestran.' : 'La verificación de identidad de particulares llega muy pronto. Mientras tanto tus publicaciones muestran “Identidad sin verificar”.'),
      verifShowForm: isAg && !['Verificada', 'Verificación en revisión', 'Suspendida'].includes(verif),
      submitVerif: async () => { try { await API.post('/me/agencies/' + ag.id + '/verification'); this.showToast('Solicitud enviada'); await this.loadMe(); this.loadBilling(); } catch (e) { this.showToast(errMsg(e)); } },
      verifAgency: ag ? { name: ag.trade_name } : { name: '' },

      // ventas
      salesHubLabel: curMonth.length + ' este mes · historial y estadísticas', photoGraceDays: 7,
      sale, saleStepNum: sale.step || 1, isSale1: sale.step === 1, isSale2: sale.step === 2, isSale3: sale.step === 3,
      saleVehicleRows: sl ? [['Vehículo', [sl.brand, sl.model].filter(Boolean).join(' ')], ['Versión', sl.version], ['Año', sl.year], ['Kilómetros', API.km(sl.km)], ['Precio publicado', API.money(sl.price_amount, sl.currency)], ['Publicada el', API.date(sl.first_published_at)]].map(([k, v]) => ({ k, v: v || '—' })) : [],
      saleChannels: SALE_CHANNELS.map(([k, l, hnt]) => ({ label: l, hint: hnt, selected: sale.channel === k, onClick: () => this.setState(s => ({ sale: { ...s.sale, channel: k } })), dotStyle: RADIO(sale.channel === k) })),
      saleNoChannel: !sale.channel, saleFinTypes: FIN_TYPES.map(([value, label]) => ({ value, label })),
      saleFinChips: [['No', false], ['Sí', true]].map(([n, v]) => ({ name: n, selected: sale.financed === v, style: sale.financed === v ? CHIP_SEL : CHIP_UNSEL, onClick: () => this.setState(s => ({ sale: { ...s.sale, financed: v } })) })),
      saleOn: ['date', 'patente', 'price', 'currency', 'finType', 'cuotas', 'finAmount', 'notes'].reduce((o, f) => { o[f] = (e) => { let v = e.target.value; if (['price', 'cuotas', 'finAmount'].includes(f)) v = digits(v).slice(0, 12); if (f === 'patente') v = v.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 7); if (f === 'notes') v = v.slice(0, 1000); this.setState(s => ({ sale: { ...s.sale, [f]: v } })); }; return o; }, {}),
      saleCantSubmit: !!sale.busy || !(sale.date && sale.price && (!sale.financed || sale.finType)) || (sale.date > today()),
      saleNext: () => { if (sale.step === 1 && sale.channel) this.setState(s => ({ sale: { ...s.sale, step: 2 } })); else if (sale.step === 2) this.commitSale(); },
      saleBack: () => { if (sale.step === 2) this.setState(s => ({ sale: { ...s.sale, step: 1 } })); else this.go('misPublicaciones'); },
      lastSale: S.lastSale ? { id: S.lastSale.public_code || String(S.lastSale.id).slice(0, 8) } : { id: '' },
      lastSaleRows: S.lastSale ? [['Vehículo', [S.lastSale.listing.brand, S.lastSale.listing.model].join(' ')], ['Versión', S.lastSale.listing.version], ['Año', S.lastSale.listing.year], ['Precio final', API.money(S.lastSale.body.final_price, S.lastSale.body.currency)], ['Vendida el', fmtDate(S.lastSale.body.sold_on)], ['Financiada', S.lastSale.body.is_financed ? 'Sí · ' + L('financing', S.lastSale.body.financing_type) : 'No'], ['Canal', L('channel', S.lastSale.body.channel)]].map(([k, v]) => ({ k, v: v || '—' })) : [],
      ventasTabs: [['resumen', 'Estadísticas'], ['historial', 'Historial']].map(([k, l]) => ({ label: l, selected: S.ventasTab === k, onClick: () => this.setState({ ventasTab: k }), style: SEG(S.ventasTab === k) })),
      isVentasResumen: S.ventasTab === 'resumen', isVentasHistorial: S.ventasTab === 'historial',
      salesMonthLabel: 'Este mes · ' + monthLabel(nowMonth), salesNoData: sItems.length === 0,
      salesKpis: [['Vehículos vendidos (mes)', String(curMonth.length)], ['Vehículos vendidos (total)', String(sum.count || 0)], ['Precio promedio', sum.avg_price_ars != null ? API.money(sum.avg_price_ars, 'ARS') : 'Sin datos suficientes'], ['Días promedio hasta vender', sum.avg_days_to_sell != null ? String(sum.avg_days_to_sell) : 'Sin datos suficientes'], ['Ventas atribuidas a Girando', String(sum.attributed || 0) + ' de ' + (sum.count || 0)]].map(([label, value]) => ({ label, value })),
      funnel: [],
      byModel: (sum.by_model || []).map(g => ({ name: g.name, count: g.count, detail: g.avg_price_ars != null ? 'Vendido en promedio ' + API.money(g.avg_price_ars, 'ARS') : 'Datos insuficientes para promedios (mínimo ' + minN + ')' })),
      pubCounts: [['Activas', String(activeCount)], ['Vendidas', String(sum.count || 0)], ['Vencidas', String(listingsAll.filter(l => l.statusCode === 'expired').length)]].map(([k, v]) => ({ k, v })),
      exportCsv: () => { const head = ['Venta', 'Fecha', 'Marca', 'Modelo', 'Versión', 'Año', 'Km', 'Precio publicado', 'Precio final', 'Moneda', 'Financiada', 'Tipo', 'Cuotas', 'Canal', 'Días hasta venta'];
        const cell = (c) => { let s = String(c == null ? '' : c); if (/^[=+\-@]/.test(s)) s = "'" + s; return '"' + s.replace(/"/g, '""') + '"'; };
        const rows = sItems.map(s => [s.public_code, s.sold_on, s.brand, s.model, s.version, s.year, s.km, s.listed_price, s.final_price, s.currency, s.is_financed ? 'Sí' : 'No', s.financing_type ? L('financing', s.financing_type) : '', s.installments || '', L('channel', s.channel), s.days_to_sell == null ? '' : s.days_to_sell]);
        const csv = [head, ...rows].map(r => r.map(cell).join(';')).join('\n'); try { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob(['﻿' + csv], { type: 'text/csv' })); a.download = 'girando-ventas.csv'; a.click(); } catch (e) { /* noop */ } this.showToast('Descargamos girando-ventas.csv'); },
      salesFilter: SF, salesOn: { month: setF('month'), brand: setF('brand'), model: setF('model'), price: setF('price') },
      salesMonths: uniq(sItems.map(monthOf)).map(m => ({ value: m, label: monthLabel(m) })), salesBrands: uniq(sItems.map(s => s.brand)).sort(), salesModels: uniq(sItems.filter(s => SF.brand === 'Todas' || s.brand === SF.brand).map(s => s.model)).sort(),
      salesFinChips: ['Todas', 'Financiadas', 'Sin financiar'].map(n => ({ name: n, selected: SF.fin === n, style: SF.fin === n ? CHIP_SEL : CHIP_UNSEL, onClick: () => this.setState(s => ({ salesFilter: { ...s.salesFilter, fin: n } })) })),
      salesCountLabel: sList.length === 1 ? '1 venta' : sList.length + ' ventas',
      salesList: sList.map(s => ({ ...s, id: s.public_code || String(s.id).slice(0, 8), date: fmtDate(s.sold_on), name: [s.brand, s.model, s.version].filter(Boolean).join(' '), km: API.km(s.km), loc: '', priceLabel: API.money(s.final_price, s.currency),
        finLabel: s.is_financed ? 'Financiada' : 'Contado', finClass: s.is_financed ? 'tag tag-accent' : 'tag tag-muted', channelShort: s.channel === 'other_channel' ? 'Otro canal' : 'Girando', channelClass: s.channel === 'other_channel' ? 'tag tag-outline' : 'tag tag-success', onOpen: () => this.go('ventaDetalle', { saleSel: s.id }) })),
      noSales: sList.length === 0,
      saleView: saleView ? { id: saleView.public_code || String(saleView.id).slice(0, 8) } : { id: '' }, saleViewRows: saleView ? recRows(saleView) : [],

      // cookies
      cookieBannerOpen: !S.cookieConsent && !S.cookieSettingsOpen && ['login', 'registro', 'recuperar', 'checkout'].indexOf(screen) === -1,
      acceptCookies: () => this.saveCookieConsent({ necesarias: true, preferencias: true, analitica: true, marketing: true }),
      rejectCookies: () => this.saveCookieConsent({ necesarias: true, preferencias: false, analitica: false, marketing: false }),
      openCookieSettings: () => this.setState({ cookieSettingsOpen: true }), closeCookieSettings: () => this.setState({ cookieSettingsOpen: false }), cookieSettingsOpen: S.cookieSettingsOpen,
      cookieCats: [['necesarias', ['Necesarias', 'Sesión, seguridad y funciones básicas. Siempre activas.'], true], ['preferencias', ['Preferencias', 'Recordar tu ubicación y filtros']], ['analitica', ['Analítica', 'Medir el uso de forma agregada para mejorar Girando']], ['marketing', ['Marketing', 'Mostrar publicidad relevante fuera de Girando']]]
        .map(([k, m, locked]) => toggleRow(m, locked ? true : !!S.cookieCats[k], !!locked, () => this.setState(s => ({ cookieCats: { ...s.cookieCats, [k]: !s.cookieCats[k] } })))),
      saveCookies: () => this.saveCookieConsent({ necesarias: true, ...S.cookieCats }),

      // shell responsive: header (tablet/desktop), navegación lateral de Mi Girando (desktop)
      screen,
      shellLayout: authed && ACCOUNT_SCREENS.includes(screen) ? 'account' : 'default',
      showAccountNav: authed && ACCOUNT_SCREENS.includes(screen),
      accountNav: [
        ['Inicio', 'perfil', ['perfil']], ['Mis publicaciones', 'misPublicaciones', ['misPublicaciones']], ['Favoritos', 'favoritos', ['favoritos']],
        ['Mensajes', 'mensajes', ['mensajes'], true], ['Notificaciones', 'notificaciones', ['notificaciones']], ['Postulaciones', 'postulaciones', ['postulaciones']],
        ['Suscripción', 'suscripcion', ['suscripcion']], ['Historial de ventas', 'ventas', ['ventas', 'ventaDetalle']], ['Estadísticas', 'estadisticas', ['estadisticas']],
        ...(isAg ? [['Mi agencia', 'miAgencia', ['miAgencia']]] : []),
        ['Configuración', 'configuracion', ['configuracion', 'verificacion', 'calificaciones']],
      ].map(([label, key, match, soon]) => ({ label, soon: !!soon, current: match.includes(screen) ? 'page' : 'false',
        badge: key === 'notificaciones' && unreadNotifs ? String(unreadNotifs) : '',
        onClick: () => { if (key === 'mensajes') this.showToast('Los mensajes llegan muy pronto. Mientras tanto, contactá al vendedor por sus datos de contacto.'); else if (key === 'notificaciones') this.go('notificaciones', { notifReturn: 'perfil' }); else this.go(key); } })),
      topNav: [
        ['Inicio', () => this.go('home'), ['home']], ['Vehículos', () => this.go('listado'), ['listado', 'detalle', 'buscar', 'agencia']],
        ['Servicios', () => this.go('servicios'), ['servicios'], true], ['Empleos', () => this.go('empleos'), ['empleos'], true], ['Repuestos', () => this.go('repuestos'), ['repuestos'], true],
        ['Planes para agencias', () => this.go('planes'), ['planes', 'checkout', 'limite']],
      ].map(([label, onClick, match, soon]) => ({ label, onClick, soon: !!soon, current: match.includes(screen) ? 'page' : 'false' })),
      favCurrent: screen === 'favoritos' ? 'page' : 'false', acctCurrent: ACCOUNT_SCREENS.includes(screen) && screen !== 'favoritos' ? 'page' : 'false',
      notifsAria: unreadNotifs ? 'Notificaciones, ' + unreadNotifs + ' sin leer' : 'Notificaciones',
      openPublishChooser: () => this.setState({ publishChooserOpen: true }),
      goHomeLink: (e) => { if (e) e.preventDefault(); this.go('home'); },
      filtersOpen: S.sheetOpen ? 'true' : 'false',

      // navegación inferior
      showBottomNav: onNav && !anySheet,
      navItems: navDef.map(n => { const active = n.match.includes(screen); return { label: n.label, isPublish: n.key === 'publish', notPublish: n.key !== 'publish', current: active ? 'page' : 'false', style: '',
        barStyle: active ? 'background:var(--color-accent);' : 'background:transparent;', labelStyle: n.key === 'publish' ? 'font-weight:700;color:var(--color-accent-700);' : (active ? 'font-weight:700;color:var(--color-text);' : 'font-weight:600;color:var(--color-muted);'),
        onClick: () => { if (n.key === 'publish') this.setState({ publishChooserOpen: true }); else this.go(n.key); } }; }),
    };
    if (window.__GR_CHECK) window.__GR_KEYS = Object.keys(out);
    return out;
  }
}
