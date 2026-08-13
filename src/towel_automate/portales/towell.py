"""Towell - Portal interno de proveedores (Odoo).

A diferencia de los otros tres, la URL no está fija en el código: es un portal
interno que puede cambiar de host, así que sale de `TOWELL_URL` en el .env. El
usuario es un número de empleado, y el campo es un `spinbutton` (input numérico),
no un textbox.

El reporte se filtra por una sola fecha y deja dos archivos: Excel y PDF.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from ..config import Credenciales, settings
from ..ui import PuenteUI
from .base import ErrorPortal, Portal, guardar_descarga, normalizar

TIMEOUT_EXPORTACION_MS = 120_000


class Towell(Portal):
    clave = "towell"
    nombre = "Towell"

    # Menú y fecha del reporte. Se sobreescriben en caliente:
    # PORTALES["towell"].fecha = "2026-08-01"
    seccion = "Tejido Tejido"
    reporte = "Cortes de Eficiencia Cortes"
    fecha: str | None = None  # None = hoy

    @property
    def url_login(self) -> str:  # type: ignore[override]
        return settings.towell_url

    @property
    def area(self) -> str:  # type: ignore[override]
        # Sigue al reporte elegido: si se cambia arriba, la carpeta acompaña.
        return normalizar(self.reporte)

    def _campo_usuario(self, page: Page):
        # Número de empleado: input numérico, no textbox.
        return page.get_by_role("spinbutton", name="Número de Empleado")

    def sesion_activa(self, page: Page) -> bool:
        return self._campo_usuario(page).count() == 0

    def login(self, page: Page, credenciales: Credenciales, ui: PuenteUI) -> None:
        if not self.url_login:
            raise ErrorPortal(
                "Falta TOWELL_URL en el .env. Es la URL del portal interno, "
                "no una credencial: va en el archivo, no en el keyring."
            )
        if not credenciales.completas:
            raise ErrorPortal("Faltan credenciales de Towell")

        page.goto(self.url_login, wait_until="domcontentloaded")

        if self.sesion_activa(page):
            ui.log("Towell ya tenía sesión abierta", "ok")
            return

        self._campo_usuario(page).fill(credenciales.usuario)
        page.get_by_role("textbox", name="Contraseña").fill(credenciales.password)
        page.get_by_role("button", name="Iniciar Sesión").click()

        try:
            self._campo_usuario(page).wait_for(state="detached", timeout=30_000)
        except Exception as exc:
            raise ErrorPortal(f"Towell rechazó el acceso: {self._error(page)}") from exc

        ui.log(f"Sesión iniciada en Towell (empleado {credenciales.usuario})", "ok")

    def _error(self, page: Page) -> str:
        for selector in (".alert", ".o_notification_content", ".text-danger"):
            localizador = page.locator(selector)
            if localizador.count():
                texto = (localizador.first.inner_text() or "").strip()
                if texto:
                    return texto[:200]
        return "credenciales incorrectas o portal sin responder"

    # -------------------------------------------------------------- descargar

    def descargar(self, page: Page, ui: PuenteUI, destino: Path) -> list[Path]:
        self._abrir_reporte(page, ui)

        archivos: list[Path] = []
        # Excel y PDF son del mismo reporte: si falla uno, el otro sigue sirviendo.
        for etiqueta, boton in (("Excel", "Exportar Excel"), ("PDF", "Descargar PDF")):
            if ui.cancelado():
                raise ErrorPortal("Cancelado por el usuario")
            archivo = self._exportar(page, ui, destino, etiqueta, boton)
            if archivo:
                archivos.append(archivo)

        if not archivos:
            raise ErrorPortal("Towell no devolvió archivos para esa fecha")
        return archivos

    def _abrir_reporte(self, page: Page, ui: PuenteUI) -> None:
        fecha = self.fecha or date.today().isoformat()
        ui.log(f"Navegando a {self.seccion} > {self.reporte} (fecha {fecha})", "info")

        try:
            page.get_by_role("link", name=self.seccion).first.click()
            page.get_by_role("link", name=self.reporte).first.click()
            page.get_by_role("button", name="Fechas").click()
            page.get_by_role("textbox", name="Fecha").fill(fecha)
            page.get_by_text("Visualizar").first.click()
        except PlaywrightTimeoutError as exc:
            raise ErrorPortal(
                f"No se pudo abrir {self.seccion} > {self.reporte} en Towell"
            ) from exc

    def _exportar(
        self, page: Page, ui: PuenteUI, destino: Path, etiqueta: str, boton: str
    ) -> Path | None:
        ui.log(f"Descargando {etiqueta}", "info")
        try:
            with page.expect_download(timeout=TIMEOUT_EXPORTACION_MS) as info:
                page.get_by_role("button", name=boton).click()
            return guardar_descarga(info.value, destino, self.clave, self.area)
        except Exception as exc:  # noqa: BLE001 - el otro formato puede salir bien
            ui.log(f"{etiqueta} sin descargar: {exc}", "error")
            return None
