# register_asu_june_bot_index_v2_watchdog.ps1
# Registers a Windows Task Scheduler task for monitor_asu_june_bot_index_v2.ps1.

[CmdletBinding()]
param(
    [string]$Root = (Join-Path $env:USERPROFILE 'Desktop\AI\MeetingAgent'),
    [string]$TaskName = 'AsuJuneBotIndexV2Watchdog',
    [int]$IntervalMinutes = 30
)

$ErrorActionPreference = 'Stop'
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

$MonitorScript = Join-Path $Root 'monitor_asu_june_bot_index_v2.ps1'
if (-not (Test-Path -LiteralPath $MonitorScript)) {
    throw "Monitor script not found: $MonitorScript"
}

$Action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$MonitorScript`" -Root `"$Root`" -TaskName `"$TaskName`""

$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew

try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
} catch {
    # ignore
}

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description 'Asu June Bot index v2 watchdog: restarts embed-only build if it stops before completion' | Out-Null

Write-Host "Registered task: $TaskName"
Write-Host "Interval: every $IntervalMinutes minutes"
Write-Host "Monitor: $MonitorScript"
Write-Host "Root: $Root"
Write-Host "To run now: Start-ScheduledTask -TaskName $TaskName"
Write-Host "To check: Get-ScheduledTask -TaskName $TaskName"
Write-Host "To remove: Unregister-ScheduledTask -TaskName $TaskName -Confirm:`$false"
