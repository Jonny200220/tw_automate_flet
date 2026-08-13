# Instalar Towell Automate en una computadora nueva

## Lo que hace falta antes

- Windows 10 u 11.
- Google Chrome instalado. No es opcional para Soriana: ese portal está detrás de
  Cloudflare y con el navegador de prueba de Playwright suele rechazar el acceso.
- Conexión a internet la primera vez.

No hace falta tener Python: el instalador lo baja solo.

## Instalación

1. Copiá la carpeta del proyecto completa a la computadora (por ejemplo a
   `C:\towell_automate`). Da igual dónde, mientras el usuario pueda escribir ahí.
2. Clic derecho sobre **`instalar.ps1`** > **Ejecutar con PowerShell**.

Si Windows bloquea el script, abrí PowerShell en esa carpeta y corré:

```powershell
powershell -ExecutionPolicy Bypass -File instalar.ps1
```

El instalador deja todo listo en cinco pasos: baja `uv`, instala Python y las
dependencias, revisa el navegador, prepara el `.env` y crea el acceso directo
**Towell Automate** en el escritorio.

Se puede volver a correr cuando haga falta (por ejemplo después de actualizar el
código): lo que ya está hecho se saltea y el `.env` existente no se toca.

## Primer uso

1. Abrí **Towell Automate** desde el escritorio.
2. Tocá el botón de la llave y cargá usuario y contraseña de cada portal.

   Las credenciales van al **Administrador de credenciales de Windows**, no a un
   archivo. Son de esa computadora y de esa cuenta de Windows: cada persona carga
   las suyas y no viajan con el proyecto.

3. Marcá los portales que necesitás y dale a **Descargar reportes**.

Provecomer pide el captcha en una ventana dentro de la app. Soriana abre Chrome a
la vista porque a veces hay que resolver el desafío de Cloudflare a mano; el resto
del tiempo se resuelve solo.

## Dónde quedan los archivos

```
Escritorio\towell_automate\providers\<portal>\<AAAAMMDD>_<área>\
```

Por ejemplo: `...\providers\heb\20260813_inventarios\`.

Las carpetas se crean solas. Si volvés a correr el mismo día, los archivos se
suman a la carpeta de ese día en vez de reemplazarla; si un nombre se repite, al
nuevo se le agrega la hora.

Para guardarlos en otro lado, poné la ruta en `DIR_DESCARGAS` dentro del `.env`.

## Si algo falla

**"No se encontró uv"** al abrir el acceso directo — corré `instalar.ps1` otra vez.

**La ventana se cierra sola** — abrí `towell_automate.bat` con doble clic: al fallar
deja la consola abierta con el error.

**Soriana se queda en "Cloudflare está validando el navegador"** — resolvé el
desafío en la ventana de Chrome. Una vez resuelto queda recordado un buen rato,
porque el perfil del navegador se conserva entre corridas.

**Un portal falla y el resto sigue** — es a propósito. La bitácora de la app dice
cuál falló y por qué, y los demás terminan igual.
