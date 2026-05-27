[CmdletBinding()]
param(
    [string]$DatasetPath = "docs\quality\realistic_100_queries.jsonl",
    [string]$ReportPath = "data\realistic_100_eval_report.jsonl",
    [string]$ReviewPath = "data\realistic_100_eval_review.jsonl",
    [string]$SummaryPath = "data\realistic_100_eval_review_summary.json",
    [string]$ChatScript = "scripts\09_chat_quality.py",
    [string]$Mode = "hybrid",
    [string]$ActiveCorpus = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
$runner = Join-Path $repoRoot "scripts\14_run_realistic_100_eval.py"
$reviewer = Join-Path $repoRoot "scripts\15_prepare_realistic_eval_review.py"
$statePath = Join-Path $repoRoot "data\realistic_100_eval_automation_state.json"
$chatScriptPath = Join-Path $repoRoot $ChatScript
$datasetFullPath = Join-Path $repoRoot $DatasetPath

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Python venv not found: $pythonExe"
}
if (-not (Test-Path -LiteralPath $runner)) {
    throw "Runner not found: $runner"
}
if (-not (Test-Path -LiteralPath $reviewer)) {
    throw "Review preparer not found: $reviewer"
}
if (-not (Test-Path -LiteralPath $chatScriptPath)) {
    throw "Chat script not found: $chatScriptPath"
}
if (-not (Test-Path -LiteralPath $datasetFullPath)) {
    throw "Dataset not found: $datasetFullPath"
}

$active = Get-CimInstance Win32_Process -Filter "name = 'python.exe'" |
    Where-Object { $_.CommandLine -like "*14_run_realistic_100_eval.py*" }
if ($active) {
    Write-Host "realistic 100 eval is already running:"
    $active | Select-Object ProcessId, CommandLine | Format-List
    exit 0
}

$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$outLog = "logs\realistic_100_eval_full_$ts.out.log"
$errLog = "logs\realistic_100_eval_full_$ts.err.log"

New-Item -ItemType Directory -Force -Path "logs" | Out-Null
New-Item -ItemType Directory -Force -Path "data" | Out-Null

$state = [ordered]@{
    status = "running"
    controller_pid = $PID
    started_at = (Get-Date).ToString("o")
    dataset = $DatasetPath
    report = $ReportPath
    review = $ReviewPath
    summary = $SummaryPath
    chat_script = $ChatScript
    mode = $Mode
    active_corpus = $ActiveCorpus
    stdout_log = $outLog
    stderr_log = $errLog
}
$state | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $statePath -Encoding UTF8

Write-Host "Starting realistic 100 eval"
Write-Host "Dataset: $DatasetPath"
Write-Host "Report: $ReportPath"
Write-Host "Chat script: $ChatScript"
Write-Host "Logs: $outLog / $errLog"

if ($ActiveCorpus) {
    $env:ASU_JUNE_BOT_ACTIVE_CORPUS = $ActiveCorpus
    Write-Host "ASU_JUNE_BOT_ACTIVE_CORPUS=$ActiveCorpus"
}

$proc = Start-Process `
    -FilePath $pythonExe `
    -ArgumentList @($runner, "--dataset", $DatasetPath, "--output", $ReportPath, "--chat-script", $ChatScript, "--mode", $Mode) `
    -WorkingDirectory $repoRoot `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog `
    -PassThru `
    -Wait

$exitCode = $proc.ExitCode
$rows = 0
if (Test-Path -LiteralPath $ReportPath) {
    $rows = (Get-Content -LiteralPath $ReportPath -Encoding UTF8 | Measure-Object -Line).Lines
}

if ($exitCode -eq 0 -and $rows -ge 100) {
    Write-Host "Eval complete. Preparing manual-review file."
    & $pythonExe $reviewer --input $ReportPath --output $ReviewPath --summary $SummaryPath --require-complete
    $finalStatus = "review_ready"
}
else {
    $finalStatus = "incomplete_or_failed"
}

$state = [ordered]@{
    status = $finalStatus
    controller_pid = $PID
    started_at = $state.started_at
    finished_at = (Get-Date).ToString("o")
    exit_code = $exitCode
    rows = $rows
    dataset = $DatasetPath
    report = $ReportPath
    review = $ReviewPath
    summary = $SummaryPath
    chat_script = $ChatScript
    mode = $Mode
    active_corpus = $ActiveCorpus
    stdout_log = $outLog
    stderr_log = $errLog
}
$state | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $statePath -Encoding UTF8

Write-Host "Automation finished: $finalStatus, rows=$rows, exit_code=$exitCode"
