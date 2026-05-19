# monitor_asu_june_bot_index_v2.ps1 - single-tick watchdog for Asu June Bot embeddings/index v2.
# Intended schedule: every 30 minutes while embeddings_cache_v2 is being built.

[CmdletBinding()]
param(
    [string]$Root = (Join-Path $env:USERPROFILE 'Desktop\AI\MeetingAgent'),
    [string]$TaskName = 'AsuJuneBotIndexV2Watchdog',
    [switch]$NoAutoStart
)

$ErrorActionPreference = 'Continue'
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

$LogDir = Join-Path $Root 'logs'
$WatchLog = Join-Path $LogDir 'asu_june_bot_index_v2_watchdog.log'
$ChunksPath = Join-Path $Root 'data\asu_june_bot\chunks_v2.jsonl'
$CachePath = Join-Path $Root 'data\asu_june_bot\embeddings_cache_v2.jsonl'
$ReportPath = Join-Path $Root 'data\asu_june_bot\index_v2_report.json'
$PythonPath = Join-Path $Root '.venv\Scripts\python.exe'
$BuildScript = Join-Path $Root 'scripts\asu_june_bot_build_index_v2.py'

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

function Write-WLog {
    param([string]$Message)
    $line = '[{0}] {1}' -f (Get-Date).ToString('o'), $Message
    $line | Out-File -FilePath $WatchLog -Append -Encoding utf8
    Write-Host $line
}

function Get-JsonlLineCount {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return 0 }
    return (Get-Content -LiteralPath $Path -Encoding UTF8 | Measure-Object -Line).Lines
}

function Get-EmbeddingTargetCount {
    if (-not (Test-Path -LiteralPath $ChunksPath)) { return 0 }
    $allowed = @('project_doc', 'meeting_artifact', 'analytical_note', 'instruction')
    $count = 0
    Get-Content -LiteralPath $ChunksPath -Encoding UTF8 | ForEach-Object {
        if ($_ -match '"source_type"\s*:\s*"([^"]+)"') {
            if ($allowed -contains $Matches[1]) {
                $count += 1
            }
        }
    }
    return $count
}

function Get-EmbedProcesses {
    try {
        Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction Stop |
            Where-Object { $_.CommandLine -like '*asu_june_bot_build_index_v2.py*' -and $_.CommandLine -like '*--embed-only*' }
    } catch {
        Write-WLog "WARN: Cannot read Python command lines through CIM: $($_.Exception.Message)"
        @()
    }
}

function Get-ProcIds {
    param($Processes)
    $ids = @()
    foreach ($proc in @($Processes)) {
        if ($null -ne $proc.ProcessId) {
            $ids += [string]$proc.ProcessId
        } elseif ($null -ne $proc.Id) {
            $ids += [string]$proc.Id
        }
    }
    if ($ids.Count -eq 0) { return '-' }
    return ($ids -join ',')
}

function Test-EmbedComplete {
    param([int]$TargetCount)
    if (-not (Test-Path -LiteralPath $ReportPath)) { return $false }
    try {
        $report = Get-Content -LiteralPath $ReportPath -Encoding UTF8 -Raw | ConvertFrom-Json
        $summary = $report.summary
        if ($null -eq $summary) { return $false }
        return (
            [bool]$report.embed_only -and
            [int]$summary.chunks_total -ge $TargetCount -and
            [int]$summary.missing_after -eq 0
        )
    } catch {
        Write-WLog "WARN: Cannot parse index report: $($_.Exception.Message)"
        return $false
    }
}

function Disable-SelfTask {
    try {
        $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($task -and $task.State -ne 'Disabled') {
            Disable-ScheduledTask -TaskName $TaskName | Out-Null
            Write-WLog "Disabled scheduled task after completion: $TaskName"
        }
    } catch {
        Write-WLog "WARN: Cannot disable scheduled task ${TaskName}: $($_.Exception.Message)"
    }
}

function Start-EmbedBuild {
    if ($NoAutoStart) {
        Write-WLog 'NoAutoStart is set; embed build will not be started.'
        return 'auto-start disabled'
    }
    if (-not (Test-Path -LiteralPath $PythonPath)) {
        Write-WLog "ABORT: python not found: $PythonPath"
        return 'aborted'
    }
    if (-not (Test-Path -LiteralPath $BuildScript)) {
        Write-WLog "ABORT: build script not found: $BuildScript"
        return 'aborted'
    }
    Write-WLog 'Starting asu_june_bot_build_index_v2.py --embed-only hidden.'
    Start-Process -FilePath $PythonPath `
        -ArgumentList @($BuildScript, '--embed-only') `
        -WorkingDirectory $Root `
        -WindowStyle Hidden
    return 'embed build started'
}

Set-Location -LiteralPath $Root

$targetCount = Get-EmbeddingTargetCount
$cacheLines = Get-JsonlLineCount -Path $CachePath
$embedProcesses = @(Get-EmbedProcesses)
$isComplete = Test-EmbedComplete -TargetCount $targetCount
$actionTaken = 'none'

Write-WLog '---- index v2 check ----'
Write-WLog ("target_chunks: {0}" -f $targetCount)
Write-WLog ("cache_lines: {0}" -f $cacheLines)
Write-WLog ("embed_processes: {0}" -f (Get-ProcIds -Processes $embedProcesses))
Write-WLog ("complete_report: {0}" -f $isComplete)

if ($isComplete) {
    $actionTaken = 'complete; watchdog disabled'
    Disable-SelfTask
} elseif ($embedProcesses.Count -gt 0) {
    $actionTaken = 'build already running'
} else {
    $actionTaken = Start-EmbedBuild
}

Write-WLog ("TICK OUTPUT: target={0}, cache_lines={1}, processes={2}, complete={3}. Action taken: {4}." -f $targetCount, $cacheLines, (Get-ProcIds -Processes $embedProcesses), $isComplete, $actionTaken)
