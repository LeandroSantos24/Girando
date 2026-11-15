# Girando — Investigación: traza de datos, publicidad inteligente y paneles (15/11/2026)

Para qué sirve este documento: decidir **cómo medir**, **cómo vender y servir publicidad con inteligencia**, **cómo mostrarle
resultados a quien paga** y **cómo deben ser los paneles** de Super Admin, Admin, comercios y personas. Está pensado para que
lo lea el equipo (o el agente) que implementa la fase 4 junto con `docs/10-contexto-girando.md` y `docs/PROMPT-FASE-4.md`.

Las fuentes están al final. Donde algo es opinión o recomendación propia, se dice.

---

## 0. Resumen en 12 decisiones

1. **La medición de publicidad la tiene que tener el propio código de Girando.** Es lo que se factura y se le muestra al anunciante: no puede depender de una herramienta externa que mide distinto. Herramientas como Umami o PostHog pueden sumarse para analítica de producto, no para facturar.
2. **PostgreSQL alcanza para la etapa actual**: eventos crudos particionados + tablas resumen (rollups) por hora y por día. ClickHouse recién cuando haya cientos de millones de eventos.
3. **Publicidad contextual primero** (vertical, marca/modelo, carrocería, rango de precio, zona, búsqueda). Personalización por comportamiento solo con consentimiento. **Nunca cookies de terceros.**
4. **Motor de avisos propio y simple**: candidatos elegibles → filtros (fechas, presupuesto, ritmo de gasto, frecuencia) → puntaje = puja × calidad → pocos patrocinados por página, siempre rotulados.
5. **Impresión visible según el estándar MRC**: 50% del aviso en pantalla durante 1 segundo continuo (30% en formatos grandes). Se cuentan aparte “servidas” y “visibles”.
6. **Filtro de tráfico inválido desde el día uno**: bots, clics duplicados, clics imposibles. Lo que no es humano no se cobra ni se reporta.
7. **Panel del anunciante con la lógica de Meta**: Campaña → Grupo de anuncios → Anuncio, columnas configurables, desgloses (día, hora, dispositivo, zona, ubicación), ventanas de atribución explícitas.
8. **En autos la venta pasa afuera**: la conversión medible es el **contacto** (mensaje, WhatsApp, llamada) y, después, la **venta informada** por la agencia.
9. **Panel de agencias inspirado en Cars.com**: rendimiento por vehículo, calidad de la ficha, precio vs mercado, días publicado y demanda del mercado.
10. **Configuración jerárquica**: árbol de configuración → secciones → subsecciones que se despliegan (progressive disclosure), buscador global (Ctrl+K) y vistas guardadas.
11. **IA como componente, no como chat pegado**: resúmenes semanales, alertas de anomalías y preguntas en lenguaje natural **solo sobre métricas definidas**, mostrando cómo se calculó.
12. **Por etapas**: primero medición confiable y reportes; después subasta y personalización. Comprar un ad server externo (Kevel, Topsort) solo si el volumen lo justifica.

---

## 1. Traza de datos: qué medir y cómo

### 1.1 ¿Lo tiene que tener el código? Sí, el núcleo.

| Qué | Dónde vive | Por qué |
|---|---|---|
| Impresiones, impresiones visibles, clics y contactos de **avisos y publicaciones** | Código de Girando (API + PostgreSQL) | Se factura y se reporta al anunciante; tiene que ser auditable y consistente |
| Estadísticas de agencias, comercios y personas | Código de Girando | Son parte del producto que se vende |
| Recomendaciones | Código de Girando | Usan los mismos eventos, con consentimiento |
| Tráfico general del sitio (páginas, orígenes, campañas de marketing propias) | Opcional: Umami (sin cookies, liviano) | Útil para marketing, no para facturar |
| Embudos, cohortes, grabación de sesiones | Opcional: PostHog Cloud | Para producto; el self-hosted pide ClickHouse, Kafka, Redis y ~32 GB de RAM, y no conviene por debajo de ~10M eventos/mes |

### 1.2 Esquema de evento (propuesta)

Un solo formato para todo, versionado:

- `event_id` (UUID generado en el navegador → evita duplicados si se reenvía), `event_name`, `occurred_at`, `received_at`.
- `session_id` propio (cookie de primera parte, rota cada 30 min de inactividad), `user_id` solo si inició sesión.
- `consent` (necesarias / analítica / publicidad) vigente al momento del evento.
- Contexto: `vertical`, `page`, `placement`, `query_hash`, filtros activos resumidos (marca, modelo, carrocería, rango de precio, departamento).
- Objetos: `listing_id`, `agency_id`, `promotion_id`, `campaign_id`, `ad_id`, `decision_id` (vincula impresión → clic → contacto).
- Entorno: tipo de dispositivo, navegador resumido, departamento aproximado (derivado de la IP **sin guardar la IP**), dominio de referencia.

Eventos clave: `search`, `listing_impression`, `listing_view`, `listing_favorite`, `listing_contact` (por canal), `ad_served`, `ad_viewable`, `ad_click`, `ad_contact`, `external_click`, `message_sent`, `sale_reported`.

### 1.3 Pipeline

```
Navegador ──(lote cada 5 s o al salir, sendBeacon)──► POST /api/e
   │                                                    │ validación de esquema, rate limit, filtro de bots,
   │                                                    │ deduplicación por event_id, consentimiento
   ▼                                                    ▼
Servidor (eventos que el server ya conoce:      analytics_events (particionada por mes, ya existe)
contactos, ventas, pagos)  ────────────────────►        │
                                                        ▼ worker cada 5 min (idempotente)
                                      ad_stats_hourly · ad_stats_daily · listing_stats_daily (ya existe)
                                      agency_stats_daily · market_stats_daily
                                                        ▼
                               Paneles (leen SOLO resúmenes, nunca la tabla cruda)
```

- Eventos críticos (contacto, venta, pago) los registra **el servidor**, no el navegador: no se pierden por bloqueadores.
- Retención propuesta: crudos 180 días, resúmenes 5 años (alineado con la política de retención existente).
- Escalado (recomendación propia): hasta ~10k usuarios, solo Postgres; luego réplica de lectura para analítica y DuckDB para análisis offline; con cientos de millones de eventos, ClickHouse para eventos y Postgres para el negocio (es lo que hace PostHog).

### 1.4 Consentimiento y ley

- Chrome **mantuvo las cookies de terceros**: Google abandonó Privacy Sandbox y retiró sus APIs en octubre de 2025. Para Girando no cambia nada: **no se usan cookies de terceros**.
- Argentina: rige la **Ley 25.326** (consentimiento previo, expreso e informado). Hay un proyecto de reforma tipo GDPR impulsado por la AAIP en el Congreso, **todavía no vigente**. Diseñar ya como si lo estuviera.
- Regla de producto: sin consentimiento de analítica → solo eventos necesarios y agregados anónimos; sin consentimiento de publicidad → avisos contextuales, sin perfil.
- Transparencia: “¿Por qué veo este aviso?” en cada aviso y en cada recomendación; el usuario puede borrar su historial de intereses.
- Esto no es asesoramiento legal: validar con un abogado antes de lanzar.

---

## 2. Publicidad inteligente

### 2.1 Qué se vende

| Formato | Dónde | Cobro sugerido | Para quién |
|---|---|---|---|
| **Publicación patrocinada** | Dentro de los resultados (se ve como una publicación más, con “Patrocinado”) | Precio fijo semanal al inicio, luego CPC | Agencias, particulares |
| **Agencia destacada** | Directorio, resultados por marca, Home | Fijo mensual | Agencias, concesionarias |
| **Banner / display** | Home, resultados, detalle | CPM o tenencia fija por fecha | Bancos, aseguradoras, marcas, repuestos |
| **Paquetes** | Combinación de formatos con fechas y precio único | Fijo | Concesionarias oficiales, anunciantes grandes |
| **Avisos de anunciantes no automotores** (bancos, seguros, financieras, telcos) | Espacios contextuales (ej. “financiá tu 0 km” en detalle de autos nuevos) | CPM o fijo | Es el segmento con más presupuesto en marketplaces |

### 2.2 Cómo decide qué aviso mostrar (motor propio, versión 1)

1. **Candidatos**: avisos activos cuyo segmento coincide con el contexto (vertical, marca/modelo, carrocería, rango de precio, departamento, búsqueda). Para publicaciones patrocinadas, el candidato tiene que ser **relevante para la búsqueda** (subconjunto de los resultados orgánicos), como hace el *auction as a service* de Kevel.
2. **Filtros**: fechas, presupuesto disponible, **ritmo de gasto** (repartir el presupuesto en el día), **límite de frecuencia** por sesión, exclusiones (no mostrar el aviso de una agencia en su propia página).
3. **Puntaje**: `puja × calidad`. Calidad = CTR estimado suavizado (con un valor base para avisos nuevos) × completitud de la ficha × verificación de la agencia.
4. **Precio**: segunda puja + incremento mínimo, con piso por ubicación (las más valiosas tienen piso más alto). Con pocos anunciantes, empezar con **precio fijo** y pasar a subasta cuando haya competencia real.
5. **Mezcla con orgánicos**: tope de patrocinados por página (sugerencia: posiciones 1 y 7 de cada 12), siempre rotulados, nunca disfrazados.
6. **Registro**: cada decisión genera un `decision_id`; impresión, visibilidad, clic y contacto se encadenan a ese id.

Latencia objetivo: menos de 50 ms por decisión (referencia de la industria).

### 2.3 Medición honesta

- **Servida**: el servidor la eligió. **Visible**: el 50% del aviso estuvo en pantalla 1 segundo continuo, con la pestaña activa (IntersectionObserver en el navegador). En formatos grandes (≥ 970×250), alcanza con 30%. Video: 50% durante 2 segundos.
- **Tráfico inválido**: lista de bots conocidos, límites por sesión, clics repetidos del mismo aviso en 30 min cuentan una vez, clics en menos de ~300 ms tras la impresión no cuentan, picos anómalos van a revisión. Lo filtrado se informa como “inválido” y no se cobra.
- **Contacto atribuido**: mensaje, WhatsApp, llamada o formulario después de un clic en el aviso (ventana sugerida: 7 días) o después de verlo (1 día), mostrados **por separado**.
- **Venta influida** (idea de Cars.com): venta informada por la agencia con al menos una vista y un contacto en los 15 días previos.

### 2.4 Construir o comprar

Recomendación propia: construir el modelo de datos, el motor v1 y la medición (es poco código y es el corazón del negocio). Evaluar **Kevel** (API de decisión; Edmunds armó sus avisos patrocinados de autos así) o **Topsort** solo si el volumen y la cantidad de anunciantes hacen que subasta, ritmo de gasto y atribución propios cuesten más que el proveedor.

---

## 3. Cómo mostrarle estadísticas a quien paga

### 3.1 Estructura (como Meta Ads Manager, más simple)

```
Cuenta del anunciante
└── Campaña        objetivo (visitas, contactos, reconocimiento), presupuesto, fechas
    └── Grupo      segmentación (vertical, zona, marca/modelo, precio), ubicaciones, puja
        └── Anuncio publicación patrocinada, banner o agencia destacada
```

La tabla principal tiene pestañas por nivel; al elegir campañas se filtran los grupos y anuncios (igual que Meta).

### 3.2 Métricas

| Grupo | Métricas |
|---|---|
| Entrega | Impresiones servidas, visibles, % visible, alcance (sesiones únicas), frecuencia |
| Interacción | Clics, CTR, vistas de ficha, favoritos, clics a web/WhatsApp de la agencia |
| Resultado | Contactos por canal, costo por contacto, ventas influidas informadas |
| Costo | Gasto, CPM, CPC, presupuesto restante, ritmo de gasto |
| Calidad | Tráfico inválido filtrado, puntaje de calidad del aviso |

### 3.3 Funciones del reporte

- **Desgloses**: día, semana, hora, dispositivo, departamento, ubicación del aviso, vertical, publicación.
- **Columnas personalizables** con conjuntos guardados (“Rendimiento”, “Costos”, “Entrega”).
- **Comparar períodos** y **comparar ventanas de atribución** (clic 1/7 días, vista 1 día), aclarando qué es medido y qué es estimado.
- **Exportar** CSV/Excel, **reporte programado** por email (semanal), **enlace compartible** de solo lectura para la agencia de marketing del anunciante.
- **Referencia del mercado**: CTR y costo por contacto promedio de la categoría, **solo con 5 anunciantes o más** en el grupo (para no revelar a nadie).
- Mínimos estadísticos: sin volumen suficiente se dice “Sin datos suficientes”, nunca un porcentaje sobre 3 casos.

---

## 4. Paneles: llevar cada uno al siguiente nivel

### 4.1 Principios comunes

- **5 a 7 indicadores arriba**, el resto bajo demanda (progressive disclosure).
- **Filtros globales** de fecha y segmento que afectan a todo el panel.
- **Tablas** con columnas configurables, orden, búsqueda, **acciones masivas** y **detalle en panel lateral** (drawer) sin perder la lista.
- **Buscador global Ctrl/Cmd+K**: ir a cualquier pantalla, usuario, publicación o configuración y ejecutar acciones.
- **Vistas guardadas** (“Publicaciones pendientes de Godoy Cruz”, “Agencias por vencer”).
- **Configuración jerárquica** (ver 4.2).
- **Estados vacíos con la próxima acción** (“Todavía no tenés contactos: completá las fotos de 3 vehículos”).
- **Densidad elegible** (compacta/cómoda); modo oscuro opcional en el Admin.
- **Responsive real**: en mobile, tablas → tarjetas, filtros → hoja desde abajo, botones de 44×44 px mínimo, acción principal fija abajo.
- **IA integrada**: resumen del período al entrar (“Esta semana subieron 18% los contactos; 4 vehículos llevan 60 días sin consultas”), alertas de anomalías, preguntas en lenguaje natural sobre métricas definidas, siempre mostrando cómo se calculó.

### 4.2 Configuración que se despliega (estilo Meta Business)

Árbol a la izquierda → panel de la sección a la derecha → subsecciones que se expanden. Cada cambio pide confirmación, muestra el impacto y queda en auditoría.

```
Configuración (Super Admin)
├── Empresa            datos fiscales, marca, dominios, remitentes de email
├── Monetización
│   ├── Planes         particular · agencia 30 / 60 / +60 · repuestos · servicios
│   ├── Precios        historial de cambios, vigencia
│   ├── Promociones    productos, duración, precio
│   └── Publicidad     ubicaciones · formatos · pisos de precio · tope de patrocinados · ventanas de atribución
├── Verticales
│   ├── Vehículos      campos, filtros, catálogo, reglas de moderación
│   ├── Taxis          datos del permiso, avisos legales, verificación
│   ├── Servicios      rubros, zonas, matrículas a validar
│   ├── Repuestos      checklist de verificación presencial
│   └── Empleos        puestos, licencias, reglas de contacto
├── Financiación       entidades, ofertas, logos autorizados, campos obligatorios (TNA, TEA, CFT)
├── Confianza          verificaciones, checklists, motivos de rechazo, reportes
├── Comunicación       plantillas de email, notificaciones, mensajes del sistema
├── Privacidad         cookies, retención, pedidos de datos de usuarios
├── Integraciones      Mercado Pago, Cloudinary, email, cotización
├── Equipo y roles     personas, roles, permisos
└── Auditoría
```

### 4.3 Super Admin (dueños): “cómo va el negocio”

- **Inicio**: ingresos del mes (planes + publicidad + promociones), ingreso recurrente, **ocupación del inventario publicitario** (% de impresiones vendidas por ubicación), usuarios y comercios activos, alertas (pagos rechazados, campañas sin presupuesto, picos de tráfico inválido).
- **Publicidad**: inventario de espacios y su ocupación, calendario de banners, campañas activas, aprobación de creatividades, precios y pisos, ingresos por ubicación.
- **Negocio y finanzas** (ya existe): sumar cohortes de agencias (altas, bajas, upgrades), ingresos por vertical.
- **Mercado**: demanda por marca/modelo, precios promedio, días hasta la venta (con mínimos de muestra).

### 4.4 Admin (operación): “la bandeja de trabajo”

- Una sola **bandeja** con colas: moderación, verificaciones, reportes, creatividades publicitarias, ofertas de financiación, soporte. Cada cola con **tiempo de espera** y prioridad.
- Revisión rápida: detalle en panel lateral, **atajos de teclado** (A aprobar, R rechazar, siguiente), **motivos predefinidos**, acciones masivas.
- Señales de riesgo: publicación duplicada, precio fuera de rango, usuario nuevo con muchas publicaciones, muchos reportes.

### 4.5 Comercios (agencias, concesionarias, repuestos, servicios): “vender más”

- **Inicio**: vistas, contactos, costo por contacto, publicadas/límite del plan, resumen de IA de la semana.
- **Inventario**: tabla con **calidad de la ficha (%)**, **precio vs mercado** (por encima ≥105%, en mercado 95–105%, por debajo ≤95% del promedio de igual modelo/año/zona, solo con muestra suficiente), **días publicado**, vistas y contactos por vehículo; acciones masivas (pausar, publicar, cambiar precio, destacar).
- **Demanda del mercado** (idea de Cars.com): cuadrantes por modelo — mucho interés/poco stock (“oportunidad”), mucho stock/poco interés (“cuesta vender”) — con datos agregados y anónimos.
- **Contactos**: mensajes y consultas en una bandeja, con estado (nuevo, respondido, vendido) y tiempo de respuesta.
- **Publicidad**: el Ads Manager de la sección 3, simplificado (“Destacar este auto 7 días”).
- **Equipo, facturación, perfil y verificación**.

### 4.6 Personas: “Mi Girando”

- **Favoritos** con aviso de baja de precio o venta; **búsquedas guardadas** con alertas.
- **Mis publicaciones** con estadísticas simples y **sugerencias** (faltan fotos, precio por encima del mercado).
- **Mensajes**, **historial** (vistos, pagos, cambios de plan).
- **Privacidad**: qué intereses infirió Girando, borrar historial, descargar o eliminar mis datos.

---

## 5. Recomendaciones (de vehículos y de avisos)

- **Etapa 1 (sin modelos)**: “similares” por reglas (misma carrocería, rango de precio ±15%, año ±2, zona) + popularidad reciente. Explicable y medible.
- **Etapa 2**: perfil de interés del usuario (con consentimiento) a partir de vistas, favoritos y contactos; búsqueda con BM25 (`pg_search`) y similitud vectorial (`pgvector`) en PostgreSQL con el patrón *recuperar y reordenar* (traer 100 candidatos, combinar puntajes).
- Cuidado conocido: con índice HNSW de pgvector el filtro se aplica después de la búsqueda y puede devolver pocos resultados; filtrar primero en SQL o usar pgvectorscale.
- Medir siempre contra un grupo de control (A/B): CTR, contactos por sesión.

---

## 6. Gráficos y frontend de paneles

- Recomendación propia: una librería de gráficos **servida desde el propio servidor** (sin CDN, por la CSP), por ejemplo Apache ECharts (completa) o uPlot (muy liviana para series de tiempo), con paleta accesible y modo claro/oscuro.
- Cada gráfico con: título que dice la conclusión, tooltip con valores exactos, opción “ver como tabla” y nota de cálculo.

---

## 7. Hoja de ruta sugerida

| Etapa | Qué | Resultado |
|---|---|---|
| A. Medición confiable | Endpoint de eventos, esquema, visibilidad, filtro de bots, rollups, consentimiento | Números en los que se puede facturar |
| B. Ads Manager v1 | Campañas/grupos/anuncios, precio fijo, reportes con desgloses, export y envío programado | Primeros anunciantes pagando |
| C. Paneles nuevos | Bandeja del Admin, configuración jerárquica, inventario con precio vs mercado, Ctrl+K | Operación y comercios más rápidos |
| D. Inteligencia | Recomendaciones etapa 2, subasta con calidad, resúmenes de IA, alertas | Más ingresos por impresión |
| E. Escala | Réplica de lectura, ClickHouse si hace falta, evaluar ad server externo | Crecer sin rehacer |

---

## 8. Agregado para el prompt de la fase 4 (pegar al final de `PROMPT-FASE-4.md`)

> Leé también `docs/INVESTIGACION-DATOS-PUBLICIDAD-PANELES.md`. La medición de publicidad, los reportes de anunciantes y las
> estadísticas de comercios son **código propio** sobre PostgreSQL (eventos + resúmenes), con impresión visible según MRC,
> filtro de tráfico inválido y consentimiento. Implementá la etapa A completa y la B al menos con precio fijo; diseñá los
> paneles con la configuración jerárquica de la sección 4.2, la bandeja del Admin (4.4) y el inventario con precio vs mercado (4.5).
> Toda métrica con muestra insuficiente muestra “Sin datos suficientes”.

---

## Fuentes

Publicidad y subastas
- [Topsort — Retail media auctions](https://www.topsort.com/post/retail-media-auctions)
- [Topsort — Cómo construir una red de retail media](https://www.topsort.com/post/how-to-build-a-retail-media-network)
- [Topsort — Ad server para sponsored display](https://www.topsort.com/post/ad-server-for-sponsored-display)
- [Topsort — Ad servers para marketplaces (2026)](https://www.topsort.com/post/best-ad-server-software-retail-marketplaces)
- [Osmos — Formatos de retail media 2026](https://osmos.ai/blog/retail-media-ads-sponsored-formats-2026)
- [Kevel — Auction as a service](https://dev.kevel.com/docs/auction-as-a-service)
- [Kevel — Caso Edmunds, avisos patrocinados de autos](https://www.casestudies.com/company/kevel/case-study/edmunds-builds-industrys-fastest-sponsored-car-listings-ad-platform)

Medición
- [MRC — Viewable Ad Impression Guideline v2.0](https://mediaratingcouncil.org/sites/default/files/Standards/081815%20Viewable%20Ad%20Impression%20Guideline_v2.0_Final.pdf)
- [Estándares MRC de visibilidad (resumen)](https://headerbidding.co/mrc-viewability-standards/)
- [Pixalate — Historia y definición de visibilidad MRC](https://www.pixalate.com/blog/mrc-viewability-standards-definition-history)
- [Digital Applied — Modelos de atribución 2026](https://www.digitalapplied.com/blog/marketing-attribution-models-2026-what-still-works)

Paneles y reportes de referencia
- [Cars Commerce — VIN performance media report](https://help.carscommerce.inc/cars-com/reporting-and-analytics/how-to-access-your-vin-performance-media-report/)
- [Cars Commerce — Demand signals](https://help.carscommerce.inc/?p=9883)
- [Cars Commerce — Listings optimizer](https://help.carscommerce.inc/?p=9869)
- [Cars Commerce — Performance trends](https://help.carscommerce.inc/?p=9753)
- [Cars Commerce — Sales attribution](https://help.carscommerce.inc/cars-com/reporting-and-analytics/how-to-access-your-sales-attribution-report/)
- [Desgloses en Meta Ads Manager](https://www.relevantaudience.com/facebook-ads/facebook-ads-breakdown-meta-ads-manager/)
- [Jon Loomer — Atribución en Meta Ads](https://www.jonloomer.com/meta-ads-attribution-reporting/)
- [Mercado Libre: de ACOS a ROAS en Product Ads (2025)](https://algoritmodigital.com.ar/fin-del-acos-en-mercado-libre-2025-optimizacion-por-roas/)
- [AdminLTE — Diseño de dashboards de administración (2026)](https://adminlte.io/blog/admin-dashboard-design/)
- [SaaSUI — Tendencias de UI SaaS 2026](https://saasui.design/blog/7-saas-ui-design-trends-2026)
- [925 Studios — Ejemplos de dashboards SaaS 2026](https://925studios.co/blog/saas-dashboard-design-examples-2026)

Arquitectura de datos y recomendaciones
- [PostHog — Por qué rehicieron su data warehouse (DuckDB + ClickHouse)](https://posthog.com/blog/why-we-rebuilt-our-data-warehouse)
- [Umami vs PostHog self-hosted (2026)](https://blog.elest.io/umami-vs-posthog-which-self-hosted-analytics-in-2026/)
- [Cotera — Guía de PostHog self-hosted](https://cotera.co/articles/posthog-self-hosted-guide.md)
- [ParadeDB — Postgres como motor de recomendación](https://paradedb.com/blog/personalized-search-in-postgresql)
- [Tiger Data — Recomendaciones con pgvector/pgvectorscale](https://www.tigerdata.com/blog/how-we-built-a-content-recommendation-system-with-pgai-and-pgvectorscale)
- [Cube — Analítica conversacional](https://cube.dev/articles/best-conversational-analytics-software)

Privacidad
- [Secure Privacy — Fin de Privacy Sandbox y consentimiento en 2026](https://secureprivacy.ai/blog/google-killed-privacy-sandbox-what-changes-for-cookie-consent-in-2026)
- [Search Engine Land — Google cierra Privacy Sandbox](https://searchengineland.com/google-officially-shuts-down-privacy-sandbox-463561)
- [FlexyConsent — Reforma de protección de datos en Argentina](https://flexyconsent.com/blog/argentina-data-protection-reform-cookie-consent-guide/)
- [Diario Judicial — ¿Alcanza la Ley 25.326 en 2026?](https://www.diariojudicial.com/news-103126-proteccion-de-datos-personales-sigue-siendo-suficiente-la-ley-25326-en-2026)
