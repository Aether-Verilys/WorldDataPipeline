# UE Render Job Executor
# Execute a render job using UnrealEditor-Cmd.exe (headless mode)

param(
    [Parameter(Mandatory=$true)]
    [string]$ManifestPath
)

# ============================================================
# Configuration
# ============================================================

# Worker Render script path
$WorkerRender = "$PSScriptRoot\python\worker_render.py"

# Default paths (used if not specified in manifest)
$DefaultUEEditor = "D:\Program Files\Epic Games\UE_5.7\Engine\Binaries\Win64\UnrealEditor.exe"
$DefaultProject = "F:\UE_Projects\NorthernForest\NorthernForest.uproject"

# ============================================================

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "UE Render Job Executor" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check manifest file
if (-not (Test-Path $ManifestPath)) {
    Write-Host "ERROR: Manifest file not found: $ManifestPath" -ForegroundColor Red
    exit 1
}

# Parse manifest to get job_id, job_type, and ue_config
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
        $UEEditor = if ($manifest.ue_config.editor_path) { $manifest.ue_config.editor_path } else { $DefaultUEEditor }
        $Project = if ($manifest.ue_config.project_path) { $manifest.ue_config.project_path } else { $DefaultProject }
    } else {
        $UEEditor = $DefaultUEEditor
        $Project = $DefaultProject
        Write-Host "WARNING: No ue_config in manifest, using default paths" -ForegroundColor Yellow
    }
    
    Write-Host "Job ID:       $jobId" -ForegroundColor Yellow
    Write-Host "Job Type:     $jobType" -ForegroundColor Yellow
} catch {
    Write-Host "ERROR: Cannot parse manifest" -ForegroundColor Red
    exit 1
}

Write-Host "Manifest:     $ManifestPath" -ForegroundColor Yellow
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

if (-not (Test-Path $WorkerRender)) {
    Write-Host "ERROR: Worker render script not found at: $WorkerRender" -ForegroundColor Red
    exit 1
}

Write-Host "Starting render job..." -ForegroundColor Green
Write-Host ""

# Resolve absolute path for manifest
$AbsManifestPath = Resolve-Path $ManifestPath

# Build command
$pyCommand = "py `"$WorkerRender`" --manifest=`"$AbsManifestPath`""

# Build UE launch arguments (GUI mode for Movie Render Queue)
$ueArgs = @(
    "`"$Project`""
    "-ExecCmds=`"$pyCommand`""
    "-NoLoadingScreen"
    "-log"
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
