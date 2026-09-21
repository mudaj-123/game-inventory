Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$script:RuntimeDir = Join-Path $ProjectRoot 'runtime'
$script:LogDir = Join-Path $ProjectRoot 'logs'
$script:PidFile = Join-Path $RuntimeDir 'inventory.pid'

function Import-InventoryEnvironment {
    param([string]$Path = (Join-Path $ProjectRoot '.env'))
    if (-not (Test-Path -LiteralPath $Path)) { throw "Environment file not found: $Path" }
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        if ($line -match '^\s*(#|$)') { continue }
        $parts = $line -split '=', 2
        if ($parts.Count -ne 2) { throw "Invalid environment line: $line" }
        [Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1], 'Process')
    }
}

function Get-InventoryPython {
    $python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) { throw "Virtual environment missing: $python" }
    return $python
}

function Initialize-InventoryDirectories {
    New-Item -ItemType Directory -Force -Path $RuntimeDir, $LogDir | Out-Null
}

function Invoke-InventoryLogRotation {
    param([long]$MaximumBytes = 10MB, [int]$Keep = 5)
    foreach ($name in @('application.log', 'error.log')) {
        $path = Join-Path $LogDir $name
        if (-not (Test-Path $path) -or (Get-Item $path).Length -lt $MaximumBytes) { continue }
        Remove-Item "$path.$Keep" -Force -ErrorAction SilentlyContinue
        for ($index = $Keep - 1; $index -ge 1; $index--) {
            if (Test-Path "$path.$index") { Move-Item "$path.$index" "$path.$($index + 1)" -Force }
        }
        Move-Item $path "$path.1" -Force
    }
}
