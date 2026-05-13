# set_asu_june_bot_project_root.ps1
# Compatibility wrapper. Main config update logic lives in scripts/asu_june_bot_apply_config_v2_1.py.
# Pass -Root explicitly to avoid PowerShell encoding issues with non-ASCII paths.

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Root,

    [string]$ConfigPath = '.\config.yaml'
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$ApplyScript = Join-Path $RepoRoot 'scripts\asu_june_bot_apply_config_v2_1.py'

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python venv not found: $Python"
}

if (-not (Test-Path -LiteralPath $ApplyScript)) {
    throw "Apply config script not found: $ApplyScript"
}

& $Python $ApplyScript --project-root $Root --config $ConfigPath
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host 'Verify project_root:'
Select-String -Path $ConfigPath -Pattern '^project_root:'
