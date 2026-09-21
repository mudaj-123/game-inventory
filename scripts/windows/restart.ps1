& (Join-Path $PSScriptRoot 'stop.ps1')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& (Join-Path $PSScriptRoot 'start.ps1')
exit $LASTEXITCODE
