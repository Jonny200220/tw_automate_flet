"""Provecomer (Grupo La Comer).

Login legacy con captcha de texto. La imagen del captcha llega embebida en el
HTML como data URI base64 (#captchaImage), así que se puede mostrar dentro de
la app en vez de obligar al usuario a mirar el navegador.
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Page

from ..config import Credenciales
from ..ui import PuenteUI
from .base import ErrorPortal, Portal, png_desde_data_uri

INTENTOS_CAPTCHA = 4


class Provecomer(Portal):
    clave = "provecomer"
    nombre = "Provecomer"
    url_login = "https://www.provecomer.com.mx/provecomer_angular/#/auth/login"
    requiere_captcha = True

    SEL_USUARIO = "#proveedor"
    SEL_PASSWORD = "#password"
    SEL_CAPTCHA_IMG = "#captchaImage"
    SEL_CAPTCHA_INPUT = "#captcha"
    SEL_ENVIAR = "#btnEnviar"
    SEL_REFRESCAR = "#generateCaptchaButton"

    def sesion_activa(self, page: Page) -> bool:
        return "Login" not in page.url and "provecomer" in page.url.lower()

    def login(self, page: Page, credenciales: Credenciales, ui: PuenteUI) -> None:
        if not credenciales.completas:
            raise ErrorPortal("Faltan credenciales de Provecomer")

        page.goto(self.url_login, wait_until="domcontentloaded")

        for intento in range(1, INTENTOS_CAPTCHA + 1):
            if ui.cancelado():
                raise ErrorPortal("Cancelado por el usuario")

            page.fill(self.SEL_USUARIO, credenciales.usuario)
            page.fill(self.SEL_PASSWORD, credenciales.password)

            src = page.get_attribute(self.SEL_CAPTCHA_IMG, "src") or ""
            texto = ui.pedir_captcha(png_desde_data_uri(src), self.nombre, intento)
            if not texto:
                raise ErrorPortal("Captcha cancelado o sin respuesta")

            page.fill(self.SEL_CAPTCHA_INPUT, texto.strip())

            with page.expect_navigation(wait_until="domcontentloaded"):
                page.click(self.SEL_ENVIAR)

            if self._login_exitoso(page):
                ui.log("Sesión iniciada en Provecomer", "ok")
                return

            motivo = self._mensaje_error(page)
            ui.log(f"Intento {intento} rechazado: {motivo}", "error")

            # Si las credenciales están mal, reintentar el captcha no sirve.
            if "captcha" not in motivo.lower():
                raise ErrorPortal(f"Provecomer rechazó el acceso: {motivo}")

            if page.locator(self.SEL_REFRESCAR).count():
                page.click(self.SEL_REFRESCAR)
                page.wait_for_timeout(600)

        raise ErrorPortal(f"No se pudo pasar el captcha en {INTENTOS_CAPTCHA} intentos")

    def _login_exitoso(self, page: Page) -> bool:
        return "LoginProvecomerNpSrv" not in page.url

    def _mensaje_error(self, page: Page) -> str:
        for selector in (".error", ".mensaje", "font[color='red']", "td[bgcolor]"):
            localizador = page.locator(selector)
            if localizador.count():
                texto = (localizador.first.inner_text() or "").strip()
                if texto:
                    return texto[:200]
        return "captcha o credenciales incorrectas"

    def descargar(self, page: Page, ui: PuenteUI, destino: Path) -> list[Path]:
        # Pendiente: mapear el árbol de reportes interno con el modo explorar.
        raise NotImplementedError(
            "Falta mapear la navegación interna de Provecomer. "
            "Corré `uv run towel-automate explorar provecomer`."
        )
