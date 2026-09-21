Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
if (-not (Test-Path $PidFile)) { Write-Host 'Inventory is not running (no PID file).'; exit 0 }
$processId = [int](Get-Content $PidFile -Raw)
$process = Get-Process -Id $processId -ErrorAction SilentlyContinue
if ($process) { Stop-Process -Id $processId; $process.WaitForExit(15000) | Out-Null; Write-Host "Stopped PID $processId." }
Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
