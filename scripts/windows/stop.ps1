Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
# Stop the scheduler supervisor first so it cannot restart the child during maintenance.
$task = Get-ScheduledTask -TaskName 'GameInventory' -ErrorAction SilentlyContinue
if ($task -and $task.State -eq 'Running') { Stop-ScheduledTask -TaskName 'GameInventory' }
$process = Get-OwnedInventoryProcess
if ($process) {
    Stop-Process -Id $process.Id
    if (-not $process.WaitForExit(15000)) { throw 'Application did not stop within 15 seconds.' }
    Write-Host "Stopped application PID $($process.Id)."
}
Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
