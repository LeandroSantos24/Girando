"""Datos BASE (no demo): configuración y catálogos de referencia necesarios para operar.

- geo: provincias argentinas + departamentos de Cuyo (región de lanzamiento). Sin coordenadas
  ni códigos oficiales inventados: se completan importando Georef AR (pendiente).
- catálogo: el catálogo inicial del prototipo (6 marcas). Marcado para revisión antes de
  producción; cilindrada/potencia quedan vacías hasta cargarlas de una fuente confiable.
- planes, motivos de reporte, tipos de notificación, plantillas, productos, retención y
  parámetros: configuración inicial editable desde el Admin.
"""

PROVINCES = [
    "Buenos Aires", "Ciudad Autónoma de Buenos Aires", "Catamarca", "Chaco", "Chubut", "Córdoba", "Corrientes", "Entre Ríos",
    "Formosa", "Jujuy", "La Pampa", "La Rioja", "Mendoza", "Misiones", "Neuquén", "Río Negro", "Salta", "San Juan", "San Luis",
    "Santa Cruz", "Santa Fe", "Santiago del Estero", "Tierra del Fuego, Antártida e Islas del Atlántico Sur", "Tucumán",
]

DEPARTMENTS = {
    "Mendoza": ["Capital", "General Alvear", "Godoy Cruz", "Guaymallén", "Junín", "La Paz", "Las Heras", "Lavalle", "Luján de Cuyo",
                "Maipú", "Malargüe", "Rivadavia", "San Carlos", "San Martín", "San Rafael", "Santa Rosa", "Tunuyán", "Tupungato"],
    "San Juan": ["Albardón", "Angaco", "Calingasta", "Capital", "Caucete", "Chimbas", "Iglesia", "Jáchal", "9 de Julio", "Pocito",
                 "Rawson", "Rivadavia", "San Martín", "Santa Lucía", "Sarmiento", "Ullum", "Valle Fértil", "25 de Mayo", "Zonda"],
    "San Luis": ["Ayacucho", "Belgrano", "Coronel Pringles", "Chacabuco", "General Pedernera", "Gobernador Dupuy", "Junín",
                 "Juan Martín de Pueyrredón", "Libertador General San Martín"],
}

# (marca, [(modelo, tipo, carrocería, [(generación, año_desde, año_hasta, [(versión, motor, combustible, transmisión, tracción, puertas)])])])
CATALOG = [
    ("Chevrolet", [
        ("Corsa", "car", "sedan", [("Classic", 2010, 2016, [("1.4 LS", "1.4 Nafta", "gasoline", "manual", "front", 4), ("1.6 Super", "1.6 Nafta", "gasoline", "manual", "front", 4)])]),
        ("Onix", "car", "hatchback", [
            ("Primera generación", 2013, 2019, [("LT 1.4", "1.4 Nafta", "gasoline", "manual", "front", 5), ("LTZ 1.4", "1.4 Nafta", "gasoline", "manual", "front", 5)]),
            ("Segunda generación", 2020, None, [("LT 1.0 Turbo", "1.0 Turbo Nafta", "gasoline", "manual", "front", 5), ("Premier 1.0 Turbo AT", "1.0 Turbo Nafta", "gasoline", "automatic", "front", 5)])]),
        ("S10", "light_truck", "pickup", [("Segunda generación", 2012, None, [("LS 2.8 TD 4x2", "2.8 Diésel", "diesel", "manual", "4x2", 4), ("LTZ 2.8 TD 4x4 AT", "2.8 Diésel", "diesel", "automatic", "4x4", 4)])]),
        ("Tracker", "light_truck", "suv", [("Segunda generación", 2021, None, [("LTZ 1.2 Turbo AT", "1.2 Turbo Nafta", "gasoline", "automatic", "front", 5), ("Premier 1.2 Turbo AT", "1.2 Turbo Nafta", "gasoline", "automatic", "front", 5)])]),
    ]),
    ("Volkswagen", [
        ("Gol Trend", "car", "hatchback", [("Trend", 2008, 2023, [("Trendline 1.6", "1.6 Nafta", "gasoline", "manual", "front", 5), ("Highline 1.6", "1.6 Nafta", "gasoline", "manual", "front", 5)])]),
        ("Amarok", "light_truck", "pickup", [("Primera generación", 2010, 2024, [("Comfortline 2.0 TDI 4x2", "2.0 Diésel", "diesel", "manual", "4x2", 4), ("Highline V6 3.0 TDI 4x4 AT", "3.0 V6 Diésel", "diesel", "automatic", "4x4", 4)])]),
        ("Vento", "car", "sedan", [("Sexta generación", 2014, 2019, [("2.0 GLI TSI AT", "2.0 Turbo Nafta", "gasoline", "automatic", "front", 4)])]),
    ]),
    ("Fiat", [
        ("Cronos", "car", "sedan", [("Primera generación", 2018, None, [("1.3 Drive", "1.3 Nafta", "gasoline", "manual", "front", 4), ("1.3 GSE Drive", "1.3 Nafta", "gasoline", "manual", "front", 4), ("1.8 Precision AT", "1.8 Nafta", "gasoline", "automatic", "front", 4)])]),
    ]),
    ("Toyota", [
        ("Hilux", "light_truck", "pickup", [("Octava generación", 2016, None, [("SR 2.4 TDI 4x2", "2.4 Diésel", "diesel", "manual", "4x2", 4), ("SRV 2.8 TDI 4x4 AT", "2.8 Diésel", "diesel", "automatic", "4x4", 4)])]),
        ("Corolla", "car", "sedan", [("Duodécima generación", 2020, None, [("XEI 2.0 CVT", "2.0 Nafta", "gasoline", "cvt", "front", 4), ("SEG Hybrid", "1.8 Híbrido", "hybrid", "cvt", "front", 4)])]),
    ]),
    ("Peugeot", [
        ("208", "car", "hatchback", [("Primera generación", 2013, 2022, [("Allure 1.6", "1.6 Nafta", "gasoline", "manual", "front", 5)]),
                                     ("Segunda generación", 2023, None, [("Feline 1.6 AT", "1.6 Nafta", "gasoline", "automatic", "front", 5)])]),
    ]),
    ("Ford", [
        ("Ranger", "light_truck", "pickup", [("Tercera generación", 2012, 2023, [("XLT 3.2 4x4 AT", "3.2 Diésel", "diesel", "automatic", "4x4", 4)])]),
        ("Territory", "light_truck", "suv", [("Primera generación", 2023, None, [("Titanium 1.8 Turbo", "1.8 Turbo Nafta", "gasoline", "automatic", "front", 5)])]),
    ]),
]

# code, nombre, audiencia, precio, período, límite, destacadas, stats_level, miembros, default, orden, features
PLANS = [
    # code, nombre, audiencia, precio, período, publicaciones activas, destacadas incluidas, nivel de estadísticas, miembros, default, orden, features
    # Los valores son iniciales: el Super Admin los edita desde Admin → Planes (la App los lee de PostgreSQL).
    ("particular", "Particular Free", "particular", 0, "none", 1, 0, 0, 1, True, 0, ["1 publicación activa", "Perfil público", "Favoritos y búsquedas"]),
    ("agencia-30", "Agencia 30", "agency", 54900, "month", 30, 0, 2, 3, False, 1, ["Hasta 30 publicaciones activas", "Inventario sin límite (borradores y pausadas)", "Estadísticas por publicación", "Hasta 3 vendedores"]),
    ("agencia-60", "Agencia 60", "agency", 79900, "month", 60, 1, 2, 6, False, 2, ["Hasta 60 publicaciones activas", "Inventario sin límite (borradores y pausadas)", "1 publicación destacada incluida", "Hasta 6 vendedores"]),
    ("agencia-100", "Agencia +60", "agency", 99900, "month", 100, 2, 3, 10, False, 3, ["Más de 60: hasta 100 publicaciones activas", "Inventario sin límite (borradores y pausadas)", "2 publicaciones destacadas incluidas", "Métricas avanzadas"]),
    # Fase 4 · otros rubros. Precios y límites: valores iniciales A CONFIRMAR POR EL DUEÑO (ver PLAN_EXTRAS).
    ("repuestos", "Repuestos verificada", "parts_store", 4000, "month", 500, 0, 1, 3, False, 10, ["Catálogo de repuestos por marca, modelo y categoría", "Verificación presencial del local", "Sello de casa verificada"]),
    ("servicios", "Servicios", "service_provider", 0, "none", 20, 0, 1, 2, True, 20, ["1 ficha por rubro y zona", "Mensajes dentro de Girando", "Sello con verificación del equipo"]),
    ("empresa", "Empresa (empleos)", "company", 0, "none", 0, 0, 0, 2, True, 30, ["Publicación de puestos del rubro", "Postulaciones por mensaje, sin CVs"]),
]

# Extras de fase 4 por plan: empleos activos, exige verificación, valor pendiente de confirmar por el dueño.
# code: (max_active_jobs, requires_verification, pending_owner_confirmation)
PLAN_EXTRAS = {
    "particular": (1, False, False),       # el empleo comparte el único cupo gratis (lo hace cumplir app.limit_for)
    "agencia-30": (2, False, True), "agencia-60": (4, False, True), "agencia-100": (8, False, True),
    "repuestos": (1, True, True), "servicios": (1, False, True), "empresa": (3, False, True),
}

REPORT_REASONS = [
    ("precio_falso", "Precio falso", ["listing", "post"]), ("vehiculo_inexistente", "Vehículo inexistente", ["listing"]),
    ("informacion_enganosa", "Información engañosa", ["listing", "agency", "post"]), ("duplicada", "Publicación duplicada", ["listing", "post"]),
    ("contenido_inapropiado", "Contenido inapropiado", ["listing", "agency", "user", "message", "review", "post"]),
    ("posible_estafa", "Posible estafa", ["listing", "agency", "user", "message", "post"]), ("ya_vendido", "Vehículo ya vendido", ["listing"]),
    ("otro", "Otro", ["listing", "agency", "user", "message", "review", "post"]),
    ("spam", "Spam o publicidad no pedida", ["message", "post"]),
    ("pide_datos", "Pide datos personales, CV o dinero", ["message", "post"]),
]

# code, categoría, descripción, comercial, obligatoria, email, plantilla
NOTIFICATION_TYPES = [
    ("listing.approved", "listing", "Publicación aprobada", False, False, True, "listing.approved"),
    ("listing.changes_requested", "moderation", "Moderación pidió cambios", False, True, True, "listing.changes_requested"),
    ("listing.rejected", "moderation", "Publicación rechazada", False, True, True, "listing.rejected"),
    ("listing.paused", "moderation", "Publicación pausada por moderación", False, True, False, None),
    ("listing.deleted", "moderation", "Publicación eliminada por moderación", False, True, False, None),
    ("listing.expiring", "listing", "Publicación por vencer (3 días)", False, False, True, "listing.expiring"),
    ("listing.expired", "listing", "Publicación vencida", False, False, False, None),
    ("verification.agency_status", "verifications", "Cambio en la verificación de agencia", False, True, False, None),
    ("account.security", "security", "Actividad de seguridad de la cuenta", False, True, False, None),
    ("marketing.news", "marketing", "Novedades de Girando", True, False, False, None),
    ("subscription.activated", "subscriptions", "Plan activo", False, True, False, None),
    ("subscription.expiring", "subscriptions", "El plan termina pronto", False, True, False, None),
    ("subscription.expired", "subscriptions", "El plan terminó", False, True, False, None),
    ("subscription.payment_failed", "payments", "No se pudo cobrar la suscripción", False, True, False, None),
    # fase 4
    ("favorite.price_drop", "favorites", "Bajó de precio una publicación guardada", False, False, False, None),
    ("favorite.sold", "favorites", "Se vendió una publicación guardada", False, False, False, None),
    ("search.new_results", "favorites", "Novedades en una búsqueda guardada", False, False, False, None),
    ("message.new", "messages", "Mensaje nuevo", False, False, False, None),
    ("financing.reviewed", "moderation", "Oferta de financiación revisada", False, True, False, None),
    ("promotion.activated", "payments", "Promoción activa", False, True, False, None),
    ("post.expired", "listing", "Publicación de taxis, servicios, repuestos o empleos vencida", False, False, False, None),
]

EMAIL_TEMPLATES = [
    ("auth.verify_email", "Confirmá tu email para empezar", "Hola. Confirmá tu email en Girando: {{link}}", ["link"]),
    ("auth.password_reset", "Creá una contraseña nueva", "Pediste recuperar tu contraseña. Enlace válido por 1 hora: {{link}}", ["link"]),
    ("listing.approved", "Tu vehículo ya está publicado", "Tu publicación {{title}} fue aprobada.", ["title"]),
    ("listing.changes_requested", "Necesitamos que revises tu publicación", "Moderación pidió cambios en {{title}}: {{reason}}", ["title", "reason"]),
    ("listing.rejected", "Tu publicación fue rechazada", "{{title}} fue rechazada: {{reason}}", ["title", "reason"]),
    ("listing.expiring", "Tu publicación vence en 3 días", "Renová {{title}} para que siga visible.", ["title"]),
]

# code, etiqueta, categoría, duración, desde, acción
RETENTION = [
    ("media_sold", "Fotos de publicación vendida", "media", "7 days", "Venta registrada", "delete"),
    ("media_deleted", "Fotos de publicación eliminada o reemplazada", "media", "30 days", "Baja de la foto o publicación", "delete"),
    ("plate_after_sale", "Patente del vehículo vendido", "historical", "24 months", "Venta registrada", "delete"),
    ("sales", "Registros de venta", "historical", "5 years", "Fecha de venta", "aggregate_then_delete"),
    ("messages", "Mensajes", "operational", "12 months", "Última actividad", "delete"),
    ("listing_closed", "Texto de publicaciones cerradas", "operational", "12 months", "Cierre", "anonymize"),
    ("reports", "Denuncias y moderación", "historical", "3 years", "Resolución", "anonymize"),
    ("technical_logs", "Logs técnicos, intentos de login e IP de sesiones", "operational", "90 days", "Registro", "delete"),
    ("analytics_raw", "Eventos de analytics sin agregar", "operational", "25 months", "Registro", "aggregate_then_delete"),
    ("audit", "Auditoría administrativa", "audit", "10 years", "Registro", "keep"),
]

SETTINGS = [
    ("listings.duration_days", 60, "Días de vigencia de una publicación", True),
    ("listings.expiry_notice_days", 3, "Aviso antes del vencimiento (días)", True),
    ("listings.max_images", 6, "Máximo de fotos activas por publicación", True),
    ("messaging.max_new_conversations_per_day", 10, "Conversaciones nuevas por usuario por día", False),
    ("stats.min_sample_size", 3, "Muestra mínima para mostrar promedios", True),
    ("market.min_sample_size", 5, "Muestra mínima de publicaciones comparables para mostrar precio vs mercado y demanda del mercado", True),
    ("fx.source", "BCRA - Comunicación A 3500 (referencia mayorista)", "Fuente de cotización USD para normalizar precios", True),
    ("payments.bank_transfer", None, "Datos bancarios para transferencias. PENDIENTE: cargar datos reales desde el Admin.", False),
    ("billing.renewal_window_days", 15, "Días antes del fin del período en que un pago cuenta como renovación (continúa la fecha)", False),
    ("billing.grace_days", 10, "Días de gracia después del fin del período antes de vencer la suscripción", False),
    ("billing.expiry_notice_days", 7, "Aviso a la agencia antes de que termine un plan que no se renueva solo", False),
    # ---- fase 4
    ("messaging.max_messages_per_hour", 60, "Mensajes por usuario por hora (anti-spam)", False),
    ("posts.duration_days_job", 30, "Vigencia de un aviso de empleo (días)", True),
    ("posts.duration_days_taxi", 60, "Vigencia de una publicación de taxi o permiso (días)", True),
    ("posts.duration_days_service", 3650, "Vigencia de una ficha de servicio (días)", False),
    ("posts.duration_days_part", 3650, "Vigencia de un ítem del catálogo de repuestos (días)", False),
    ("financing.disclaimer",
     "Simulación orientativa. No es una oferta de crédito ni una aprobación: el otorgamiento, la tasa y la cuota final los define la entidad "
     "según su evaluación. La cuota estimada se calcula con sistema francés sobre la TNA informada y no incluye seguros, gastos ni impuestos; "
     "el costo total es el CFT. Girando no presta dinero ni intermedia créditos: muestra información cargada por la agencia o la entidad, con su vigencia.",
     "Leyenda de la calculadora y de las ofertas de financiación", True),
    # Decisión del dueño (CONTEXTO.md §2): taxis sin límite de antigüedad ni validaciones. Solo este aviso corto.
    ("taxi.legal_notice",
     "La transferencia del permiso requiere autorización de la autoridad de transporte.",
     "Aviso corto de la sección Taxis (único texto legal de la sección)", True),
    ("ads.min_impressions_for_ctr", 100, "Impresiones mínimas para mostrar un porcentaje de clics", False),
]

VERIFICATION_PRODUCTS = [
    ("identity", "Identidad verificada", "Validación del DNI del titular.", "identity", "user", "active",
     "Certifica la identidad del vendedor. No certifica el estado del vehículo."),
    ("agency", "Agencia verificada", "Datos fiscales, habilitación y responsable de la empresa.", "agency", "agency", "active",
     "Certifica los datos de la empresa. Girando no inspecciona los vehículos."),
    ("parts_store", "Casa de repuestos verificada", "Visita presencial al local, identidad del responsable y datos completos. Requiere la suscripción paga vigente.",
     "onsite_visit", "agency", "active", "Certifica que el local existe y quién es su responsable. Girando no garantiza los repuestos."),
    ("vehicle_documentation", "Documentación del vehículo", "Revisión documental (título / cédula).", "documentation", "vehicle", "draft",
     "Certifica que la documentación presentada coincide con la publicación. No es una inspección física."),
]

PROMOTION_PRODUCTS = [
    ("destacada", "Publicación destacada", "Aparece en Destacados de Inicio con la etiqueta Patrocinado.", "featured_listing", "home_featured", 4900, 7),
    ("posicion", "Posición promocionada", "Espacio patrocinado en búsquedas de su marca y modelo.", "promoted_position", "search_brand_model", 8900, 7),
    ("agencia-destacada", "Agencia destacada", "La agencia aparece destacada en el directorio con la etiqueta Patrocinado.", "featured_agency", "agency_directory", 14900, 30),
]

POLICIES = [("terms", "terminos.html"), ("privacy_policy", "privacidad.html"), ("cookies_policy", "cookies.html")]

# Checklist PRELIMINAR de revisión (borrador): ordena el trabajo del revisor, no define todavía
# las reglas comerciales definitivas de "Agencia Verificada por Girando". Editable sin deploy.
VERIFICATION_CHECKLISTS = {
    "agency": [
        {"key": "cuit", "label": "CUIT y razón social coinciden con constancia de AFIP/ARCA"},
        {"key": "domicilio", "label": "Domicilio comercial verificado"},
        {"key": "habilitacion", "label": "Habilitación municipal o registro correspondiente"},
        {"key": "responsable", "label": "Identidad del responsable de la agencia"},
        {"key": "contacto", "label": "Teléfono / WhatsApp y email responden"},
    ],
    # Repuestos: el sello se otorga con pago aprobado + visita presencial + identidad del responsable + datos completos
    "parts_store": [
        {"key": "pago", "label": "Suscripción de repuestos paga y vigente (lo controla también la base)"},
        {"key": "visita", "label": "Visita presencial al local: existe, está abierto y vende repuestos"},
        {"key": "responsable", "label": "Identidad del responsable verificada (DNI visto en la visita, no se guarda copia fuera del almacenamiento privado)"},
        {"key": "cuit", "label": "CUIT y razón social coinciden con la constancia de ARCA"},
        {"key": "datos", "label": "Datos completos y correctos: domicilio, horarios, teléfono, rubros"},
    ],
}

# Entidades de financiación: datos de referencia reales (nombre y sitio oficial). Sin logo: el uso de la marca
# requiere autorización escrita de cada entidad (logo_authorized = false hasta que exista y quede anotada).
FINANCING_ENTITIES = [
    ("banco-nacion", "Banco de la Nación Argentina", "bank", "https://www.bna.com.ar"),
    ("banco-supervielle", "Banco Supervielle", "bank", "https://www.supervielle.com.ar"),
    ("banco-santander", "Banco Santander Argentina", "bank", "https://www.santander.com.ar"),
    ("banco-galicia", "Banco Galicia", "bank", "https://www.galicia.ar"),
    ("bbva", "BBVA Argentina", "bank", "https://www.bbva.com.ar"),
    ("banco-macro", "Banco Macro", "bank", "https://www.macro.com.ar"),
    ("banco-credicoop", "Banco Credicoop", "bank", "https://www.bancocredicoop.coop"),
]
