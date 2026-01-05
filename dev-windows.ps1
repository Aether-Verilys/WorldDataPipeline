# UE Pipeline Development Environment Setup Script (Windows)
# Usage: . .\dev-windows.ps1  (note the dot at the beginning)

Write-Host "=" -ForegroundColor Cyan -NoNewline
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  UE Pipeline Development Environment (Windows)" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan

$REPO_ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$VENV_PATH = Join-Path $REPO_ROOT ".venv"
$UE_PIPELINE_DIR = Join-Path $REPO_ROOT "ue_pipeline"

# 1. Activate virtual environment
if (Test-Path (Join-Path $VENV_PATH "Scripts\Activate.ps1")) {
    Write-Host "Activating virtual environment..." -ForegroundColor Yellow
    & (Join-Path $VENV_PATH "Scripts\Activate.ps1")
    Write-Host "  OK Virtual environment activated" -ForegroundColor Green
} else {
    Write-Host "  WARNING Virtual environment not found: $VENV_PATH" -ForegroundColor Red
    Write-Host "  Please create it first: python -m venv .venv" -ForegroundColor Yellow
}

# 2. Set environment variables
Write-Host "Setting environment variables..." -ForegroundColor Yellow
$env:UE_SYSTEM_TYPE = "windows"
Write-Host "  OK UE_SYSTEM_TYPE = windows" -ForegroundColor Green

# 3. Change to ue_pipeline directory
Write-Host "Changing working directory..." -ForegroundColor Yellow
Set-Location $UE_PIPELINE_DIR
Write-Host "  OK Current directory: $UE_PIPELINE_DIR" -ForegroundColor Green

Write-Host ""
Write-Host "  Environment Ready!" -ForegroundColor Green
Write-Host ""

# Define shortcut functions
function ue-bake {
    if ($args.Count -eq 0) {
        python app.py bake_navmesh --manifest examples/job_bake.json
    } elseif ($args[0] -eq "--manifest") {
        # Remove --manifest flag, app.py will add it
        python app.py bake_navmesh --manifest $args[1]
    } else {
        # Assume it's a path, add --manifest
        python app.py bake_navmesh --manifest $args[0]
    }
}

function ue-sequence {
    if ($args.Count -eq 0) {
        python app.py create_sequence --manifest examples/job_sequence_analysis.json
    } elseif ($args[0] -eq "--manifest") {
        python app.py create_sequence --manifest $args[1]
    } else {
        python app.py create_sequence --manifest $args[0]
    }
}

function ue-render {
    if ($args.Count -eq 0) {
        python app.py render --manifest examples/job_render.json
    } elseif ($args[0] -eq "--manifest") {
        python app.py render --manifest $args[1]
    } else {
        python app.py render --manifest $args[0]
    }
}

function ue-export {
    if ($args.Count -eq 0) {
        python app.py export --manifest examples/job_export.json
    } elseif ($args[0] -eq "--manifest") {
        python app.py export --manifest $args[1]
    } else {
        python app.py export --manifest $args[0]
    }
}

function ue-upload {
    python app.py upload_scenes
}

function ue-help {
    Write-Host ""
    Write-Host "Available shortcut commands:" -ForegroundColor Yellow
    Write-Host "  ue-bake       - Bake NavMesh" -ForegroundColor White
    Write-Host "  ue-sequence   - Create sequences" -ForegroundColor White
    Write-Host "  ue-render     - Render" -ForegroundColor White
    Write-Host "  ue-export     - Export" -ForegroundColor White
    Write-Host "  ue-upload     - Upload scenes" -ForegroundColor White
    Write-Host "  ue-help       - Show this help" -ForegroundColor White
    Write-Host ""
    Write-Host "Examples:" -ForegroundColor Yellow
    Write-Host "  ue-sequence                                   # Use default config" -ForegroundColor Gray
    Write-Host "  ue-sequence examples/job_sequence_cameraman.json  # Specify config file" -ForegroundColor Gray
    Write-Host "  ue-sequence --manifest examples/job_sequence_cameraman.json  # Also works" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Or use app.py directly:" -ForegroundColor Yellow
    Write-Host "  python app.py --help" -ForegroundColor Gray
    Write-Host "  python app.py create_sequence --manifest examples/job_sequence_analysis.json" -ForegroundColor Gray
    Write-Host ""
}

# Show help
ue-help

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Functions loaded! You can now use:" -ForegroundColor Green
Write-Host "  ue-bake, ue-sequence, ue-render, etc." -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
