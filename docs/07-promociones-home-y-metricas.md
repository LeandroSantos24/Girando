# Promociones, Home, publicidad y métricas (fase 3)

## Promociones (entidad real)

Tabla `app.promotions` + historial `app.promotion_events`. Estados: `pending` → `active` ⇄ `paused` → `finished`, o
`canceled` desde cualquiera abierto. La App sabe si algo está promocionado solo por la vista `api_public.sponsored`
(promoción `active` y dentro de fechas). Nunca por cookies ni `localStorage`.

| Tipo | Ubicación posible | Necesita |
|---|---|---|
| Publicación destacada / posición promocionada | Home destacados, búsqueda | Código `P-XXXXXXXX` publicado |
| Agencia destacada | Directorio / Home | Agencia |
| Banner | Home banner | Anunciante, enlace https e imagen |

Reglas: una promoción con precio solo se activa con un pago aprobado (las cortesías tienen precio 0 y quedan auditadas);
pausar y cancelar piden motivo; un banner sin imagen no se activa; el worker la termina al vencer.
Hoy las crea el Super Admin (Admin → Promociones). Pendiente: que la agencia la compre con Mercado Pago y subir la imagen del banner a Cloudinary.

## Publicidad (diseño conceptual)

- Todo contenido pago se rotula **“Patrocinado”** (publicaciones, agencias) o **“Publicidad”** (banners). El rótulo lo guarda la base (`disclosure_label`) y la App lo muestra siempre.
- Solo material provisto por el anunciante, creado por Girando o con licencia.
- Espacios previstos: banner de Home, destacados de Home, arriba de la búsqueda, búsqueda por marca/modelo, directorio de agencias.
- Medición: impresiones y clics por promoción, sin datos personales. Los eventos (`promotion_impression`, `promotion_click`) existen en la base; **falta registrarlos desde la App** (pendiente, IMPORTANTE antes de vender promociones).
- Fuera de alcance: subasta de espacios, segmentación por usuario, redes publicitarias de terceros.

## Home administrable (sin CMS)

Admin → Home (solo Super Admin): bloques `hero` (portada), `announcement` (aviso) y `cta` (llamado a la acción) con título,
texto corto, botón (destino interno: listado, publicar, planes, registro, o un enlace https), orden, fechas y estado
(borrador/activo/archivado). La App los lee de `GET /api/home` (solo activos y en fecha). En mobile la portada se muestra
como aviso destacado. Los vehículos y agencias destacados se manejan desde Promociones, no desde acá.

## Clics a canales externos de agencias

La agencia carga su web, tienda online (Tienda Nube u otra), WhatsApp y redes en **Mi agencia**. En su perfil público
cada botón apunta a `GET /api/out/agency/{slug}/{canal}?l=P-XXXXXXXX`:

1. Busca el destino **guardado por la agencia** (no hay redirección abierta: no acepta URLs por parámetro).
2. Registra `external_click` con agencia, canal, publicación (si viene) y fecha. **Sin usuario ni IP.**
3. Responde `302` al destino (`Cache-Control: no-store`, `Referrer-Policy: origin`). Rate limit por IP (60/min).

## Métricas: solo eventos reales

- Agencia (Estadísticas): vistas, favoritos, consultas y compartidas por publicación (agregadas por el worker), visitas al perfil y clics por canal.
- Admin → Negocio: conteo de eventos de los últimos 30 días.
- Sin eventos se muestra **“Sin datos suficientes”**. No se estima, no se extrapola, no se multiplican datos.
- Los promedios de ventas se muestran recién con 3 ventas o más del modelo en el período.
