"""HEB Business (go.heb2b.com.mx).

ASP.NET MVC con antiforgery token. No hay captcha en el login: el reCAPTCHA que
aparece en el HTML pertenece al formulario de recuperar contraseña.

El reporte vive dentro de un iframe de Power BI (`#embedContainer iframe`) y sus
controles se ubican por `data-testid` (`visual-more-options-btn`,
`pbimenu-item.Exportar datos`, `export-btn`). Esos IDs los define Power BI; si
cambian tras una actualización, recapturá el flujo con
`uv run towel-automate explorar heb2b` y ajustá `descargar()`.
"""

from __future__ import annotations

import re
from pathlib import Path

from playwright.sync_api import Locator, Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from ..config import Credenciales
from ..ui import PuenteUI
from .base import ErrorPortal, Portal, guardar_descarga, normalizar

# Iframe que contiene el reporte de Power BI.
SEL_IFRAME = "#embedContainer iframe"

# Power BI renderiza el visual perezosamente y el export pasa por el servidor.
TIMEOUT_RENDER_MS = 90_000
TIMEOUT_EXPORTACION_MS = 120_000


class Heb2b(Portal):
    clave = "heb2b"
    nombre = "HEB Business"
    carpeta = "heb"
    url_login = "https://go.heb2b.com.mx/HEBusiness/"

    # Menú lateral. Se pueden sobreescribir en caliente:
    # PORTALES["heb2b"].reporte = "Ventas"
    seccion = "Business Info"
    reporte = "Inventarios"

    @property
    def area(self) -> str:  # type: ignore[override]
        # Sigue al reporte elegido: si se cambia arriba, la carpeta acompaña.
        return normalizar(self.reporte)

    # Fallback por ID del formulario de login; el rol accesible es lo primario.
    SEL_USUARIO = "#Usuario"
    SEL_PASSWORD = "#password"
    SEL_ENTRAR = "#btnEntrar"

    # ------------------------------------------------------------------ login

    def _campo_usuario(self, page: Page) -> Locator:
        return page.get_by_role("textbox", name="Ingresa tu Nombre de Usuario")

    def _campo_password(self, page: Page) -> Locator:
        return page.get_by_role("textbox", name="Ingresa tu contraseña")

    def sesion_activa(self, page: Page) -> bool:
        return page.locator(self.SEL_USUARIO).count() == 0

    def login(self, page: Page, credenciales: Credenciales, ui: PuenteUI) -> None:
        if not credenciales.completas:
            raise ErrorPortal("Faltan credenciales de HEB Business")

        page.goto(self.url_login, wait_until="domcontentloaded")

        if self.sesion_activa(page):
            ui.log("HEB Business ya tenía sesión abierta", "ok")
            return

        usuario = self._campo_usuario(page)
        password = self._campo_password(page)

        # Si el portal cambió los textos accesibles, caemos a los IDs del form.
        if not usuario.count():
            usuario = page.locator(self.SEL_USUARIO)
            password = page.locator(self.SEL_PASSWORD)

        usuario.first.fill(credenciales.usuario)
        password.first.fill(credenciales.password)
        page.get_by_role("button", name="Entrar").click()

        try:
            page.wait_for_selector(self.SEL_USUARIO, state="detached", timeout=30_000)
        except Exception as exc:
            raise ErrorPortal(f"HEB Business rechazó el acceso: {self._error(page)}") from exc

        ui.log("Sesión iniciada en HEB Business", "ok")

    def _error(self, page: Page) -> str:
        for selector in (".validation-summary-errors", ".field-validation-error", ".alert"):
            localizador = page.locator(selector)
            if localizador.count():
                texto = (localizador.first.inner_text() or "").strip()
                if texto:
                    return texto[:200]
        return "credenciales incorrectas o portal sin responder"

    # -------------------------------------------------------------- descargar

    def descargar(self, page: Page, ui: PuenteUI, destino: Path) -> list[Path]:
        self._abrir_reporte(page, ui)
        archivos = self._exportar_visual(page, ui, destino)
        self._cerrar_sesion(page, ui)

        if not archivos:
            raise ErrorPortal("HEB Business no devolvió archivos")
        return archivos

    def _abrir_reporte(self, page: Page, ui: PuenteUI) -> None:
        # El dashboard carga widgets por AJAX; esperar a que la red se calme
        # asegura que el menú lateral esté completamente inicializado.
        try:
            page.wait_for_load_state("networkidle", timeout=20_000)
        except PlaywrightTimeoutError:
            ui.log("El dashboard siguió cargando; continúo igual", "info")

        ui.log(f"Navegando a {self.seccion} > {self.reporte}", "info")
        seccion = page.get_by_role("link", name=self.seccion)
        reporte = page.get_by_role("link", name=self.reporte)

        # La sección es un acordeón del menú lateral: al hacer clic despliega el
        # submenú. Reintentamos una vez por si el primer clic cierra un acordeón
        # que ya venía abierto.
        seccion.first.scroll_into_view_if_needed()
        for intento in (1, 2):
            seccion.first.click()
            try:
                reporte.first.wait_for(state="visible", timeout=15_000)
                break
            except PlaywrightTimeoutError as exc:
                ui.log(f"'{self.reporte}' no apareció tras el clic {intento}", "error")
                if intento == 2:
                    raise ErrorPortal(
                        f"No se pudo abrir {self.seccion} > {self.reporte} en HEB Business"
                    ) from exc

        reporte.first.click()

    def _exportar_visual(self, page: Page, ui: PuenteUI, destino: Path) -> list[Path]:
        embed = page.locator(SEL_IFRAME)
        marco = page.frame_locator(SEL_IFRAME)
        mas_opciones = marco.get_by_test_id("visual-more-options-btn")

        # Power BI solo dibuja el visual cuando el iframe entra al viewport.
        embed.scroll_into_view_if_needed()
        ui.log("Esperando a que renderice el reporte de Power BI...", "info")

        try:
            mas_opciones.wait_for(state="attached", timeout=TIMEOUT_RENDER_MS)
        except PlaywrightTimeoutError as exc:
            raise ErrorPortal(
                "El reporte de Power BI no terminó de renderizar. "
                "Si el portal cambió, recapturá con `explorar heb2b`."
            ) from exc

        # El botón "..." del visual solo aparece con el cursor encima.
        marco.locator("body").hover()
        mas_opciones.click()
        marco.get_by_test_id("pbimenu-item.Exportar datos").click()

        ui.log("Exportando datos", "info")
        try:
            with page.expect_download(timeout=TIMEOUT_EXPORTACION_MS) as info:
                marco.get_by_test_id("export-btn").click()
        except PlaywrightTimeoutError as exc:
            raise ErrorPortal("La exportación de Power BI no generó archivo") from exc

        return [guardar_descarga(info.value, destino, self.clave, self.area)]

    def _cerrar_sesion(self, page: Page, ui: PuenteUI) -> None:
        """Best-effort: la descarga ya está, un logout fallido no importa."""
        try:
            # El menú de usuario es un enlace sin texto (solo icono).
            page.get_by_role("link").filter(has_text=re.compile(r"^$")).first.click(timeout=5_000)
            page.get_by_role("link", name="Cerrar Sesión").click(timeout=5_000)
            ui.log("Sesión de HEB Business cerrada", "info")
        except Exception:  # noqa: BLE001
            pass
