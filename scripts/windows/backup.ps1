[CmdletBinding()]
param([string]$OutputDirectory, [int]$RetentionDays = 30)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
Import-InventoryEnvironment
if (-not $OutputDirectory) { $OutputDirectory = $env:BACKUP_DIR }
if (-not $OutputDirectory) { throw 'Set BACKUP_DIR or pass -OutputDirectory.' }
if (-not $PSBoundParameters.ContainsKey('RetentionDays') -and $env:BACKUP_RETENTION_DAYS) { $RetentionDays = [int]$env:BACKUP_RETENTION_DAYS }
& (Get-InventoryPython) -m app.operations backup --directory $OutputDirectory --retention-days $RetentionDays
if ($LASTEXITCODE -ne 0) { throw "Backup failed; see application.log (exit $LASTEXITCODE)." }
