<#
    Instalador de Towell Automate para Windows.

    Deja la máquina lista de una sola pasada: uv, Python, dependencias,
    navegador y un acceso directo en el escritorio. Se puede volver a correr
    cuantas veces haga falta; todo lo que ya está hecho se saltea.

    Uso (clic derecho sobre el archivo > "Ejecutar con PowerShell") o bien:
        powershell -ExecutionPolicy Bypass -File instalar.ps1
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $raiz

function Escribir-Paso($numero, $texto) {
    Write-Host ""
    Write-Host "[$numero/5] $texto" -ForegroundColor Cyan
}

function Escribir-Ok($texto)    { Write-Host "      $texto" -ForegroundColor Green }
function Escribir-Aviso($texto) { Write-Host "      $texto" -ForegroundColor Yellow }

function Buscar-Uv {
    # Recién instalado, uv todavía no está en el PATH de esta sesión.
    $enPath = Get-Command uv -ErrorAction SilentlyContinue
    if ($enPath) { return $enPath.Source }

    foreach ($candidato in @(
        (Join-Path $env:USERPROFILE ".local\bin\uv.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\uv\uv.exe")
    )) {
        if (Test-Path $candidato) { return $candidato }
    }
    return $null
}

function Buscar-Chrome {
    foreach ($candidato in @(
        (Join-Path $env:ProgramFiles "Google\Chrome\Application\chrome.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Google\Chrome\Application\chrome.exe"),
        (Join-Path $env:LOCALAPPDATA "Google\Chrome\Application\chrome.exe")
    )) {
        if ($candidato -and (Test-Path $candidato)) { return $candidato }
    }
    return $null
}

Write-Host ""
Write-Host "=== Instalando Towell Automate ===" -ForegroundColor White
Write-Host "    Carpeta: $raiz" -ForegroundColor DarkGray

# ---------------------------------------------------------------- 1. uv
Escribir-Paso 1 "Buscando uv (gestor de Python)"
$uv = Buscar-Uv
if ($uv) {
    Escribir-Ok "Ya estaba instalado: $uv"
} else {
    Escribir-Aviso "No estaba; descargando desde astral.sh..."
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    $uv = Buscar-Uv
    if (-not $uv) {
        throw "No se pudo instalar uv. Revisá la conexión a internet o instalalo a mano desde https://astral.sh/uv"
    }
    Escribir-Ok "Instalado en $uv"
}

# ------------------------------------------------- 2. Python y dependencias
Escribir-Paso 2 "Instalando Python y las dependencias del proyecto"
Escribir-Aviso "La primera vez puede tardar varios minutos."
& $uv sync
if ($LASTEXITCODE -ne 0) { throw "'uv sync' falló. Revisá el mensaje de arriba." }
Escribir-Ok "Entorno listo"

# ------------------------------------------------------------ 3. Navegador
Escribir-Paso 3 "Verificando el navegador"
$chrome = Buscar-Chrome
if ($chrome) {
    Escribir-Ok "Chrome encontrado: $chrome"
} else {
    Escribir-Aviso "No hay Chrome instalado. Bajando el Chromium de Playwright..."
    & $uv run playwright install chromium
    Escribir-Aviso "Ojo: con Chromium, Soriana puede fallar por Cloudflare."
    Escribir-Aviso "Si vas a usar Soriana, instalá Google Chrome y volvé a correr esto."
}

# ------------------------------------------------------ 4. Configuración
Escribir-Paso 4 "Preparando la configuración local"
$env_local = Join-Path $raiz ".env"
$env_ejemplo = Join-Path $raiz ".env.example"
if (Test-Path $env_local) {
    Escribir-Ok ".env ya existía; no se toca"
} elseif (Test-Path $env_ejemplo) {
    Copy-Item $env_ejemplo $env_local
    Escribir-Ok ".env creado a partir de .env.example"
} else {
    Escribir-Aviso "No hay .env.example; la app usará sus valores por defecto"
}

# --------------------------------------------------------- 5. Acceso directo
Escribir-Paso 5 "Creando el acceso directo en el escritorio"
$lanzador = Join-Path $raiz "towell_automate.bat"
if (-not (Test-Path $lanzador)) {
    throw "Falta towell_automate.bat en $raiz"
}

# GetFolderPath respeta OneDrive y el nombre en español de la carpeta.
$escritorio = [Environment]::GetFolderPath("Desktop")
$acceso = Join-Path $escritorio "Towell Automate.lnk"

# CreateShortcut sobre un .lnk que ya existe no pisa sus propiedades: si quedó
# a medio escribir de un intento anterior, el acceso directo se queda sin
# destino y no abre nada. Se borra primero y se crea de cero.
if (Test-Path $acceso) { Remove-Item $acceso -Force }

$shell = New-Object -ComObject WScript.Shell
$enlace = $shell.CreateShortcut($acceso)
$enlace.TargetPath = $lanzador
$enlace.WorkingDirectory = $raiz
$enlace.Description = "Descarga los reportes de los portales de proveedores"
$enlace.WindowStyle = 7   # minimizada: la ventana útil es la de la app
# Sin IconLocation a propósito: apuntarlo a "C:\Program Files\...\chrome.exe,0"
# deja el .lnk sin TargetPath. El icono lindo no vale un acceso directo muerto.
$enlace.Save()

# Verificación: un .lnk sin destino se ve normal en el escritorio y no hace nada.
# Hay que releerlo con un WScript.Shell nuevo; el mismo objeto devuelve el
# shortcut que tiene en memoria y siempre diría que está bien.
$comprobar = (New-Object -ComObject WScript.Shell).CreateShortcut($acceso)
if (-not $comprobar.TargetPath) {
    throw "El acceso directo se creó vacío. Abrí towell_automate.bat directamente y avisá de este error."
}
Escribir-Ok "Listo: $acceso"

Write-Host ""
Write-Host "=== Instalación terminada ===" -ForegroundColor Green
Write-Host ""
Write-Host "  1. Abrí 'Towell Automate' desde el escritorio." -ForegroundColor White
Write-Host "  2. Tocá el boton de la llave y cargá tus credenciales de cada portal." -ForegroundColor White
Write-Host "     Se guardan en el Administrador de credenciales de Windows, solo en esta máquina." -ForegroundColor DarkGray
Write-Host "  3. Elegí los portales y dale a 'Descargar reportes'." -ForegroundColor White
Write-Host ""
Write-Host "  Los archivos quedan en:" -ForegroundColor White
Write-Host "  $escritorio\towell_automate\providers\<portal>\<fecha>_<area>\" -ForegroundColor DarkGray
Write-Host ""
