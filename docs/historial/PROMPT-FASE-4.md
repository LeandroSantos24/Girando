# GIRANDO — FASE 4: el portal automotor que le gana a todos en 2026

Te habla el director del proyecto. Vas a trabajar como un equipo completo de producto e ingeniería sobre el repositorio de
Girando, en local (no hay nada desplegado). Antes de escribir una línea, leé:

1. `docs/10-contexto-girando.md` — qué es Girando, cómo gana plata y las reglas que no se negocian.
2. `README.md`, `SECURITY.md`, `ARCHITECTURE.md`.
3. `docs/05` a `docs/09` (roles, planes y finanzas, promociones y métricas, verificación y email, gap analysis de la fase 3).
4. El código: `backend/sql/` (migraciones 0001–0003), `backend/app/api/routers/`, `backend/app/cli.py`, `web/src/`.

No rehagas lo que funciona. Extendelo. Todo lo nuevo entra como migraciones nuevas (`0004_…`, `0005_…`), nunca editando las anteriores.

---

## Cómo vas a trabajar: roles

Organizate con estos roles y hacé explícito en tus notas cuál está actuando en cada decisión:

| Rol | Responsabilidad |
|---|---|
| **Product manager** | Prioriza, define criterios de aceptación, corta alcance. Nada de “50 features”: cada cosa tiene que servir para vender publicidad, planes o atraer tráfico. |
| **Arquitecto de datos (PostgreSQL)** | Modelo, enums, constraints, RLS, triggers, índices de búsqueda. La base hace cumplir las reglas de negocio. |
| **Backend (FastAPI)** | Endpoints, validación, permisos por rol, idempotencia, jobs del worker. |
| **Diseñador UX/UI** | Experiencia simple, blanca y agradable; navegación por vertical; filtros claros; mobile primero, desktop impecable. |
| **Frontend** | Implementación en `web/src/` (App y Admin), accesibilidad, rendimiento, sin estado de negocio en el navegador. |
| **Pagos** | Todas las rutas de cobro y de mejora de plan, Mercado Pago (sandbox), webhooks, estados de suscripción. |
| **Seguridad y privacidad** | Roles, RLS, datos mínimos, consentimiento de cookies (Ley 25.326), rate limits, auditoría. |
| **Cumplimiento** | Publicidad de crédito (TNA, TEA, CFT), uso de marcas de bancos, régimen de permisos de taxi en Mendoza. Investigá en fuentes oficiales y citá. |
| **QA** | Tests de backend, E2E en 390×844, 768×1024 y 1440×900, pruebas de permisos por API directa, pruebas de todos los cobros. |

---

## Qué hay que construir (en este orden)

### 1. Marketplace de autos de primer nivel (prioridad máxima)

Es el corazón. Tiene que ser mejor que deRuedas y comparable con Mercado Libre Autos y Kavak.

**Filtros** (combinables, con contadores reales por opción, persistidos en la URL para compartir búsquedas):
- Precio (ARS y USD, con normalización por cotización BCRA ya existente), año desde/hasta, kilómetros desde/hasta.
- Marca, modelo, versión (múltiple), condición (0 km / usado), vendedor (particular, agencia, concesionaria oficial), verificado.
- **Carrocería**: Hatchback, Sedán, SUV, Crossover, Pick-Up, Rural, Coupé, Cabriolet, Roadster, Monovolumen, Minivan, Furgón, Van, Light Truck, Off-Road. Ampliá el enum `body_type` (hoy le faltan varias) y migrá los valores existentes.
- Combustible, transmisión, tracción, puertas, color, ubicación (provincia/departamento/radio).
- **Financiación**: apto crédito, entidad (Banco Nación, Supervielle, etc.), anticipo máximo que tengo disponible, cuota máxima, acepta permuta.
- Ordenar por relevancia, precio, año, km, más recientes.
- Búsquedas guardadas con aviso de novedades (la tabla `saved_searches` ya existe).

**Financiación en la publicación** (nueva entidad, no texto libre):
- Ofertas de financiación por entidad: nombre de la entidad, tipo (prendario, personal, propio de la agencia, plan de ahorro), anticipo mínimo, monto o porcentaje financiable, plazos, vigencia, condiciones y fuente.
- Si se muestra una tasa, mostrar **TNA, TEA y CFT** con la misma jerarquía visual que exige la normativa. Si no hay tasa, no se inventa.
- Calculadora “con cuánto lo retirás”: anticipo + cuotas, rotulada como **orientativa**, con los datos de la oferta.
- Logos de bancos: solo si el banco lo autorizó (marcalo como dato de la entidad con “logo autorizado: sí/no”); si no, nombre en texto.
- Las ofertas las carga la agencia o Girando (convenio). Moderación las aprueba antes de mostrarlas.

**Detalle y confianza**: fotos (Cloudinary, flujo real ya hecho), datos técnicos del catálogo, historial de precio, sello de verificación real, vendedor con su perfil y canales medidos, reporte de publicación.

### 2. Mi Girando: el apartado del usuario

- **Me gusta / favoritos**: lista de publicaciones que guardó, con aviso si bajan de precio o se venden.
- **Mis publicaciones**: vehículos y empleos publicados, estado, estadísticas, editar, pausar, vender.
- **Historial**: vistos recientemente, búsquedas guardadas, pagos y facturación, cambios de plan.
- **Plan gratis del particular**: **1 publicación activa gratis en total**: un vehículo **o** un puesto de trabajo (no uno de cada). Lo hace cumplir la base.
- Mensajes (ver punto 5) y notificaciones.

### 3. Planes y todas las rutas de cobro

Todo plan y precio vive en PostgreSQL y lo edita el Super Admin. Valores iniciales (marcalos como “a confirmar por el dueño”):

| Audiencia | Plan | Publicadas | Cobro |
|---|---|---|---|
| Particular | Free | 1 (vehículo o empleo) | Gratis |
| Agencia / concesionaria | Hasta 30 | 30 | Mensual |
| Agencia / concesionaria | Hasta 60 | 60 | Mensual |
| Agencia / concesionaria | Más de 60 | 100 (o el número que defina el dueño) | Mensual |
| Casa de repuestos | Repuestos verificada | Catálogo | **$ 4.000** obligatorio (período: mensual por defecto, a confirmar) |
| Prestador de servicios | Servicios | 1 ficha por rubro y zona | A definir (dejalo configurable, gratis por defecto) |

Rutas de cobro que tienen que **funcionar de punta a punta** (Mercado Pago sandbox + webhook firmado + simulador de webhook para tests locales + camino manual del Super Admin):
- Particular → destacar una publicación.
- Agencia → contratar plan, **subir de plan** (30 → 60 → más de 60), bajar de plan (rige al terminar el período; lo que excede se pausa, no se borra), cancelar.
- Casa de repuestos → pagar la suscripción **antes** de la verificación presencial; sin pago aprobado y verificación aprobada no publica.
- Promociones y publicidad.
- Cada ruta: estados visibles para el usuario, comprobante en su historial, auditoría, idempotencia (el webhook puede llegar dos veces) y prueba automática.

Upgrade a mitad de período: definí y documentá la regla (recomendado: el nuevo límite rige al aprobarse el pago y el período se reinicia; sin prorrateo en esta fase).

### 4. Verticales nuevas, cada una con su sector, su publicación y sus filtros

**Taxis y permisos** (sección exclusiva)
- Publicaciones de: taxi con permiso, permiso sin vehículo, vehículo apto taxi.
- Datos: tipo (taxi / remis), número de permiso declarado, departamento/zona, titular declarado, vehículo afectado, año (antigüedad máxima 10 años para incorporarse, uso hasta 13 según decreto; investigá y confirmá), GNC, reloj y GPS, equipamiento, precio del permiso y del vehículo por separado, si incluye trabajo con chofer.
- Filtros: zona/departamento, tipo, con o sin vehículo, año del vehículo, combustible (GNC, eléctrico), precio.
- Aviso fijo y visible: el permiso lo otorga el Estado (Ley 9086, Subsecretaría de Transporte) y su transferencia requiere autorización de la Dirección de Transporte. Girando no garantiza la transferencia.
- Sello “permiso verificado” solo con verificación real del equipo.
- Investigá en fuentes oficiales de Mendoza (mendoza.gov.ar, boletín oficial) y documentá lo que encuentres con links.

**Servicios**: grúas y auxilio, gestoría automotor, productores asesores de seguros (verificá matrícula de la Superintendencia de Seguros de la Nación como dato a validar), fletes, transporte de cargas y de pasajeros, mecánica, gomería, electricidad, chapa y pintura, lavadero, GNC, VTV/RTO.
- Filtros: rubro, zona de cobertura, atención 24 h, tipo de vehículo atendido, a domicilio, verificado.

**Repuestos**: casas de repuestos verificadas en persona (ver plan). Ficha del comercio y su catálogo por marca/modelo/categoría. Filtros por marca y modelo del vehículo, categoría, nuevo/usado, zona. El sello se otorga con: pago aprobado + verificación presencial + identidad del responsable + datos completos.

**Empleos**
- Publica una empresa o un particular (1 gratis del particular, compartido con vehículos).
- **No se suben CVs ni documentos.** El candidato se contacta por la mensajería de Girando.
- Filtros: puesto (chofer, mecánico, vendedor, administrativo, etc.), licencia requerida (profesional, categorías), zona, jornada, modalidad.

### 5. Mensajería interna

Base para empleos, vehículos y servicios (las tablas `conversations` y `messages` ya existen). Conversación por publicación, notificaciones, bloqueo y reporte, moderación, rate limit anti-spam, retención definida, sin exponer emails ni teléfonos salvo que el usuario los comparta.

### 6. Publicidad y recomendaciones (el fuerte económico)

- Espacios publicitarios por vertical y por página (Home, resultados, detalle), rotulados siempre, con impresiones y clics registrados desde la App (los eventos ya existen en la base; falta emitirlos) y reporte para el anunciante.
- **Recomendaciones**: “Te puede interesar” y “Similares” con eventos propios de Girando (vistas, favoritos, búsquedas, contactos) solo si el usuario aceptó cookies de analítica; sin consentimiento, solo por contexto. Empezá con reglas explicables (marca/modelo/carrocería/rango de precio/zona) y medí el resultado; nada de caja negra. Nada de cookies ni píxeles de terceros sin consentimiento.

### 7. Diseño

- Mantené la identidad: fondo blanco, azul de marca, logo, componentes actuales. Nada de rediseño total.
- Proponé y aplicá una tipografía más agradable (candidatas: Plus Jakarta Sans, Inter, Manrope; la actual es Sora). Servila **desde el propio servidor** (woff2, licencia OFL), no desde un CDN externo, para respetar la CSP.
- Navegación principal por vertical: Vehículos · Taxis · Servicios · Repuestos · Empleos. Cada una con su buscador y sus filtros.
- Mobile primero; desktop con filtros laterales. Sin scroll horizontal en ningún tamaño.

---

## Reglas (se heredan de las fases anteriores)

- Todo local. No se despliega nada. No se usan credenciales reales de producción.
- PostgreSQL es la única fuente de verdad. El backend y la base validan roles, límites y pagos.
- Nada de datos inventados: sin publicaciones, reseñas ni métricas de relleno. “Sin datos suficientes” cuando corresponda.
- Una suscripción o promoción se activa solo con pago aprobado o cortesía auditada del Super Admin.
- Datos personales mínimos. Documentos solo en almacenamiento privado.
- Cada cambio de estado relevante queda en auditoría.
- No borres migraciones, código, documentación ni datos que no sean de la base local de desarrollo.

## Cuándo frenar y preguntarme

Solo si una decisión cambia el modelo de negocio, la seguridad, implica costos importantes, es irreversible, toca datos o pagos reales o producción. Lo demás lo decidís vos, lo implementás y lo documentás.
Valores de negocio sin definir (precios, período de repuestos, plan de servicios): usá el valor inicial indicado, dejalo editable en el Admin y anotalo en la lista de decisiones pendientes.

## Definición de terminado

- Un visitante encuentra un auto con los filtros nuevos (carrocería, financiación, km, año, precio) y entiende con cuánto lo retira.
- Un particular publica 1 cosa gratis (vehículo o empleo) y la segunda se bloquea desde la base.
- Una agencia sube de 30 a 60 y a más de 60 pagando en sandbox; el límite cambia solo con el pago aprobado.
- Una casa de repuestos no puede publicar sin pagar la suscripción y sin verificación aprobada.
- Existen las secciones Taxis, Servicios, Repuestos y Empleos con publicación, filtros y moderación.
- Un candidato contacta a un empleador por mensajes, sin CV.
- Los espacios publicitarios registran impresiones y clics reales; las recomendaciones respetan el consentimiento.
- Tests de backend verdes (incluidos todos los cobros y permisos por API directa), ruff y bandit limpios, migraciones desde base vacía dos veces, E2E en los tres tamaños.

## Entregables

1. Código y migraciones nuevas.
2. Docs: `docs/11-…` en adelante (marketplace y filtros, financiación y cumplimiento, taxis, servicios, repuestos, empleos y mensajes, publicidad y recomendaciones, rutas de cobro) y actualización de `README.md`, `SECURITY.md` y `docs/10-contexto-girando.md`.
3. Informe final en español: qué hiciste, qué quedó pendiente, decisiones que tomaste, decisiones que necesito tomar yo, resultados de tests, y estado honesto (MVP técnico, comercial, listo para pruebas o listo para producción). No digas “listo para producción” si faltan integraciones, credenciales, seguridad operacional o pruebas reales.
