# Instala mercadona-mcp y lo registra en Claude Desktop.
# Ejecutar en PowerShell:  cd C:\ruta\a\MCP_Mercadona ; .\install.ps1

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

Write-Host "[1/3] Instalando dependencias..."
python -m pip install -e $root --quiet

Write-Host "[2/3] Registrando servidor en Claude Desktop (merge seguro via Python)..."
python (Join-Path $root "register.py")

Write-Host "[3/3] Smoke test contra la API real..."
Set-Location $root
python smoke_test.py 28001

Write-Host ""
Write-Host "Listo. Reinicia Claude Desktop para cargar el servidor 'mercadona'."
Write-Host "Para login/carrito, anade MERCADONA_EMAIL y MERCADONA_PASSWORD al bloque env de la config."
