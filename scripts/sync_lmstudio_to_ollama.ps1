# ==============================================================================
# Automatic Zero-Copy Model Synchronizer: LM Studio -> Ollama (NTFS Hardlinks)
# Guarantees that models in C:\Users\PC\.lmstudio\models are instantly shared
# with Ollama without duplicate downloads or wasted SSD disk space.
# ==============================================================================
param (
    [string]$LmStudioDir = "$env:USERPROFILE\.lmstudio\models",
    [string]$OllamaExe = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe",
    [string]$BlobDir = "$env:USERPROFILE\.ollama\blobs"
)

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  LM Studio <-> Ollama Zero-Copy Model Synchronizer" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

if (-not (Test-Path $OllamaExe)) {
    $found = Get-Command ollama -ErrorAction SilentlyContinue
    if ($found) {
        $OllamaExe = $found.Source
    } else {
        Write-Error "Ollama executable not found. Ensure Ollama is installed."
        exit 1
    }
}

if (-not (Test-Path $LmStudioDir)) {
    Write-Warning "LM Studio models directory not found at $LmStudioDir"
    exit 0
}

if (-not (Test-Path $BlobDir)) {
    # Check alternate models\blobs directory
    $alt = "$env:USERPROFILE\.ollama\models\blobs"
    if (Test-Path $alt) { $BlobDir = $alt }
}

# Fetch currently registered Ollama models
$existingList = & $OllamaExe list 2>&1
$existingNames = @()
foreach ($line in $existingList) {
    if ($line -match '^([a-zA-Z0-9\._\-:]+)\s+') {
        $existingNames += $matches[1].ToLower()
    }
}

Write-Host "Existing Ollama models: $($existingNames -join ', ')" -ForegroundColor DarkGray

# Scan for GGUF files (excluding multimodal projectors from being treated as base models)
$allGgufs = Get-ChildItem -Path $LmStudioDir -Recurse -Filter "*.gguf" -File
$baseModels = $allGgufs | Where-Object { $_.Name -notlike "mmproj*" }

if ($baseModels.Count -eq 0) {
    Write-Host "No GGUF models found in $LmStudioDir." -ForegroundColor Yellow
    exit 0
}

function Get-OllamaTagForModel($file) {
    $fn = $file.Name.ToLower()
    $dn = $file.Directory.Name.ToLower()

    if ($fn -match "gemma-4-e4b") { return "gemma4:e4b" }
    if ($fn -match "gemma-4-12b") { return "gemma4:12b" }
    if ($fn -match "gemma-4-26b") { return "gemma4:26b" }
    if ($fn -match "qwen3.8-27b.*smaller") { return "qwen3.8:27b-smaller" }
    if ($fn -match "qwen3.8-27b") { return "qwen3.8:27b" }

    # Fallback clean name
    $clean = $file.BaseName.ToLower() -replace "[^a-z0-9\-_\.]", "-"
    return "lmstudio-" + ($clean -replace "-+", "-").Trim("-")
}

$tempDir = Join-Path $env:TEMP "ollama_sync"
if (-not (Test-Path $tempDir)) {
    New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
}

$syncedCount = 0
$totalSavedBytes = 0

foreach ($m in $baseModels) {
    $tag = Get-OllamaTagForModel $m
    $tagBase = $tag.Split(':')[0]

    # Check if this model or tag is already in Ollama
    $isRegistered = $false
    foreach ($en in $existingNames) {
        if ($en -eq $tag -or $en -eq "$($tag):latest" -or $en.StartsWith($tag)) {
            $isRegistered = $true
            break
        }
    }

    if ($isRegistered) {
        Write-Host "  [OK] $tag is registered in Ollama (Source: $($m.Name))" -ForegroundColor Green
        continue
    }

    Write-Host "`nRegistering new model into Ollama: $tag" -ForegroundColor Cyan
    Write-Host "  Source: $($m.FullName)" -ForegroundColor DarkGray

    # Check for matching mmproj projector in the same directory
    $dir = $m.DirectoryName
    $mmproj = Get-ChildItem -Path $dir -Filter "mmproj*.gguf" -File | Select-Object -First 1

    # Create temporary Modelfile
    $modelfile = Join-Path $tempDir "Modelfile_$($tag -replace ':', '_')"
    $content = "FROM `"$($m.FullName)`"`n"
    if ($mmproj) {
        Write-Host "  Attaching Multimodal Projector: $($mmproj.Name)" -ForegroundColor Magenta
        $content += "FROM `"$($mmproj.FullName)`"`n"
    }
    Set-Content -Path $modelfile -Value $content -Encoding UTF8

    # Run ollama create
    & $OllamaExe create $tag -f $modelfile

    # Replace duplicate blobs with NTFS hardlinks
    $baseLen = $m.Length
    $projLen = if ($mmproj) { $mmproj.Length } else { 0 }

    $matchedBlobs = Get-ChildItem -Path $BlobDir -File | Where-Object { $_.Length -eq $baseLen -or ($projLen -gt 0 -and $_.Length -eq $projLen) }
    foreach ($b in $matchedBlobs) {
        if ($b.Length -eq $baseLen) {
            Remove-Item $b.FullName -Force
            New-Item -ItemType HardLink -Path $b.FullName -Target $m.FullName -Force | Out-Null
            $totalSavedBytes += $baseLen
            Write-Host "  OK: Converted base blob to NTFS HardLink! [0 extra bytes]" -ForegroundColor Green
        } elseif ($projLen -gt 0 -and $b.Length -eq $projLen) {
            Remove-Item $b.FullName -Force
            New-Item -ItemType HardLink -Path $b.FullName -Target $mmproj.FullName -Force | Out-Null
            $totalSavedBytes += $projLen
            Write-Host "  OK: Converted mmproj blob to NTFS HardLink! [0 extra bytes]" -ForegroundColor Green
        }
    }

    Remove-Item $modelfile -Force -ErrorAction SilentlyContinue
    $syncedCount++
}

Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "`n============================================================" -ForegroundColor Cyan
$savedGB = [math]::Round($totalSavedBytes / 1GB, 2)
Write-Host "Sync Complete! Newly synced: $syncedCount models. Saved: $savedGB GB via NTFS Hardlinks." -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
