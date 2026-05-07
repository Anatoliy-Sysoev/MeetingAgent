$ErrorActionPreference = "Continue"
$env:PYTHONIOENCODING = "utf-8"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$LogDir = Join-Path $Root "logs"
$Stamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$LogPath = Join-Path $LogDir "full_rag_$Stamp.log"
$DonePath = Join-Path $LogDir "full_rag_$Stamp.done.txt"
$FailPath = Join-Path $LogDir "full_rag_$Stamp.failed.txt"

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
    Write-Step "Full RAG build started"
    Write-Step "Root: $Root"
    Write-Step "Python: $Python"

    if (-not (Test-Path -LiteralPath $Python)) {
        throw "Python venv not found: $Python"
    }

    Run-Step "01_inventory" @("scripts\01_inventory.py")
    Run-Step "02_extract_text" @("scripts\02_extract_text.py")
    Run-Step "03_build_index" @("scripts\03_build_index.py")
    Run-Step "05_build_numpy_index" @("scripts\05_build_numpy_index.py")

    Write-Step "Full RAG build completed successfully"
    Set-Content -LiteralPath $DonePath -Encoding UTF8 -Value "Completed at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')`nLog: $LogPath"
}
catch {
    $message = "FAILED at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss'): $($_.Exception.Message)"
    Write-Step $message
    Set-Content -LiteralPath $FailPath -Encoding UTF8 -Value "$message`nLog: $LogPath"
    exit 1
}
