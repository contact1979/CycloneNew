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
if (Get-Command poetry -ErrorAction SilentlyContinue) {
    poetry install --with dev
} else {
    # Fallback if Poetry isn't available
    pip install -r requirements.txt
    pip install -r dev-requirements.txt
}

Write-Host "✅ Env ready. Run tests with: python -m pytest -q"
