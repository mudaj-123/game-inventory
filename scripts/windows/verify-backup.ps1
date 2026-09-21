[CmdletBinding()]
param([Parameter(Mandatory)][string]$DumpFile)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
Import-InventoryEnvironment
& (Get-InventoryPython) -m app.operations drill $DumpFile
if ($LASTEXITCODE -ne 0) { throw "Isolated restore drill failed; see application.log (exit $LASTEXITCODE)." }
