# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Qué es

App de escritorio que descarga reportes (xlsx/xls/txt) de tres portales de proveedores
mexicanos, para después cargarlos a Supabase y consumirlos desde una PWA aparte
(Vite + React, fuera de este repo). La usan 5-10 personas, ~10-15 archivos por corrida.

El código, los comentarios y los identificadores están en español. Mantener esa convención.

## Comandos

```bash
uv sync                              # instalar dependencias
uv run towel-automate                # abrir la app (GUI Flet)
uv run towel-automate explorar <portal>   # modo grabación: provecomer | heb2b | soriana
uv run playwright install chromium   # solo si no hay Chrome del sistema
```

No hay suite de tests ni linter configurados todavía.

Para probar el flujo de descarga sin GUI (`PuenteConsola` pide el captcha por stdin):

```bash
uv run python -c "
from towel_automate.runner import ejecutar
from towel_automate.ui import PuenteConsola
print(ejecutar(['heb2b'], PuenteConsola()))
"
```

## Restricciones del navegador (no cambiar sin releer esto)

`navegador.py` toma dos decisiones que parecen mejorables y no lo son:

- **`headless=False`.** Soriana está detrás de Cloudflare; en headless devuelve
  `Attention Required!` y el challenge nunca pasa.
- **`channel="chrome"`** (Chrome instalado, no el Chromium de Playwright). El Chromium
  de prueba dispara la detección de Cloudflare mucho más seguido. Hay fallback a
  Chromium, pero con él Soriana puede fallar.

El perfil persistente (`.perfil_navegador/`) es lo que hace esto tolerable: conserva la
cookie `cf_clearance` y las sesiones, así el challenge y los logins se piden pocas veces.

## Arquitectura

**Frontera worker ↔ interfaz.** Playwright es síncrono y bloquea, así que corre en un
hilo lanzado con `page.run_thread()`. Ese hilo **nunca importa Flet ni construye widgets**:
habla solo contra el protocolo `PuenteUI` (`ui.py`), que tiene dos implementaciones —
`PuenteFlet` (en `gui.py`, muta controles ya creados y llama `page.update()`) y
`PuenteConsola` (para pruebas y modo explorar). Al agregar interacción nueva con el
usuario, extender el protocolo, no importar Flet dentro de `portales/`.

**`pedir_captcha()` es bloqueante a propósito.** El worker se detiene en un
`threading.Event` hasta que un humano lee el captcha, y sigue solo cuando hay respuesta
(timeout 300 s). Es el único punto donde la automatización espera a una persona.

**Aislamiento de fallas.** `runner.ejecutar()` abre el navegador una vez y recorre los
portales elegidos; un portal que falla se registra en su `ResultadoPortal` y la corrida
continúa con los demás.

**Credenciales.** Van al Administrador de credenciales de Windows vía `keyring`
(`config.py`), nunca a archivos — son 5-10 personas con credenciales distintas. El `.env`
solo lleva config compartida de Supabase, con `anon key` + RLS (nunca `service_role`).

## Portales

Cada uno hereda de `Portal` (`portales/base.py`) e implementa `login()` y `descargar()`.
Los selectores actuales se extrajeron del DOM real, pero **los logins no están probados
con credenciales**.

| Portal | Stack | Particularidad |
|---|---|---|
| Provecomer | Java/JSP legacy | Captcha de texto; la imagen llega como data URI base64 en `#captchaImage`, por eso se renderiza dentro de la app en vez de obligar a mirar el navegador |
| HEB Business | ASP.NET MVC | Sin captcha en login (el reCAPTCHA del HTML es del form de recuperar contraseña) |
| Soriana | SPA de SAP UI5 | Cloudflare + IDs con prefijo generado: anclar con `[id$='logon_user-inner']`, nunca con el ID completo |

En Provecomer, si el error de login **no** menciona captcha, cortar de inmediato en vez
de gastar reintentos contra credenciales incorrectas.

## Estado: `descargar()` sin implementar

Los tres portales lanzan `NotImplementedError` en `descargar()`. El árbol de reportes solo
existe con sesión iniciada, así que **no se puede programar a ciegas**. El flujo previsto es
correr `explorar <portal>`, navegar a mano hasta los reportes y descargarlos; eso deja un
`descargas/mapa_<portal>_*.json` con las URLs visitadas y las descargas hechas, y de ahí se
escribe la navegación real.

Pendientes después de eso: parseo de xlsx/xls/txt y carga a Supabase (con hash SHA-256 por
archivo para no duplicar reportes entre corridas).

## Flet 0.86

La API cambió respecto a versiones anteriores; lo que aparece en la mayoría de ejemplos
viejos ya no existe:

- `ft.run(main)`, no `ft.app(...)`
- `page.show_dialog(dlg)` / `page.pop_dialog()`, no `page.open()` / `page.close()`
- `ft.Border.all(...)`, no `ft.border.all(...)`
- `ft.Image(src=<bytes>)`, no `src_base64=`
- `ft.Button`, `ft.Colors`, `ft.Icons`, `ft.BoxFit` (no `ft.ImageFit`)

Ante la duda, consultar context7 (`/websites/flet_dev`) en vez de asumir la API vieja.
