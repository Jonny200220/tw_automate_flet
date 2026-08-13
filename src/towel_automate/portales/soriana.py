"""Soriana - Portal de socios comerciales.

Dos particularidades frente a los otros portales:

1. Está detrás de Cloudflare. En headless devuelve "Attention Required!" y nunca
   deja pasar; por eso la app corre con Chrome real y ventana visible.
2. Es una SPA de SAP UI5. Los IDs llevan un prefijo generado
   (`sap.f.FlexibleColumnLayoutWithOneColumnStart---logon--logon_user-inner`)
   que cambia según cómo se monte la vista, así que anclamos con `[id$=...]`
   sobre el sufijo estable en vez de usar el ID completo.
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Page

from ..config import Credenciales, settings
from ..ui import PuenteUI
from .base import ErrorPortal, Portal

TITULOS_CLOUDFLARE = ("attention required", "just a moment", "un momento")


class Soriana(Portal):
    clave = "soriana"
    nombre = "Soriana"
    url_login = "https://socios.soriana.com/index/index.html"

    SEL_USUARIO = "input[id$='logon_user-inner']"
    SEL_PASSWORD = "input[id$='logon_pass-inner']"
    SEL_ENTRAR = "button:has-text('Entrar')"

    def sesion_activa(self, page: Page) -> bool:
        return page.locator(self.SEL_USUARIO).count() == 0

    def login(self, page: Page, credenciales: Credenciales, ui: PuenteUI) -> None:
        if not credenciales.completas:
            raise ErrorPortal("Faltan credenciales de Soriana")

        page.goto(self.url_login, wait_until="domcontentloaded")
        self._esperar_cloudflare(page, ui)

        # UI5 monta los campos por JS, no vienen en el HTML inicial.
        try:
            page.wait_for_selector(self.SEL_USUARIO, timeout=settings.timeout_ms)
        except Exception as exc:
            if self.sesion_activa(page):
                ui.log("Soriana ya tenía sesión abierta", "ok")
                return
            raise ErrorPortal("No apareció el formulario de Soriana") from exc

        # UI5 valida en el evento change: fill + Tab para que registre el valor.
        page.fill(self.SEL_USUARIO, credenciales.usuario)
        page.press(self.SEL_USUARIO, "Tab")
        page.fill(self.SEL_PASSWORD, credenciales.password)
        page.press(self.SEL_PASSWORD, "Tab")

        page.click(self.SEL_ENTRAR)

        try:
            page.wait_for_selector(self.SEL_PASSWORD, state="detached", timeout=40_000)
        except Exception as exc:
            raise ErrorPortal(f"Soriana rechazó el acceso: {self._error(page)}") from exc

        ui.log("Sesión iniciada en Soriana", "ok")

    def _esperar_cloudflare(self, page: Page, ui: PuenteUI) -> None:
        """Cloudflare suele resolverse solo; si pide interacción, avisa al humano."""
        if not self._es_challenge(page):
            return

        ui.log("Cloudflare está validando el navegador...", "info")
        page.wait_for_timeout(6_000)

        if not self._es_challenge(page):
            ui.log("Cloudflare superado", "ok")
            return

        ui.log("Resolvé el desafío de Cloudflare en la ventana del navegador", "error")
        limite = settings.timeout_humano_ms
        transcurrido = 0
        while transcurrido < limite:
            if ui.cancelado():
                raise ErrorPortal("Cancelado por el usuario")
            page.wait_for_timeout(2_000)
            transcurrido += 2_000
            if not self._es_challenge(page):
                ui.log("Cloudflare superado", "ok")
                return

        raise ErrorPortal("Cloudflare siguió bloqueando el acceso a Soriana")

    def _es_challenge(self, page: Page) -> bool:
        try:
            titulo = (page.title() or "").lower()
        except Exception:
            return False
        return any(marca in titulo for marca in TITULOS_CLOUDFLARE)

    def _error(self, page: Page) -> str:
        for selector in ("[id$='messageText']", ".sapMMessageToast", ".sapMMsgStripMessage"):
            localizador = page.locator(selector)
            if localizador.count():
                texto = (localizador.first.inner_text() or "").strip()
                if texto:
                    return texto[:200]
        return "credenciales incorrectas o sesión no iniciada"

    def descargar(self, page: Page, ui: PuenteUI, destino: Path) -> list[Path]:
        raise NotImplementedError(
            "Falta mapear la navegación interna de Soriana. "
            "Corré `uv run towel-automate explorar soriana`."
        )
