param([string]$Python='python')

if (!(Test-Path 'venv')) {
    & $Python -m venv venv
}

.\venv\Scripts\Activate

pip install -r requirements.txt
pip install -r dev-requirements.txt

Write-Host 'Environment ready.'
