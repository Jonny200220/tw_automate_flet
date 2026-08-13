"""Interfaz de escritorio (Flet).

El worker de Playwright corre en un hilo aparte vía page.run_thread() para que
la ventana no se congele. El hilo no construye widgets: solo muta controles ya
creados y llama page.update().
"""

from __future__ import annotations

import threading
from datetime import datetime

import flet as ft

from .config import (
    Credenciales,
    borrar_credenciales,
    guardar_credenciales,
    leer_credenciales,
    settings,
)
from .portales import PORTALES
from .runner import ejecutar
from .ui import Cancelacion

COLOR_NIVEL = {"ok": ft.Colors.GREEN, "error": ft.Colors.RED, "info": ft.Colors.ON_SURFACE}


class PuenteFlet:
    """Implementa PuenteUI actualizando la ventana desde el hilo del worker."""

    def __init__(self, page: ft.Page, bitacora: ft.ListView, barra: ft.ProgressBar,
                 etiqueta: ft.Text, cancelacion: Cancelacion) -> None:
        self.page = page
        self.bitacora = bitacora
        self.barra = barra
        self.etiqueta = etiqueta
        self.cancelacion = cancelacion

    def log(self, mensaje: str, nivel: str = "info") -> None:
        hora = datetime.now().strftime("%H:%M:%S")
        self.bitacora.controls.append(
            ft.Text(f"{hora}  {mensaje}", size=12, color=COLOR_NIVEL.get(nivel),
                    selectable=True, font_family="Consolas")
        )
        self.page.update()

    def progreso(self, actual: int, total: int, etiqueta: str = "") -> None:
        self.barra.value = (actual / total) if total else 0
        self.etiqueta.value = etiqueta
        self.page.update()

    def pedir_captcha(self, png: bytes, portal: str, intento: int = 1) -> str | None:
        listo = threading.Event()
        respuesta: dict[str, str | None] = {"texto": None}

        campo = ft.TextField(label="Escribí el captcha", autofocus=True, width=260)

        def aceptar(_: ft.Event | None = None) -> None:
            respuesta["texto"] = (campo.value or "").strip()
            self.page.pop_dialog()
            self.page.update()
            listo.set()

        def cancelar(_: ft.Event) -> None:
            respuesta["texto"] = None
            self.page.pop_dialog()
            self.page.update()
            listo.set()

        campo.on_submit = aceptar

        aviso = "" if intento == 1 else f"  (intento {intento})"
        dialogo = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Captcha de {portal}{aviso}"),
            content=ft.Column(
                controls=[
                    ft.Image(src=png, width=260, height=80, fit=ft.BoxFit.CONTAIN),
                    campo,
                ],
                tight=True, spacing=14,
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=cancelar),
                ft.Button("Continuar", on_click=aceptar),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self.page.show_dialog(dialogo)
        self.page.update()

        if not listo.wait(timeout=300):
            return None
        return respuesta["texto"]

    def cancelado(self) -> bool:
        return self.cancelacion.activa()


def main(page: ft.Page) -> None:
    page.title = "Towel Automate"
    page.window.width = 760
    page.window.height = 680
    page.padding = 18

    cancelacion = Cancelacion()

    casillas = {
        clave: ft.Checkbox(label=portal.nombre, value=True)
        for clave, portal in PORTALES.items()
    }
    bitacora = ft.ListView(expand=True, spacing=2, auto_scroll=True, padding=10)
    barra = ft.ProgressBar(value=0)
    etiqueta = ft.Text("Listo para empezar", size=12, italic=True)
    puente = PuenteFlet(page, bitacora, barra, etiqueta, cancelacion)

    boton_descargar = ft.Button("Descargar reportes", icon=ft.Icons.DOWNLOAD)
    boton_cancelar = ft.OutlinedButton("Cancelar", icon=ft.Icons.STOP, disabled=True)

    def trabajo(claves: list[str]) -> None:
        try:
            resultados = ejecutar(claves, puente)
            exitosos = sum(1 for r in resultados if r.ok)
            total = sum(len(r.archivos) for r in resultados)
            puente.log(
                f"Fin: {exitosos}/{len(resultados)} portales, {total} archivos",
                "ok" if exitosos == len(resultados) else "error",
            )
        except Exception as exc:  # noqa: BLE001 - el hilo no debe morir en silencio
            puente.log(f"Error inesperado: {exc}", "error")
        finally:
            boton_descargar.disabled = False
            boton_cancelar.disabled = True
            page.update()

    def iniciar(_: ft.Event) -> None:
        claves = [c for c, casilla in casillas.items() if casilla.value]
        if not claves:
            puente.log("Elegí al menos un portal", "error")
            return
        cancelacion.reiniciar()
        bitacora.controls.clear()
        boton_descargar.disabled = True
        boton_cancelar.disabled = False
        page.update()
        page.run_thread(trabajo, claves)

    def cancelar(_: ft.Event) -> None:
        cancelacion.pedir()
        puente.log("Cancelando al terminar el paso actual...", "error")

    boton_descargar.on_click = iniciar
    boton_cancelar.on_click = cancelar

    def abrir_credenciales(_: ft.Event) -> None:
        campos: dict[str, tuple[ft.TextField, ft.TextField]] = {}
        filas: list[ft.Control] = []

        for clave, portal in PORTALES.items():
            actuales = leer_credenciales(clave)
            usuario = ft.TextField(label="Usuario", value=actuales.usuario, width=200, dense=True)
            password = ft.TextField(
                label="Contraseña", value=actuales.password, width=200,
                password=True, can_reveal_password=True, dense=True,
            )
            campos[clave] = (usuario, password)
            filas.append(
                ft.Column(
                    controls=[ft.Text(portal.nombre, weight=ft.FontWeight.BOLD),
                              ft.Row(controls=[usuario, password])],
                    spacing=6,
                )
            )

        def guardar(_: ft.Event) -> None:
            for clave, (usuario, password) in campos.items():
                if usuario.value or password.value:
                    guardar_credenciales(
                        clave, Credenciales(usuario=usuario.value or "",
                                            password=password.value or "")
                    )
                else:
                    borrar_credenciales(clave)
            page.pop_dialog()
            page.update()
            puente.log("Credenciales guardadas en el Administrador de Windows", "ok")

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Credenciales de los portales"),
                content=ft.Column(controls=filas, tight=True, spacing=18, scroll=ft.ScrollMode.AUTO),
                actions=[
                    ft.TextButton("Cerrar", on_click=lambda _: (page.pop_dialog(), page.update())),
                    ft.Button("Guardar", on_click=guardar),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
        )
        page.update()

    page.add(
        ft.Row(
            controls=[
                ft.Text("Towel Automate", size=22, weight=ft.FontWeight.BOLD),
                ft.IconButton(icon=ft.Icons.KEY, tooltip="Credenciales",
                              on_click=abrir_credenciales),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        ),
        ft.Text(f"Los archivos se guardan en {settings.dir_descargas}", size=11, italic=True),
        ft.Divider(),
        ft.Text("Portales", weight=ft.FontWeight.BOLD),
        ft.Row(controls=list(casillas.values()), wrap=True),
        ft.Row(controls=[boton_descargar, boton_cancelar]),
        barra,
        etiqueta,
        ft.Container(
            content=bitacora,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=8,
            expand=True,
        ),
    )


def lanzar() -> None:
    ft.run(main)
