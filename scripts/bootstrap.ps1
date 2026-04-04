$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPath = Join-Path $projectRoot ".venv"

if (-not (Test-Path $venvPath)) {
    python -m venv $venvPath
}

$pythonExe = Join-Path $venvPath "Scripts\\python.exe"

& $pythonExe -m pip install --upgrade pip
& $pythonExe -m pip install -r (Join-Path $projectRoot "requirements-dev.lock")
& $pythonExe -m pip install -e $projectRoot

Write-Host "Bootstrap complete. Activate with: $venvPath\\Scripts\\Activate.ps1"
