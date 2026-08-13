"""Arranque del navegador para la automatización.

Dos decisiones que no son negociables y conviene no "optimizar" después:

1. headless=False. Soriana está detrás de Cloudflare y en modo headless el
   challenge nunca se resuelve (devuelve "Attention Required!").
2. channel="chrome" (el Chrome instalado, no el Chromium de Playwright). El
   Chromium de prueba dispara la detección de Cloudflare mucho más seguido.

El perfil persistente es lo que hace todo esto tolerable: conserva la cookie
cf_clearance y las sesiones, así que el challenge y los logins se piden pocas
veces en vez de en cada corrida.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import BrowserContext, sync_playwright

from .config import settings


@contextmanager
def contexto_navegador(dir_temporal: Path | None = None) -> Iterator[BrowserContext]:
    # Playwright solo escribe acá el archivo a medio bajar. El definitivo lo
    # coloca save_as() en la carpeta del portal, en el escritorio.
    temporal = dir_temporal or settings.dir_temporal
    temporal.mkdir(parents=True, exist_ok=True)
    settings.dir_perfil_navegador.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        argumentos = {
            "user_data_dir": str(settings.dir_perfil_navegador),
            "headless": settings.headless,
            "accept_downloads": True,
            "downloads_path": str(temporal),
            "viewport": {"width": 1366, "height": 900},
            "locale": "es-MX",
        }
        try:
            contexto = p.chromium.launch_persistent_context(channel="chrome", **argumentos)
        except Exception:
            # Sin Chrome instalado caemos al Chromium de Playwright; Soriana
            # puede fallar aquí, los otros dos portales funcionan igual.
            contexto = p.chromium.launch_persistent_context(**argumentos)

        contexto.set_default_timeout(settings.timeout_ms)
        try:
            yield contexto
        finally:
            contexto.close()


def pagina_limpia(contexto: BrowserContext):
    """Devuelve una pestaña utilizable, reusando la que abre el perfil."""
    return contexto.pages[0] if contexto.pages else contexto.new_page()
