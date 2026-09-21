[CmdletBinding()]
param([string]$Python = 'py', [switch]$SkipChecks)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
Set-Location $ProjectRoot
if (-not (Test-Path '.env')) { Copy-Item '.env.windows.example' '.env'; Write-Warning 'Edit .env before production startup.' }
if ($Python -eq 'py') { & py -3.12 -m venv .venv } else { & $Python -m venv .venv }
if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 virtual environment creation failed.' }
$venvPython = Get-InventoryPython
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }
& $venvPython -m pip install -e '.[dev]'
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
if (-not $SkipChecks) {
    & $venvPython -m pytest
    if ($LASTEXITCODE -ne 0) { throw 'pytest failed.' }
    & $venvPython -m ruff check .
    if ($LASTEXITCODE -ne 0) { throw 'Ruff failed.' }
}
Write-Host 'Setup complete. Configure .env, then run scripts/windows/start.ps1.'
