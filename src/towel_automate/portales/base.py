"""Contrato común de los portales."""

from __future__ import annotations

import base64
import re
import unicodedata
from abc import ABC, abstractmethod
from datetime import date, datetime
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

    #: De dónde sale el reporte, para nombrar la carpeta: "inventarios",
    #: "orden_compra", etc. Un portal con varios reportes lo pasa por descarga.
    area: str = "reportes"

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


def normalizar(texto: str) -> str:
    """Convierte a un fragmento de nombre de carpeta seguro en Windows.

    "Ventas e Inven. Mensuales" -> "ventas_e_inven_mensuales"
    """
    sin_acentos = unicodedata.normalize("NFKD", texto)
    sin_acentos = sin_acentos.encode("ascii", "ignore").decode("ascii")
    limpio = re.sub(r"[^a-zA-Z0-9]+", "_", sin_acentos).strip("_").lower()
    return limpio or "reporte"


def carpeta_descarga(raiz: Path, portal: str, area: str, dia: date | None = None) -> Path:
    """`<raiz>/<portal>/<AAAAMMDD>_<area>/`, creada si no existe.

    Dos corridas del mismo día sobre la misma área comparten carpeta a
    propósito: los archivos se acumulan ahí en vez de dispersarse.
    """
    sello = (dia or date.today()).strftime("%Y%m%d")
    carpeta = raiz / normalizar(portal) / f"{sello}_{normalizar(area)}"
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def _ruta_libre(carpeta: Path, nombre: str) -> Path:
    """Evita pisar un archivo de una corrida anterior del mismo día."""
    ruta = carpeta / nombre
    if not ruta.exists():
        return ruta

    base = Path(nombre)
    sello = datetime.now().strftime("%H%M%S")
    ruta = carpeta / f"{base.stem}_{sello}{base.suffix}"

    contador = 2
    while ruta.exists():
        ruta = carpeta / f"{base.stem}_{sello}_{contador}{base.suffix}"
        contador += 1
    return ruta


def guardar_descarga(
    descarga: Download,
    raiz: Path,
    portal: str,
    area: str,
    prefijo: str = "",
) -> Path:
    """Guarda en `<raiz>/<portal>/<fecha>_<area>/` conservando el nombre original.

    La fecha y el origen ya están en la ruta, así que el archivo no los repite.
    `prefijo` sirve cuando un portal baja varios reportes de la misma área y el
    nombre sugerido no alcanza para distinguirlos.
    """
    carpeta = carpeta_descarga(raiz, portal, area)
    sugerido = Path(descarga.suggested_filename or "reporte").name
    nombre = f"{normalizar(prefijo)}_{sugerido}" if prefijo else sugerido

    ruta = _ruta_libre(carpeta, nombre)
    descarga.save_as(str(ruta))
    return ruta
