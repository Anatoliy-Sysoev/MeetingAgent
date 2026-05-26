param(
    [Parameter(Mandatory = $true)]
    [string]$InputPath,

    [string]$OutputDir = "",
    [string]$GigaAMRoot = "",
    [string]$CacheRoot = "",
    [string]$Model = "v3_e2e_rnnt",
    [int]$ChunkSeconds = 24,
    [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"

$UserProfile = [Environment]::GetFolderPath("UserProfile")

function Resolve-FullPath([string]$PathValue) {
    return [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $PathValue).Path)
}

if (-not $GigaAMRoot) {
    $GigaAMRoot = Join-Path $UserProfile "GigaAM"
}
if (-not $CacheRoot) {
    $CacheRoot = Join-Path $env:ProgramData "gigaam_cache"
}
if (-not $OutputDir) {
    $baseName = [System.IO.Path]::GetFileNameWithoutExtension($InputPath)
    $safeName = ($baseName -replace '[^\p{L}\p{Nd}_-]+', '_').Trim('_')
    if (-not $safeName) {
        $safeName = "gigaam_run"
    }
    $OutputDir = Join-Path (Join-Path $UserProfile "Downloads") ("gigaam_" + $safeName)
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$inputFull = Resolve-FullPath $InputPath
$outputFull = [System.IO.Path]::GetFullPath($OutputDir)
$chunksDir = Join-Path $outputFull "chunks_24s"
$wavPath = Join-Path $outputFull "audio_16k_mono.wav"

New-Item -ItemType Directory -Force -Path $outputFull | Out-Null
New-Item -ItemType Directory -Force -Path $chunksDir | Out-Null
New-Item -ItemType Directory -Force -Path $CacheRoot | Out-Null

$ffmpeg = Get-Command ffmpeg -ErrorAction Stop
$ffprobe = Get-Command ffprobe -ErrorAction SilentlyContinue

& $ffmpeg.Source -y -i $inputFull -vn -ac 1 -ar 16000 -c:a pcm_s16le $wavPath
& $ffmpeg.Source -y -i $wavPath -f segment -segment_time $ChunkSeconds -ac 1 -ar 16000 -c:a pcm_s16le (Join-Path $chunksDir "chunk_%04d.wav")

$duration = $null
if ($ffprobe) {
    $duration = & $ffprobe.Source -v error -show_entries format=duration -of default=nokey=1:noprint_wrappers=1 $wavPath
}

& $PythonExe (Join-Path $repoRoot "scripts\gigaam_transcribe_chunks.py") `
    --chunks-dir $chunksDir `
    --output-dir $outputFull `
    --source-file $inputFull `
    --gigaam-root $GigaAMRoot `
    --cache-root $CacheRoot `
    --model $Model `
    --chunk-seconds $ChunkSeconds

$chunkCount = (Get-ChildItem -LiteralPath $chunksDir -Filter "chunk_*.wav").Count
[pscustomobject]@{
    input = $inputFull
    output_dir = $outputFull
    wav = $wavPath
    duration_sec = $duration
    chunks = $chunkCount
    model = $Model
    cache_root = $CacheRoot
} | ConvertTo-Json -Depth 3
