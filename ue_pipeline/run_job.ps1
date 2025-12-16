# UE Job Dispatcher
# Automatically detects job type and routes to appropriate executor

param(
    [Parameter(Mandatory=$true)]
    [string]$ManifestPath
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "UE Job Dispatcher" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check manifest file
if (-not (Test-Path $ManifestPath)) {
    Write-Host "ERROR: Manifest file not found: $ManifestPath" -ForegroundColor Red
    exit 1
}

# Parse manifest to detect job type
try {
    $manifest = Get-Content $ManifestPath | ConvertFrom-Json
    $jobId = $manifest.job_id
    $jobType = $manifest.job_type
    
    Write-Host "Job ID:       $jobId" -ForegroundColor Yellow
    Write-Host "Job Type:     $jobType" -ForegroundColor Yellow
    Write-Host "Manifest:     $ManifestPath" -ForegroundColor Yellow
    Write-Host ""
    
    # Route to appropriate executor
    if ($jobType -eq "record") {
        Write-Host "Routing to: run_single_job.ps1 (Recording Job)" -ForegroundColor Green
        Write-Host ""
        & "$PSScriptRoot\run_single_job.ps1" -ManifestPath $ManifestPath
        exit $LASTEXITCODE
    }
    elseif ($jobType -eq "render") {
        Write-Host "Routing to: run_render_job.ps1 (Render Job)" -ForegroundColor Green
        Write-Host ""
        & "$PSScriptRoot\run_render_job.ps1" -ManifestPath $ManifestPath
        exit $LASTEXITCODE
    }
    elseif ($jobType -eq "export") {
        Write-Host "Routing to: run_export_job.ps1 (Export Job)" -ForegroundColor Green
        Write-Host ""
        & "$PSScriptRoot\run_export_job.ps1" -ManifestPath $ManifestPath
        exit $LASTEXITCODE
    }
    elseif ($jobType -eq "gen_levelsequence") {
        Write-Host "Routing to: run_gen_levelsequence_job.ps1 (Generate LevelSequence Job)" -ForegroundColor Green
        Write-Host ""
        & "$PSScriptRoot\run_gen_levelsequence_job.ps1" -ManifestPath $ManifestPath
        exit $LASTEXITCODE
    }
    else {
        Write-Host "ERROR: Unknown job type: $jobType" -ForegroundColor Red
        Write-Host "Supported types: 'record', 'render', 'export', 'gen_levelsequence'" -ForegroundColor Yellow
        exit 1
    }
    
} catch {
    Write-Host "ERROR: Cannot parse manifest: $_" -ForegroundColor Red
    exit 1
}
