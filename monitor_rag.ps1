# monitor_rag.ps1 - single-tick watchdog for MeetingAgent RAG build.
# Safe for Cyrillic Windows profiles: build paths from $env:USERPROFILE.

[CmdletBinding()]
param(
    [string]$Root = (Join-Path $env:USERPROFILE 'Desktop\AI\MeetingAgent'),
    [string]$EmbeddingModel = 'bge-m3',
    [string]$OllamaUrl = 'http://localhost:11434',
    [int]$EmbeddingNumCtx = 8192,
    [string]$KeepAlive = '24h',
    [int]$StallMinutes = 10
)

$ErrorActionPreference = 'Continue'
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

$LogDir = Join-Path $Root 'logs'
$DataDir = Join-Path $Root 'data'
$Lock = Join-Path $LogDir 'build_index.lock'
$Cache = Join-Path $DataDir 'embeddings_cache.jsonl'
$Chunks = Join-Path $DataDir 'chunks.jsonl'
$WatchLog = Join-Path $LogDir 'watchdog.log'
$StateFile = Join-Path $LogDir '.watchdog_state.json'
$ArchiveDir = Join-Path $LogDir 'archive'

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

function Get-CacheLines {
    return Get-JsonlLineCount -Path $Cache
}

function Get-TotalChunks {
    return Get-JsonlLineCount -Path $Chunks
}

function Get-WrapperProcess {
    try {
        Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction Stop |
            Where-Object { $_.CommandLine -like '*run_full_rag*' }
    } catch {
        Write-WLog "WARN: Cannot read PowerShell command lines through CIM: $($_.Exception.Message)"
        @()
    }
}

function Get-BuilderProcess {
    try {
        Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction Stop |
            Where-Object { $_.CommandLine -like '*03_build_index*' }
    } catch {
        Write-WLog "WARN: Cannot read Python command lines through CIM: $($_.Exception.Message)"
        $venvPython = Join-Path $Root '.venv\Scripts\python.exe'
        Get-Process -Name python -ErrorAction SilentlyContinue |
            Where-Object { $_.Path -eq $venvPython }
    }
}

function Get-LockPid {
    if (-not (Test-Path -LiteralPath $Lock)) { return $null }
    try {
        $line = Get-Content -LiteralPath $Lock -ErrorAction Stop |
            Where-Object { $_ -like 'pid=*' } |
            Select-Object -First 1
        if (-not $line) { return $null }
        return [int]($line -replace '^pid=', '')
    } catch {
        return $null
    }
}

function Test-LockPidAlive {
    $pidFromLock = Get-LockPid
    if ($null -eq $pidFromLock) { return $false }
    return [bool](Get-Process -Id $pidFromLock -ErrorAction SilentlyContinue)
}

function New-EmbeddingPayload {
    param([string]$Prompt)
    @{
        model = $EmbeddingModel
        prompt = $Prompt
        keep_alive = $KeepAlive
        options = @{ num_ctx = $EmbeddingNumCtx }
    } | ConvertTo-Json -Depth 5 -Compress
}

function Invoke-EmbeddingCheck {
    param(
        [int]$PromptChars = 6000,
        [int]$TimeoutSec = 60
    )
    $prompt = 'RAG healthcheck. ' * [Math]::Ceiling($PromptChars / 17)
    if ($prompt.Length -gt $PromptChars) {
        $prompt = $prompt.Substring(0, $PromptChars)
    }
    $body = New-EmbeddingPayload -Prompt $prompt
    $r = Invoke-RestMethod -Method Post -Uri "$OllamaUrl/api/embeddings" `
        -ContentType 'application/json' -Body $body -TimeoutSec $TimeoutSec
    return ($r.embedding -and $r.embedding.Count -eq 1024)
}

function Test-OllamaEmbedding {
    foreach ($i in 1..2) {
        try {
            if (Invoke-EmbeddingCheck -PromptChars 6000 -TimeoutSec 60) { return $true }
            Write-WLog "Embedding healthcheck attempt $i returned a non-1024 vector."
        } catch {
            Write-WLog "Embedding healthcheck attempt $i failed: $($_.Exception.Message)"
            Start-Sleep -Seconds 3
        }
    }
    return $false
}

function Restart-Ollama {
    Write-WLog 'Restarting Ollama.'
    $script:ActionTaken = 'Ollama restarted'

    Get-Process -Name ollama -ErrorAction SilentlyContinue |
        Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 5

    if (-not (Get-Process -Name ollama -ErrorAction SilentlyContinue)) {
        Write-WLog 'Ollama did not auto-respawn. Starting "ollama serve" fallback.'
        try {
            Start-Process -FilePath 'ollama' -ArgumentList 'serve' -WindowStyle Hidden
        } catch {
            Write-WLog "Failed to start ollama serve fallback: $($_.Exception.Message)"
        }
    }

    $deadline = (Get-Date).AddSeconds(40)
    $up = $false
    do {
        Start-Sleep -Seconds 2
        try {
            Invoke-RestMethod "$OllamaUrl/api/tags" -TimeoutSec 5 | Out-Null
            $up = $true
        } catch {
            $up = $false
        }
    } while (-not $up -and (Get-Date) -lt $deadline)

    if (-not $up) {
        Write-WLog 'Ollama did not come online within 40 seconds.'
        return $false
    }

    try {
        if (Invoke-EmbeddingCheck -PromptChars 6000 -TimeoutSec 60) {
            Write-WLog 'Ollama warmup succeeded with 1024-vector embedding.'
            return $true
        }
        Write-WLog 'Ollama warmup returned a non-1024 vector.'
        return $false
    } catch {
        Write-WLog "Ollama warmup failed: $($_.Exception.Message)"
        return $false
    }
}

function Read-State {
    if (-not (Test-Path -LiteralPath $StateFile)) { return $null }
    try {
        $state = Get-Content -LiteralPath $StateFile -Raw | ConvertFrom-Json
        if ($null -eq $state.cache_lines -or -not $state.timestamp) { return $null }
        return $state
    } catch {
        return $null
    }
}

function Save-State {
    param([int]$CacheLines)
    @{
        cache_lines = $CacheLines
        timestamp = (Get-Date).ToString('o')
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $StateFile -Encoding utf8
}

function Start-Build {
    Write-WLog 'Starting run_full_rag.ps1 hidden.'
    Start-Process -FilePath powershell.exe `
        -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $Root 'run_full_rag.ps1')) `
        -WorkingDirectory $Root `
        -WindowStyle Hidden
    $script:ActionTaken = 'build started'
}

function Move-FailedMarkersToArchive {
    $failedMarkers = Get-ChildItem -LiteralPath $LogDir -Filter 'full_rag_*.failed.txt' -ErrorAction SilentlyContinue
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

function Write-TickOutput {
    param(
        [string]$Status,
        [int]$CacheLines,
        [int]$TotalChunks
    )
    $failure = if ($script:FailureCause) { $script:FailureCause } else { 'none' }
    $paragraph = "TICK OUTPUT: Current status: $Status, cache $CacheLines/$TotalChunks. Action taken: $script:ActionTaken. Latest relevant marker: $script:LatestMarker. Most recent failure cause: $failure."
    Write-WLog $paragraph
}

Set-Location -LiteralPath $Root

$done = Get-ChildItem -LiteralPath $LogDir -Filter 'full_rag_*.done.txt' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
$failed = Get-ChildItem -LiteralPath $LogDir -Filter 'full_rag_*.failed.txt' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
$wrappers = @(Get-WrapperProcess)
$builders = @(Get-BuilderProcess)
if ($builders.Count -eq 0 -and (Test-LockPidAlive)) {
    $lockPid = Get-LockPid
    $builders = @(Get-Process -Id $lockPid -ErrorAction SilentlyContinue)
    Write-WLog "Using live lock PID as builder fallback: $lockPid"
}
$cacheLines = Get-CacheLines
$totalChunks = Get-TotalChunks

if ($done) { $script:LatestMarker = $done.Name }
if ($failed -and (-not $done -or $failed.LastWriteTime -gt $done.LastWriteTime)) { $script:LatestMarker = $failed.Name }
$script:FailureCause = Get-FailureCause -FailedMarker $failed

Write-WLog '---- check ----'
Write-WLog ("done: {0}" -f $(if ($done) { $done.Name } else { '-' }))
Write-WLog ("failed: {0}" -f $(if ($failed) { $failed.Name } else { '-' }))
Write-WLog ("wrappers: {0}" -f (Get-ProcIds -Processes $wrappers))
Write-WLog ("builders: {0}" -f (Get-ProcIds -Processes $builders))
Write-WLog ("cache_lines: {0}" -f $cacheLines)

if ($wrappers.Count -gt 0 -and $builders.Count -eq 0) {
    Write-WLog 'Build wrapper is running; waiting for current run instead of using old done markers.'
    Save-State -CacheLines $cacheLines
    Write-TickOutput -Status ("running (wrapper PID {0})" -f (Get-ProcIds -Processes $wrappers)) -CacheLines $cacheLines -TotalChunks $totalChunks
    return
}

if ($builders.Count -eq 0 -and $wrappers.Count -eq 0 -and $done -and (-not $failed -or $done.LastWriteTime -gt $failed.LastWriteTime)) {
    Write-WLog 'build complete'
    Write-TickOutput -Status 'done' -CacheLines $cacheLines -TotalChunks $totalChunks
    return
}

if ($builders.Count -gt 0) {
    $state = Read-State
    if (-not $state) {
        Write-WLog 'Build running. No valid prior state; initializing state.'
        Save-State -CacheLines $cacheLines
        Write-TickOutput -Status ("running (PID {0})" -f (Get-ProcIds -Processes $builders)) -CacheLines $cacheLines -TotalChunks $totalChunks
        return
    }

    $growth = $cacheLines - [int]$state.cache_lines
    $elapsed = ((Get-Date) - [DateTime]$state.timestamp).TotalMinutes
    Write-WLog ("Build running. Cache growth {0} over {1:N1} minutes." -f $growth, $elapsed)

    if ($growth -le 0 -and $elapsed -ge $StallMinutes) {
        Write-WLog 'STALL detected. Restarting Ollama; build process is kept alive.'
        [void](Restart-Ollama)
    } elseif ($growth -gt 0 -and $failed) {
        Write-WLog 'Build is progressing; archiving stale failed markers.'
        Move-FailedMarkersToArchive
        $script:LatestMarker = 'no marker yet'
        $script:FailureCause = ''
    }

    Save-State -CacheLines (Get-CacheLines)
    Write-TickOutput -Status ("running (PID {0})" -f (Get-ProcIds -Processes $builders)) -CacheLines (Get-CacheLines) -TotalChunks $totalChunks
    return
}

Write-WLog 'Build is not running and no newer done marker exists.'

if (-not (Test-OllamaEmbedding)) {
    Write-WLog 'Ollama embeddings unhealthy before build restart.'
    if (Restart-Ollama) {
        try {
            if (-not (Invoke-EmbeddingCheck -PromptChars 6000 -TimeoutSec 60)) {
                Write-WLog 'ABORT: Ollama unhealthy after restart.'
                $script:ActionTaken = 'aborted'
                Write-TickOutput -Status 'not running' -CacheLines $cacheLines -TotalChunks $totalChunks
                return
            }
        } catch {
            Write-WLog "ABORT: Ollama unhealthy after restart: $($_.Exception.Message)"
            $script:ActionTaken = 'aborted'
            Write-TickOutput -Status 'not running' -CacheLines $cacheLines -TotalChunks $totalChunks
            return
        }
    } else {
        Write-WLog 'ABORT: Ollama unhealthy.'
        $script:ActionTaken = 'aborted'
        Write-TickOutput -Status 'not running' -CacheLines $cacheLines -TotalChunks $totalChunks
        return
    }
}

if ((Test-Path -LiteralPath $Lock) -and -not (Test-LockPidAlive)) {
    Write-WLog "Removing stale lock: $Lock"
    Remove-Item -LiteralPath $Lock -Force -ErrorAction SilentlyContinue
} elseif (Test-Path -LiteralPath $Lock) {
    Write-WLog "Lock exists and PID is alive; not removing lock."
    Save-State -CacheLines (Get-CacheLines)
    Write-TickOutput -Status 'running (lock PID alive)' -CacheLines (Get-CacheLines) -TotalChunks $totalChunks
    return
}

Move-FailedMarkersToArchive
Start-Build
Start-Sleep -Seconds 12

$builders = @(Get-BuilderProcess)
if ($builders.Count -gt 0) {
    Write-WLog ("Build started. python PID {0}." -f (Get-ProcIds -Processes $builders))
} else {
    Write-WLog 'WARN: build did not start.'
}

Save-State -CacheLines (Get-CacheLines)
Write-TickOutput -Status $(if ($builders.Count -gt 0) { "running (PID $(Get-ProcIds -Processes $builders))" } else { 'not running' }) -CacheLines (Get-CacheLines) -TotalChunks (Get-TotalChunks)
