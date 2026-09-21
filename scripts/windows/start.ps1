[CmdletBinding()]
param([switch]$Foreground)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
Import-InventoryEnvironment
Initialize-InventoryDirectories
$lockPath = Join-Path $RuntimeDir 'startup.lock'
$startupLock = $null
try {
    $startupLock = [IO.File]::Open($lockPath, 'OpenOrCreate', 'ReadWrite', 'None')
    if (Get-OwnedInventoryProcess) { throw 'Inventory is already running. Use health-check.ps1 or restart.ps1.' }
    $python = Get-InventoryPython
    # app.runner waits for PostgreSQL, runs alembic upgrade head, then uvicorn using APP_HOST/APP_PORT.
    $process = Start-Process -FilePath $python -ArgumentList @('-m', 'app.runner') -WorkingDirectory $ProjectRoot -PassThru
    # Start-Process can return before the executable path is available. Re-query using the
    # same API as stop.ps1, and do not persist a partially initialized Process object.
    $launchedId = $process.Id
    for ($identityAttempt = 0; $identityAttempt -lt 20; $identityAttempt++) {
        $identity = Get-Process -Id $launchedId -ErrorAction Stop
        if ($identity.Path) { break }
        Start-Sleep -Milliseconds 100
    }
    if (-not $identity.Path) { throw 'Started process identity was unavailable; inspect Task Manager.' }
    @{ id = $process.Id; started = $identity.StartTime.ToUniversalTime().Ticks.ToString(); path = $identity.Path } | ConvertTo-Json | Set-Content -LiteralPath $PidFile -Encoding UTF8
} finally { if ($startupLock) { $startupLock.Dispose() } }
if ($Foreground) {
    try { $process.WaitForExit(); $code = $process.ExitCode }
    finally {
        if (Test-Path $PidFile) {
            $record = Get-Content $PidFile -Raw | ConvertFrom-Json
            if ($record.id -eq $process.Id) { Remove-Item $PidFile -Force }
        }
    }
    exit $code
}
$port = if ($env:APP_PORT) { $env:APP_PORT } else { '18081' }
$hostAddress = if ($env:APP_HOST -and $env:APP_HOST -ne '0.0.0.0') { $env:APP_HOST } else { '127.0.0.1' }
for ($attempt = 0; $attempt -lt 90; $attempt++) {
    $process.Refresh()
    if ($process.HasExited) { throw "Startup failed. See $LogDir\application.log" }
    try {
        $health = Invoke-RestMethod -Uri "http://${hostAddress}:$port/health" -TimeoutSec 2
        if ($health.status -eq 'ok') { Write-Host "Inventory and database healthy (PID $($process.Id))."; exit 0 }
    } catch { }
    Start-Sleep -Seconds 2
}
throw "Startup health timeout. Inspect $LogDir\application.log and stop.ps1 before retrying."
