# UE Render Job Executor (Headless Mode)
# Execute a render job using command-line MRQ execution

param(
    [Parameter(Mandatory=$true)]
    [string]$ManifestPath
)

# ============================================================
# Configuration
# ============================================================

# Default paths (used if not specified in manifest)
$DefaultUEEditor = "D:\Program Files\Epic Games\UE_5.7\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
$DefaultProject = "F:\UE_Projects\NorthernForest\NorthernForest.uproject"

# ============================================================

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "UE Render Job Executor (Headless Mode)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check manifest file
if (-not (Test-Path $ManifestPath)) {
    Write-Host "ERROR: Manifest file not found: $ManifestPath" -ForegroundColor Red
    exit 1
}

# Parse manifest
try {
    $manifest = Get-Content $ManifestPath | ConvertFrom-Json
    $jobId = $manifest.job_id
    $jobType = $manifest.job_type
    
    if ($jobType -ne "render") {
        Write-Host "ERROR: Invalid job type '$jobType', expected 'render'" -ForegroundColor Red
        exit 1
    }
    
    # Read UE paths from manifest or use defaults
    if ($manifest.ue_config) {
        $UEEditor = if ($manifest.ue_config.editor_path) { $manifest.ue_config.editor_path.Replace("UnrealEditor.exe", "UnrealEditor-Cmd.exe") } else { $DefaultUEEditor }
        $Project = if ($manifest.ue_config.project_path) { $manifest.ue_config.project_path } else { $DefaultProject }
    } else {
        $UEEditor = $DefaultUEEditor
        $Project = $DefaultProject
        Write-Host "WARNING: No ue_config in manifest, using default paths" -ForegroundColor Yellow
    }
    
    # Get render configuration
    $sequence = $manifest.sequence
    $map = $manifest.map
    $renderConfig = $manifest.rendering
    $configPreset = $renderConfig.preset
    $outputPath = $renderConfig.output_path
    
    Write-Host "Job ID:       $jobId" -ForegroundColor Yellow
    Write-Host "Sequence:     $sequence" -ForegroundColor Yellow
    Write-Host "Map:          $map" -ForegroundColor Yellow
    Write-Host "Config:       $configPreset" -ForegroundColor Yellow
    Write-Host "Output:       $outputPath" -ForegroundColor Yellow
} catch {
    Write-Host "ERROR: Cannot parse manifest: $_" -ForegroundColor Red
    exit 1
}

Write-Host "UE Editor:    $UEEditor" -ForegroundColor Yellow
Write-Host "Project:      $Project" -ForegroundColor Yellow
Write-Host ""

# Check required files
if (-not (Test-Path $UEEditor)) {
    Write-Host "ERROR: UE Editor not found at: $UEEditor" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $Project)) {
    Write-Host "ERROR: Project not found at: $Project" -ForegroundColor Red
    exit 1
}

# Ensure output directory exists
if ($outputPath) {
    $absOutputPath = [System.IO.Path]::GetFullPath($outputPath)
    if (-not (Test-Path $absOutputPath)) {
        New-Item -ItemType Directory -Path $absOutputPath -Force | Out-Null
        Write-Host "Created output directory: $absOutputPath" -ForegroundColor Green
    }
}

Write-Host "Starting headless render job..." -ForegroundColor Green
Write-Host ""

# Build UE command-line arguments using Python worker script
# Note: This is the correct way to trigger MRQ rendering from command line
$pythonWorkerScript = Join-Path $PSScriptRoot "python\worker_render.py"

if (-not (Test-Path $pythonWorkerScript)) {
    Write-Host "ERROR: Python worker script not found: $pythonWorkerScript" -ForegroundColor Red
    exit 1
}

# Set manifest path as environment variable for Python script to read
$env:UE_RENDER_MANIFEST = $ManifestPath
Write-Host "Manifest Path: $ManifestPath" -ForegroundColor Gray

$ueArgs = @(
    "`"$Project`""
    
    # Execute Python script that calls MRQ API internally
    "-ExecutePythonScript=`"$pythonWorkerScript`""
    
    # Rendering optimization flags for headless mode
    "-RenderOffscreen"
    
    # Resolution settings
    "-ResX=1920"
    "-ResY=1080"
    "-ForceRes"
    
    # Headless/automation flags
    "-Windowed"
    "-NoLoadingScreen"
    "-NoScreenMessages"
    "-NoSplash"
    "-Unattended"
    "-NoSound"
    "-AllowStdOutLogVerbosity"
    
    # Logging
    "-log"
    "-stdout"
    "-FullStdOutLogOutput"
    "LOG=RenderLog_$jobId.txt"
)

Write-Host "Command: $UEEditor $($ueArgs -join ' ')" -ForegroundColor Gray
Write-Host ""
Write-Host "----------------------------------------" -ForegroundColor Cyan

# Launch UE
try {
    $ueProcess = Start-Process -FilePath $UEEditor -ArgumentList $ueArgs -PassThru -NoNewWindow -Wait
    
    Write-Host ""
    Write-Host "----------------------------------------" -ForegroundColor Cyan
    
    if ($ueProcess.ExitCode -eq 0) {
        Write-Host "Render job completed successfully" -ForegroundColor Green
        exit 0
    } else {
        Write-Host "Render job failed with exit code: $($ueProcess.ExitCode)" -ForegroundColor Red
        exit $ueProcess.ExitCode
    }
} catch {
    Write-Host "ERROR: Failed to launch UE: $_" -ForegroundColor Red
    exit 1
}
