# Girando — Auditoría del estado actual (27/09/2026)

**Alcance revisado:** export de Claude Design "Mobile app design planning" (`Girando Autos.dc.html`, `Girando Admin.dc.html`, `Girando Reglas de negocio.dc.html`, `girando-data.js`, `girando-store.js`, `support.js`, `image-slot.js`, `ios-frame.jsx`, assets). El artifact compartido (`claude.ai/artifact/N1xx9w…`) es el mismo prototipo empaquetado. El repo `github.com/LeandroSantos24/Girando` está **vacío** (sin commits).

## 1. Estructura actual

| Pieza | Qué es | Tamaño |
|---|---|---|
| `Girando Autos.dc.html` | App móvil (≈45 pantallas: home, búsqueda, detalle, publicar en 5 pasos, mis publicaciones, venta, estadísticas, chat, notificaciones, suscripción/checkout, verificación, perfil, configuración, empleos, servicios, repuestos) | 327 KB (124 KB lógica + 203 KB template) |
| `Girando Admin.dc.html` | Panel admin (≈25 secciones: resumen, usuarios, agencias, publicaciones, catálogo, ventas, planes, suscripciones, pagos, promociones, publicidad, verificaciones, productos de verificación, reportes, mensajes, calificaciones, notificaciones, plantillas, cola de envíos, consentimientos, auditoría, retención) | 86 KB |
| `Girando Reglas de negocio.dc.html` | Documento de reglas (estados, límites, pagos, retención) | 26 KB |
| `girando-data.js` | Catálogo de ejemplo (6 marcas, anidado por nombre) + planes | 6 KB |
| `girando-store.js` | "Backend" simulado: un objeto en `localStorage` compartido entre App y Admin | 3 KB |
| `support.js`, `image-slot.js`, `ios-frame.jsx` | Runtime de Claude Design / marco iOS. **No son código de producto.** | — |

## 2. Backend, API y autenticación

- **No existe backend, API, base de datos ni rutas.** Todo es estado de React en el navegador + `localStorage`.
- **Autenticación simulada:** cualquier email válido con contraseña ≥ 6 caracteres "inicia sesión"; el usuario siempre es `juan.martinez@mail.com`. El estado de sesión y el de suscripción se fuerzan desde *props* de diseño (`sessionState`, `subscriptionState`).
- **Integraciones:** Mercado Pago, Cloudinary, email, Google Places y sesiones están **simuladas** (el propio documento de reglas lo declara). Deben quedar marcadas como *pendiente de integración real*.

## 3. Cómo se representan hoy las entidades

| Entidad | Representación actual | Problema |
|---|---|---|
| Vehículo/Publicación | Un solo objeto `CARS[]` que mezcla vehículo, publicación, vendedor y ubicación. Precio `'$ 21.000.000'`, km `'69.000 km'`, año `'2024'` como **strings formateados** | No hay separación vehículo/publicación; los filtros parsean texto; imposible indexar |
| Catálogo | Árbol anidado por **nombre** (sin IDs). `engine: '1.6 Nafta'` mezcla cilindrada y combustible | Renombrar rompe referencias; no hay entidad motor |
| Publicaciones del vendedor | `MY_LISTINGS[]` separado de `CARS[]` con otros IDs (`my1`) | Dos modelos distintos para lo mismo |
| Agencias | `AGENCIES{}` indexado por **nombre comercial**; verificación en `store.agencyVerif['Raina Automotores']` | Clave por nombre; sin CUIT único; sin miembros |
| Usuarios | Filas de texto en el admin; las agencias aparecen como "usuarios tipo Agencia" | Confunde cuenta con organización |
| Ventas | `SALES[]` en estado local de la App (no en el store) con patente en texto plano | El admin no ve ventas reales; `days: 56` fijo al registrar |
| Suscripción | **Un único** `store.subscription` global | No es por usuario/agencia |
| Pagos | Montos como texto (`'$ 54.900'`), método + referencia concatenados | No conciliable |
| Auditoría | Array posicional `[id, quién, qué, sobre, motivo, fecha]`; admin fijo "Sofía Ruiz" | Sin rol, IP, antes/después |

## 4. Datos hardcodeados (deben venir del backend)

`CARS`, `MY_LISTINGS`, `LISTING_META`, `SALES`, `AGENCIES` (+ ratings de Google de ejemplo), `CONVOS`, `NOTIFS`, `SESSIONS`, `ACCOUNT_EVENTS`, `REVIEWS_*`, `APPLICATIONS`, `PAY_HISTORY`, `PROMOS`, `PROMO_PRODUCTS` (precios $4.900/$8.900), `ADS`/`CAMPAIGNS` (concesionarias reales usadas como demo), `PROVINCES` y `DEPARTMENTS_BY_PROVINCE` (3 provincias), `JOBS`, `SHOPS`, `SERVICES`, datos bancarios de transferencia (CBU, alias, CUIT de "Girando S.A.S." — **de ejemplo**), `USD_RATE = 1250`, `PHOTO_GRACE_DAYS = 7`, filas y KPIs del admin (3.482 usuarios, 1.126 publicaciones, 186 suscripciones, ingresos $9,8 M, barras semanales), `RETENTION`, `MEDIA_SEED`, `AUDIT_SEED`, estadísticas por modelo del admin.

## 5. Datos duplicados

1. **Anuncios de publicidad**: `ADS` en la App y `CAMPAIGNS` en el store (mismo contenido).
2. **Planes**: `PLANS` (Gratuito/Bronce/Plata/Oro/Platino, "hasta 5/8/10 fotos", videos) en la App vs `GIRANDO_PLANS` (Particular/Agencia Básica/Pro/Premium). El primero es código muerto que contradice la regla de 6 fotos.
3. **Secciones del admin** definidas tres veces con `Object.assign` (versiones viejas de `publicaciones`, `usuarios`, `agencias`, `verificaciones` con otros estados).
4. **Publicaciones**: `CARS` + `MY_LISTINGS` + filas del admin + `listingId: 'P-88412'` de ventas → cuatro esquemas de ID.
5. **Lógica de validación de fotos** duplicada (`processFile` y `onPhotoFile`).

## 6. Inconsistencias App ↔ Admin

| # | Inconsistencia | Riesgo |
|---|---|---|
| 1 | Admin (resumen) usa estados `Moderación / Activa / Denunciada`; Admin (publicaciones) usa `Pendiente / Publicada`; `submitPublish` viejo de la App crea `'Activa'` | Estados que no existen en la máquina de estados |
| 2 | "Denunciada" aparece como estado en secciones viejas, pero las reglas dicen que es una alerta | Una denuncia podría ocultar publicaciones sin moderación |
| 3 | **Fail-open de confianza:** si una agencia no está en el store, la App la muestra como `'Verificada'` (`|| 'Verificada'`) | Se muestra "Agencia verificada" sin verificación |
| 4 | El filtro "Verificado" de búsqueda considera verificada a **toda agencia** (`sellerType !== 'Particular'`) y a un particular por ID fijo (`vento19`) | Sello de confianza falso |
| 5 | Verificación de identidad del particular vive solo en estado local de la App; aprobarla en Admin no cambia nada | Dos fuentes de verdad |
| 6 | Catálogo editado en Admin queda en el estado local del Admin (no se persiste en el store) → la App nunca lo ve | Admin "controla" algo que no aplica |
| 7 | Admin inicializa planes desde `GIRANDO_PLANS` y luego desde el store (carrera) | Puede mostrar precios viejos |
| 8 | Ventas registradas en la App no llegan al Admin (solo cambia el estado de la publicación) | Estadísticas del admin inventadas |
| 9 | Retención editable en Admin, pero la App usa la constante `PHOTO_GRACE_DAYS` y fecha fija `04/10/2026` | Configuración ignorada |
| 10 | Tipos de vehículo: búsqueda tiene *Cuatriciclo*, el asistente *Utilitario*; carrocería `Pick-Up` vs `Pickup`; transmisión `Automática CVT` vs `CVT` | Filtros que no matchean |
| 11 | La App **reactiva una suscripción** y el checkout de MP la **activa** desde el frontend | Autoconcesión de permisos |

## 7. Métricas inventadas (deben eliminarse, no migrarse)

- "Operaciones concretadas" = `reviews × 2,4`.
- "Contactos" = `consultas × 0,6`.
- Embudo fijo `24 / 143 / 61`.
- `pubCount()` del admin: número pseudoaleatorio por hash del nombre.
- Alerta "Precio 40 % bajo el promedio" fija.
- Visitas/favoritos/consultas por publicación como strings fijos.

## 8. Formularios y datos personales que ya pide el prototipo

- Registro: email, contraseña. Configuración: nombre y apellido, email, teléfono, "mostrar mi teléfono", "perfil público", preferencias de comunicación, cookies.
- Verificación de agencia: razón social, CUIT, condición fiscal, dirección del local, responsable, teléfono, email, constancia ARCA, habilitación comercial, DNI frente/dorso.
- Venta: fecha, patente (opcional), precio final, moneda, financiada, tipo, cuotas, monto financiado, observaciones. **No pide datos del comprador** (correcto).
- Postulación a empleo: nombre, apellido, teléfono, **edad**, tipo de carnet, experiencia, **CV en PDF** → datos personales de terceros; fuera del alcance de este modelo (módulo Empleos, fase 2) pero con impacto de privacidad.
- Solicitud de servicio: nombre, teléfono, **dirección**.

## 9. Lo que el prototipo ya resuelve bien (se conserva)

- Reglas de negocio escritas: límite por plan (published + pending), 409 `LIMITE_ALCANZADO`, estados de suscripción y cuáles otorgan permisos, webhook como fuente de verdad, transferencia aprobada solo por admin, "Vendida ≠ Eliminada", 60 días de vigencia + aviso a 3 días, 6 fotos JPG/PNG/WEBP ≤ 10 MB, "Patrocinado" separado del orden orgánico, mínimo 3 ventas para promedios, anti-spam (10 conversaciones/día, mensaje repetido), motivos de reporte, consentimiento con versión, retención configurable, "Agencia verificada no certifica los vehículos".
- El flujo del asistente de publicación ya elige Marca → Modelo → Generación → Versión del catálogo y autocompleta datos técnicos.
- Separación conceptual Vehículo / Publicación / Cuenta / Plan / Suscripción / Promoción / Verificación.

Todo esto se traslada al modelo y a la base (ver `01-modelo-de-datos.md`).
