"""Towel Automate: descarga reportes de portales de proveedores."""

import sys


def main() -> None:
    argumentos = sys.argv[1:]

    if argumentos and argumentos[0] == "explorar":
        from .explorar import explorar

        if len(argumentos) < 2:
            from .portales import PORTALES

            raise SystemExit(f"Uso: towel-automate explorar <{'|'.join(PORTALES)}>")
        explorar(argumentos[1])
        return

    from .gui import lanzar

    lanzar()
