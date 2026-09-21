Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script:ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$script:RuntimeDir = Join-Path $ProjectRoot 'runtime'
$script:LogDir = Join-Path $ProjectRoot 'logs'
$script:PidFile = Join-Path $RuntimeDir 'inventory.pid'

function Import-InventoryEnvironment {
    param([string]$Path = (Join-Path $ProjectRoot '.env'))
    if (-not (Test-Path -LiteralPath $Path)) { throw 'Environment file is missing. Run setup.ps1 and configure .env.' }
    $lineNumber = 0
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $lineNumber++
        if ($line -match '^\s*(#|$)') { continue }
        if ($line -notmatch '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$') { throw "Invalid environment syntax at line $lineNumber (value suppressed)." }
        $name = $Matches[1]; $value = $Matches[2].Trim()
        if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) { $value = $value.Substring(1, $value.Length - 2) }
        [Environment]::SetEnvironmentVariable($name, $value, 'Process')
    }
    if ($env:LOG_DIR) {
        $script:LogDir = if ([IO.Path]::IsPathRooted($env:LOG_DIR)) { $env:LOG_DIR } else { Join-Path $ProjectRoot $env:LOG_DIR }
    }
    Set-Location $ProjectRoot
}

function Get-InventoryPython {
    $python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) { throw 'Virtual environment missing. Run setup.ps1.' }
    return $python
}

function Initialize-InventoryDirectories {
    New-Item -ItemType Directory -Force -Path $RuntimeDir, $LogDir | Out-Null
}

function Get-OwnedInventoryProcess {
    if (-not (Test-Path -LiteralPath $PidFile)) { return $null }
    $record = Get-Content -LiteralPath $PidFile -Raw | ConvertFrom-Json
    $process = Get-Process -Id $record.id -ErrorAction SilentlyContinue
    if (-not $process) { Remove-Item -LiteralPath $PidFile -Force; return $null }
    # PID reuse must never kill an unrelated program.
    if ($process.StartTime.ToUniversalTime().Ticks.ToString() -ne $record.started -or $process.Path -ne $record.path) {
        $timeMatches = $process.StartTime.ToUniversalTime().Ticks.ToString() -eq $record.started
        $pathMatches = $process.Path -eq $record.path
        throw "PID record mismatch (start time matches: $timeMatches; executable matches: $pathMatches); refusing to stop an unverified process."
    }
    return $process
}
