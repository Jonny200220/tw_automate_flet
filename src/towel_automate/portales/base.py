"""Contrato común de los portales."""

from __future__ import annotations

import base64
import re
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Download, Page

from ..config import Credenciales
from ..ui import PuenteUI

EXTENSIONES_VALIDAS = {".xlsx", ".xls", ".csv", ".txt", ".zip", ".pdf"}


class ErrorPortal(RuntimeError):
    """Falla esperable de un portal (login rechazado, reporte ausente, etc.)."""


class Portal(ABC):
    clave: str
    nombre: str
    url_login: str
    requiere_captcha: bool = False

    @abstractmethod
    def login(self, page: Page, credenciales: Credenciales, ui: PuenteUI) -> None:
        """Deja la sesión abierta o lanza ErrorPortal."""

    @abstractmethod
    def descargar(self, page: Page, ui: PuenteUI, destino: Path) -> list[Path]:
        """Descarga los reportes del portal ya autenticado."""

    def sesion_activa(self, page: Page) -> bool:
        """Heurística para saltarse el login si el perfil ya trae sesión."""
        return False


def png_desde_data_uri(data_uri: str) -> bytes:
    """Convierte el src del captcha (data:image/png;base64,...) en bytes."""
    coincidencia = re.match(r"data:image/\w+;base64,(.+)", data_uri, re.DOTALL)
    if not coincidencia:
        raise ErrorPortal("El captcha no vino como data URI base64")
    return base64.b64decode(coincidencia.group(1))


def guardar_descarga(descarga: Download, destino: Path, prefijo: str) -> Path:
    """Guarda con nombre trazable: portal + fecha + nombre original."""
    destino.mkdir(parents=True, exist_ok=True)
    sugerido = Path(descarga.suggested_filename or "reporte")
    sello = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre = f"{prefijo}_{sello}_{sugerido.name}"
    ruta = destino / nombre
    descarga.save_as(str(ruta))
    return ruta
