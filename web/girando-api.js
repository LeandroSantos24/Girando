// Girando — cliente de la API (única fuente de verdad para App y Admin).
// - Sesión en cookies httpOnly (el JS nunca ve tokens).
// - CSRF double-submit: cookie gr_csrf + header X-CSRF-Token en toda mutación.
// - Si el access token expiró (401) intenta un refresh una vez y reintenta.
// - Errores con formato {error:{code,message}} → se lanzan como ApiError.
(function () {
  const BASE = '/api';

  class ApiError extends Error {
    constructor(status, code, message, detail) { super(message || code); this.status = status; this.code = code; this.detail = detail; }
  }

  function readCookie(name) {
    const m = document.cookie.split('; ').find(c => c.startsWith(name + '='));
    return m ? decodeURIComponent(m.split('=')[1]) : null;
  }

  let csrfPromise = null;
  async function ensureCsrf() {
    if (readCookie('gr_csrf')) return readCookie('gr_csrf');
    if (!csrfPromise) csrfPromise = fetch(BASE + '/auth/csrf', { credentials: 'same-origin' }).then(r => r.json()).then(j => j.csrf_token).finally(() => { csrfPromise = null; });
    return csrfPromise;
  }

  let refreshing = null;
  async function tryRefresh() {
    if (!refreshing) {
      refreshing = (async () => {
        const token = await ensureCsrf();
        const r = await fetch(BASE + '/auth/refresh', { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRF-Token': token } });
        return r.ok;
      })().finally(() => { setTimeout(() => { refreshing = null; }, 0); });
    }
    return refreshing;
  }

  function qs(params) {
    if (!params) return '';
    const u = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v === undefined || v === null || v === '' || v === false) return;
      if (Array.isArray(v)) v.forEach(x => u.append(k, x)); else u.append(k, v);
    });
    const s = u.toString();
    return s ? '?' + s : '';
  }

  async function request(method, path, { body, params, form, retry = true } = {}) {
    const headers = { 'Accept': 'application/json' };
    const unsafe = !['GET', 'HEAD'].includes(method);
    if (unsafe) headers['X-CSRF-Token'] = await ensureCsrf();
    let payload;
    if (form) payload = form;
    else if (body !== undefined) { headers['Content-Type'] = 'application/json'; payload = JSON.stringify(body); }
    const res = await fetch(BASE + path + qs(params), { method, headers, body: payload, credentials: 'same-origin' });
    if (res.status === 401 && retry && !path.startsWith('/auth/login') && !path.startsWith('/auth/refresh')) {
      if (await tryRefresh()) return request(method, path, { body, params, form, retry: false });
    }
    if (res.status === 403 && retry && unsafe) {
      const j = await res.clone().json().catch(() => ({}));
      if (j.error && j.error.code === 'CSRF_INVALIDO') {
        document.cookie = 'gr_csrf=; Max-Age=0; path=/';
        await ensureCsrf();
        return request(method, path, { body, params, form, retry: false });
      }
    }
    const text = await res.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch (e) { data = null; }
    if (!res.ok) {
      const e = (data && data.error) || {};
      throw new ApiError(res.status, e.code || ('HTTP_' + res.status), e.message || 'Ocurrió un error. Probá de nuevo.', e.detail);
    }
    return data;
  }

  const api = {
    ApiError,
    get: (p, params) => request('GET', p, { params }),
    post: (p, body) => request('POST', p, { body: body || {} }),
    put: (p, body) => request('PUT', p, { body: body || {} }),
    patch: (p, body) => request('PATCH', p, { body: body || {} }),
    del: (p) => request('DELETE', p, {}),
    upload: (p, file, fields) => { const f = new FormData(); f.append('file', file); Object.entries(fields || {}).forEach(([k, v]) => f.append(k, v)); return request('POST', p, { form: f }); },
    csrf: ensureCsrf,
    // Formateo
    money(amount, currency) {
      if (amount === null || amount === undefined || amount === '') return 'Sin precio';
      const n = Number(amount);
      return (currency === 'USD' ? 'USD ' : '$ ') + n.toLocaleString('es-AR', { maximumFractionDigits: 0 });
    },
    km(n) { return (n === null || n === undefined) ? '—' : Number(n).toLocaleString('es-AR') + ' km'; },
    date(iso) { if (!iso) return '—'; const d = new Date(iso); return d.toLocaleDateString('es-AR'); },
    dateTime(iso) { if (!iso) return '—'; const d = new Date(iso); return d.toLocaleDateString('es-AR') + ' ' + d.toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' }); },
    ago(iso) {
      if (!iso) return '';
      const s = (Date.now() - new Date(iso).getTime()) / 1000;
      if (s < 60) return 'Ahora'; if (s < 3600) return Math.floor(s / 60) + ' min'; if (s < 86400) return Math.floor(s / 3600) + ' h';
      if (s < 172800) return 'Ayer'; return new Date(iso).toLocaleDateString('es-AR', { day: 'numeric', month: 'short' });
    },
  };

  // Etiquetas en español para los códigos técnicos de la base
  api.LABELS = {
    status: { draft: 'Borrador', pending: 'Pendiente', published: 'Publicada', paused: 'Pausada', requires_changes: 'Requiere cambios', rejected: 'Rechazada', sold: 'Vendida', expired: 'Expirada', deleted: 'Eliminada' },
    fuel: { gasoline: 'Nafta', diesel: 'Diésel', cng: 'GNC', gasoline_cng: 'Nafta/GNC', hybrid: 'Híbrido', plugin_hybrid: 'Híbrido enchufable', electric: 'Eléctrico', other: 'Otro' },
    transmission: { manual: 'Manual', automatic: 'Automática', cvt: 'CVT', automated_manual: 'Automatizada', other: 'Otra' },
    traction: { front: 'Delantera', rear: 'Trasera', '4x2': '4x2', '4x4': '4x4', awd: 'AWD' },
    body_type: { sedan: 'Sedán', hatchback: 'Hatchback', suv: 'SUV', pickup: 'Pickup', coupe: 'Coupé', convertible: 'Cabrio', wagon: 'Familiar', van: 'Furgón', minivan: 'Monovolumen', chassis: 'Chasis', motorcycle: 'Moto', other: 'Otro' },
    vehicle_type: { car: 'Auto', light_truck: 'Camioneta', van: 'Utilitario', truck: 'Camión', motorcycle: 'Moto', atv: 'Cuatriciclo', other: 'Otro' },
    condition: { new: 'Nuevo', used: 'Usado' },
    seller_type: { particular: 'Particular', agency: 'Agencia', official_dealer: 'Concesionaria oficial' },
    agency_status: { pending: 'Pendiente', review: 'Verificación en revisión', verified: 'Verificada', rejected: 'Rechazada', suspended: 'Suspendida', revoked: 'Revocada' },
    user_status: { pending: 'Pendiente', active: 'Activo', suspended: 'Suspendido', blocked: 'Bloqueado', deleted: 'Eliminado' },
    channel: { girando: 'A través de Girando', buyer_from_girando: 'Cliente de Girando', other_channel: 'Otro canal' },
    financing: { bank_loan: 'Crédito bancario', pledge_loan: 'Crédito prendario', dealer_financing: 'Financiación propia', savings_plan: 'Plan de ahorro', other: 'Otro' },
    verification: { pending: 'Pendiente', review: 'En revisión', approved: 'Aprobada', rejected: 'Rechazada', revoked: 'Revocada' },
  };
  api.label = (group, v) => (api.LABELS[group] && api.LABELS[group][v]) || v || '—';

  window.GirandoAPI = api;
})();
