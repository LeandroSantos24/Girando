// Servidor web de desarrollo SIN Docker: sirve web/ y hace de proxy de /api y /media hacia la API.
// Replica las mismas rutas y cabeceras de seguridad que web/nginx.conf (lo que corre en Docker).
//   node scripts/dev-web.mjs            → http://localhost:3100  (API en http://127.0.0.1:8100)
//   API_URL=http://127.0.0.1:8001 PORT=3001 node scripts/dev-web.mjs
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'web');
const PORT = +(process.env.PORT || 3100);
const API = new URL(process.env.API_URL || 'http://127.0.0.1:8100');
const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.jsx': 'text/babel; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp', '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.json': 'application/json' };
// Debe coincidir con web/security-headers.conf
const CSP = ["default-src 'self'", "script-src 'self' 'unsafe-eval'", "style-src 'self' 'unsafe-inline'", "img-src 'self' data: blob: https://res.cloudinary.com",
  "font-src 'self'", "connect-src 'self' https://api.cloudinary.com", "frame-src https://www.youtube-nocookie.com", "object-src 'none'", "base-uri 'self'",
  "form-action 'self'", "frame-ancestors 'none'"].join('; ');
const SEC = { 'Content-Security-Policy': CSP, 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'strict-origin-when-cross-origin',
  'Permissions-Policy': 'camera=(), microphone=(), geolocation=(), payment=(), usb=()', 'X-Frame-Options': 'DENY', 'Cross-Origin-Opener-Policy': 'same-origin' };
const ROUTES = { '/': '/index.html', '/admin': '/admin/index.html', '/admin/': '/admin/index.html' };
const HIDDEN = [/^\/src\//, /\.dc\.html$/, /^\/nginx/, /^\/Dockerfile/, /\.conf$/];

function proxy(req, res) {
  const opts = { hostname: API.hostname, port: API.port, path: req.url, method: req.method,
    headers: { ...req.headers, host: API.host, 'x-real-ip': req.socket.remoteAddress.replace('::ffff:', ''), 'x-forwarded-proto': 'http' } };
  const p = http.request(opts, (r) => { res.writeHead(r.statusCode, r.headers); r.pipe(res); });
  p.on('error', () => { res.writeHead(502, { 'content-type': 'application/json' }); res.end('{"error":{"code":"API_NO_DISPONIBLE","message":"La API no responde."}}'); });
  req.pipe(p);
}

http.createServer((req, res) => {
  const url = new URL(req.url, 'http://x');
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/media/')) return proxy(req, res);
  let rel = ROUTES[url.pathname] || decodeURIComponent(url.pathname);
  if (HIDDEN.some(r => r.test(rel))) { res.writeHead(404, SEC); return res.end('Not found'); }
  const file = path.join(ROOT, path.normalize(rel));
  if (!file.startsWith(ROOT)) { res.writeHead(403, SEC); return res.end(); }
  fs.readFile(file, (err, data) => {
    if (err) { res.writeHead(404, SEC); return res.end('Not found'); }
    const ext = path.extname(file);
    res.writeHead(200, { ...SEC, 'Content-Type': TYPES[ext] || 'application/octet-stream', 'Cache-Control': ext === '.html' ? 'no-cache' : 'public, max-age=300' });
    res.end(data);
  });
}).listen(PORT, () => console.log(`Girando web → http://localhost:${PORT}  (API ${API.href})`));
