# Frontend responsive (fase 2)

Girando pasó de ser un prototipo mobile dentro de un marco de iPhone a una web responsive real.
Mismo frontend, mismo backend y mismos datos en mobile, tablet y desktop. La identidad visual
(logo, colores, Sora, radios, botones, tags, cards) no cambió: los tokens del diseño original
siguen al principio de `web/css/app.css`.

## Dónde está cada cosa

| Archivo | Qué es |
| --- | --- |
| `web/src/app.html` | Plantilla de la App (marcado del diseño + estructura responsive) |
| `web/src/admin.html` | Plantilla del Admin |
| `web/src/app-logic.js`, `admin-logic.js` | Lógica (datos de la API, navegación). Sin reglas de negocio nuevas |
| `web/css/app.css`, `admin.css` | Tokens y componentes del diseño + capa responsive |
| `web/girando-photo.js` | `<image-slot>` (fotos) y `<yt-embed>` (video de YouTube) |
| `scripts/build_web.py` | Une plantilla + lógica → `web/index.html` y `web/admin/index.html`, con hash de versión del CSS |
| `design/prototipo/` | Diseño original de Claude Design, solo como referencia |

Hasta la fase 1 los HTML se generaban aplicando reemplazos sobre `design/prototipo/*.dc.html`. Un layout
desktop (header, sidebars, grillas) no se puede expresar como parches sobre marcado de 390 px, así que
la plantilla pasó a `web/src/`. Los estilos inline del diseño se conservan; lo que depende del viewport
vive en clases (`gr-*` en la App, `ad-*` en el Admin).

## Breakpoints (mobile first)

| Nombre | Desde | Qué cambia |
| --- | --- | --- |
| mobile | 0 | Experiencia del diseño original: barra inferior, hojas desde abajo, cards compactas en fila |
| mobile grande | 600 px | Resultados en 2 columnas, galería 16:10 |
| tablet | 768 px | Header superior (logo, búsqueda, favoritos, notificaciones, Publicar, Mi Girando/Ingresar) y navegación de secciones; sin barra inferior; las hojas pasan a modales centrados; pie de página |
| desktop | 1024 px | Filtros en columna izquierda, detalle en 2 columnas con panel fijo, asistente con pasos laterales, Mi Girando con navegación lateral |
| desktop ancho | 1440 px | Tipografía de títulos y precios un poco mayor, más aire |

El contenido se centra en `--gr-container: 1360px`. En 1920 px queda aire lateral.

Admin (desktop first): sidebar fija desde 1200 px; por debajo, cajón con botón de menú (tablet y notebooks
chicas, así la tabla usa todo el ancho). Por debajo de 768 px la tabla principal se muestra como cards
(etiqueta + valor por celda). Tablas secundarias (planes, retención, ventas) hacen scroll dentro de su panel.

## Componentes y patrones

- **Shell**: `gr-app` → `gr-header` (≥768) · `gr-main` · `gr-footer` (≥768) · capas · `gr-tabbar` (<768).
  El documento hace scroll (antes: un contenedor absoluto dentro del iPhone).
- **Card de vehículo** (`gr-vcard`): un solo componente en Home, Buscar y Favoritos. Vertical (foto 4:3, título,
  año · km, precio, ubicación, vendedor y sello de verificación si el backend lo informa). Variante
  `gr-vcard--row`: en mobile vuelve a ser la card compacta del diseño. En la Home mobile, carrusel horizontal.
- **Grillas**: `gr-vgrid` (2/3/4 columnas) y `gr-vgrid--fluid` (`auto-fill, minmax(210px)`: 3 o 4 por fila según
  el ancho real al lado de los filtros).
- **Filtros** (`gr-filters`): el mismo marcado es hoja en mobile/tablet (`data-open`) y columna sticky en desktop.
- **Capas**: `gr-overlay` + `gr-sheet` (hoja abajo en mobile, modal centrado desde 768 px). Escape las cierra.
- **Mi Girando**: `gr-main[data-layout=account]` agrega la navegación lateral (`gr-acct-nav`) en desktop.
- **Asistente de publicación**: `gr-wizard` con lista de pasos lateral en desktop; en mobile, barra de pasos original.
  Las validaciones siguen siendo del backend.
- **Utilidades**: `gr-show-md`, `gr-hide-md`, `gr-show-lg`, `gr-hide-lg` (solo presentación).

## Accesibilidad

- Foco visible en todo lo interactivo; enlace "Saltar al contenido".
- Cards y filas con `role="link"`/`role="button"` + `tabindex`, activables con Enter/Espacio.
- Botones con nombre accesible también cuando solo muestran ícono (header en tablet, menú del Admin).
- Escape cierra hojas/modales (App) y el menú lateral (Admin).
- Sin dependencia de hover: todas las acciones están visibles.

## Sin datos inventados

- Home: "Destacados" solo aparece si hay promociones reales; "Recién publicados" sale de la API; si no hay
  publicaciones se muestra un estado vacío. El espacio patrocinado explica qué va ahí; no simula anuncios.
- Servicios, Empleos, Repuestos y Mensajes siguen marcados como "Pronto/Próximamente".

## Cómo verificar

```bash
python3 scripts/build_web.py                 # regenerar
python3 scripts/e2e_checkpoint.py http://localhost:3100 --viewport 1440x900
python3 scripts/e2e_checkpoint.py http://localhost:3100 --viewport 768x1024
python3 scripts/e2e_checkpoint.py http://localhost:3100 --viewport 390x844
```

Probado en 1920×1080, 1440×900, 1366×768, 1024×768, 768×1024, 390×844 y 375×812 (Home, Buscar, Detalle,
Publicar, Ingresar/Registro, Mi Girando, Mis publicaciones, Favoritos, Configuración, Suscripción, Planes,
Admin): sin scroll horizontal del documento en ningún caso.
