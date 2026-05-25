param(
    [int]$IntervalMinutes = 30,
    [switch]$Loop
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$ChunksPath = "data\asu_june_bot_ntk\chunks_v2.jsonl"
$CachePath = "data\asu_june_bot_ntk\embeddings_cache_v2.jsonl"
$IndexDir = "data\asu_june_bot_ntk\numpy_index_v2"
$ReportPath = "data\asu_june_bot_ntk\index_v2_report.json"
$LogDir = Join-Path $Root "logs"
$WatchdogLog = Join-Path $LogDir "ntk_yandex_index_watchdog.log"

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

function Write-WatchdogLog {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-ddTHH:mm:ssK"), $Message
    Add-Content -Path $WatchdogLog -Value $line -Encoding UTF8
    Write-Host $line
}

function Count-JsonlLines {
    param([string]$Path)
    $FullPath = Join-Path $Root $Path
    if (-not (Test-Path $FullPath)) {
        return 0
    }
    return (Get-Content $FullPath -Encoding UTF8).Count
}

function Get-NtkIndexProcess {
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.CommandLine -like "*asu_june_bot_build_index_v2.py*" -and
            $_.CommandLine -like "*data\asu_june_bot_ntk*"
        }
}

function Start-NtkIndexBuild {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $out = Join-Path $LogDir "ntk_yandex_index_$stamp.out.log"
    $err = Join-Path $LogDir "ntk_yandex_index_$stamp.err.log"
    $args = @(
        "scripts\asu_june_bot_build_index_v2.py",
        "--chunks-path", $ChunksPath,
        "--cache-path", $CachePath,
        "--index-dir", $IndexDir,
        "--report-path", $ReportPath
    )
    $proc = Start-Process -FilePath $Python -ArgumentList $args -WorkingDirectory $Root -RedirectStandardOutput $out -RedirectStandardError $err -WindowStyle Hidden -PassThru
    Write-WatchdogLog "started pid=$($proc.Id) out=$out err=$err"
}

function Invoke-NtkIndexCheck {
    $manifest = Join-Path $Root (Join-Path $IndexDir "manifest.json")
    $cacheLines = Count-JsonlLines $CachePath
    $chunkLines = Count-JsonlLines $ChunksPath
    $proc = @(Get-NtkIndexProcess)

    Write-WatchdogLog "check cache=$cacheLines/$chunkLines running=$($proc.Count) manifest_exists=$(Test-Path $manifest)"

    if (Test-Path $manifest) {
        Write-WatchdogLog "index already built; no action"
        return
    }

    if ($proc.Count -gt 0) {
        Write-WatchdogLog "build already running; no action"
        return
    }

    Start-NtkIndexBuild
}

do {
    Invoke-NtkIndexCheck
    if ($Loop) {
        Start-Sleep -Seconds ([Math]::Max(1, $IntervalMinutes) * 60)
    }
} while ($Loop)
