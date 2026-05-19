[CmdletBinding()]
param(
    [string]$ChatApiUrl = "http://127.0.0.1:8000/chat",
    [string]$AllowedChatIds = $env:ASU_JUNE_BOT_ALLOWED_CHAT_IDS,
    [int]$TopK = 5,
    [string]$Model = "qwen2.5:7b-instruct",
    [int]$MaxTokens = 700,
    [int]$TimeoutSec = 300
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
$telegramScript = Join-Path $repoRoot "scripts\asu_june_bot_telegram.py"

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Python venv not found: $pythonExe"
}

if (-not (Test-Path -LiteralPath $telegramScript)) {
    throw "Telegram script not found: $telegramScript"
}

if (-not $env:ASU_JUNE_BOT_TELEGRAM_TOKEN) {
    $secureToken = Read-Host "Telegram bot token" -AsSecureString
    if ($secureToken.Length -eq 0) {
        throw "Telegram token is required"
    }

    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
    try {
        $env:ASU_JUNE_BOT_TELEGRAM_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

$env:ASU_JUNE_BOT_CHAT_API_URL = $ChatApiUrl
$env:ASU_JUNE_BOT_TELEGRAM_TOP_K = [string]$TopK
$env:ASU_JUNE_BOT_TELEGRAM_MODEL = $Model
$env:ASU_JUNE_BOT_TELEGRAM_MAX_TOKENS = [string]$MaxTokens
$env:ASU_JUNE_BOT_TELEGRAM_TIMEOUT_SEC = [string]$TimeoutSec

if ($AllowedChatIds) {
    $env:ASU_JUNE_BOT_ALLOWED_CHAT_IDS = $AllowedChatIds
}

Write-Host "Starting Telegram adapter over $ChatApiUrl"
Write-Host "Token is read from process environment and is not passed as a command-line argument."
& $pythonExe $telegramScript
