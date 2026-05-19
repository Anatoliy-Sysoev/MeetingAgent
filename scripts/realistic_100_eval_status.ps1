[CmdletBinding()]
param(
    [string]$ReportPath = "data\realistic_100_eval_report.jsonl",
    [string]$ReviewPath = "data\realistic_100_eval_review.jsonl",
    [string]$SummaryPath = "data\realistic_100_eval_review_summary.json",
    [switch]$PrepareNextIfComplete
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
$reviewer = Join-Path $repoRoot "scripts\15_prepare_realistic_eval_review.py"
$statePath = Join-Path $repoRoot "data\realistic_100_eval_automation_state.json"
$state = $null
if (Test-Path -LiteralPath $statePath) {
    $state = Get-Content -LiteralPath $statePath -Encoding UTF8 -Raw | ConvertFrom-Json
}

$activeEval = @(Get-CimInstance Win32_Process -Filter "name = 'python.exe'" |
    Where-Object { $_.CommandLine -like "*14_run_realistic_100_eval.py*" })
$activeController = @(Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -like "*run_realistic_100_eval_automation.ps1*" })

$rows = 0
if (Test-Path -LiteralPath $ReportPath) {
    $rows = (Get-Content -LiteralPath $ReportPath -Encoding UTF8 | Measure-Object -Line).Lines
}

$reviewExists = Test-Path -LiteralPath $ReviewPath
$summaryExists = Test-Path -LiteralPath $SummaryPath

$latestOut = Get-ChildItem logs -Filter "realistic_100_eval_full_*.out.log" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
$latestErr = Get-ChildItem logs -Filter "realistic_100_eval_full_*.err.log" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if ($PrepareNextIfComplete -and $rows -ge 100 -and -not $reviewExists) {
    & $pythonExe $reviewer --input $ReportPath --output $ReviewPath --summary $SummaryPath --require-complete
    $reviewExists = Test-Path -LiteralPath $ReviewPath
    $summaryExists = Test-Path -LiteralPath $SummaryPath
}

$status = if ($rows -ge 100 -and $reviewExists) {
    "review_ready"
}
elseif ($rows -ge 100) {
    "eval_complete"
}
elseif ($activeEval -or $activeController) {
    "running"
}
elseif ($rows -gt 0) {
    "partial_stopped"
}
else {
    "not_started"
}

$payload = [ordered]@{
    status = $status
    rows = $rows
    report = $ReportPath
    review = $ReviewPath
    chat_script = if ($state -and $state.chat_script) { $state.chat_script } else { $null }
    review_exists = $reviewExists
    summary_exists = $summaryExists
    active_eval_pids = @($activeEval | ForEach-Object { $_.ProcessId })
    active_controller_pids = @($activeController | ForEach-Object { $_.ProcessId })
    latest_stdout_log = if ($latestOut) { $latestOut.FullName } else { $null }
    latest_stderr_log = if ($latestErr) { $latestErr.FullName } else { $null }
    state_file = if (Test-Path -LiteralPath $statePath) { $statePath } else { $null }
}

$payload | ConvertTo-Json -Depth 5

if ($latestOut) {
    Write-Host ""
    Write-Host "Latest stdout tail:"
    Get-Content -LiteralPath $latestOut.FullName -Tail 20 -ErrorAction SilentlyContinue
}

if ($latestErr -and $latestErr.Length -gt 0) {
    Write-Host ""
    Write-Host "Latest stderr tail:"
    Get-Content -LiteralPath $latestErr.FullName -Tail 20 -ErrorAction SilentlyContinue
}
