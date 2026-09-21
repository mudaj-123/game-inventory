[CmdletBinding()]
param([string]$OutputDirectory, [int]$RetentionDays)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
Import-InventoryEnvironment
if (-not $OutputDirectory) { $OutputDirectory = $env:BACKUP_DIR }
if (-not $OutputDirectory) { throw 'Set BACKUP_DIR or pass -OutputDirectory (the store HDD is recommended).' }
if (-not $RetentionDays) { $RetentionDays = if ($env:BACKUP_RETENTION_DAYS) { [int]$env:BACKUP_RETENTION_DAYS } else { 30 } }
if ($RetentionDays -lt 1) { throw 'RetentionDays must be at least 1.' }
$pgBin = $env:POSTGRES_BIN
if (-not $pgBin) { throw 'POSTGRES_BIN must point to the PostgreSQL bin directory.' }
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$final = Join-Path $OutputDirectory "inventory_$stamp.dump"
$temp = "$final.tmp"
try {
    & (Join-Path $pgBin 'pg_dump.exe') --format=custom --file=$temp --host=$env:PGHOST --port=$env:PGPORT --username=$env:PGUSER --dbname=$env:PGDATABASE --no-password
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $temp) -or (Get-Item $temp).Length -eq 0) { throw 'pg_dump failed or produced an empty file.' }
    & (Join-Path $pgBin 'pg_restore.exe') --list $temp | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'pg_restore could not read the new backup.' }
    Move-Item -LiteralPath $temp -Destination $final
    Get-ChildItem $OutputDirectory -Filter 'inventory_*.dump' | Where-Object LastWriteTimeUtc -lt (Get-Date).ToUniversalTime().AddDays(-$RetentionDays) | Remove-Item -Force
    Write-Host "Backup complete: $final"
} finally { Remove-Item $temp -Force -ErrorAction SilentlyContinue }
