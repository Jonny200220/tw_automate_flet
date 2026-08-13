"""Registro de portales soportados."""

from .base import ErrorPortal, Portal, guardar_descarga
from .heb2b import Heb2b
from .provecomer import Provecomer
from .soriana import Soriana
from .towell import Towell

PORTALES: dict[str, Portal] = {
    p.clave: p for p in (Provecomer(), Heb2b(), Soriana(), Towell())
}

__all__ = ["PORTALES", "ErrorPortal", "Portal", "guardar_descarga"]
