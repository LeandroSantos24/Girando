# GIRANDO — Contexto maestro del proyecto

**Versión 1.0 · 15/11/2026 · Estado: borrador para aprobación del dueño (Leandro).**
Este archivo es la fuente única de contexto. Cualquier persona o agente que trabaje en Girando lo lee primero, completo.
Reemplaza a `docs/10-contexto-girando.md` y a `docs/PROMPT-FASE-4.md` (quedan como historial).
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
| Limpieza | Borrar la basura fuera del repo (ver §9, paso 1) |

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
- **Carpetas**: `backend/sql` (esquema), `backend/migrations` (Alembic que ejecuta los SQL), `backend/app/api/routers`, `backend/app/services`, `backend/app/cli.py` (migrate, seeds, jobs, reset), `backend/tests`, `web/src`, `docs/`, `scripts/`.
- **Rol de base de la API**: `girando_api` (NOINHERIT) con `SET LOCAL ROLE` por transacción.
- **Integraciones**: Mercado Pago (preapproval + webhook firmado; simulador `PAYMENTS_SIMULATOR=true` solo en desarrollo), Cloudinary (fotos, firmado), email por proveedor (sin configurar), cotización BCRA.
- **Cuentas de desarrollo** (solo local, contraseña `DEV_SEED_PASSWORD` del `.env`): `superadmin@`, `admin@`, `moderador@`, `usuario@`, `agencia@girando.test`.
- **Reinicio local**: `docker compose exec api python -m app.cli reset-dev-db --confirm girando` y `docker compose restart api worker`.

## 8. Estado al 15/11/2026

- Fases 1–3 completas (cuentas, vehículos, moderación, agencias, planes, Admin por rol, finanzas, promociones, Home, verificación).
- Fase 4 (Fable 5.2, dos sesiones): backend de marketplace, financiación, planes por rubro, rutas de cobro, verticales, mensajería, publicidad y recomendaciones escrito. Tests: 62/62 de fases 1–3 y 12/18 de fase 4. Detalle en `docs/FASE4-ESTADO.md`.
- En rojo: recursión en la política RLS de `messages` (arreglar con función `SECURITY DEFINER` de participación), rate limit de registro en los tests (resetear en el helper `register`), verificación de casas de repuestos que queda en `pending`.
- Falta: frontend de la fase 4, documentación, ruff, bandit, migraciones x2, E2E.

## 9. Orden de trabajo inmediato

1. **Git**: `git init` en `girando/`, revisar el `.gitignore` (nunca `.env`, `*.rdb`, `media/`), primer commit, remoto `git@github.com:LeandroSantos24/Girando.git`. Antes de subir, `git fetch` y revisar si el remoto ya tiene historia: nunca `push --force` sin preguntar. Un commit por paso de esta lista.
2. **Limpieza fuera del repo** (en `/home/leandro/Documentos/Girando/`): borrar `backend/` (propuesta v0 duplicada), `Claude outputs/` y `girando-completo.zip`. Conservar `logoGirando.png`, `logoGirandoHorizontal.png` y `Mobile app design planning.zip`.
3. **Limpieza dentro del repo**: buscar referencias antes de borrar (por ejemplo `web/ios-frame.jsx`, scripts duplicados, documentos superados → mover a `docs/historial/`). Listar en el commit qué se borró y por qué.
4. **Arreglar los 6 tests en rojo** (§8).
5. **Taxis**: quitar toda validación y texto de antigüedad; dejar solo el aviso corto.
6. **Compactar migraciones**: reemplazar 0001–0007 (y el arreglo de RLS) por una base única (`backend/sql/0001_base/` dividida por dominio + una sola versión de Alembic). Verificación obligatoria: `pg_dump --schema-only` antes y después debe ser equivalente; `reset-dev-db`; todos los tests; migrar dos veces desde base vacía.
7. **Todo el país**: cargar provincias, departamentos y localidades de Argentina desde el dataset oficial Georef (datos.gob.ar), versionado en el repo, en lugar de solo Mendoza/San Juan/San Luis.
8. **Frontend de la fase 4** (navegación por sección, filtros, calculadora, Mi Girando, mensajes, Admin nuevo, configuración jerárquica, tipografía autoservida).
9. **Publicidad etapa A** (medición confiable) y **etapa B** (Destacar 7 días con precio fijo y panel del anunciante).
10. Docs, ruff, bandit, E2E en 390×844, 768×1024 y 1440×900, informe final honesto.

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
| `docs/00`–`docs/09` | Historia de las fases 1–3 |
