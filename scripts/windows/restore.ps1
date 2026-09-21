[CmdletBinding()]
param([Parameter(Mandatory)][string]$DumpFile, [Parameter(Mandatory)][string]$TargetDatabase, [Parameter(Mandatory)][string]$ConfirmTarget)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
Import-InventoryEnvironment
if ($TargetDatabase -ne $ConfirmTarget) { throw 'ConfirmTarget must exactly match TargetDatabase.' }
if (-not (Test-Path -LiteralPath $DumpFile)) { throw "Backup not found: $DumpFile" }
if (-not $env:POSTGRES_BIN) { throw 'POSTGRES_BIN must point to the PostgreSQL bin directory.' }
& (Join-Path $env:POSTGRES_BIN 'pg_restore.exe') --list $DumpFile | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Backup validation failed.' }
& (Join-Path $env:POSTGRES_BIN 'pg_restore.exe') --clean --if-exists --no-owner --exit-on-error --host=$env:PGHOST --port=$env:PGPORT --username=$env:PGUSER --dbname=$TargetDatabase --no-password $DumpFile
if ($LASTEXITCODE -ne 0) { throw 'pg_restore failed.' }
$oldDatabase = $env:PGDATABASE; $env:PGDATABASE = $TargetDatabase
try {
    $url = $env:DATABASE_URL
    if (-not $url) { throw 'DATABASE_URL is required to run Alembic after restore.' }
    $queryIndex = $url.IndexOf('?')
    $urlWithoutQuery = if ($queryIndex -ge 0) { $url.Substring(0, $queryIndex) } else { $url }
    $query = if ($queryIndex -ge 0) { $url.Substring($queryIndex) } else { '' }
    $databaseSeparator = $urlWithoutQuery.LastIndexOf('/')
    if ($databaseSeparator -lt $urlWithoutQuery.IndexOf('://') + 3) { throw 'DATABASE_URL has no database path.' }
    $env:DATABASE_URL = $urlWithoutQuery.Substring(0, $databaseSeparator + 1) + $TargetDatabase + $query
    & (Get-InventoryPython) -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Alembic upgrade failed after restore.' }
} finally { $env:PGDATABASE = $oldDatabase; $env:DATABASE_URL = $url }
$validationSql = @'
SELECT 'users' AS table_name, count(*) AS row_count FROM users
UNION ALL SELECT 'products', count(*) FROM products
UNION ALL SELECT 'catalog_entries', count(*) FROM catalog_entries
UNION ALL SELECT 'inventory_transactions', count(*) FROM inventory_transactions;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM products WHERE quantity < 0) THEN
    RAISE EXCEPTION 'negative product inventory found';
  END IF;
  IF EXISTS (SELECT barcode FROM products GROUP BY barcode HAVING count(*) > 1) THEN
    RAISE EXCEPTION 'duplicate product barcode found';
  END IF;
  IF EXISTS (
    SELECT 1 FROM inventory_transactions reversal
    LEFT JOIN inventory_transactions original ON original.id = reversal.related_transaction_id
    WHERE reversal.operation_type = 'REVERSAL' AND original.id IS NULL
  ) THEN
    RAISE EXCEPTION 'orphan reversal found';
  END IF;
END $$;
'@
& (Join-Path $env:POSTGRES_BIN 'psql.exe') --host=$env:PGHOST --port=$env:PGPORT --username=$env:PGUSER --dbname=$TargetDatabase --no-password --set=ON_ERROR_STOP=1 --command=$validationSql
if ($LASTEXITCODE -ne 0) { throw 'Post-restore integrity validation failed.' }
Write-Host "Restore, migration, row counts, and integrity checks complete for: $TargetDatabase"
