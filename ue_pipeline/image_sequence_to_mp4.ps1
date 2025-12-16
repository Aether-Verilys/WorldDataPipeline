# Convert Image Sequence to MP4 using FFmpeg
# Converts rendered image sequences to H.264 MP4 video

param(
    [Parameter(Mandatory=$false)]
    [string]$InputDir,
    
    [Parameter(Mandatory=$false)]
    [string]$OutputFile,
    
    [Parameter(Mandatory=$false)]
    [int]$Framerate = 30,
    
    [Parameter(Mandatory=$false)]
    [string]$Quality = "high"  # high, medium, low
)

# ============================================================
# Configuration
# ============================================================

# FFmpeg executable path
$FFmpeg = "ffmpeg"  # Assumes ffmpeg is in PATH, or specify full path like "C:\ffmpeg\bin\ffmpeg.exe"

# ============================================================

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Image Sequence to MP4 Converter" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if FFmpeg is available
try {
    $null = & $FFmpeg -version 2>&1
} catch {
    Write-Host "ERROR: FFmpeg not found. Please install FFmpeg or specify the path." -ForegroundColor Red
    Write-Host "Download from: https://ffmpeg.org/download.html" -ForegroundColor Yellow
    exit 1
}

# If no input directory specified, scan for recent output directories
if (-not $InputDir) {
    $outputRoot = "D:\WorldDataPipeline\output"
    if (Test-Path $outputRoot) {
        Write-Host "Scanning for image sequences in: $outputRoot" -ForegroundColor Yellow
        
        # Find all directories with image files
        $imageDirs = Get-ChildItem -Path $outputRoot -Recurse -Directory | Where-Object {
            (Get-ChildItem -Path $_.FullName -Filter "*.png" -ErrorAction SilentlyContinue).Count -gt 0 -or
            (Get-ChildItem -Path $_.FullName -Filter "*.jpg" -ErrorAction SilentlyContinue).Count -gt 0 -or
            (Get-ChildItem -Path $_.FullName -Filter "*.exr" -ErrorAction SilentlyContinue).Count -gt 0
        } | Sort-Object LastWriteTime -Descending
        
        if ($imageDirs.Count -eq 0) {
            Write-Host "ERROR: No image sequences found in $outputRoot" -ForegroundColor Red
            exit 1
        }
        
        Write-Host "Found $($imageDirs.Count) directories with images:" -ForegroundColor Green
        for ($i = 0; $i -lt [Math]::Min(10, $imageDirs.Count); $i++) {
            $dir = $imageDirs[$i]
            $imageCount = (Get-ChildItem -Path $dir.FullName -Filter "*.png","*.jpg","*.exr" -ErrorAction SilentlyContinue).Count
            Write-Host "  [$($i+1)] $($dir.FullName) ($imageCount images)" -ForegroundColor Gray
        }
        
        # Use most recent directory
        $InputDir = $imageDirs[0].FullName
        Write-Host ""
        Write-Host "Using most recent: $InputDir" -ForegroundColor Yellow
    } else {
        Write-Host "ERROR: No input directory specified and default output path not found" -ForegroundColor Red
        Write-Host "Usage: .\image_sequence_to_mp4.ps1 -InputDir <path> [-OutputFile <path>] [-Framerate 30] [-Quality high]" -ForegroundColor Yellow
        exit 1
    }
}

# Validate input directory
if (-not (Test-Path $InputDir)) {
    Write-Host "ERROR: Input directory not found: $InputDir" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Input Directory: $InputDir" -ForegroundColor Yellow

# Detect image format and pattern
$pngFiles = Get-ChildItem -Path $InputDir -Filter "*.png" | Sort-Object Name
$jpgFiles = Get-ChildItem -Path $InputDir -Filter "*.jpg" | Sort-Object Name
$exrFiles = Get-ChildItem -Path $InputDir -Filter "*.exr" | Sort-Object Name

$imageFiles = @()
$imageExt = ""

if ($pngFiles.Count -gt 0) {
    $imageFiles = $pngFiles
    $imageExt = "png"
} elseif ($jpgFiles.Count -gt 0) {
    $imageFiles = $jpgFiles
    $imageExt = "jpg"
} elseif ($exrFiles.Count -gt 0) {
    $imageFiles = $exrFiles
    $imageExt = "exr"
} else {
    Write-Host "ERROR: No supported image files found (png, jpg, exr)" -ForegroundColor Red
    exit 1
}

Write-Host "Found $($imageFiles.Count) $imageExt images" -ForegroundColor Green

if ($imageFiles.Count -eq 0) {
    Write-Host "ERROR: No images to convert" -ForegroundColor Red
    exit 1
}

# Detect naming pattern
$firstFile = $imageFiles[0].Name
Write-Host "First frame: $firstFile" -ForegroundColor Gray

# Try to detect frame number pattern
if ($firstFile -match '(\d+)\.\w+$') {
    $frameNumber = $matches[1]
    $frameLength = $frameNumber.Length
    $baseName = $firstFile -replace "\d+\.\w+$", ""
    $inputPattern = "$baseName%0$($frameLength)d.$imageExt"
    Write-Host "Detected pattern: $inputPattern" -ForegroundColor Gray
} else {
    Write-Host "WARNING: Could not detect frame numbering pattern, will use glob pattern" -ForegroundColor Yellow
    $inputPattern = "*.$imageExt"
}

# Generate output file name if not specified
if (-not $OutputFile) {
    $parentDirName = Split-Path $InputDir -Leaf
    $OutputFile = Join-Path $InputDir "$parentDirName.mp4"
}

Write-Host "Output File: $OutputFile" -ForegroundColor Yellow
Write-Host "Framerate: $Framerate fps" -ForegroundColor Yellow
Write-Host "Quality: $Quality" -ForegroundColor Yellow
Write-Host ""

# Set quality parameters
switch ($Quality.ToLower()) {
    "high" {
        $crf = 18
        $preset = "slow"
    }
    "medium" {
        $crf = 23
        $preset = "medium"
    }
    "low" {
        $crf = 28
        $preset = "fast"
    }
    default {
        $crf = 23
        $preset = "medium"
    }
}

Write-Host "Encoding settings: CRF=$crf, Preset=$preset" -ForegroundColor Gray
Write-Host ""

# Build FFmpeg command
$ffmpegArgs = @(
    "-y"  # Overwrite output file
    "-framerate", $Framerate
    "-i", (Join-Path $InputDir $inputPattern)
    "-c:v", "libx264"
    "-preset", $preset
    "-crf", $crf
    "-pix_fmt", "yuv420p"
    "-movflags", "+faststart"
    "`"$OutputFile`""
)

Write-Host "Running FFmpeg..." -ForegroundColor Green
Write-Host "Command: $FFmpeg $($ffmpegArgs -join ' ')" -ForegroundColor Gray
Write-Host ""
Write-Host "----------------------------------------" -ForegroundColor Cyan

# Run FFmpeg
try {
    $process = Start-Process -FilePath $FFmpeg -ArgumentList $ffmpegArgs -NoNewWindow -Wait -PassThru
    
    Write-Host ""
    Write-Host "----------------------------------------" -ForegroundColor Cyan
    
    if ($process.ExitCode -eq 0) {
        if (Test-Path $OutputFile) {
            $fileSize = (Get-Item $OutputFile).Length / 1MB
            Write-Host "✓ Conversion successful!" -ForegroundColor Green
            Write-Host "Output: $OutputFile" -ForegroundColor Green
            Write-Host "Size: $([math]::Round($fileSize, 2)) MB" -ForegroundColor Green
            
            # Calculate duration
            $duration = $imageFiles.Count / $Framerate
            Write-Host "Duration: $([math]::Round($duration, 2)) seconds" -ForegroundColor Green
        } else {
            Write-Host "ERROR: Output file not created" -ForegroundColor Red
            exit 1
        }
    } else {
        Write-Host "ERROR: FFmpeg failed with exit code: $($process.ExitCode)" -ForegroundColor Red
        exit $process.ExitCode
    }
} catch {
    Write-Host "ERROR: Failed to run FFmpeg: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Done!" -ForegroundColor Cyan
