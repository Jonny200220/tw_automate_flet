"""Modo exploración: graba el camino hasta los reportes.

El interior de los portales solo se ve con sesión iniciada, así que no se puede
programar a ciegas. Este modo abre el navegador, deja navegar a mano y registra
cada URL visitada y cada archivo descargado. Con esa bitácora se escribe después
el método `descargar()` de cada portal.

Uso:
    uv run towel-automate explorar provecomer
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .config import settings
from .navegador import contexto_navegador, pagina_limpia
from .portales import PORTALES


def explorar(clave: str) -> Path:
    portal = PORTALES.get(clave)
    if portal is None:
        opciones = ", ".join(PORTALES)
        raise SystemExit(f"Portal desconocido: {clave}. Opciones: {opciones}")

    bitacora: dict[str, list] = {"urls": [], "descargas": []}

    print(f"\n=== Explorando {portal.nombre} ===")
    print("1. Iniciá sesión a mano en la ventana que se abre.")
    print("2. Navegá hasta los reportes y descargá los que usás normalmente.")
    print("3. Cerrá el navegador cuando termines.\n")

    with contexto_navegador() as contexto:
        page = pagina_limpia(contexto)

        def registrar_navegacion(frame) -> None:
            if frame.parent_frame is not None:
                return
            url = frame.url
            if url and url != "about:blank" and url not in bitacora["urls"]:
                bitacora["urls"].append(url)
                print(f"  [url] {url}")

        def registrar_descarga(descarga) -> None:
            destino = settings.dir_descargas / f"explorar_{descarga.suggested_filename}"
            descarga.save_as(str(destino))
            bitacora["descargas"].append(
                {"archivo": descarga.suggested_filename,
                 "url": descarga.url,
                 "pagina": page.url}
            )
            print(f"  [descarga] {descarga.suggested_filename}  <- {page.url}")

        page.on("framenavigated", registrar_navegacion)
        page.on("download", registrar_descarga)
        contexto.on("page", lambda p: (p.on("framenavigated", registrar_navegacion),
                                       p.on("download", registrar_descarga)))

        page.goto(portal.url_login, wait_until="domcontentloaded")

        try:
            # El contexto vive hasta que el usuario cierre la ventana.
            page.wait_for_event("close", timeout=0)
        except Exception:
            pass

    sello = datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = settings.dir_descargas / f"mapa_{clave}_{sello}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(bitacora, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nMapa guardado en: {destino}")
    print(f"  {len(bitacora['urls'])} URLs, {len(bitacora['descargas'])} descargas")
    return destino
