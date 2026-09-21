[CmdletBinding()]
param([Parameter(Mandatory)][string]$DumpFile, [Parameter(Mandatory)][string]$TargetDatabase, [Parameter(Mandatory)][string]$ConfirmTarget)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
Import-InventoryEnvironment
if ($TargetDatabase -ne $ConfirmTarget) { throw 'ConfirmTarget must exactly match TargetDatabase.' }
& (Get-InventoryPython) -m app.operations restore $DumpFile --target $TargetDatabase --confirm $ConfirmTarget
if ($LASTEXITCODE -ne 0) { throw "Restore failed; see application.log (exit $LASTEXITCODE)." }
