# Convert rendered frame sequences to H264 MP4 videos
# Usage: .\convert_frames_to_video.ps1 -ConfigPath "examples\job_render_1218.json"

param(
    [Parameter(Mandatory=$true)]
    [string]$ConfigPath,
    
    [int]$Framerate = 0,  # 0 means read from config
    
    [string]$VideoCodec = "libx264",
    
    [string]$CRF = "23",
    
    [switch]$KeepFrames
)

$ErrorActionPreference = "Continue"

function Write-ErrorAndExit {
    param([string]$Message)
    Write-Host ""
    Write-Host "ERROR: $Message" -ForegroundColor Red
    Write-Host "Press any key to exit..." -ForegroundColor Yellow
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "Frame Sequence to Video Converter" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# Check if ffmpeg is available
try {
    $ffmpegCheck = Get-Command ffmpeg -ErrorAction Stop
    $ffmpegVersion = & ffmpeg -version 2>&1 | Select-Object -First 1
    Write-Host "FFmpeg found: $ffmpegVersion" -ForegroundColor Green
} catch {
    Write-ErrorAndExit "FFmpeg not found. Please install FFmpeg and add it to PATH."
}

# Load configuration
if (-not (Test-Path $ConfigPath)) {
    Write-ErrorAndExit "Config file not found: $ConfigPath"
}

Write-Host "Loading config: $ConfigPath" -ForegroundColor Yellow
try {
    $config = Get-Content $ConfigPath -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
} catch {
    Write-ErrorAndExit "Failed to parse config file: $_"
}

# Extract paths from config
try {
    $baseOutputPath = $config.rendering.output_path
    $projectPath = $config.ue_config.project_path
    $mapPath = $config.map
    $sequencePath = $config.sequence
    
    # Get framerate from config if not specified
    if ($Framerate -eq 0) {
        if ($config.rendering.PSObject.Properties.Name -contains 'framerate') {
            $Framerate = $config.rendering.framerate
            Write-Host "Using framerate from config: $Framerate fps" -ForegroundColor Cyan
        } else {
            $Framerate = 30  # Default fallback
            Write-Host "No framerate in config, using default: $Framerate fps" -ForegroundColor Yellow
        }
    }
    
    if (-not $baseOutputPath -or -not $projectPath -or -not $mapPath -or -not $sequencePath) {
        Write-ErrorAndExit "Config missing required fields (output_path, project_path, map, or sequence)"
    }
} catch {
    Write-ErrorAndExit "Failed to read config fields: $_"
}

# Extract scene ID from map path
# Map path format: /Game/S0001/LevelPrototyping/Lvl_FirstPerson
$sceneId = "UnknownScene"
$pathParts = $mapPath -split '/'

# Try to find scene ID in path (format: S####)
foreach ($part in $pathParts) {
    if ($part -match '^S\d{4}$') {
        $sceneId = $part
        break
    }
}

# If no scene ID found in path, try to lookup from config scenes
if ($sceneId -eq "UnknownScene" -and $config.PSObject.Properties.Name -contains 'scenes') {
    foreach ($scene in $config.scenes) {
        foreach ($map in $scene.maps) {
            if ($map.path -eq $mapPath) {
                $sceneId = $scene.id
                break
            }
        }
        if ($sceneId -ne "UnknownScene") {
            break
        }
    }
}

# Extract map name
$mapName = $mapPath.Split('/')[-1]

# Extract sequence name
$sequenceName = $sequencePath.Split('/')[-1]

# Construct output directory path: base/scene_id/map_name/sequence_name
$outputDir = Join-Path $baseOutputPath $sceneId
$outputDir = Join-Path $outputDir $mapName
$outputDir = Join-Path $outputDir $sequenceName

Write-Host "Scene: $sceneId" -ForegroundColor Cyan
Write-Host "Map: $mapName" -ForegroundColor Cyan
Write-Host "Sequence: $sequenceName" -ForegroundColor Cyan
Write-Host "Output directory: $outputDir" -ForegroundColor Cyan

# Check if output directory exists
if (-not (Test-Path $outputDir)) {
    Write-ErrorAndExit "Output directory not found: $outputDir`nMake sure rendering has completed successfully."
}

# Find frame sequences
$framePattern = "$sequenceName.*.png"
try {
    $frames = Get-ChildItem -Path $outputDir -Filter $framePattern -ErrorAction Stop | Sort-Object Name
} catch {
    Write-ErrorAndExit "Failed to search for frames: $_"
}

if ($frames.Count -eq 0) {
    Write-ErrorAndExit "No frame sequences found matching pattern: $framePattern`nDirectory: $outputDir"
}

Write-Host "Found $($frames.Count) frames" -ForegroundColor Green
Write-Host "First frame: $($frames[0].Name)" -ForegroundColor Gray
Write-Host "Last frame: $($frames[-1].Name)" -ForegroundColor Gray

# Prepare output video path
$outputVideo = Join-Path $outputDir "$sequenceName.mp4"

# Check if video already exists
if (Test-Path $outputVideo) {
    Write-Host "Warning: Video already exists: $outputVideo" -ForegroundColor Yellow
    $response = Read-Host "Overwrite? (y/n)"
    if ($response -ne 'y') {
        Write-Host "Cancelled." -ForegroundColor Yellow
        exit 0
    }
    Remove-Item $outputVideo -Force
}

# FFmpeg command to convert frames to video
Write-Host ""
Write-Host "Converting frames to video..." -ForegroundColor Yellow
Write-Host "  Framerate: $Framerate fps" -ForegroundColor Gray
Write-Host "  Codec: $VideoCodec" -ForegroundColor Gray
Write-Host "  CRF: $CRF" -ForegroundColor Gray
Write-Host "  Output: $outputVideo" -ForegroundColor Gray

# Construct FFmpeg input pattern
# Pattern: Scene_1_02.%04d.png (for Scene_1_02.0001.png, Scene_1_02.0002.png, ...)
$inputPattern = "$sequenceName.%04d.png"

$ffmpegArgs = @(
    "-framerate", $Framerate,
    "-start_number", "1",
    "-i", $inputPattern,
    "-c:v", $VideoCodec,
    "-crf", $CRF,
    "-pix_fmt", "yuv420p",
    "-y",
    "$sequenceName.mp4"
)

try {
    # Change to output directory to use relative paths
    Push-Location $outputDir
    
    Write-Host ""
    Write-Host "Running FFmpeg..." -ForegroundColor Yellow
    Write-Host "Command: ffmpeg $($ffmpegArgs -join ' ')" -ForegroundColor Gray
    
    # Run FFmpeg
    $ffmpegOutput = & ffmpeg @ffmpegArgs 2>&1
    
    Pop-Location
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "FFmpeg output:" -ForegroundColor Yellow
        Write-Host $ffmpegOutput -ForegroundColor Gray
        Write-ErrorAndExit "FFmpeg failed with exit code: $LASTEXITCODE"
    }
    
    Write-Host "Video created successfully!" -ForegroundColor Green
    
    # Get video info
    $videoInfo = Get-Item $outputVideo
    $videoSizeMB = [math]::Round($videoInfo.Length / 1MB, 2)
    Write-Host "  Size: $videoSizeMB MB" -ForegroundColor Gray
    Write-Host "  Path: $outputVideo" -ForegroundColor Gray
    
} catch {
    Write-Host "Error during video conversion: $_" -ForegroundColor Red
    exit 1
}

# Delete frame sequences if successful
if (-not $KeepFrames) {
    Write-Host ""
    Write-Host "Deleting frame sequences..." -ForegroundColor Yellow
    
    $deletedCount = 0
    foreach ($frame in $frames) {
        try {
            Remove-Item $frame.FullName -Force
            $deletedCount++
        } catch {
            Write-Host "Warning: Failed to delete $($frame.Name): $_" -ForegroundColor Yellow
        }
    }
    
    Write-Host "Deleted $deletedCount frames" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "Keeping frame sequences (--KeepFrames flag set)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "Conversion complete!" -ForegroundColor Green
Write-Host "Video: $outputVideo" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press any key to exit..." -ForegroundColor Yellow
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
