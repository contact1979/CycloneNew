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

# Install runtime dependencies
pip install -r requirements.txt

# Install dev tooling
if (Test-Path "./dev-requirements.txt") {
    pip install -r dev-requirements.txt
} else {
    pip install pytest coverage mypy
}

Write-Host "✅ Env ready. Run tests with: python -m pytest -q"
