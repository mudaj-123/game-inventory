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
    @{ id = $process.Id; started = $process.StartTime.ToUniversalTime().Ticks.ToString(); path = $process.Path } | ConvertTo-Json | Set-Content -LiteralPath $PidFile -Encoding UTF8
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
