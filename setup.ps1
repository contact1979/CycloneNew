# MIT License
# Setup script for HydroBot on Windows 11
param(
    [string]$Python = "python"
)

# Create venv if missing
if (!(Test-Path "./venv")) {
    & $Python -m venv venv
}

.\venv\Scripts\activate

# Install all dependencies with Poetry, including dev tools
poetry install --with dev

Write-Host "✅ Env ready. Run tests with: poetry run pytest -q"
