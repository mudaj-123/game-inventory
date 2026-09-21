[CmdletBinding()]
param([string]$Url)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
Import-InventoryEnvironment
if (-not $Url) { $port = if ($env:APP_PORT) { $env:APP_PORT } else { '18081' }; $Url = "http://127.0.0.1:$port/health" }
$response = Invoke-RestMethod -Uri $Url -TimeoutSec 10
if ($response.status -ne 'ok') { throw "Unhealthy response from $Url" }
Write-Host "Healthy: application and database at $Url"
