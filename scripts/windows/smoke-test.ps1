# CI-only process lifecycle check. Never run against a store .env or database.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location $root
if (Test-Path '.env') { throw 'Smoke test requires a disposable checkout with no .env.' }
@'
APP_ENV=test
APP_HOST=127.0.0.1
APP_PORT=18089
DATABASE_URL=sqlite+aiosqlite:///./windows-smoke.db
LOG_DIR=./logs
'@ | Set-Content '.env' -Encoding ASCII
try {
    & (Join-Path $PSScriptRoot 'start.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'Startup smoke failed.' }
    & (Join-Path $PSScriptRoot 'health-check.ps1')
    & (Join-Path $PSScriptRoot 'stop.ps1')
    $stillRunning = $false
    try { Invoke-RestMethod 'http://127.0.0.1:18089/health' -TimeoutSec 2 | Out-Null; $stillRunning = $true } catch { }
    if ($stillRunning) { throw 'Application child survived stop.ps1.' }
    & (Join-Path $PSScriptRoot 'start.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'Second startup smoke failed.' }
    & (Join-Path $PSScriptRoot 'stop.ps1')
    Write-Host 'Windows native start, health, process-tree stop and second startup passed (test SQLite only).'
} finally {
    & (Join-Path $PSScriptRoot 'stop.ps1')
    Remove-Item '.env' -Force -ErrorAction SilentlyContinue
}
