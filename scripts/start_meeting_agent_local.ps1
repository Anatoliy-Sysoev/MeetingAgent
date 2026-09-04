param(
    [string]$BindHost = "127.0.0.1",
    [ValidateRange(1, 65535)]
    [int]$Port = 8000,
    [switch]$Background,
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$entrypoint = Join-Path $repoRoot "scripts\meeting_agent_api.py"
$healthUrl = "http://${BindHost}:${Port}/health"
if (-not (Test-Path -LiteralPath $entrypoint -PathType Leaf)) {
    throw "MeetingAgent API entrypoint was not found. Run this launcher from a complete repository checkout."
}

function Test-MeetingAgentHealth {
    try {
        $response = Invoke-RestMethod -Uri $healthUrl -Method Get -TimeoutSec 3
        return $response.status -eq "ok" -and $response.service -eq "meetingagent"
    }
    catch {
        return $false
    }
}

function Test-PortListener {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
    return $null -ne $listener
}

function Test-LivePython {
    param([string]$PythonPath)

    if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
        return $false
    }

    $probe = "import importlib; names=('vosk','sounddevice','pyaudiowpatch','soxr','silero_vad'); [importlib.import_module(n) for n in names]"
    $result = & $PythonPath -c $probe 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Verbose "Rejected Python ${PythonPath}: missing $result"
        return $false
    }
    return $true
}

$meetingAgentAlreadyRunning = Test-MeetingAgentHealth
$portAlreadyInUse = Test-PortListener

if ($env:MEETINGAGENT_LIVE_PYTHON) {
    if (-not (Test-LivePython -PythonPath $env:MEETINGAGENT_LIVE_PYTHON)) {
        throw "MEETINGAGENT_LIVE_PYTHON does not point to a complete live runtime."
    }
    $livePython = $env:MEETINGAGENT_LIVE_PYTHON
}
else {
    $pythonCandidates = @(
        "C:\ma-live\Scripts\python.exe",
        "C:\ma-live-venv\Scripts\python.exe",
        "C:\MeetingAgentLiveVenv312\Scripts\python.exe",
        (Join-Path $repoRoot ".venv\Scripts\python.exe")
    )
    $livePython = $null
    foreach ($candidate in ($pythonCandidates | Select-Object -Unique)) {
        if (Test-LivePython -PythonPath $candidate) {
            $livePython = $candidate
            break
        }
    }
}
if (-not $livePython) {
    throw "No verified live Python runtime was found. Set MEETINGAGENT_LIVE_PYTHON to a Python 3.12 environment containing requirements-live.txt dependencies."
}

$modelPath = $env:MEETINGAGENT_LIVE_MODEL_PATH
if (-not $modelPath) {
    $asciiModel = "C:\ma-models\vosk-model-small-ru-0.22"
    if (Test-Path -LiteralPath $asciiModel -PathType Container) {
        $modelPath = $asciiModel
    }
}
if (-not $modelPath) {
    $repoModel = Join-Path $repoRoot "models\vosk\vosk-model-small-ru-0.22"
    if ($repoModel -notmatch '[^\x00-\x7F]' -and (Test-Path -LiteralPath $repoModel -PathType Container)) {
        $modelPath = $repoModel
    }
}
if (-not $modelPath) {
    throw "No live Vosk model path is configured. Set MEETINGAGENT_LIVE_MODEL_PATH to an ASCII-only model directory."
}

$requiredModelFiles = @("am\final.mdl", "conf\model.conf")
foreach ($relativePath in $requiredModelFiles) {
    $requiredPath = Join-Path $modelPath $relativePath
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "The configured live Vosk model is incomplete: missing $relativePath."
    }
}

$env:MEETINGAGENT_LIVE_MODEL_PATH = $modelPath
Write-Host "Live runtime ready."
Write-Host "Python: $livePython"
Write-Host "Vosk model: $modelPath"

if ($CheckOnly) {
    exit 0
}

if ($meetingAgentAlreadyRunning) {
    Write-Host "MeetingAgent is already running: $healthUrl"
    exit 0
}
if ($portAlreadyInUse) {
    throw "Port $Port is already in use, but MeetingAgent health check failed. Stop the conflicting process or select another port."
}

$arguments = @("scripts\meeting_agent_api.py", "--host", $BindHost, "--port", "$Port")
if (-not $Background) {
    Push-Location $repoRoot
    try {
        & $livePython @arguments
        exit $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
}

$process = Start-Process `
    -FilePath $livePython `
    -ArgumentList $arguments `
    -WorkingDirectory $repoRoot `
    -WindowStyle Hidden `
    -PassThru

$deadline = (Get-Date).AddSeconds(30)
do {
    Start-Sleep -Milliseconds 500
    if ($process.HasExited) {
        throw "MeetingAgent exited during startup with code $($process.ExitCode)."
    }
    if (Test-MeetingAgentHealth) {
        Write-Host "MeetingAgent started (PID $($process.Id)): $healthUrl"
        Write-Host "Open: http://${BindHost}:${Port}/MeetingAgent"
        exit 0
    }
} while ((Get-Date) -lt $deadline)

throw "MeetingAgent did not become healthy within 30 seconds."
