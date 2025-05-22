param(
    [string]$Python = 'python',
    [switch]$Check
)

if (!(Test-Path 'venv')) {
    & $Python -m venv venv
}

.\venv\Scripts\Activate

pip install -r requirements.txt
if (Test-Path 'dev-requirements.txt') {
    pip install -r dev-requirements.txt
}

if ($Check) {
    $env:PYTHONUNBUFFERED = '1'
    $log = Join-Path $PSScriptRoot 'setup.log'

    Write-Host 'Running black...'
    black --check --quiet hydrobot tests *> $log
    if ($LASTEXITCODE -ne 0) {
        Get-Content $log -Tail 20
        throw 'black failed'
    }

    Write-Host 'Running flake8...'
    flake8 hydrobot tests *> $log
    if ($LASTEXITCODE -ne 0) {
        Get-Content $log -Tail 20
        throw 'flake8 failed'
    }

    Write-Host 'Running pytest...'
    pytest -q *> $log
    if ($LASTEXITCODE -ne 0) {
        Get-Content $log -Tail 20
        throw 'pytest failed'
    }

    Remove-Item $log -ErrorAction Ignore
}

Write-Host 'Environment ready.'
Write-Host 'Run tests with: python -m pytest -q'
