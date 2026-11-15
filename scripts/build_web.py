"""Genera web/index.html (App) y web/admin/index.html (Admin).

    python3 scripts/build_web.py

Fuentes (lo que se edita):
  web/src/app.html      plantilla de la App (marcado del diseño de Claude Design, ya responsive)
  web/src/app-logic.js  lógica de la App (consume /api, sin datos inventados)
  web/src/admin.html    plantilla del Admin
  web/src/admin-logic.js
  web/css/app.css, web/css/admin.css   estilos (tokens del diseño + capa responsive)

El diseño original sigue en design/prototipo/*.dc.html como referencia visual; no se sirve.
Hasta la fase 1 este script aplicaba reemplazos sobre ese diseño. Desde la fase 2 (desktop + responsive)
la plantilla vive en web/src/ porque la estructura responsive (header, sidebars, grillas) ya no se
puede expresar como parches sobre el marcado mobile. Los HTML generados se versionan.
"""
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'web'


def css_version(path):
    return hashlib.sha256((WEB / path.lstrip('/')).read_bytes()).hexdigest()[:10]


def build(template, logic, out, css):
    t = (WEB / 'src' / template).read_text(encoding='utf-8')
    code = (WEB / 'src' / logic).read_text(encoding='utf-8')
    errors = []
    if '</script' in code:
        errors.append(f'{logic}: no puede contener </script')
    if t.count('<x-dc>') != 1 or t.count('</x-dc>') != 1:
        errors.append(f'{template}: tiene que tener un único <x-dc>…</x-dc>')
    if 'data-dc-script' in t:
        errors.append(f'{template}: la lógica va en {logic}, no en la plantilla')
    # Cache-busting de la hoja de estilos: cambia el HTML solo si cambia el CSS.
    link = f'<link rel="stylesheet" href="{css}">'
    if t.count(link) != 1:
        errors.append(f'{template}: falta {link}')
    if errors:
        print('\n'.join(errors))
        sys.exit(1)
    t = t.replace(link, f'<link rel="stylesheet" href="{css}?v={css_version(css)}">')
    t = t.rstrip()
    assert t.endswith('</x-dc>')
    html = (t + '\n<script type="text/x-dc" data-dc-script>\n' + code + '\n</script>\n</body>\n</html>\n')
    out_path = WEB / out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding='utf-8')
    # Controles mínimos de la salida
    if re.search(r'<x-import[^>]*IOSDevice', html):
        print(f'{out}: quedó el marco de iPhone'); sys.exit(1)
    print('ok', out, len(html))


if __name__ == '__main__':
    build('app.html', 'app-logic.js', 'index.html', '/css/app.css')
    build('admin.html', 'admin-logic.js', 'admin/index.html', '/css/admin.css')
