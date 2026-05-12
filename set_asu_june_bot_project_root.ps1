# set_asu_june_bot_project_root.ps1
# Safely updates project_root in config.yaml for Asu June Bot / MeetingAgent.

[CmdletBinding()]
param(
    [string]$Root = 'C:\Users\Сотрудник\Desktop\!Проектные документы АСУ',
    [string]$ConfigPath = '.\config.yaml'
)

$ErrorActionPreference = 'Stop'
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

if (-not (Test-Path -LiteralPath $Root)) {
    throw "Project root not found: $Root"
}

if (-not (Test-Path -LiteralPath $ConfigPath)) {
    throw "Config file not found: $ConfigPath"
}

$RootForYaml = $Root.Replace('\', '/')
$Raw = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8
$Updated = [regex]::Replace($Raw, '(?m)^project_root:\s*".*"\s*$', "project_root: `"$RootForYaml`"")

if ($Updated -eq $Raw) {
    throw 'project_root line was not updated. Check config.yaml format.'
}

$BackupPath = "$ConfigPath.bak_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
Copy-Item -LiteralPath $ConfigPath -Destination $BackupPath -Force
[System.IO.File]::WriteAllText((Resolve-Path -LiteralPath $ConfigPath), $Updated, $Utf8NoBom)

Write-Host "Updated project_root: $RootForYaml"
Write-Host "Backup: $BackupPath"
Write-Host 'Verify:'
Select-String -Path $ConfigPath -Pattern '^project_root:'
