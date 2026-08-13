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

**Dónde caen los archivos.** La app corre en máquinas ajenas, así que los reportes van al
escritorio, no junto al código:

```
<Escritorio>/towell_automate/providers/<portal>/<AAAAMMDD>_<area>/<archivos>
```

`carpeta_descarga()` (`portales/base.py`) crea lo que falte y reusa lo que exista; dos
corridas del mismo día sobre la misma área comparten carpeta, y `_ruta_libre()` evita que
la segunda pise a la primera. El escritorio se resuelve por registro de Windows, no con
`~/Desktop`: en Windows en español es "Escritorio" y con OneDrive está redirigido.

`dir_temporal` (`downloads/`, junto al código) es otra cosa: ahí Playwright deja el
archivo a medio bajar antes de que `save_as()` escriba el definitivo.

Cada portal declara `area` (de dónde sale el reporte) y, si difiere de `clave`, `carpeta`.
`clave` no se puede cambiar a la ligera: también indexa el keyring, y renombrarla dejaría
a todos sin sus credenciales guardadas.

## Portales

Cada uno hereda de `Portal` (`portales/base.py`) e implementa `login()` y `descargar()`.

| Portal | Stack | Particularidad |
|---|---|---|
| Provecomer | SPA de Angular Material | Captcha de texto: la imagen llega como data URI base64 en `img.captcha-image`, por eso se renderiza dentro de la app. Campos por `formControlName`, nunca por los `mat-input-N` que numera Angular. El submit no navega: se espera a que la ruta deje de ser `/auth/login` |
| HEB Business | ASP.NET MVC + Power BI | Sin captcha en login. El reporte vive en un iframe (`#embedContainer iframe`) y se exporta por `data-testid` de Power BI |
| Soriana | SPA de SAP UI5 | Cloudflare + IDs con prefijo generado: anclar por rol accesible, o con `[id$=...]` cuando no hay rol |
| Towell | Odoo interno | La URL sale de `TOWELL_URL` en el `.env` (cambia de host); el usuario es un número de empleado en un `spinbutton` |

**Selectores: rol accesible primero, ID como fallback.** Los flujos de HEB, Soriana y
Towell se portaron de scrapers ya probados contra esos portales, que resuelven todo con
`get_by_role` / `get_by_label`. Los selectores por ID salieron del DOM pero nunca pasaron
un login real: quedan como plan B, no como opción principal.

**Nada de listas fijas de filas ni fechas hardcodeadas.** Los scrapers originales traían
números de pedido y un mes clavados del codegen. Acá las filas se descubren por rol
(`row` que contenga "Exportar detalle") y las fechas se calculan de la fecha del sistema,
con override en caliente: `PORTALES["soriana"].dia_fin = "15"`.

En Provecomer, si el error de login **no** menciona captcha, cortar de inmediato en vez
de gastar reintentos contra credenciales incorrectas.

## Estado

Los cuatro portales tienen `login()` y `descargar()` implementados. **Solo el login de
Provecomer está confirmado contra el portal real**; el resto no se probó de punta a punta
con credenciales.

En Provecomer, los cuatro reportes son columnas de la misma tabla
(`.cdk-column-opcUniv`, `opcImp`, `opcUniv2`, `opcImp2`) y se entra por URL directa a
`#/ventas-e-inventarios/sub/ventas-e-inven.-mensuales`, no caminando el menú lateral: el
acordeón se abre y se cierra con el mismo clic. Cada reporte deja un overlay abierto, por
eso se vuelve a entrar por URL antes del siguiente.

Para mapear un portal que cambie, grabar con codegen y pasarme el archivo:

```bash
uv run playwright codegen --channel=chrome --target python \
  --test-id-attribute formcontrolname -o downloads/codegen_<portal>.py "<url>"
```

El `--test-id-attribute formcontrolname` importa en los portales Angular: sin eso codegen
ancla a los `mat-input-N`, que se renumeran. Ese archivo queda con las credenciales en
texto plano; `downloads/` y `codegen_*.py` están en `.gitignore` justamente por eso.

Pendientes: parseo de xlsx/xls/txt y carga a Supabase (con hash SHA-256 por archivo para
no duplicar reportes entre corridas).

## Flet 0.86

La API cambió respecto a versiones anteriores; lo que aparece en la mayoría de ejemplos
viejos ya no existe:

- `ft.run(main)`, no `ft.app(...)`
- `page.show_dialog(dlg)` / `page.pop_dialog()`, no `page.open()` / `page.close()`
- `ft.Border.all(...)`, no `ft.border.all(...)`
- `ft.Image(src=<bytes>)`, no `src_base64=`
- `ft.Button`, `ft.Colors`, `ft.Icons`, `ft.BoxFit` (no `ft.ImageFit`)

Ante la duda, consultar context7 (`/websites/flet_dev`) en vez de asumir la API vieja.
