[CmdletBinding()]
param([switch]$Uninstall)
# Uses the built-in Task Scheduler: no NSSM/WinSW binary or download is required.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
$taskName = 'GameInventory'
if ($Uninstall) { & (Join-Path $PSScriptRoot 'stop.ps1'); Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue; Write-Host 'Startup task removed.'; exit 0 }
$scriptPath = Join-Path $PSScriptRoot 'start.ps1'
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -Foreground" -WorkingDirectory $ProjectRoot
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Game Inventory FastAPI server' -Force | Out-Null
Write-Host "Installed task $taskName. Start with: Start-ScheduledTask -TaskName $taskName"
