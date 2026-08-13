"""Configuración de la app.

Las credenciales de cada portal NO viven en archivos: se guardan en el
Administrador de credenciales de Windows vía keyring, una por usuario/máquina.
El .env solo lleva la configuración compartida (Supabase, rutas).
"""

import os
import sys
from pathlib import Path

import keyring
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ = Path(__file__).resolve().parents[2]
SERVICIO_KEYRING = "towel_automate"

CARPETA_APP = "towell_automate"
CARPETA_PORTALES = "providers"


def dir_escritorio() -> Path:
    """Ruta real del escritorio del usuario.

    No sirve asumir `~/Desktop`: en Windows en español la carpeta se llama
    "Escritorio", y con OneDrive activo el escritorio vive redirigido dentro de
    la carpeta de OneDrive. El registro tiene la ruta verdadera; los fallbacks
    cubren el caso de que la consulta falle.
    """
    if sys.platform == "win32":
        try:
            import winreg

            ruta_registro = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, ruta_registro) as clave:
                valor, _ = winreg.QueryValueEx(clave, "Desktop")
            escritorio = Path(os.path.expandvars(valor))
            if escritorio.is_dir():
                return escritorio
        except Exception:  # noqa: BLE001 - quedan los fallbacks de abajo
            pass

    casa = Path.home()
    candidatos = (
        casa / "Desktop",
        casa / "Escritorio",
        casa / "OneDrive" / "Desktop",
        casa / "OneDrive" / "Escritorio",
    )
    for candidato in candidatos:
        if candidato.is_dir():
            return candidato

    return casa / "Desktop"


def dir_portales_por_defecto() -> Path:
    """<Escritorio>/towell_automate/providers"""
    return dir_escritorio() / CARPETA_APP / CARPETA_PORTALES


class Credenciales(BaseModel):
    usuario: str = ""
    password: str = ""

    @property
    def completas(self) -> bool:
        return bool(self.usuario and self.password)


def guardar_credenciales(portal: str, credenciales: Credenciales) -> None:
    """Persiste en el Administrador de credenciales de Windows."""
    keyring.set_password(SERVICIO_KEYRING, f"{portal}:usuario", credenciales.usuario)
    keyring.set_password(SERVICIO_KEYRING, f"{portal}:password", credenciales.password)


def leer_credenciales(portal: str) -> Credenciales:
    return Credenciales(
        usuario=keyring.get_password(SERVICIO_KEYRING, f"{portal}:usuario") or "",
        password=keyring.get_password(SERVICIO_KEYRING, f"{portal}:password") or "",
    )


def borrar_credenciales(portal: str) -> None:
    for sufijo in ("usuario", "password"):
        try:
            keyring.delete_password(SERVICIO_KEYRING, f"{portal}:{sufijo}")
        except keyring.errors.PasswordDeleteError:
            pass


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=RAIZ / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # La anon key es pública por diseño: la seguridad la da RLS en Supabase.
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_bucket: str = "reportes"

    # Portal interno: la URL no está fija en el código porque puede cambiar de
    # host. No es una credencial, por eso va acá y no en el keyring.
    towell_url: str = ""

    # Raíz de los reportes, en el escritorio para que el usuario los encuentre
    # sin saber dónde está instalada la app. Se puede mover con DIR_DESCARGAS.
    dir_descargas: Path = Field(default_factory=dir_portales_por_defecto)

    # Playwright deja acá los archivos a medio bajar; el definitivo lo escribe
    # save_as() en la carpeta del portal. Va junto al código, no en el escritorio.
    dir_temporal: Path = RAIZ / "downloads"
    dir_perfil_navegador: Path = RAIZ / ".perfil_navegador"

    # Soriana está detrás de Cloudflare: en headless el challenge nunca pasa.
    headless: bool = False
    timeout_ms: int = 45_000
    timeout_humano_ms: int = 300_000


settings = Settings()
