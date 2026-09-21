Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'stop.ps1')
$task = Get-ScheduledTask -TaskName 'GameInventory' -ErrorAction SilentlyContinue
if ($task) { Start-ScheduledTask -TaskName 'GameInventory' }
else { & (Join-Path $PSScriptRoot 'start.ps1') }
