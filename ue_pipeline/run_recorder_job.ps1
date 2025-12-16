# UE Single Job Executor
# Execute a single job and exit

param(
    [Parameter(Mandatory=$true)]
    [string]$ManifestPath
)

# ============================================================
# Configuration
# ============================================================

# Worker Entry script path
$WorkerEntry = "$PSScriptRoot\python\worker_entry.py"

# Default paths (used if not specified in manifest)
$DefaultUEEditor = "D:\Program Files\Epic Games\UE_5.7\Engine\Binaries\Win64\UnrealEditor.exe"
$DefaultProject = "F:\UE_Projects\NorthernForest\NorthernForest.uproject"

# ============================================================

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "UE Single Job Executor" -ForegroundColor Cyan
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
    $jobType = if ($manifest.job_type) { $manifest.job_type } else { "record" }
    
    # Validate job type
    if ($jobType -ne "record") {
        Write-Host "ERROR: Invalid job type '$jobType' for this executor" -ForegroundColor Red
        Write-Host "This script only handles 'record' jobs. For render jobs, use run_render_job.ps1" -ForegroundColor Yellow
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
    Write-Host "WARNING: Cannot parse manifest, assuming record job" -ForegroundColor Yellow
    $jobId = "unknown"
    $UEEditor = $DefaultUEEditor
    $Project = $DefaultProject
}

Write-Host "Manifest:     $ManifestPath" -ForegroundColor Yellow
Write-Host "UE Editor:    $UEEditor" -ForegroundColor Yellow
Write-Host "Project:      $Project" -ForegroundColor Yellow
Write-Host ""

# Check required files
if (-not (Test-Path $UEEditor)) {
    Write-Host "ERROR: UE Editor not found: $UEEditor" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $Project)) {
    Write-Host "ERROR: UE Project file not found: $Project" -ForegroundColor Red
    exit 1
}

Write-Host "Starting UE Editor to execute job..." -ForegroundColor Green
Write-Host "This will:" -ForegroundColor Cyan
Write-Host "  1. Load the map specified in manifest" -ForegroundColor Gray
Write-Host "  2. Start PIE (Play In Editor)" -ForegroundColor Gray
Write-Host "  3. Add player source to Take Recorder" -ForegroundColor Gray
Write-Host "  4. Record for 5 seconds" -ForegroundColor Gray
Write-Host "  5. Stop recording and PIE" -ForegroundColor Gray
Write-Host "  6. Exit UE" -ForegroundColor Gray
Write-Host ""

# Check if Worker Entry script exists
if (-not (Test-Path $WorkerEntry)) {
    Write-Host "ERROR: Worker Entry script not found: $WorkerEntry" -ForegroundColor Red
    exit 1
}

# Build Python command with proper escaping
$pythonCmd = "py `"$WorkerEntry`" --manifest=`"$ManifestPath`""
Write-Host "Command: $UEEditor $Project -ExecCmds=`"$pythonCmd`" -NoSplash -log" -ForegroundColor Gray
Write-Host ""

# Execute job
try {
    & $UEEditor $Project `
        -ExecCmds="$pythonCmd" `
        -NoSplash `
        -log
    
    $exitCode = $LASTEXITCODE
    
    # When using -ExecCmds, UE may return immediately while still processing
    # Wait a moment and check if UE process exists
    Start-Sleep -Seconds 3
    
    $ueProcess = Get-Process "UnrealEditor" -ErrorAction SilentlyContinue
    
    if ($ueProcess) {
        Write-Host "UE Editor is running, processing job..." -ForegroundColor Cyan
        Write-Host "Waiting for job to complete (this may take a while)..." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Monitor the UE Editor window for progress." -ForegroundColor Gray
        Write-Host "The job will:" -ForegroundColor Gray
        Write-Host "  - Load map" -ForegroundColor DarkGray
        Write-Host "  - Setup Take Recorder" -ForegroundColor DarkGray
        Write-Host "  - Start PIE" -ForegroundColor DarkGray
        Write-Host "  - Record for 5 seconds" -ForegroundColor DarkGray
        Write-Host "  - Stop and exit" -ForegroundColor DarkGray
        Write-Host ""
        Write-Host "Press Ctrl+C to abort" -ForegroundColor Yellow
        
        # Wait for UE to finish
        $ueProcess.WaitForExit()
        $exitCode = $ueProcess.ExitCode
        Write-Host ""
        Write-Host "UE Editor has closed." -ForegroundColor Cyan
    } elseif ($null -eq $exitCode) {
        $exitCode = 1
        Write-Host "WARNING: Exit code is empty and UE is not running" -ForegroundColor Yellow
    }
} catch {
    Write-Host "ERROR: Exception occurred: $_" -ForegroundColor Red
    $exitCode = 1
}

Write-Host ""
if ($exitCode -eq 0) {
    Write-Host "SUCCESS: Job completed" -ForegroundColor Green
} else {
    Write-Host "FAILED: Job failed (Exit Code: $exitCode)" -ForegroundColor Red
}

# Display status file
$statusFile = "$PSScriptRoot\jobs\status\$jobId.status.json"
if (Test-Path $statusFile) {
    Write-Host ""
    Write-Host "Job Status File:" -ForegroundColor Cyan
    Get-Content $statusFile | ConvertFrom-Json | ConvertTo-Json -Depth 10
}

Write-Host ""
pause
exit $exitCode
