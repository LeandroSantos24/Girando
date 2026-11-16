# GIRANDO — Contexto maestro del proyecto

**Versión 1.1 · 16/11/2026 · Estado: vigente. Dueño y director: Leandro.**
Este archivo es la fuente única de contexto. Cualquier persona o agente que trabaje en Girando lo lee primero, completo.
Reemplaza a `docs/historial/10-contexto-girando.md` y a `docs/historial/PROMPT-FASE-4.md` (quedan como historial).
Si algo de otro documento contradice a este, manda este.

---

## 1. Qué es Girando

Portal automotor argentino para comprar y vender vehículos, con secciones del mismo rubro que suman tráfico y anunciantes.
Objetivo: ser en 2026 el lugar donde la gente compra y vende autos, superando a los clasificados viejos (deRuedas, que se sigue
usando por costumbre) con mejor experiencia, mejores filtros y más confianza.

| Sección | Qué se publica | Quién publica |
|---|---|---|
| **Vehículos** (el corazón) | Autos, camionetas, pick-ups, utilitarios, motos, camiones | Particulares, agencias (reventas), concesionarias oficiales |
| **Taxis** | Taxis y remises en venta, con o sin permiso | Cualquiera |
| **Servicios** | Grúas, gestoría automotor, productores de seguros, fletes, transporte, mecánica, gomería, etc. | Prestadores |
| **Repuestos** | Casas de repuestos y su catálogo | Solo comercios verificados en persona |
| **Empleos** | Puestos del rubro (choferes, mecánicos, vendedores, etc.) | Empresas y particulares |

Diseño: blanco, limpio, fácil de entender, agradable. Se mantiene la identidad actual (logo, azul de marca, componentes).

## 2. Decisiones del dueño (vigentes)

| Tema | Decisión |
|---|---|
| Alcance | **Todo el país** desde el lanzamiento (no solo Mendoza) |
| Gratis para particulares | **1 publicación activa en total**: un vehículo, un taxi **o** un empleo |
| Agencias / concesionarias | Planes por volumen de publicadas: hasta 30, hasta 60, más de 60. El inventario sin publicar no cuenta |
| Casas de repuestos | **$ 4.000 por mes**, obligatorio, más verificación en persona del local, identidad del responsable y datos completos. Sin pago aprobado y verificación aprobada no publica |
| Servicios y empresas de empleo | **Gratis al lanzar**. Se monetizan con destacados y publicidad |
| Taxis | **Sin límite de antigüedad ni validaciones**: la gente publica y listo. Solo un aviso corto: “La transferencia del permiso requiere autorización de la autoridad de transporte” |
| Empleos | **Sin CV ni documentos**. El aviso muestra el contacto del empleador y el candidato le escribe por WhatsApp |
| Contacto | **Lo más cómodo para el usuario: ve el auto (o el servicio) y toca WhatsApp**, que abre la conversación directa con quien vende. WhatsApp es obligatorio para publicar. El clic pasa por Girando (`/api/out`), se mide sin guardar quién lo hizo y el número no queda expuesto en la página. Los mensajes internos quedan como alternativa secundaria |
| Fuerte económico | **Publicidad** en el portal, medida con datos propios y siempre rotulada |
| Recomendaciones | Con datos propios de Girando y consentimiento de cookies; sin cookies de terceros |
| Financiación | Se muestra “Apto crédito”, entidad, anticipo, monto financiable y cuotas. Si hay tasa: **CFT destacado, con TNA y TEA**. Logos de bancos solo con autorización |
| Versiones | **Git + GitHub privado**: `git@github.com:LeandroSantos24/Girando.git` (SSH) |
| Migraciones | **Compactar ahora** en una base única, antes del frontend de la fase 4 |
| Limpieza | Borrar la basura fuera del repo (ver §9, pendientes menores) |
| Año de taxis | 1900–2100, igual que vehículos: control de plausibilidad, no de antigüedad |
| Compactación | Conservadora: base única por dominio; los archivos de fases 3–4 siguen usando `ALTER TABLE` |
| Bases locales viejas | No se actualizan en el lugar: se recrean con `make reset-dev-db` |
| CI | Se recrea `.github/workflows/ci.yml` (el README lo menciona y no existe) |
| Forma de trabajo | No escribir pantallas ni endpoints que no se puedan probar. Mejor 3 pasos sólidos que 6 a medias |

## 3. Modelo de negocio

En orden de importancia:

1. **Publicidad**: vehículos patrocinados en búsquedas relevantes, agencias destacadas, espacios reservados por período (Home, detalle, directorio) para agencias, marcas, bancos y aseguradoras. **Arranca con precio fijo por período**; CPC o subasta recién cuando varios anunciantes compitan por el mismo espacio.
2. **Planes de agencias** por volumen de publicadas.
3. **Suscripción de repuestos** ($ 4.000/mes).
4. **Promociones**: destacar publicación, posición, agencia destacada.

### Planes (valores iniciales, editables por el Super Admin; precios a confirmar)

| Plan | Publicadas | Precio inicial |
|---|---|---|
| Particular Free | 1 (vehículo, taxi o empleo) | Gratis |
| Agencia 30 | 30 | $ 54.900 / mes |
| Agencia 60 | 60 | $ 79.900 / mes |
| Agencia +60 | 100 | $ 99.900 / mes |
| Repuestos | Catálogo (500 ítems, a confirmar) | $ 4.000 / mes |
| Servicios | 1 ficha por rubro y zona | Gratis |
| Empresa (empleos) | 3 avisos activos | Gratis |

- **Subir de plan**: rige cuando se aprueba el pago; el período se reinicia; sin prorrateo.
- **Bajar de plan**: rige al renovar; lo que excede se pausa, nunca se borra.
- Períodos por mes calendario (zona Argentina). Una suscripción solo se activa o extiende con un pago aprobado (o cortesía auditada del Super Admin).

## 4. Reglas por sección

**Vehículos**
- Filtros combinables con contadores reales: precio (ARS/USD normalizado por BCRA), año, km, marca, modelo, versión, condición, tipo de vendedor, verificado, carrocería (Hatchback, Sedán, SUV, Crossover, Pick-Up, Rural, Coupé, Cabriolet, Roadster, Monovolumen, Minivan, Furgón, Van, Light Truck, Off-Road), combustible, transmisión, tracción, puertas, color, ubicación (provincia/departamento/radio), financiación (apto crédito, entidad, anticipo máximo, cuota máxima), permuta.
- Calculadora “con cuánto lo retirás”, rotulada como orientativa.
- Precio vs mercado solo con muestra suficiente; si no, “Sin datos suficientes”.

**Taxis**
- Datos declarados: tipo (taxi/remis), con o sin permiso, número de permiso, localidad/zona, vehículo, año, GNC, reloj/GPS, precio del permiso y del vehículo por separado.
- Filtros: provincia y localidad, tipo, con/sin permiso, año, combustible, precio.
- Sin validación de antigüedad. Aviso corto al pie (ver §2). Sello “permiso verificado” solo si el equipo lo comprobó.

**Servicios**: rubro, zona de cobertura, 24 h, tipo de vehículo, a domicilio, verificado. La matrícula de productores de seguros (SSN) es dato declarado; el sello lo pone el equipo.

**Repuestos**: ficha del comercio y catálogo por marca/modelo/categoría; filtros por vehículo, categoría, nuevo/usado, zona.

**Empleos**: puesto, licencia requerida, zona, jornada, modalidad. Sin CV.

## 5. Publicidad y medición (cómo se hace)

La medición la hace **el código de Girando**: el informe que ve el anunciante y lo que se le cobra salen de las mismas reglas.
Detalle técnico y fuentes: `docs/INVESTIGACION-DATOS-PUBLICIDAD-PANELES.md`.

**Cadena de un aviso** (cada paso con el mismo `decision_id`):
oportunidad (búsqueda con filtros) → selección del aviso → renderizado → **impresión visible** (50% del aviso 1 s continuo con la pestaña activa; 30% en formatos ≥ 242.500 px) → clic → apertura de ficha → **toque de WhatsApp** (la conversión principal) → venta informada por la agencia.

Como la charla pasa en WhatsApp, Girando no puede confirmar que hubo conversación: el informe lo dice tal cual (“aperturas de WhatsApp”, no “consultas”). Para que la agencia sepa de dónde viene el cliente, el WhatsApp se abre con un **mensaje precargado** que incluye el código de la publicación (“Hola, vi tu Amarok 2021 en Girando (P-XXXXXXXX)”).

**Reglas**
- El servidor decide el aviso y emite el `decision_id`; el cliente nunca fija anunciante, tarifa ni importe.
- Eventos con ficha propia (nombre, significado, quién lo emite, campos, versión, regla de duplicados, retención). Eventos críticos (mensaje, venta, pago) los registra el servidor.
- **Idempotencia**: la tabla de eventos está particionada por mes y una restricción única debe incluir la clave de partición; por eso la clave de idempotencia va en un registro aparte con unicidad propia, y los movimientos facturables tienen su propia restricción. Probar un reintento que cruza la medianoche de fin de mes.
- Tráfico inválido (bots, clics repetidos, clics imposibles) se filtra, se informa aparte y no se cobra.
- Selección: filtros obligatorios de la búsqueda + vigencia + presupuesto + ritmo de entrega + límite de frecuencia → relevancia → tope de patrocinados por página. Si no hay buen candidato, resultados orgánicos completos.
- Atribución del piloto: último clic patrocinado elegible, ventana explícita; separar “abrió WhatsApp por el vehículo anunciado” de “por otro vehículo de la misma agencia”.
- WhatsApp sin iniciar sesión (lo más cómodo), con protección: el número no va en el HTML, el redirect tiene límite por IP y filtro de bots, y nunca se guarda quién hizo clic.
- Paneles leen solo resúmenes (rollups), nunca la tabla cruda. PostgreSQL alcanza en esta etapa.
- Funciones con impacto comercial inmediato: **simulador antes de contratar** (con “Sin datos suficientes” si no hay muestra), **diagnóstico de campañas sin entrega** (“el vehículo está pausado”, “no hubo búsquedas compatibles”), **protección de la búsqueda** (medir si los patrocinados bajan las consultas totales).
- Primer recorrido completo a lograr: la agencia elige una unidad, toca **Destacar 7 días**, ve la vista previa en celular, precio y condiciones, paga o recibe cortesía, y al terminar recibe un informe que une inversión, exposición, visitas y contactos.

## 6. Paneles

**Acceso = persona + organización + rol + alcance.** Una persona puede trabajar para dos agencias y vender su propio auto como particular; selector “Estás trabajando en…” visible; el servidor valida organización y permiso en cada consulta (y la conexión de la API no puede ser dueña de las tablas, porque el dueño se salta RLS).

| Panel | Para qué |
|---|---|
| Super Admin | Ingresos (planes, publicidad, promociones), calendario de espacios publicitarios y ocupación, campañas con entrega insuficiente, diferencias entre entregado, cobrado y acreditado, configuración |
| Admin | Bandeja única de trabajo (publicaciones, verificaciones, creatividades, reclamos, soporte) con prioridad, antigüedad y quién lo atiende; sin que dos operadores resuelvan lo mismo a la vez |
| Comercio / agencia | Inventario con calidad de ficha, precio vs mercado y días publicado; consultas pendientes; campañas; plan disponible; equipo con permisos por sucursal |
| Anunciante sin inventario | Bancos, aseguradoras, marcas: creatividades, ubicaciones, entrega e informes. No ve autos ni mensajes |
| Persona · Mi Girando | Favoritos (aviso de baja de precio), búsquedas guardadas, publicaciones con estadísticas simples (vistas y aperturas de WhatsApp), historial, privacidad |

**Configuración jerárquica** (estilo Meta): categorías a la izquierda, contenido a la derecha, ramas que se despliegan, buscador por palabras del usuario (“WhatsApp” encuentra el canal), enlaces directos a cada rama. En celular, cada nivel es una pantalla con Volver que conserva filtros. Las acciones frecuentes (pausar, responder) no viven en Configuración. Confirmaciones proporcionales al riesgo: cambiar una tarifa muestra precio anterior, nuevo, vigencia y contratos afectados.

Principios comunes: 4 a 7 indicadores arriba y el resto a pedido, filtros globales, tablas con columnas configurables y detalle lateral, Ctrl/Cmd+K, vistas guardadas, estados vacíos con la próxima acción, “ver como tabla” en cada gráfico, mobile real (tarjetas, hojas desde abajo, toques de 44 px), accesible con teclado y lector de pantalla.

## 7. Arquitectura técnica

- **Stack**: PostgreSQL 16 (RLS, triggers, auditoría) · FastAPI · Redis · worker (`python -m app.cli jobs`) · nginx · App y Admin web responsive generadas desde `web/src/` con `python3 scripts/build_web.py`. Docker Compose.
- **Puertos locales**: web 3100, API 8100.
- **Carpetas**: `backend/sql/0001_base/` (esquema completo, 20 archivos por dominio), `backend/migrations` (Alembic, una sola versión `base_0001`), `backend/app/api/routers`, `backend/app/services`, `backend/app/cli.py` (migrate, seeds, jobs, reset), `backend/app/seeds/georef/` (dataset oficial), `backend/tests` (pytest + `tests/sql/*.sql`), `web/src`, `docs/`, `scripts/`.
- **Rol de base de la API**: `girando_api` (NOINHERIT) con `SET LOCAL ROLE` por transacción. Las funciones del esquema `app` están revocadas a PUBLIC: toda función que use una vista de `api_public` necesita `GRANT EXECUTE` explícito para `girando_anon`.
- **Integraciones**: Mercado Pago (preapproval + webhook firmado; simulador `PAYMENTS_SIMULATOR=true` solo en desarrollo), Cloudinary (fotos, firmado), email por proveedor (sin configurar), cotización BCRA.
- **Cuentas de desarrollo** (solo local, contraseña `DEV_SEED_PASSWORD` del `.env`): `superadmin@`, `admin@`, `moderador@`, `usuario@`, `agencia@girando.test`.
- **Atajos (`Makefile`)**: `make dev`, `make test` (pytest en Docker, incluye los tests SQL), `make lint` (ruff + bandit), `make reset-dev-db` (recrea la base local con migración y seeds), `make georef` (actualiza el dataset), `make build-web`. Todos reconstruyen la imagen antes de correr.
- **Migraciones nuevas**: `backend/sql/0002_<tema>.sql` + `backend/migrations/versions/0002_<tema>.py` con `down_revision = "base_0001"`. No editar `0001_base/` cuando haya datos reales. Detalle: `docs/11-migraciones.md`.

### Notas de la máquina de desarrollo (Kali del dueño)
- El DNS de Telefónica bloquea `files.pythonhosted.org` (lo resuelve a `127.9.9.9`). Resuelto con `/etc/docker/daemon.json` → `{"dns": ["1.1.1.1", "8.8.8.8"]}` y DNS 1.1.1.1/8.8.8.8 en la conexión de NetworkManager. Si `pip` vuelve a dar `Connection refused`, es esto.
- Hubo archivos en modo 600 que el contenedor no podía leer; el Dockerfile ahora normaliza permisos (`chmod -R a+rX /app`).

## 8. Estado al 16/11/2026

**Línea base verde.** Verificado en la máquina del dueño, con Docker:

| Verificación | Resultado |
|---|---|
| `make test` (pytest fases 1–4 + tests SQL) | **80/80**, 0 salteados |
| Tests SQL (`tests/sql/`) | 900 flujos 50 · 910 arreglos fase 4 15 · 920 Georef 8 |
| `make lint` | ruff limpio, bandit sin hallazgos |
| Migraciones (Alembic) | Base única desde base vacía; segunda corrida no hace nada |
| Georef | 24 provincias, 529 departamentos, 4.028 localidades cargadas; 0 omitidas |

- Fases 1–3 completas (cuentas, vehículos, moderación, agencias, planes, Admin por rol, finanzas, promociones, Home, verificación).
- Fase 4, **backend completo y probado**: marketplace, financiación, planes por rubro, cobros con simulador, verticales (taxis, servicios, repuestos, empleos), mensajería, publicidad básica y recomendaciones.
- Fase 4, **frontend: no empezado.** `web/src` solo tiene las pantallas de las fases 1–3.
- Hecho el 15–16/11: limpieza del repo, Makefile, taxis sin antigüedad (solo el aviso corto), migraciones compactadas con esquema idéntico verificado por `pg_dump`, Georef.
- Bugs reales corregidos al poner los tests en verde: recursión RLS en `messages`; casa de repuestos que quedaba `pending` aun aprobada; listado público de las verticales que daba 403 sin sesión; sello de verificación inalcanzable (ruta tapada por otra); conversación sin asunto para quien contacta.
- Detalle y bitácora: `docs/FASE4-ESTADO.md`.

## 9. Orden de trabajo inmediato

**Paso 0, siempre:** comprobar que se puede correr `docker compose`, `make test` y la API. Si no se puede, frenar y decir qué habilitar.
Confirmar la línea base con `make reset-dev-db && make test && make lint` antes de escribir código.

Hecho: Git y remoto, limpieza dentro del repo, tests en verde, taxis, migraciones, Georef (datos).

Pendientes menores:
- Limpieza fuera del repo, en `/home/leandro/Documentos/Girando/`: borrar `backend/` (propuesta v0 duplicada), `Claude outputs/`, `girando-completo.zip` y los `*.bundle` ya aplicados. Conservar los dos logos y `Mobile app design planning.zip`.
- `GET /api/geo?level=locality` devuelve las 4.028 localidades sin paginar: limitarlo antes de armar los selectores.
- Actualizar `docs/FASE4-ESTADO.md` al cerrar cada paso.

**Paso 3 · Frontend de la fase 4** (`web/src`, misma identidad blanca; mobile primero, desktop impecable). Criterio de aceptación:
- Navegación por sección: Vehículos · Taxis · Servicios · Repuestos · Empleos, cada una con su buscador y filtros. Búsqueda y publicación por provincia y localidad de todo el país.
- Vehículos: todos los filtros de §4 con contadores reales y estado en la URL (búsqueda compartible); carrocerías completas; financiación y calculadora “con cuánto lo retirás” rotulada orientativa; CFT destacado con TNA y TEA si hay tasa; precio vs mercado solo con muestra suficiente.
- Ficha (vehículo, taxi, servicio, repuesto, empleo): botón principal WhatsApp. Pasa por `/api/out`, abre wa.me con “Hola, vi tu {título} en Girando ({código})”, el número no aparece en el HTML, no pide login y no guarda quién hizo clic. Mensaje interno como alternativa secundaria.
- Publicar en las 5 secciones, con WhatsApp obligatorio. Cupo gratis único del particular visible (“Te queda 1 publicación gratis”); al llegar al límite, ofrecer el plan correcto y que la base lo haga cumplir.
- Taxis: solo el aviso corto, sin nada de antigüedad.
- Mi Girando: favoritos con aviso de baja de precio, búsquedas guardadas, mis publicaciones con vistas y aperturas de WhatsApp, historial de pagos y planes, privacidad (borrar historial de intereses, preferencias de cookies).
- Planes y pagos: contratar, subir 30→60→+60, bajar, cancelar, destacar, y la suscripción de repuestos. Todo por el simulador, con estados visibles y comprobante en el historial.
- Admin: bandeja única con colas (publicaciones, verificaciones, ofertas de financiación, creatividades, mensajes reportados); prioridad, antigüedad y quién la toma; atajos de teclado; motivos predefinidos.
- Configuración jerárquica estilo Meta (§6). Ctrl/Cmd+K global. Vistas guardadas en tablas. Estados vacíos con la próxima acción.
- Tipografía: proponer 2 opciones autoservidas (woff2, licencia OFL, sin CDN), elegir una y documentar la otra.
- Accesible: teclado, foco visible, lector de pantalla, toques de 44 px, sin scroll horizontal.
- Tests de API para todo endpoint nuevo y E2E de “buscar → ficha → WhatsApp” y “publicar → moderar → publicado” en 390×844, 768×1024 y 1440×900. Commit por bloque.

**Paso 4 · Publicidad etapa A (medición confiable):** endpoint de eventos con esquema versionado, `decision_id` de punta a punta, impresión visible MRC con IntersectionObserver, filtro de tráfico inválido, clave de idempotencia en un registro aparte, rollups por hora y por día, consentimiento. Test de reintento que cruza la medianoche de fin de mes.

**Paso 5 · Publicidad etapa B (“Destacar 7 días”, precio fijo):** unidad publicada → Destacar 7 días → vista previa en celular → precio y condiciones → pago (simulador) o cortesía auditada → activo. Patrocinado solo en búsquedas compatibles, rotulado, con tope por página; si el auto se pausa o se vende, deja de promocionarse. Panel del anunciante con gasto, impresiones servidas y visibles, clics, vistas de ficha y aperturas de WhatsApp (nunca “consultas”); desglose por día, dispositivo, provincia y ubicación; CSV idéntico al panel; diagnóstico de campaña sin entrega. Dos reintentos de pago = una sola activación.

**Paso 6 · Cierre:** `.github/workflows/ci.yml` (ruff, bandit, pytest con servicio PostgreSQL 16, migraciones x2, chequeo de que el frontend generado esté al día, `docker compose build`). README, SECURITY, ARCHITECTURE y `docs/` (un documento por tema nuevo). E2E en los tres tamaños. Informe final honesto.

**Cómo trabajar:** un commit por paso o bloque; `git push origin main`, nunca `--force`; al cerrar cada paso actualizar `docs/FASE4-ESTADO.md` y escribirle al director 5 líneas (qué se hizo, tests, qué sigue). Si se acaba el tiempo o el contexto, cortar en un estado verde.

## 10. Reglas que no se negocian

1. PostgreSQL es la única fuente de verdad. Nada de `localStorage` o cookies como fuente de verdad.
2. El backend valida roles, límites, pagos y estados. Ocultar un botón no es seguridad.
3. Cero datos inventados. Sin muestra suficiente: “Sin datos suficientes”.
4. Activar algo pago solo con pago aprobado o cortesía auditada.
5. Publicidad siempre rotulada (“Patrocinado” / “Publicidad”).
6. Datos personales mínimos; documentos solo en almacenamiento privado; no se envían búsquedas libres, teléfonos ni mensajes a herramientas externas.
7. Todo cambio relevante queda en auditoría.
8. Todo local hasta que el dueño decida desplegar. Las credenciales de desarrollo nunca van a producción.
9. Preguntar al dueño solo por: modelo de negocio, seguridad, costos importantes, decisiones irreversibles, datos o pagos reales, producción.

## 11. Pendiente de decisión del dueño

- Precios definitivos de los planes y tope de catálogo de repuestos.
- Tipografía final (candidatas autoservidas: Plus Jakarta Sans, Inter, Manrope; hoy Sora).
- Convenios reales con bancos (hasta tenerlos, la financiación la cargan las agencias y la aprueba moderación).
- Revisión legal (Ley 25.326 y textos legales) antes de lanzar.
- Cuándo y dónde desplegar.
- **Visibilidad del repo**: `LeandroSantos24/Girando` está **público** en GitHub y §2 dice privado. No hay secretos versionados, pero el código y la documentación están a la vista.

## 12. Referencias de producto (en qué basarse)

| Sitio | Qué tomar | Qué evitar |
|---|---|---|
| [Cars.com](https://www.cars.com/) | Búsqueda simple arriba y filtros muy completos; ficha con fotos grandes, precio comparado con el mercado y contacto a un toque; panel de concesionarias con rendimiento por vehículo, calidad de ficha, días publicado y demanda del mercado | La cantidad de publicidad mezclada en la ficha |
| [deRuedas](https://www.deruedas.com.ar/) | Lo que la gente ya usa por costumbre: publicar rápido, contacto directo con el vendedor, mucha oferta local | Diseño viejo, filtros pobres, poca confianza en quién vende |
| [Mercado Libre Autos](https://autos.mercadolibre.com.ar/) | Filtros por carrocería y atributos con contadores, financiación visible, reputación del vendedor, avisos patrocinados (Product Ads) que diferencian ventas directas e indirectas | Contacto lento y encerrado en la plataforma |

Idea guía: **la búsqueda y los filtros de Mercado Libre/Cars.com, la confianza y los paneles de Cars.com, y la inmediatez de deRuedas (ver el auto y escribir por WhatsApp)**, con un diseño limpio de 2026.

## 13. Documentos

| Documento | Para qué |
|---|---|
| `CONTEXTO.md` (este) | Fuente única de contexto |
| `docs/FASE4-ESTADO.md` | Avance técnico de la fase 4 |
| `docs/INVESTIGACION-DATOS-PUBLICIDAD-PANELES.md` | Medición, publicidad y paneles, con fuentes |
| `README.md`, `SECURITY.md`, `ARCHITECTURE.md` | Cómo levantarlo, seguridad, arquitectura |
| `docs/11-migraciones.md` | Base única, cómo se verificó y cómo agregar una migración |
| `backend/app/seeds/georef/README.md` | Dataset Georef: origen, licencia y cómo actualizarlo |
| `docs/historial/` | Documentos superados (no describen el estado actual) |
| `docs/00`–`docs/09` | Historia de las fases 1–3 |
