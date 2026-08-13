@echo off
rem Lanzador de Towell Automate. Sin acentos a proposito: cmd.exe los rompe
rem segun la pagina de codigos de cada maquina.

cd /d "%~dp0"

set "UV=uv"
where uv >nul 2>&1
if errorlevel 1 set "UV=%USERPROFILE%\.local\bin\uv.exe"

if not exist "%UV%" if "%UV%" neq "uv" (
    echo.
    echo No se encontro uv. Ejecuta primero instalar.ps1
    echo.
    pause
    exit /b 1
)

"%UV%" run towel-automate
if errorlevel 1 (
    echo.
    echo La aplicacion termino con un error. El detalle esta arriba.
    echo.
    pause
)
