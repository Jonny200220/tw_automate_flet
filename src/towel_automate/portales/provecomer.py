"""Provecomer (Grupo La Comer).

El portal migró del JSP viejo a una SPA de Angular Material:
`/provecomer_angular/#/auth/login`. Consecuencias para el bot:

- Los campos se anclan por `formControlName` (`username`, `password`, `captcha`).
  Los `id` que genera Angular Material (`mat-input-0`, `mat-input-1`, ...) se
  numeran por orden de montaje y cambian si la vista se arma distinto: no sirven.
- El submit **no navega**. Angular resuelve por AJAX y solo cambia la ruta del
  hash, así que se espera a que la URL deje de ser `/auth/login` en vez de usar
  `expect_navigation`.
- El captcha sigue llegando como data URI base64, ahora en `img.captcha-image`,
  así que se puede seguir mostrando dentro de la app.

El JSP viejo (`/webPrvd/LoginProvecomerNpSrv`) todavía responde, pero es el que
está quedando atrás.
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from ..config import Credenciales
from ..ui import PuenteUI
from .base import ErrorPortal, Portal, guardar_descarga, png_desde_data_uri

INTENTOS_CAPTCHA = 4
RUTA_LOGIN = "/auth/login"

BASE = "https://www.provecomer.com.mx/provecomer_angular/#"
URL_REPORTE = f"{BASE}/ventas-e-inventarios/sub/ventas-e-inven.-mensuales"

# Cada reporte es una columna de opciones de la misma tabla. Se entra por URL en
# vez de caminar el menú lateral: el acordeón se abre y se cierra con el mismo
# clic, y basta que renombren un ítem para romper la navegación.
COLUMNAS_REPORTE = ("opcUniv", "opcImp", "opcUniv2", "opcImp2")

TIMEOUT_EXPORTACION_MS = 120_000


class Provecomer(Portal):
    clave = "provecomer"
    nombre = "Provecomer"
    url_login = "https://www.provecomer.com.mx/provecomer_angular/#/auth/login"
    requiere_captcha = True
    area = "ventas_inventarios"

    SEL_USUARIO = "input[formcontrolname='username']"
    SEL_PASSWORD = "input[formcontrolname='password']"
    SEL_CAPTCHA_INPUT = "input[formcontrolname='captcha']"
    SEL_CAPTCHA_IMG = "img.captcha-image"
    SEL_REFRESCAR = "button.refresh-btn"
    SEL_ENVIAR = "button[type='submit']"

    def sesion_activa(self, page: Page) -> bool:
        return RUTA_LOGIN not in page.url and page.locator(self.SEL_USUARIO).count() == 0

    def login(self, page: Page, credenciales: Credenciales, ui: PuenteUI) -> None:
        if not credenciales.completas:
            raise ErrorPortal("Faltan credenciales de Provecomer")

        page.goto(self.url_login, wait_until="domcontentloaded")

        # Angular monta el formulario recién después de cargar el bundle.
        try:
            page.wait_for_selector(self.SEL_USUARIO, state="visible", timeout=30_000)
        except PlaywrightTimeoutError as exc:
            if self.sesion_activa(page):
                ui.log("Provecomer ya tenía sesión abierta", "ok")
                return
            raise ErrorPortal("No apareció el formulario de Provecomer") from exc

        for intento in range(1, INTENTOS_CAPTCHA + 1):
            if ui.cancelado():
                raise ErrorPortal("Cancelado por el usuario")

            page.fill(self.SEL_USUARIO, credenciales.usuario)
            page.fill(self.SEL_PASSWORD, credenciales.password)

            src = self._src_captcha(page)
            texto = ui.pedir_captcha(png_desde_data_uri(src), self.nombre, intento)
            if not texto:
                raise ErrorPortal("Captcha cancelado o sin respuesta")

            page.fill(self.SEL_CAPTCHA_INPUT, texto.strip())
            page.click(self.SEL_ENVIAR)

            if self._salio_del_login(page):
                ui.log("Sesión iniciada en Provecomer", "ok")
                return

            motivo = self._mensaje_error(page)
            ui.log(f"Intento {intento} rechazado: {motivo}", "error")

            # Si las credenciales están mal, reintentar el captcha no sirve.
            if "captcha" not in motivo.lower():
                raise ErrorPortal(f"Provecomer rechazó el acceso: {motivo}")

            self._refrescar_captcha(page, src)

        raise ErrorPortal(f"No se pudo pasar el captcha en {INTENTOS_CAPTCHA} intentos")

    def _src_captcha(self, page: Page) -> str:
        try:
            page.wait_for_selector(self.SEL_CAPTCHA_IMG, state="visible", timeout=20_000)
        except PlaywrightTimeoutError as exc:
            raise ErrorPortal("No cargó la imagen del captcha de Provecomer") from exc
        return page.get_attribute(self.SEL_CAPTCHA_IMG, "src") or ""

    def _salio_del_login(self, page: Page) -> bool:
        """La SPA no navega: solo cambia el hash cuando el login sale bien."""
        try:
            page.wait_for_url(lambda url: RUTA_LOGIN not in url, timeout=20_000)
        except PlaywrightTimeoutError:
            return False
        return True

    def _refrescar_captcha(self, page: Page, src_previo: str) -> None:
        """Pide un captcha nuevo y espera a que la imagen cambie de verdad.

        Sin esta espera se le muestra al usuario el captcha viejo y el intento
        siguiente se quema solo.
        """
        if page.locator(self.SEL_REFRESCAR).count():
            page.click(self.SEL_REFRESCAR)

        try:
            page.wait_for_function(
                """([selector, previo]) => {
                    const imagen = document.querySelector(selector);
                    return imagen && imagen.src && imagen.src !== previo;
                }""",
                arg=[self.SEL_CAPTCHA_IMG, src_previo],
                timeout=10_000,
            )
        except PlaywrightTimeoutError:
            page.wait_for_timeout(800)

    def _mensaje_error(self, page: Page) -> str:
        # Angular Material avisa por snackbar; los errores de campo van en mat-error.
        selectores = (
            ".mat-mdc-snack-bar-label",
            ".mdc-snackbar__label",
            "simple-snack-bar",
            "mat-error",
            ".alert",
        )
        for selector in selectores:
            localizador = page.locator(selector)
            if localizador.count():
                texto = (localizador.first.inner_text() or "").strip()
                if texto:
                    return texto[:200]
        return "captcha o credenciales incorrectas"

    # -------------------------------------------------------------- descargar

    def descargar(self, page: Page, ui: PuenteUI, destino: Path) -> list[Path]:
        self._cerrar_aviso(page, ui)

        archivos: list[Path] = []
        total = len(COLUMNAS_REPORTE)

        for indice, columna in enumerate(COLUMNAS_REPORTE, start=1):
            if ui.cancelado():
                raise ErrorPortal("Cancelado por el usuario")

            ui.progreso(indice - 1, total, f"Provecomer: reporte {indice}/{total}")
            archivo = self._descargar_columna(page, ui, destino, columna)
            if archivo:
                archivos.append(archivo)

        self._cerrar_sesion(page, ui)

        if not archivos:
            raise ErrorPortal("Provecomer no devolvió ningún reporte")
        return archivos

    def _cerrar_aviso(self, page: Page, ui: PuenteUI) -> None:
        """Aviso que sale al entrar. A veces no aparece; nunca es fatal."""
        try:
            page.get_by_role("button", name="Cerrar").click(timeout=5_000)
            ui.log("Aviso de bienvenida cerrado", "info")
        except Exception:  # noqa: BLE001 - el aviso es opcional
            pass

    def _descargar_columna(
        self, page: Page, ui: PuenteUI, destino: Path, columna: str
    ) -> Path | None:
        """Abre el reporte de una columna y baja el archivo.

        Cada reporte se pide desde la tabla y deja un overlay abierto, así que
        se vuelve a entrar por URL antes de cada uno en vez de intentar cerrarlo.
        """
        selector = f".cdk-column-{columna} > .mat-mdc-tooltip-trigger"

        try:
            # Por si quedó un overlay del reporte anterior.
            page.keyboard.press("Escape")
            page.goto(URL_REPORTE, wait_until="domcontentloaded")
            page.wait_for_selector(selector, state="visible", timeout=45_000)
        except PlaywrightTimeoutError:
            ui.log(f"No apareció la columna {columna} en la tabla", "error")
            return None

        try:
            page.locator(selector).first.click()
            with page.expect_download(timeout=TIMEOUT_EXPORTACION_MS) as info:
                page.get_by_label("Descargar reporte").click()
        except Exception as exc:  # noqa: BLE001 - los otros reportes siguen
            ui.log(f"Reporte {columna} sin descargar: {exc}", "error")
            return None

        return guardar_descarga(info.value, destino, self.nombre_carpeta, self.area, prefijo=columna)

    def _cerrar_sesion(self, page: Page, ui: PuenteUI) -> None:
        """Best-effort: los archivos ya están, un logout fallido no importa."""
        try:
            page.keyboard.press("Escape")
            page.get_by_label("Profile").click(timeout=5_000)
            page.get_by_role("button", name="Cerrar sesión").click(timeout=5_000)
            ui.log("Sesión de Provecomer cerrada", "info")
        except Exception:  # noqa: BLE001
            pass
