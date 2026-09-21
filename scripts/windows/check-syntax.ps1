Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$failed = $false
Get-ChildItem $PSScriptRoot -Filter '*.ps1' | ForEach-Object {
    $tokens = $null; $errors = $null
    [System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$tokens, [ref]$errors) | Out-Null
    if ($errors.Count -gt 0) { $failed = $true; $errors | Write-Output }
}
if ($failed) { exit 1 }
Write-Host 'PowerShell parser: all scripts passed.'
