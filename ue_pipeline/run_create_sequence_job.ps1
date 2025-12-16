# UE LevelSequence Creation Test Job (Headless)
# Simple test: create an empty LevelSequence asset

param(
    [Parameter(Mandatory=$true)]
    [string]$ManifestPath
)

# ============================================================
# Configuration
# ============================================================

$Worker = "$PSScriptRoot\python\worker_create_sequence.py"

# Default paths
$DefaultUEEditor = "D:\Program Files\Epic Games\UE_5.7\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
$DefaultProject  = "D:\UE_Projects\WorldProject\WorldProject.uproject"

# ============================================================

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "UE Create LevelSequence Test" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $ManifestPath)) {
    Write-Host "ERROR: Manifest file not found: $ManifestPath" -ForegroundColor Red
    exit 1
}

try {
    $manifest = Get-Content $ManifestPath | ConvertFrom-Json
    $jobId = $manifest.job_id
    $jobType = $manifest.job_type

    if ($jobType -ne "create_sequence") {
        Write-Host "ERROR: Invalid job type '$jobType', expected 'create_sequence'" -ForegroundColor Red
        exit 1
    }

    if ($manifest.ue_config) {
        $editorPath = if ($manifest.ue_config.editor_path) { $manifest.ue_config.editor_path } else { $DefaultUEEditor }
        $UEEditor = $editorPath -replace "UnrealEditor\.exe", "UnrealEditor-Cmd.exe"
        $Project  = if ($manifest.ue_config.project_path) { $manifest.ue_config.project_path } else { $DefaultProject }
    } else {
        $UEEditor = $DefaultUEEditor
        $Project  = $DefaultProject
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

if (-not (Test-Path $UEEditor)) {
    Write-Host "ERROR: UE Editor not found at: $UEEditor" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $Project)) {
    Write-Host "ERROR: Project not found at: $Project" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $Worker)) {
    Write-Host "ERROR: Worker script not found at: $Worker" -ForegroundColor Red
    exit 1
}

Write-Host "Creating LevelSequence..." -ForegroundColor Green
Write-Host ""

$AbsManifestPath = Resolve-Path $ManifestPath
$pyCommand = "py `"$Worker`" --manifest=`"$AbsManifestPath`""

# Full headless mode arguments (no GUI, no rendering)
$ueArgs = @(
    "`"$Project`""
    "-ExecCmds=`"$pyCommand`""
    "-unattended"
    "-nopause"
    "-nosplash"
    "-NullRHI"
    "-buildmachine"
    "-NoSound"
    "-AllowStdOutLogVerbosity"
    "-stdout"
    "-FullStdOutLogOutput"
    "-log"
)

Write-Host "Command: $UEEditor $($ueArgs -join ' ')" -ForegroundColor Gray
Write-Host ""
Write-Host "----------------------------------------" -ForegroundColor Cyan

try {
    $ueProcess = Start-Process -FilePath $UEEditor -ArgumentList $ueArgs -PassThru -NoNewWindow -Wait

    Write-Host ""
    Write-Host "----------------------------------------" -ForegroundColor Cyan

    if ($ueProcess.ExitCode -eq 0) {
        Write-Host "Job completed successfully" -ForegroundColor Green
        exit 0
    } else {
        Write-Host "Job failed with exit code: $($ueProcess.ExitCode)" -ForegroundColor Red
        exit $ueProcess.ExitCode
    }
} catch {
    Write-Host "ERROR: Failed to launch UE: $_" -ForegroundColor Red
    exit 1
}
