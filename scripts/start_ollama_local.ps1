param(
    [string]$ModelStore = "C:\ollama-models",
    [switch]$Restart
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $ModelStore)) {
    New-Item -ItemType Directory -Path $ModelStore | Out-Null
}

$env:OLLAMA_MODELS = $ModelStore
$env:OLLAMA_KEEP_ALIVE = "24h"
$env:OLLAMA_NUM_PARALLEL = "1"

$existing = Get-Process -Name ollama -ErrorAction SilentlyContinue
if ($existing) {
    if (-not $Restart) {
        Write-Host "Ollama is already running. Restart it to apply OLLAMA_MODELS=$ModelStore."
        Write-Host "Run: .\scripts\start_ollama_local.ps1 -Restart"
        exit 2
    }
    $existing | Stop-Process -Force
    Start-Sleep -Seconds 3
}

Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden

$deadline = (Get-Date).AddSeconds(40)
do {
    Start-Sleep -Seconds 2
    try {
        $tags = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -Method Get -TimeoutSec 5
        Write-Host "Ollama is ready. Model store: $ModelStore"
        $tags.models | Select-Object name, size, modified_at | Format-Table -AutoSize
        exit 0
    }
    catch {
        if ((Get-Date) -ge $deadline) {
            throw "Ollama did not become ready within 40 seconds."
        }
    }
} while ($true)
