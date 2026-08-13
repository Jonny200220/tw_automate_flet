"""Orquestador: abre el navegador una vez y recorre los portales elegidos."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .config import leer_credenciales, settings
from .navegador import contexto_navegador, pagina_limpia
from .portales import PORTALES, ErrorPortal
from .ui import PuenteUI


@dataclass(slots=True)
class ResultadoPortal:
    portal: str
    archivos: list[Path] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def ejecutar(claves: list[str], ui: PuenteUI, destino: Path | None = None) -> list[ResultadoPortal]:
    """Corre la descarga de cada portal. Un portal caído no tumba a los demás."""
    carpeta = destino or settings.dir_descargas
    resultados: list[ResultadoPortal] = []

    with contexto_navegador(carpeta) as contexto:
        page = pagina_limpia(contexto)

        for indice, clave in enumerate(claves, start=1):
            if ui.cancelado():
                ui.log("Corrida cancelada", "error")
                break

            portal = PORTALES.get(clave)
            if portal is None:
                resultados.append(ResultadoPortal(clave, error="Portal desconocido"))
                continue

            ui.progreso(indice - 1, len(claves), portal.nombre)
            ui.log(f"--- {portal.nombre} ---")

            try:
                credenciales = leer_credenciales(clave)
                if not credenciales.completas:
                    raise ErrorPortal("Sin credenciales guardadas. Configuralas en la app.")

                portal.login(page, credenciales, ui)
                archivos = portal.descargar(page, ui, carpeta)

                for archivo in archivos:
                    ui.log(f"Descargado: {archivo.name}", "ok")
                resultados.append(ResultadoPortal(clave, archivos=archivos))

            except NotImplementedError as exc:
                ui.log(str(exc), "error")
                resultados.append(ResultadoPortal(clave, error=str(exc)))
            except ErrorPortal as exc:
                ui.log(f"{portal.nombre}: {exc}", "error")
                resultados.append(ResultadoPortal(clave, error=str(exc)))
            except Exception as exc:  # noqa: BLE001 - un portal no debe tumbar la corrida
                ui.log(f"{portal.nombre}: error inesperado: {exc}", "error")
                resultados.append(ResultadoPortal(clave, error=repr(exc)))

        ui.progreso(len(claves), len(claves), "Listo")

    return resultados
