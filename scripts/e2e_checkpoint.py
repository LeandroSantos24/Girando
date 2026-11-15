"""Recorre en un navegador real los 18 pasos del primer checkpoint del MVP.

Requisitos: el sistema levantado (docker compose up) y Playwright para Python:
    pip install playwright && playwright install chromium
    python3 scripts/e2e_checkpoint.py [http://localhost:3100] [--shots carpeta] [--viewport 1440x900]

El mismo recorrido funciona en desktop (header + navegación lateral) y en mobile (barra inferior):
    python3 scripts/e2e_checkpoint.py --viewport 390x844

Usa el moderador del seed de desarrollo (moderador@girando.test / DEV_SEED_PASSWORD).
Crea un usuario nuevo en cada corrida (e2e<timestamp>@girando.test).
"""
import io
import re
import os
import sys
import time

from playwright.sync_api import sync_playwright

BASE = next((a for a in sys.argv[1:] if a.startswith("http")), "http://localhost:3100").rstrip("/")
SHOTS = sys.argv[sys.argv.index("--shots") + 1] if "--shots" in sys.argv else None
MOD_PASS = os.environ.get("DEV_SEED_PASSWORD", "Girando-dev-2026")
VIEWPORT = tuple(int(x) for x in (sys.argv[sys.argv.index("--viewport") + 1] if "--viewport" in sys.argv else "1440x900").split("x"))
EMAIL, PASS = f"e2e{int(time.time())}{VIEWPORT[0]}@girando.test", "Probando-2026"


def visible(loc):
    """Primer elemento visible: el marcado responsive tiene variantes ocultas según el viewport."""
    loc.first.wait_for(state="attached")
    for _ in range(40):
        for i in range(loc.count()):
            if loc.nth(i).is_visible():
                return loc.nth(i)
        time.sleep(0.1)
    raise AssertionError(f"no hay elemento visible para {loc}")


def btn(pg, name, exact=False):
    visible(pg.get_by_role("button", name=name, exact=exact)).click()
    pg.wait_for_timeout(500)


def text(pg, s):
    visible(pg.get_by_text(s)).click()
    pg.wait_for_timeout(500)


def has_btn(pg, name):
    loc = pg.get_by_role("button", name=name)
    return any(loc.nth(i).is_visible() for i in range(loc.count()))


def search(pg, q):
    if not any(pg.locator('input[aria-label="Buscar vehículos"]').nth(i).is_visible() for i in range(pg.locator('input[aria-label="Buscar vehículos"]').count())):
        btn(pg, "Buscar")  # mobile: pestaña Buscar
    visible(pg.locator('input[aria-label="Buscar vehículos"]')).fill(q)
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(1800)


def jpg(color, path):
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (1024, 768), color).save(b, "JPEG")
    open(path, "wb").write(b.getvalue())
    return path


def ok(pg, n, name):
    pg.wait_for_timeout(700)
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True)
        pg.screenshot(path=os.path.join(SHOTS, f"{n:02d}_{name}.png"))
    print(f"✓ {n:2d}. {name}  [{VIEWPORT[0]}x{VIEWPORT[1]}]")


with sync_playwright() as p:
    b = p.chromium.launch()
    errors = []
    app = b.new_page(viewport={"width": VIEWPORT[0], "height": VIEWPORT[1]})
    app.on("pageerror", lambda e: errors.append(str(e)))
    # 1. levantar
    app.goto(BASE + "/")
    app.wait_for_timeout(3000)
    app.get_by_role("button", name="Rechazar las no necesarias").click()
    ok(app, 1, "App levantada")
    # 2. registrarme
    btn(app, "Ingresar")
    if has_btn(app, "Crear cuenta gratis"):
        btn(app, "Crear cuenta gratis")   # mobile: "Tu lugar en Girando"
    else:
        text(app, "Creá una gratis")      # desktop: pantalla de ingreso
    app.fill("#reg-name", "Prueba"); app.fill("#reg-last", "E2E"); app.fill("#reg-email", EMAIL)
    app.fill("#reg-pass", PASS); app.fill("#reg-pass2", PASS)
    app.get_by_role("button", name="Crear cuenta").click()
    app.wait_for_timeout(2000)
    ok(app, 2, "registro")
    # 3. cerrar sesión e iniciar sesión
    btn(app, "Mi Girando")
    btn(app, "Cerrar sesión")
    app.wait_for_timeout(800)
    btn(app, "Ingresar")
    if has_btn(app, "Ya tengo cuenta"):
        btn(app, "Ya tengo cuenta")
    app.fill("#login-email", EMAIL); app.fill("#login-pass", PASS)
    app.get_by_role("button", name="Iniciar sesión").click()
    app.wait_for_timeout(2000)
    ok(app, 3, "login")
    # 4. Mi Girando
    btn(app, "Mi Girando")
    visible(app.get_by_text("Prueba E2E"))
    ok(app, 4, "Mi Girando")
    # 6. buscar vehículos (búsqueda + filtros sobre la API)
    search(app, "volkswagen")
    if has_btn(app, re.compile(r"^Filtros")):   # mobile/tablet: hoja de filtros; desktop: columna siempre visible
        btn(app, re.compile(r"^Filtros")); app.wait_for_timeout(600)
        btn(app, re.compile(r"^Ver \d+ resultados")); app.wait_for_timeout(600)
    else:
        assert app.locator(".gr-filters__panel").is_visible()
    ok(app, 6, "búsqueda y filtros")
    btn(app, "Mi Girando")
    # 5 y 7. catálogo real dentro del asistente de publicación
    btn(app, "Publicar vehículo")
    app.wait_for_selector('#wz-b option:has-text("Volkswagen")', state="attached")
    app.select_option("#wz-b", label="Volkswagen")
    app.wait_for_selector('#wz-m option:has-text("Gol Trend")', state="attached"); app.select_option("#wz-m", label="Gol Trend")
    app.wait_for_timeout(500); app.select_option("#wz-g", index=1)
    app.wait_for_timeout(500); app.select_option("#wz-v", index=1)
    ok(app, 5, "catálogo (marca → modelo → generación → versión)")
    app.get_by_role("button", name="Continuar").click(); app.wait_for_timeout(800)
    app.select_option("#wz-y", index=3); app.fill("#wz-km", "98000")
    app.get_by_role("button", name="Continuar").click(); app.wait_for_timeout(800)
    app.fill("#wz-p", "9500000"); app.select_option("#wz-prov", label="Mendoza")
    app.wait_for_selector('#wz-dept option:has-text("Godoy Cruz")', state="attached"); app.select_option("#wz-dept", label="Godoy Cruz")
    app.get_by_role("button", name="Continuar").click(); app.wait_for_timeout(800)
    tmp = "/tmp" if os.path.isdir("/tmp") else "."
    app.set_input_files('input[aria-label="Subir fotos"]', [jpg((30, 90, 200), f"{tmp}/g1.jpg"), jpg((200, 40, 40), f"{tmp}/g2.jpg")])
    app.wait_for_timeout(3500)
    app.fill("#wz-t", "Impecable, único dueño")
    app.fill("#wz-d", "Service al día en concesionario, cubiertas nuevas y VTV vigente.")
    ok(app, 7, "crear publicación (con fotos)")
    # 8. guardar borrador
    app.get_by_role("button", name="Guardar borrador y salir").click(); app.wait_for_timeout(1500)
    visible(app.get_by_text("Borrador"))
    ok(app, 8, "borrador guardado")
    # 9. enviar a revisión
    app.get_by_role("button", name="Continuar borrador").click(); app.wait_for_timeout(1200)
    for _ in range(4):
        app.get_by_role("button", name="Continuar").click(); app.wait_for_timeout(700)
    app.get_by_role("button", name="Enviar a revisión").click(); app.wait_for_timeout(1500)
    visible(app.get_by_text("Pendiente"))
    ok(app, 9, "enviada a revisión (pendiente)")
    # 10-12. Admin
    adm = b.new_page(viewport={"width": VIEWPORT[0], "height": VIEWPORT[1]})
    adm.goto(BASE + "/admin"); adm.wait_for_timeout(2500)
    adm.fill("#adm-email", "moderador@girando.test"); adm.fill("#adm-pass", MOD_PASS)
    adm.get_by_role("button", name="Ingresar").click(); adm.wait_for_timeout(2500)
    ok(adm, 10, "Admin: login moderador")
    if has_btn(adm, "Abrir menú"):   # tablet/mobile: la navegación del Admin es un cajón
        btn(adm, "Abrir menú")
    adm.get_by_role("button", name=re.compile(r"^Publicaciones( \d+)?$")).click(); adm.wait_for_timeout(800)
    adm.get_by_role("button", name="Pendiente", exact=True).click(); adm.wait_for_timeout(1200)
    ok(adm, 11, "Admin: publicación pendiente")
    adm.get_by_role("button", name="Ver", exact=True).first.click(); adm.wait_for_timeout(1500)
    adm.get_by_role("dialog").get_by_role("button", name="Aprobar").click(); adm.wait_for_timeout(1500)
    ok(adm, 12, "Admin: aprobada")
    # 13-14. volver a la App y verla publicada
    btn(app, "Inicio"); app.wait_for_timeout(1500)
    search(app, "gol trend")
    ok(app, 13, "App: búsqueda")
    btn(app, "Mi Girando")
    text(app, "Mis publicaciones"); app.wait_for_timeout(1500)
    visible(app.get_by_text("Publicada"))
    ok(app, 14, "App: publicada")
    # 15. detalle
    search(app, "gol trend")
    text(app, "Volkswagen Gol Trend"); app.wait_for_timeout(2000)
    ok(app, 15, "App: detalle")
    # 16. editar (precio)
    btn(app, "Mi Girando")
    text(app, "Mis publicaciones"); app.wait_for_timeout(1200)
    btn(app, "Editar", exact=True); app.wait_for_timeout(1200)
    for _ in range(2):
        app.get_by_role("button", name="Continuar").click(); app.wait_for_timeout(700)
    app.fill("#wz-p", "9200000")
    for _ in range(2):
        app.get_by_role("button", name="Continuar").click(); app.wait_for_timeout(700)
    app.get_by_role("button", name="Guardar cambios").click(); app.wait_for_timeout(1500)
    visible(app.get_by_text("$ 9.200.000"))
    ok(app, 16, "App: editada (sigue publicada)")
    # 17. vendida
    btn(app, "Vendí este vehículo"); app.wait_for_timeout(1200)
    app.get_by_text("A través de Girando").click()
    app.get_by_role("button", name="Continuar").click(); app.wait_for_timeout(600)
    app.fill("#sl-price", "9000000")
    app.get_by_role("button", name="Registrar venta").click(); app.wait_for_timeout(2000)
    ok(app, 17, "App: vendida")
    # 18. historial
    app.get_by_role("button", name="Ver historial de ventas").click(); app.wait_for_timeout(1500)
    visible(app.get_by_text("Volkswagen Gol Trend"))
    ok(app, 18, "App: historial de ventas")
    b.close()
    print("Errores de página:", errors or "ninguno")
    sys.exit(1 if errors else 0)
