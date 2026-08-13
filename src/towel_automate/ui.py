"""Puente entre el worker de automatización y la interfaz.

La automatización corre en un hilo aparte (Playwright es síncrono y bloquea) y
nunca importa Flet: solo habla contra este protocolo. Eso permite correr los
mismos portales desde la GUI o desde consola.

`pedir_captcha` es intencionalmente bloqueante: el worker se detiene ahí hasta
que un humano lee el captcha, y sigue solo cuando hay respuesta.
"""

from __future__ import annotations

import threading
from typing import Protocol


class PuenteUI(Protocol):
    """Lo que un portal puede pedirle a la interfaz."""

    def log(self, mensaje: str, nivel: str = "info") -> None: ...
    def progreso(self, actual: int, total: int, etiqueta: str = "") -> None: ...
    def pedir_captcha(self, png: bytes, portal: str, intento: int = 1) -> str | None: ...
    def cancelado(self) -> bool: ...


class Cancelacion:
    """Bandera compartida para abortar una corrida en curso."""

    def __init__(self) -> None:
        self._evento = threading.Event()

    def pedir(self) -> None:
        self._evento.set()

    def reiniciar(self) -> None:
        self._evento.clear()

    def activa(self) -> bool:
        return self._evento.is_set()


class PuenteConsola:
    """Implementación sin GUI, útil para pruebas y para el modo explorar."""

    def __init__(self, cancelacion: Cancelacion | None = None) -> None:
        self.cancelacion = cancelacion or Cancelacion()

    def log(self, mensaje: str, nivel: str = "info") -> None:
        marca = {"ok": "[ok]", "error": "[!!]"}.get(nivel, "[..]")
        print(f"{marca} {mensaje}")

    def progreso(self, actual: int, total: int, etiqueta: str = "") -> None:
        if total:
            print(f"     {actual}/{total} {etiqueta}".rstrip())
        elif etiqueta:
            print(f"     {etiqueta}")

    def pedir_captcha(self, png: bytes, portal: str, intento: int = 1) -> str | None:
        ruta = f"captcha_{portal.lower()}.png"
        with open(ruta, "wb") as archivo:
            archivo.write(png)
        print(f"\nCaptcha de {portal} guardado en {ruta} (intento {intento})")
        return input("Escribí el captcha: ").strip() or None

    def cancelado(self) -> bool:
        return self.cancelacion.activa()
