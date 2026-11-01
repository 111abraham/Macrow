# Link LM Studio Models to Ollama via Zero-Copy NTFS Hardlinks
param (
    [string]$LmStudioDir = "$env:USERPROFILE\.lmstudio\models",
    [string]$OllamaExe = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe",
    [switch]$All,
    [string]$SelectModel
)

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  LM Studio -> Ollama Zero-Copy Model Linker (NTFS Hardlinks)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

if (-not (Test-Path $OllamaExe)) {
    $found = Get-Command ollama -ErrorAction SilentlyContinue
    if ($found) {
        $OllamaExe = $found.Source
    } else {
        Write-Error "Ollama executable not found. Make sure Ollama is installed."
        exit 1
    }
}

if (-not (Test-Path $LmStudioDir)) {
    Write-Error "LM Studio models directory not found at $LmStudioDir"
    exit 1
}

$ollamaBlobsDir = "$env:USERPROFILE\.ollama\models\blobs"
if (-not (Test-Path $ollamaBlobsDir)) {
    New-Item -ItemType Directory -Path $ollamaBlobsDir -Force | Out-Null
}

# Scan for all base GGUF models (excluding mmproj files from being treated as base models)
$allGgufs = Get-ChildItem -Path $LmStudioDir -Recurse -Filter "*.gguf" -File
$baseModels = $allGgufs | Where-Object { $_.Name -notlike "mmproj*" }

if ($baseModels.Count -eq 0) {
    Write-Host "No GGUF models found in $LmStudioDir." -ForegroundColor Yellow
    exit 0
}

Write-Host "`nFound $($baseModels.Count) LM Studio models:" -ForegroundColor Green
$modelList = @()
$idx = 1
foreach ($m in $baseModels) {
    $dir = $m.DirectoryName
    $sizeGB = [math]::Round($m.Length / 1GB, 2)
    # Check for matching mmproj in same folder
    $mmproj = Get-ChildItem -Path $dir -Filter "mmproj*.gguf" -File | Select-Object -First 1

    # Generate a clean, lowercase, alphanumeric identifier for Ollama
    $cleanName = $m.BaseName.ToLower() -replace "[^a-z0-9\-_\.]", "-"
    $cleanName = "lmstudio-" + ($cleanName -replace "-+", "-").Trim("-")

    $info = [PSCustomObject]@{
        Index = $idx
        Name = $cleanName
        FileName = $m.Name
        FullPath = $m.FullName
        SizeGB = $sizeGB
        Length = $m.Length
        Mmproj = if ($mmproj) { $mmproj.FullName } else { $null }
        MmprojLength = if ($mmproj) { $mmproj.Length } else { 0 }
    }
    $modelList += $info
    $mmInfo = if ($mmproj) { " [Vision/Multimodal: $($mmproj.Name)]" } else { "" }
    Write-Host "  [$idx] $($info.Name) ($($sizeGB) GB)$mmInfo" -ForegroundColor White
    $idx++
}

# Determine which models to link
$targets = @()
if ($All) {
    $targets = $modelList
} elseif ($SelectModel) {
    $targets = $modelList | Where-Object { $_.Name -like "*$SelectModel*" -or $_.FileName -like "*$SelectModel*" }
} else {
    Write-Host "`nSelect a model number to link into Ollama (or 'all' for all models): " -NoNewline -ForegroundColor Cyan
    $choice = Read-Host
    if ($choice -eq "all") {
        $targets = $modelList
    } else {
        $selIdx = [int]$choice
        $targets = $modelList | Where-Object { $_.Index -eq $selIdx }
    }
}

if ($targets.Count -eq 0) {
    Write-Host "No valid model selected." -ForegroundColor Yellow
    exit 0
}

$tempDir = Join-Path $env:TEMP "ollama_import"
if (-not (Test-Path $tempDir)) {
    New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
}

$totalSavedGB = 0

foreach ($t in $targets) {
    Write-Host "`n------------------------------------------------------------" -ForegroundColor DarkCyan
    Write-Host "Linking model: $($t.Name) ($($t.SizeGB) GB)" -ForegroundColor Cyan
    Write-Host "Source: $($t.FullPath)" -ForegroundColor Gray

    # 1. Create Modelfile
    $modelfilePath = Join-Path $tempDir "Modelfile_$($t.Name)"
    $modelfileContent = "FROM `"$($t.FullPath)`"`n"
    if ($t.Mmproj) {
        Write-Host "Multimodal Projector attached: $($t.Mmproj)" -ForegroundColor Magenta
        $modelfileContent += "FROM `"$($t.Mmproj)`"`n"
    }
    Set-Content -Path $modelfilePath -Value $modelfileContent -Encoding UTF8

    # 2. Run ollama create
    Write-Host "Registering with Ollama (running 'ollama create $($t.Name)')..." -ForegroundColor Yellow
    $createOutput = & $OllamaExe create $t.Name -f $modelfilePath 2>&1
    Write-Host ($createOutput -join "`n") -ForegroundColor Gray

    # 3. Find created blob by matching file size in $ollamaBlobsDir
    $matchedBlob = Get-ChildItem -Path $ollamaBlobsDir -File | Where-Object { $_.Length -eq $t.Length } | Sort-Object LastWriteTime -Descending | Select-Object -First 1

    if ($matchedBlob) {
        Write-Host "Found created blob: $($matchedBlob.Name) ($([math]::Round($matchedBlob.Length / 1GB, 2)) GB)" -ForegroundColor Green
        Write-Host "Replacing duplicated blob with zero-copy NTFS Hardlink..." -ForegroundColor Yellow
        try {
            Remove-Item -Path $matchedBlob.FullName -Force
            New-Item -ItemType HardLink -Path $matchedBlob.FullName -Target $t.FullPath -Force | Out-Null
            Write-Host "Success! Converted blob to NTFS Hardlink. 0 bytes extra disk space used!" -ForegroundColor Green
            $totalSavedGB += $t.SizeGB
        } catch {
            Write-Warning "Failed to convert blob to hard link: $_"
        }
    }

    # If mmproj blob was created, hardlink it too
    if ($t.Mmproj -and $t.MmprojLength -gt 0) {
        $matchedMmBlob = Get-ChildItem -Path $ollamaBlobsDir -File | Where-Object { $_.Length -eq $t.MmprojLength } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($matchedMmBlob) {
            try {
                Remove-Item -Path $matchedMmBlob.FullName -Force
                New-Item -ItemType HardLink -Path $matchedMmBlob.FullName -Target $t.Mmproj -Force | Out-Null
                Write-Host "Success! Converted mmproj blob to zero-copy NTFS Hardlink!" -ForegroundColor Green
            } catch {
                Write-Warning "Failed to hardlink mmproj blob: $_"
            }
        }
    }

    # Clean up temporary Modelfile
    Remove-Item -Path $modelfilePath -Force -ErrorAction SilentlyContinue
}

# Clean up temp folder
Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "`n============================================================" -ForegroundColor Green
Write-Host "  COMPLETED! Total disk space saved: $([math]::Round($totalSavedGB, 2)) GB" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "`nCurrent Ollama models:" -ForegroundColor Cyan
& $OllamaExe list
