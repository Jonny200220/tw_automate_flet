"""HEB Business (go.heb2b.com.mx).

ASP.NET MVC con antiforgery token. No hay captcha en el login: el reCAPTCHA que
aparece en el HTML pertenece al formulario de recuperar contraseña.
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Page

from ..config import Credenciales
from ..ui import PuenteUI
from .base import ErrorPortal, Portal


class Heb2b(Portal):
    clave = "heb2b"
    nombre = "HEB Business"
    url_login = "https://go.heb2b.com.mx/HEBusiness/"

    SEL_USUARIO = "P3389_1"
    SEL_PASSWORD = "MqtcK#*0$O"
    SEL_ENTRAR = "#btnEntrar"

    def sesion_activa(self, page: Page) -> bool:
        return page.locator(self.SEL_USUARIO).count() == 0

    def login(self, page: Page, credenciales: Credenciales, ui: PuenteUI) -> None:
        if not credenciales.completas:
            raise ErrorPortal("Faltan credenciales de HEB Business")

        page.goto(self.url_login, wait_until="domcontentloaded")

        if self.sesion_activa(page):
            ui.log("HEB Business ya tenía sesión abierta", "ok")
            return

        page.fill(self.SEL_USUARIO, credenciales.usuario)
        page.fill(self.SEL_PASSWORD, credenciales.password)
        page.click(self.SEL_ENTRAR)

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

    def descargar(self, page: Page, ui: PuenteUI, destino: Path) -> list[Path]:
        raise NotImplementedError(
            "Falta mapear la navegación interna de HEB Business. "
            "Corré `uv run towel-automate explorar heb2b`."
        )
