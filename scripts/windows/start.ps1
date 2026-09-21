[CmdletBinding()]
param([switch]$Foreground)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
Import-InventoryEnvironment
Initialize-InventoryDirectories
Invoke-InventoryLogRotation
$python = Get-InventoryPython
Set-Location $ProjectRoot
& $python -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw "Alembic migration failed with exit code $LASTEXITCODE" }
$hostAddress = if ($env:APP_HOST) { $env:APP_HOST } else { '0.0.0.0' }
$port = if ($env:APP_PORT) { $env:APP_PORT } else { '18081' }
$level = if ($env:LOG_LEVEL) { $env:LOG_LEVEL.ToLowerInvariant() } else { 'info' }
$args = @('-m','uvicorn','app.main:app','--host',$hostAddress,'--port',$port,'--log-level',$level,'--no-access-log')
if ($Foreground) {
    Set-Content -LiteralPath $PidFile -Value $PID -Encoding ASCII
    try { & $python @args 2>&1 | Tee-Object -FilePath (Join-Path $LogDir 'application.log') -Append }
    finally { Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue }
    exit $LASTEXITCODE
}
if (Test-Path $PidFile) { throw "PID file already exists; use health-check.ps1 or stop.ps1: $PidFile" }
$process = Start-Process -FilePath $python -ArgumentList $args -WorkingDirectory $ProjectRoot -RedirectStandardOutput (Join-Path $LogDir 'application.log') -RedirectStandardError (Join-Path $LogDir 'error.log') -PassThru
Set-Content -LiteralPath $PidFile -Value $process.Id -Encoding ASCII
Write-Host "Inventory started (PID $($process.Id), http://${hostAddress}:$port)."
