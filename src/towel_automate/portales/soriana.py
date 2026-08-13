"""Soriana - Portal de socios comerciales.

Tres particularidades frente a los otros portales:

1. Está detrás de Cloudflare. En headless devuelve "Attention Required!" y nunca
   deja pasar; por eso la app corre con Chrome real y ventana visible.
2. Es una SPA de SAP UI5. Los IDs llevan un prefijo generado
   (`sap.f.FlexibleColumnLayoutWithOneColumnStart---logon--logon_user-inner`)
   que cambia según cómo se monte la vista. Donde se puede anclamos por rol y
   texto accesible; donde no, con `[id$=...]` sobre el sufijo estable.
3. Después del login aparecen diálogos de bienvenida (avisos, encuestas) que no
   siempre están. Se cierran best-effort antes de tocar el tablero.

El flujo de descarga viene de un scraper ya probado contra este mismo portal:
tablero -> rango de fechas -> "Exportar detalle" por fila -> "Exportar" general.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Iterator

from playwright.sync_api import Locator, Page

from ..config import Credenciales, settings
from ..ui import PuenteUI
from .base import ErrorPortal, Portal, guardar_descarga

TITULOS_CLOUDFLARE = ("attention required", "just a moment", "un momento")

MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)

# Diálogos post-login: pueden o no aparecer, nunca son fatales.
BOTONES_DIALOGO = ("Leído", "Terminar", "Sí")

# Generar el reporte del lado del servidor tarda más que un click normal.
TIMEOUT_EXPORTACION_MS = 120_000

# El tablero UI5 tarda ~40s+ en montar el rango de fechas y poblar la tabla.
TIMEOUT_FILTROS_MS = 90_000

MSG_ESPERANDO = "Esperando a que la plataforma responda..."
INTERVALO_AVISO_S = 8


class Soriana(Portal):
    clave = "soriana"
    nombre = "Soriana"
    url_login = "https://socios.soriana.com/index/index.html"
    area = "pedidos"

    # Rango de fechas del tablero. En None: del día 1 del mes actual a hoy.
    # Se puede sobreescribir en caliente: PORTALES["soriana"].dia_fin = "15"
    dia_inicio: str | None = None
    dia_fin: str | None = None

    # Fallback por ID del formulario de login; el rol accesible es lo primario.
    SEL_USUARIO = "input[id$='logon_user-inner']"
    SEL_PASSWORD = "input[id$='logon_pass-inner']"

    # El tablero es un item de lista sin rol útil. El ID completo salió del
    # codegen y el sufijo es el plan B si UI5 cambia el prefijo del contenedor.
    SEL_TABLERO = '[id="__hbox0-__clone0-__list0-__clone0-0"]'
    SEL_TABLERO_SUFIJO = "[id$='-__list0-__clone0-0']"

    # ------------------------------------------------------------------ login

    def _campo_usuario(self, page: Page) -> Locator:
        return page.get_by_role("textbox", name="Correo")

    def _campo_password(self, page: Page) -> Locator:
        return page.get_by_role("textbox", name="Contraseña")

    def sesion_activa(self, page: Page) -> bool:
        return (
            self._campo_usuario(page).count() == 0
            and page.locator(self.SEL_USUARIO).count() == 0
        )

    def login(self, page: Page, credenciales: Credenciales, ui: PuenteUI) -> None:
        if not credenciales.completas:
            raise ErrorPortal("Faltan credenciales de Soriana")

        page.goto(self.url_login, wait_until="domcontentloaded")
        self._esperar_cloudflare(page, ui)

        usuario = self._campo_usuario(page)
        password = self._campo_password(page)

        # UI5 monta los campos por JS, no vienen en el HTML inicial.
        try:
            usuario.first.wait_for(state="visible", timeout=settings.timeout_ms)
        except Exception:
            # Plan B por ID antes de darla por perdida: el portal cambia los
            # textos accesibles más seguido que los sufijos de ID.
            if page.locator(self.SEL_USUARIO).count():
                usuario = page.locator(self.SEL_USUARIO)
                password = page.locator(self.SEL_PASSWORD)
            elif self.sesion_activa(page):
                ui.log("Soriana ya tenía sesión abierta", "ok")
                self._cerrar_dialogos(page, ui)
                return
            else:
                raise ErrorPortal("No apareció el formulario de Soriana") from None

        usuario.first.fill(credenciales.usuario)
        password.first.fill(credenciales.password)
        page.get_by_role("button", name="Entrar").click()

        try:
            password.first.wait_for(state="detached", timeout=40_000)
        except Exception as exc:
            raise ErrorPortal(f"Soriana rechazó el acceso: {self._error(page)}") from exc

        ui.log("Sesión iniciada en Soriana", "ok")
        self._cerrar_dialogos(page, ui)

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

    def _cerrar_dialogos(self, page: Page, ui: PuenteUI) -> None:
        """Avisos y encuestas post-login. Aparecen a veces; nunca son fatales."""
        for nombre in BOTONES_DIALOGO:
            try:
                page.get_by_role("button", name=nombre).click(timeout=5_000)
                ui.log(f"Diálogo '{nombre}' cerrado", "info")
            except Exception:  # noqa: BLE001 - el diálogo es opcional
                continue

    # -------------------------------------------------------------- descargar

    def descargar(self, page: Page, ui: PuenteUI, destino: Path) -> list[Path]:
        self._abrir_tablero(page, ui)
        self._elegir_rango(page, ui)

        archivos = self._exportar_detalles(page, ui, destino)
        archivos.extend(self._exportar_general(page, ui, destino))

        self._cerrar_sesion(page, ui)

        if not archivos:
            raise ErrorPortal(
                "Soriana no devolvió archivos en el rango pedido. "
                "Revisá las fechas o si hay pedidos en ese periodo."
            )
        return archivos

    def _abrir_tablero(self, page: Page, ui: PuenteUI) -> None:
        for selector in (self.SEL_TABLERO, self.SEL_TABLERO_SUFIJO):
            localizador = page.locator(selector)
            if localizador.count():
                localizador.first.click()
                ui.log("Tablero abierto", "info")
                try:
                    with self._mientras_espera(ui):
                        page.get_by_label("Abrir selector").first.wait_for(
                            state="visible", timeout=TIMEOUT_FILTROS_MS
                        )
                except Exception as exc:
                    raise ErrorPortal(
                        "El tablero abrió pero los filtros no aparecieron a tiempo"
                    ) from exc
                ui.log("Filtros listos", "ok")
                return
        raise ErrorPortal(
            "No se encontró el tablero de pedidos. Los IDs de UI5 cambiaron: "
            "volvé a capturar el flujo con `uv run towel-automate explorar soriana`."
        )

    def _rango(self) -> tuple[str, str, str]:
        """(mes ancla, día inicio, día fin). Por defecto: del 1 del mes a hoy."""
        hoy = date.today()
        ancla = f"1 de {MESES[hoy.month - 1]} de {hoy.year}"
        return ancla, self.dia_inicio or "1", self.dia_fin or str(hoy.day)

    def _elegir_rango(self, page: Page, ui: PuenteUI) -> None:
        ancla, inicio, fin = self._rango()
        ui.log(f"Rango: {inicio} al {fin} de {ancla.split(' de ', 1)[1]}", "info")

        try:
            page.get_by_label("Abrir selector").first.click(timeout=TIMEOUT_FILTROS_MS)
            mes = page.get_by_label(ancla, exact=True)
            mes.get_by_text(inicio, exact=True).first.click()
            page.get_by_text(fin, exact=True).first.click()
            page.get_by_role("button", name="Ir").first.click()
        except Exception as exc:
            raise ErrorPortal(f"No se pudo fijar el rango de fechas: {exc}") from exc

        filas = page.get_by_role("row").filter(has=page.get_by_label("Exportar detalle"))
        try:
            with self._mientras_espera(ui):
                filas.first.wait_for(state="visible", timeout=TIMEOUT_FILTROS_MS)
            ui.log("Resultados del rango listos", "ok")
        except Exception:  # noqa: BLE001 - un rango vacío es válido
            pass

    def _exportar_detalles(self, page: Page, ui: PuenteUI, destino: Path) -> list[Path]:
        """Un archivo por fila con botón 'Exportar detalle'.

        Las filas se resuelven por rol, no por número de pedido: cambian en cada
        corrida y una lista fija dejaría reportes sin bajar.
        """
        archivos: list[Path] = []
        filas = page.get_by_role("row").filter(has=page.get_by_label("Exportar detalle"))
        total = filas.count()

        if not total:
            ui.log("Sin filas para exportar detalle en este rango", "info")
            return archivos

        for indice in range(total):
            if ui.cancelado():
                raise ErrorPortal("Cancelado por el usuario")

            ui.progreso(indice, total + 1, MSG_ESPERANDO)
            ui.log(f"Exportando detalle {indice + 1}/{total}", "info")
            fila = filas.nth(indice)
            try:
                with self._mientras_espera(ui):
                    with page.expect_download(timeout=TIMEOUT_EXPORTACION_MS) as info:
                        fila.get_by_label("Exportar detalle").first.click()
                archivos.append(
                    guardar_descarga(
                        info.value, destino, self.clave, self.area,
                        prefijo=f"detalle_{indice + 1}",
                    )
                )
            except Exception as exc:  # noqa: BLE001 - una fila no tumba a las demás
                ui.log(f"Fila {indice + 1} sin exportar: {exc}", "error")

        return archivos

    def _exportar_general(self, page: Page, ui: PuenteUI, destino: Path) -> list[Path]:
        ui.log("Exportando reporte general", "info")
        try:
            with self._mientras_espera(ui):
                with page.expect_download(timeout=TIMEOUT_EXPORTACION_MS) as info:
                    page.get_by_role("button", name="Exportar", exact=True).first.click()
            return [
                guardar_descarga(info.value, destino, self.clave, self.area, prefijo="general")
            ]
        except Exception as exc:  # noqa: BLE001 - los detalles ya se bajaron
            ui.log(f"Reporte general sin exportar: {exc}", "error")
            return []

    @contextmanager
    def _mientras_espera(self, ui: PuenteUI) -> Iterator[None]:
        """Repite el aviso cada 8 s para que la bitácora no se quede muda."""
        parar = threading.Event()

        def latir() -> None:
            while not parar.wait(INTERVALO_AVISO_S):
                ui.log(MSG_ESPERANDO, "info")
                ui.progreso(0, 0, MSG_ESPERANDO)

        ui.log(MSG_ESPERANDO, "info")
        ui.progreso(0, 0, MSG_ESPERANDO)
        hilo = threading.Thread(target=latir, daemon=True)
        hilo.start()
        try:
            yield
        finally:
            parar.set()

    def _cerrar_sesion(self, page: Page, ui: PuenteUI) -> None:
        """Best-effort: las descargas ya están, un logout fallido no importa."""
        try:
            page.get_by_role("button", name="Usuario").click(timeout=5_000)
            page.get_by_role("button", name="Cerrar sesión").click(timeout=5_000)
            ui.log("Sesión de Soriana cerrada", "info")
        except Exception:  # noqa: BLE001
            pass
