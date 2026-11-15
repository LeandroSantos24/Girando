# Girando — documento de contexto

Versión del 15/11/2026. Para cualquier persona o agente que se sume al proyecto. Explica qué es Girando, cómo gana plata,
qué hay construido hoy y qué reglas no se negocian.

---

## 1. Qué es

Girando es un **portal automotor de Mendoza (y después de Cuyo y Argentina)** con un objetivo claro: ser el lugar donde
la gente compra y vende vehículos en 2026, reemplazando a los clasificados viejos (deRuedas sigue siendo el más usado en
Mendoza, pero quedó atrás en experiencia, filtros y confianza).

El **fuerte es el marketplace de autos**. Alrededor hay verticales del mismo rubro que suman tráfico y anunciantes:

| Vertical | Qué se publica | Quién publica |
|---|---|---|
| **Vehículos** (núcleo) | Autos, camionetas, pick-ups, utilitarios, motos, camiones | Particulares, agencias (reventas) y concesionarias oficiales |
| **Taxis y permisos** | Taxis en servicio y permisos de taxi/remis (con o sin vehículo) | Permisionarios y agencias |
| **Servicios** | Grúas, gestoría automotor, productores de seguros, fletes, transporte, mecánica, gomería, etc. | Prestadores (personas y empresas) |
| **Repuestos** | Casas de repuestos verificadas y su catálogo | Solo comercios verificados en persona |
| **Empleos** | Puestos del rubro transporte (choferes, mecánicos, vendedores de agencia, etc.) | Empresas y particulares |

## 2. Para quién

- **Comprador**: busca rápido, filtra bien, entiende el precio y la financiación, contacta sin vueltas.
- **Particular que vende**: 1 publicación gratis (un vehículo **o** un puesto de trabajo).
- **Agencia / concesionaria**: publica su stock, mide resultados y paga según volumen.
- **Prestador de servicios y casa de repuestos**: aparece donde lo buscan, con sello de verificación.
- **Anunciante**: marcas, bancos, aseguradoras y comercios que pagan por visibilidad rotulada.
- **Equipo Girando**: Super Admin (dueños), Admin (operación), Moderación, Finanzas.

## 3. Cómo gana plata (en orden de importancia)

1. **Publicidad en el portal**: banners y espacios patrocinados, siempre rotulados “Publicidad” o “Patrocinado”, medidos con impresiones y clics reales. Es el fuerte económico: por eso importa el tráfico y que la gente vuelva.
2. **Planes de agencias por volumen de publicadas**: hasta 30, hasta 60 y más de 60 vehículos (los precios los define el dueño en el Admin; el inventario sin publicar no cuenta).
3. **Suscripción obligatoria de casas de repuestos**: $ 4.000 (valor inicial, editable), que incluye verificación presencial del local, verificación de identidad del responsable y carga correcta de datos. Sin pago aprobado y verificación aprobada, no publica.
4. **Promociones**: destacar publicaciones, posición en búsqueda, agencia destacada.
5. **Planes para prestadores de servicios y empresas que publican empleos** (a definir).

Lo gratis: un particular tiene **1 publicación activa gratis**, sea un vehículo o un puesto de trabajo.

## 4. Decisiones de producto ya tomadas

- **Empleos sin currículums**: la gente no sube CV ni documentos. La postulación es un **contacto dentro de Girando** (mensaje en la plataforma). Menos datos personales guardados = menos riesgo y menos costo; el valor está en el tráfico y la publicidad, no en una base de CVs.
- **Contacto dentro de la plataforma**: los mensajes pasan por Girando (con moderación y retención definida). WhatsApp/teléfono quedan como opción del vendedor, medidos sin guardar quién hizo clic.
- **Recomendaciones inteligentes** basadas en lo que el usuario mira, guarda y busca **en Girando** (datos propios, con consentimiento de cookies de analítica). Sin consentimiento, se recomienda por contexto (mismo modelo, rango de precio, zona). Nada de cookies de terceros ni perfiles vendidos a terceros.
- **Todo bien sectorizado**: cada vertical con su navegación, sus filtros y su forma de publicar. Nada mezclado.
- **Financiación visible y honesta**: “Apto crédito”, entidad (Banco Nación, Supervielle, etc.), anticipo mínimo, monto financiable, cuotas. Si se muestra tasa, se muestran **TNA, TEA y CFT** (obligación en Argentina para publicidad de créditos). Girando no presta dinero: muestra información cargada por la agencia o por convenio con la entidad, con fecha de vigencia.
- **Diseño**: blanco, limpio, fácil de entender, agradable. Se mantiene la identidad actual (logo, azul de marca, componentes) y se puede mejorar la tipografía.

## 5. Taxis y permisos (contexto regulatorio en Mendoza)

- Marco: **Ley 9086 de Movilidad** y su Decreto reglamentario 1512/2018. Los permisos los otorga la **Subsecretaría de Transporte** por concurso (ej. Resolución 2122/2024) y los registra la **Dirección de Transporte** (Departamento de Registros).
- El permiso **lo otorga el Estado**: su transferencia es un **trámite ante la Dirección de Transporte**, con requisitos del titular, del vehículo y del chofer (libre deuda, seguro, RTO, GNC si corresponde, reloj y GPS, licencia profesional, etc.).
- Vehículo: antigüedad máxima para incorporarse o renovarse de 10 años (uso hasta 13 según decreto), medidas y equipamiento mínimos (aire, calefacción, cuatro pasajeros).
- Para Girando: se publica el **vehículo y el permiso declarado** (número, departamento/zona, tipo), con un aviso claro de que la transferencia requiere autorización oficial. El sello de “permiso verificado” solo se otorga si el equipo lo comprobó.
- Datos a confirmar con fuentes oficiales antes de lanzar (las referencias son de 2019–2025).

## 6. Estado actual (fases 1 a 3, todo local, sin desplegar)

**Stack**: PostgreSQL 16 (RLS, triggers, auditoría) · FastAPI · Redis · worker · nginx · frontend web responsive (App y Admin) generado desde `web/src/`. Docker Compose. Puertos locales 3100 (web) y 8100 (API).

**Funciona hoy**
- Cuentas con sesión segura (cookies httpOnly + CSRF), recuperación de contraseña, verificación de email.
- Vehículos: catálogo marca → modelo → generación → versión, publicación en 5 pasos con fotos (máx. 6, portada, orden), moderación, búsqueda con filtros, detalle, favoritos, venta informada e historial de ventas.
- Agencias: perfil editable (web, tienda online, WhatsApp, redes), inventario vs publicadas, estadísticas reales, verificación con checklist.
- Planes: Particular Free (1), Agencia 30, Agencia 100. Límite controlado por la base. Suscripciones con Mercado Pago (preapproval + webhook) y planes asignados por Girando. Períodos por mes calendario.
- Admin por rol: moderación, agencias, usuarios, catálogo, verificaciones, reportes, negocio, finanzas, planes, promociones, Home administrable, auditoría, retención.
- Tests: 62 de backend, E2E de 18 pasos en mobile, tablet y desktop.

**No existe todavía**: taxis, servicios, repuestos, empleos, mensajería interna, recomendaciones, financiación por entidad, planes de 60 y más de 60, suscripción de repuestos, medición de publicidad desde la App, credenciales reales (Cloudinary, Mercado Pago sandbox, email).

Documentación: `README.md`, `SECURITY.md`, `ARCHITECTURE.md` y `docs/00` a `docs/09` (el gap analysis está en `docs/09-gap-analysis-fase3.md`).

## 7. Reglas que no se negocian

1. **PostgreSQL es la única fuente de verdad.** Nada de `localStorage` o cookies como fuente de verdad de planes, promociones, pagos o permisos.
2. **El backend valida todo**: roles, límites, pagos, estados. Ocultar un botón no es seguridad.
3. **Cero datos inventados**: sin publicaciones, reseñas, métricas ni “promedios” de relleno. Sin datos suficientes se dice “Sin datos suficientes”.
4. **Una suscripción o promoción se activa solo con un pago aprobado** (o una cortesía explícita y auditada del Super Admin).
5. **Publicidad siempre rotulada.** Logos de bancos y marcas solo con autorización.
6. **Mínimos datos personales.** Nada de CVs, DNI solo en almacenamiento privado para verificaciones, retención definida.
7. **Todo cambio de estado relevante queda en auditoría.**
8. **No se toca producción ni datos reales** (todavía no hay); las credenciales de desarrollo nunca se usan en producción.

## 8. Cuentas de desarrollo (solo local)

Contraseña de todas: valor de `DEV_SEED_PASSWORD` en `.env` (por defecto `Girando-dev-2026`).
`superadmin@girando.test` · `admin@girando.test` · `moderador@girando.test` · `usuario@girando.test` · `agencia@girando.test`.
Empezar de cero: `docker compose exec api python -m app.cli reset-dev-db --confirm girando` y `docker compose restart api worker`.
