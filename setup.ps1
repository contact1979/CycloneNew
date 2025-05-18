# MIT License
# Setup script for HydroBot on Windows 11
param(
    [string]$Python = "python"
)

Write-Host "[HydroBot] Setting up virtual environment..."
if (-Not (Test-Path '.venv')) {
    & $Python -m venv .venv
}

& .\venv\Scripts\pip.exe install --upgrade pip
& .\venv\Scripts\pip.exe install -r requirements.txt

if (-Not (Test-Path '.env')) {
    Copy-Item '.env.example' '.env'
    Write-Host 'Created default .env from .env.example'
}

Write-Host 'Setup complete. Activate with `./venv/Scripts/Activate.ps1`.'
