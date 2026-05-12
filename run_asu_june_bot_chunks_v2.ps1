$ErrorActionPreference = "Continue"
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$LogDir = Join-Path $Root "logs"
$Stamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$LogPath = Join-Path $LogDir "asu_june_bot_chunks_v2_$Stamp.log"
$DonePath = Join-Path $LogDir "asu_june_bot_chunks_v2_$Stamp.done.txt"
$FailPath = Join-Path $LogDir "asu_june_bot_chunks_v2_$Stamp.failed.txt"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-Step {
    param([string]$Message)
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
    Write-Host $line
    Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value $line
}

function Run-Step {
    param(
        [string]$Name,
        [string[]]$ScriptArgs
    )

    Write-Step "START $Name"
    & $Python @ScriptArgs 2>&1 | ForEach-Object { $_.ToString() } | Tee-Object -FilePath $LogPath -Append
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
    Write-Step "DONE $Name"
}

Set-Location -LiteralPath $Root

try {
    Write-Step "Asu June Bot chunking v2 started"
    Write-Step "Root: $Root"
    Write-Step "Python: $Python"

    if (-not (Test-Path -LiteralPath $Python)) {
        throw "Python venv not found: $Python"
    }

    if (-not (Test-Path -LiteralPath (Join-Path $Root "data\extracted_text\_metadata.jsonl"))) {
        throw "Extracted text metadata not found. Run run_full_rag.ps1 first at least through 02_extract_text."
    }

    Run-Step "asu_june_bot_build_chunks_v2" @("scripts\asu_june_bot_build_chunks_v2.py")

    Write-Step "Asu June Bot chunking v2 completed successfully"
    Set-Content -LiteralPath $DonePath -Encoding UTF8 -Value "Completed at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')`nLog: $LogPath"
}
catch {
    $message = "FAILED at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss'): $($_.Exception.Message)"
    Write-Step $message
    Set-Content -LiteralPath $FailPath -Encoding UTF8 -Value "$message`nLog: $LogPath"
    exit 1
}
