"""Configuración de la app.

Las credenciales de cada portal NO viven en archivos: se guardan en el
Administrador de credenciales de Windows vía keyring, una por usuario/máquina.
El .env solo lleva la configuración compartida (Supabase, rutas).
"""

from pathlib import Path

import keyring
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ = Path(__file__).resolve().parents[2]
SERVICIO_KEYRING = "towel_automate"


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

    dir_descargas: Path = RAIZ / "descargas"
    dir_perfil_navegador: Path = RAIZ / ".perfil_navegador"

    # Soriana está detrás de Cloudflare: en headless el challenge nunca pasa.
    headless: bool = False
    timeout_ms: int = 45_000
    timeout_humano_ms: int = 300_000


settings = Settings()
