# monitor_asu_june_bot_v2.ps1 - single-tick watchdog for Asu June Bot v2 rebuild.
# Запускать по расписанию каждые 15 минут через Task Scheduler.

[CmdletBinding()]
param(
    [string]$Root = (Join-Path $env:USERPROFILE 'Desktop\AI\MeetingAgent'),
    [int]$StallMinutes = 30,
    [switch]$NoAutoStart
)

$ErrorActionPreference = 'Continue'
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

$LogDir = Join-Path $Root 'logs'
$WatchLog = Join-Path $LogDir 'asu_june_bot_v2_watchdog.log'
$StateFile = Join-Path $LogDir '.asu_june_bot_v2_watchdog_state.json'
$ArchiveDir = Join-Path $LogDir 'archive'
$DoneMarkerPattern = 'asu_june_bot_rebuild_v2_*.done.txt'
$FailedMarkerPattern = 'asu_june_bot_rebuild_v2_*.failed.txt'
$WrapperScript = Join-Path $Root 'run_asu_june_bot_rebuild_v2.ps1'
$ExtractedDir = Join-Path $Root 'data\asu_june_bot\extracted_v2'
$DocumentsPath = Join-Path $ExtractedDir 'documents.jsonl'
$BlocksPath = Join-Path $ExtractedDir 'blocks.jsonl'
$ProgressPath = Join-Path $ExtractedDir 'extraction_v2_progress.json'
$ChunksPath = Join-Path $Root 'data\asu_june_bot\chunks_v2.jsonl'
$ChunkReportPath = Join-Path $Root 'data\asu_june_bot\chunking_v2_report.json'

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

$script:ActionTaken = 'none'
$script:LatestMarker = 'no marker yet'
$script:FailureCause = ''

function Write-WLog {
    param([string]$Message)
    $line = '[{0}] {1}' -f (Get-Date).ToString('o'), $Message
    $line | Out-File -FilePath $WatchLog -Append -Encoding utf8
    Write-Host $line
}

function Get-JsonlLineCount {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return 0 }
    return (Get-Content -LiteralPath $Path | Measure-Object -Line).Lines
}

function Get-WrapperProcess {
    try {
        Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction Stop |
            Where-Object { $_.CommandLine -like '*run_asu_june_bot_rebuild_v2*' }
    } catch {
        Write-WLog "WARN: Cannot read PowerShell command lines through CIM: $($_.Exception.Message)"
        @()
    }
}

function Get-ExtractorProcess {
    try {
        Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction Stop |
            Where-Object { $_.CommandLine -like '*asu_june_bot_extract_text_v2*' }
    } catch {
        Write-WLog "WARN: Cannot read Python command lines through CIM: $($_.Exception.Message)"
        @()
    }
}

function Get-ChunkerProcess {
    try {
        Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction Stop |
            Where-Object { $_.CommandLine -like '*asu_june_bot_build_chunks_v2*' }
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

function Read-State {
    if (-not (Test-Path -LiteralPath $StateFile)) { return $null }
    try {
        $state = Get-Content -LiteralPath $StateFile -Raw | ConvertFrom-Json
        if ($null -eq $state.documents_lines -or -not $state.timestamp) { return $null }
        return $state
    } catch {
        return $null
    }
}

function Save-State {
    param(
        [int]$DocumentsLines,
        [int]$BlocksLines,
        [int]$ChunksLines
    )
    @{
        documents_lines = $DocumentsLines
        blocks_lines = $BlocksLines
        chunks_lines = $ChunksLines
        timestamp = (Get-Date).ToString('o')
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $StateFile -Encoding utf8
}

function Get-FailureCause {
    param($FailedMarker)
    if (-not $FailedMarker) { return '' }
    try {
        $text = Get-Content -LiteralPath $FailedMarker.FullName -Raw -ErrorAction Stop
        $line = ($text -split "`r?`n" | Where-Object { $_.Trim() } | Select-Object -First 1)
        return $line
    } catch {
        return ''
    }
}

function Move-FailedMarkersToArchive {
    $failedMarkers = Get-ChildItem -LiteralPath $LogDir -Filter $FailedMarkerPattern -ErrorAction SilentlyContinue
    if (-not $failedMarkers) { return }
    New-Item -ItemType Directory -Path $ArchiveDir -Force | Out-Null
    foreach ($marker in $failedMarkers) {
        try {
            Move-Item -LiteralPath $marker.FullName -Destination (Join-Path $ArchiveDir $marker.Name) -Force
            Write-WLog "Archived failed marker: $($marker.Name)"
        } catch {
            Write-WLog "Failed to archive marker $($marker.Name): $($_.Exception.Message)"
        }
    }
}

function Start-Rebuild {
    if ($NoAutoStart) {
        Write-WLog 'NoAutoStart is set; rebuild will not be started.'
        $script:ActionTaken = 'auto-start disabled'
        return
    }
    if (-not (Test-Path -LiteralPath $WrapperScript)) {
        Write-WLog "ABORT: wrapper not found: $WrapperScript"
        $script:ActionTaken = 'aborted'
        return
    }
    Write-WLog 'Starting run_asu_june_bot_rebuild_v2.ps1 hidden.'
    Start-Process -FilePath powershell.exe `
        -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',$WrapperScript) `
        -WorkingDirectory $Root `
        -WindowStyle Hidden
    $script:ActionTaken = 'rebuild started'
}

function Write-TickOutput {
    param(
        [string]$Status,
        [int]$DocumentsLines,
        [int]$BlocksLines,
        [int]$ChunksLines
    )
    $failure = if ($script:FailureCause) { $script:FailureCause } else { 'none' }
    $paragraph = "TICK OUTPUT: Current status: $Status, documents=$DocumentsLines, blocks=$BlocksLines, chunks=$ChunksLines. Action taken: $script:ActionTaken. Latest relevant marker: $script:LatestMarker. Most recent failure cause: $failure."
    Write-WLog $paragraph
}

function Test-RebuildDone {
    if (-not (Test-Path -LiteralPath $BlocksPath)) { return $false }
    if (-not (Test-Path -LiteralPath $ChunksPath)) { return $false }
    if (-not (Test-Path -LiteralPath $ChunkReportPath)) { return $false }
    return $true
}

Set-Location -LiteralPath $Root

$done = Get-ChildItem -LiteralPath $LogDir -Filter $DoneMarkerPattern -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
$failed = Get-ChildItem -LiteralPath $LogDir -Filter $FailedMarkerPattern -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
$wrappers = @(Get-WrapperProcess)
$extractors = @(Get-ExtractorProcess)
$chunkers = @(Get-ChunkerProcess)
$documentsLines = Get-JsonlLineCount -Path $DocumentsPath
$blocksLines = Get-JsonlLineCount -Path $BlocksPath
$chunksLines = Get-JsonlLineCount -Path $ChunksPath

if ($done) { $script:LatestMarker = $done.Name }
if ($failed -and (-not $done -or $failed.LastWriteTime -gt $done.LastWriteTime)) { $script:LatestMarker = $failed.Name }
$script:FailureCause = Get-FailureCause -FailedMarker $failed

Write-WLog '---- check ----'
Write-WLog ("done: {0}" -f $(if ($done) { $done.Name } else { '-' }))
Write-WLog ("failed: {0}" -f $(if ($failed) { $failed.Name } else { '-' }))
Write-WLog ("wrappers: {0}" -f (Get-ProcIds -Processes $wrappers))
Write-WLog ("extractors: {0}" -f (Get-ProcIds -Processes $extractors))
Write-WLog ("chunkers: {0}" -f (Get-ProcIds -Processes $chunkers))
Write-WLog ("documents_lines: {0}" -f $documentsLines)
Write-WLog ("blocks_lines: {0}" -f $blocksLines)
Write-WLog ("chunks_lines: {0}" -f $chunksLines)

if ($wrappers.Count -gt 0 -or $extractors.Count -gt 0 -or $chunkers.Count -gt 0) {
    $state = Read-State
    if ($state) {
        $growth = $documentsLines - [int]$state.documents_lines
        $elapsed = ((Get-Date) - [DateTime]$state.timestamp).TotalMinutes
        Write-WLog ("Rebuild running. Document growth {0} over {1:N1} minutes." -f $growth, $elapsed)
        if ($growth -le 0 -and $extractors.Count -gt 0 -and $elapsed -ge $StallMinutes) {
            Write-WLog 'WARN: possible extraction stall detected. No process is killed automatically; next tick will re-evaluate.'
            $script:ActionTaken = 'stall warning'
        }
    } else {
        Write-WLog 'Rebuild running. No valid prior state; initializing state.'
    }
    Save-State -DocumentsLines $documentsLines -BlocksLines $blocksLines -ChunksLines $chunksLines
    Write-TickOutput -Status 'running' -DocumentsLines $documentsLines -BlocksLines $blocksLines -ChunksLines $chunksLines
    return
}

if ($done -and (-not $failed -or $done.LastWriteTime -gt $failed.LastWriteTime) -and (Test-RebuildDone)) {
    Write-WLog 'Asu June Bot v2 rebuild complete. Watchdog will not restart it.'
    Write-TickOutput -Status 'done' -DocumentsLines $documentsLines -BlocksLines $blocksLines -ChunksLines $chunksLines
    return
}

if ($done -and (-not (Test-RebuildDone))) {
    Write-WLog 'Done marker exists, but expected outputs are missing. Restarting rebuild in resume mode.'
    Move-FailedMarkersToArchive
    Start-Rebuild
    Start-Sleep -Seconds 10
    Save-State -DocumentsLines (Get-JsonlLineCount -Path $DocumentsPath) -BlocksLines (Get-JsonlLineCount -Path $BlocksPath) -ChunksLines (Get-JsonlLineCount -Path $ChunksPath)
    Write-TickOutput -Status 'restart-after-incomplete-done' -DocumentsLines (Get-JsonlLineCount -Path $DocumentsPath) -BlocksLines (Get-JsonlLineCount -Path $BlocksPath) -ChunksLines (Get-JsonlLineCount -Path $ChunksPath)
    return
}

Write-WLog 'Rebuild is not running and no valid done state exists. Starting or resuming rebuild.'
Move-FailedMarkersToArchive
Start-Rebuild
Start-Sleep -Seconds 10
Save-State -DocumentsLines (Get-JsonlLineCount -Path $DocumentsPath) -BlocksLines (Get-JsonlLineCount -Path $BlocksPath) -ChunksLines (Get-JsonlLineCount -Path $ChunksPath)
Write-TickOutput -Status 'started-or-resumed' -DocumentsLines (Get-JsonlLineCount -Path $DocumentsPath) -BlocksLines (Get-JsonlLineCount -Path $BlocksPath) -ChunksLines (Get-JsonlLineCount -Path $ChunksPath)
