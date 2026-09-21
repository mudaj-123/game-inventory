Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
Import-InventoryEnvironment
# Stop the scheduler supervisor first so it cannot restart the child during maintenance.
$task = Get-ScheduledTask -TaskName 'GameInventory' -ErrorAction SilentlyContinue
if ($task -and $task.State -eq 'Running') { Stop-ScheduledTask -TaskName 'GameInventory' }
$process = Get-OwnedInventoryProcess
if ($process) {
    # Venv redirectors can have a child interpreter: terminate the verified process tree.
    & taskkill.exe /PID $process.Id /T /F | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Stopping the verified application process tree failed.' }
    if (-not $process.WaitForExit(15000)) { throw 'Application did not stop within 15 seconds.' }
    Write-Host "Stopped application PID $($process.Id)."
    Add-Content -LiteralPath (Join-Path $LogDir 'application.log') -Value "$(Get-Date -Format o) INFO Operator stopped application process tree."
}
Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
