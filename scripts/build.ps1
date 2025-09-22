# C:\Users\gcave\Desktop\ColectorAW\scripts\build.ps1

$Root    = Split-Path -Parent (Split-Path -Parent $PSCommandPath)  # ...\ColectorAW
$SrcDir  = Join-Path $Root "src"
$AppPy   = Join-Path $Root "src\awcollector\app.py"
$IconIco = Join-Path $Root "assets\Genika.ico"
$Assets  = Join-Path $Root "assets"  # carpeta assets

# Activa venv si existe
$Activate = Join-Path $Root ".venv\Scripts\Activate.ps1"
if (Test-Path $Activate) { & $Activate }

# Limpia restos
Remove-Item -Recurse -Force (Join-Path $Root "build"), (Join-Path $Root "dist") -ErrorAction SilentlyContinue

# Construir argumentos
$Args = @(
  "--noconfirm",
  "--onefile",
  "--windowed",
  "--name=ColectorAW",
  "--paths=""$SrcDir""",
  "--hidden-import=PIL._tkinter_finder"
)

# Icono si existe
if (Test-Path $IconIco) {
  $Args += "--icon=""$IconIco"""
}

# Empacar assets (usar '=' y ';' en Windows)
if (Test-Path $Assets) {
  $Args += "--add-data=""$Assets;assets"""
}

# Script de entrada
$Args += "`"$AppPy`""

pyinstaller @Args

Write-Host "Listo -> $(Join-Path $Root 'dist\ColectorAW.exe')"
