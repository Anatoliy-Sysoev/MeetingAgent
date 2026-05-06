$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $Root "logs"

Write-Host "MeetingAgent RAG status"
Write-Host "Root: $Root"
Write-Host ""

$latestLog = Get-ChildItem -LiteralPath $LogDir -Filter "full_rag_*.log" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

$done = Get-ChildItem -LiteralPath $LogDir -Filter "full_rag_*.done.txt" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

$failed = Get-ChildItem -LiteralPath $LogDir -Filter "full_rag_*.failed.txt" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if ($done) {
    Write-Host "DONE:"
    Get-Content -LiteralPath $done.FullName
}
elseif ($failed) {
    Write-Host "FAILED:"
    Get-Content -LiteralPath $failed.FullName
}
else {
    Write-Host "No done/failed marker yet. Build may still be running."
}

Write-Host ""
Write-Host "Python / Ollama related processes:"
Get-Process powershell,python,ollama -ErrorAction SilentlyContinue |
    Select-Object Id,ProcessName,StartTime,CPU |
    Format-Table -AutoSize

if ($latestLog) {
    Write-Host ""
    Write-Host "Latest log: $($latestLog.FullName)"
    Write-Host "Last 40 lines:"
    Get-Content -Tail 40 -LiteralPath $latestLog.FullName
}
