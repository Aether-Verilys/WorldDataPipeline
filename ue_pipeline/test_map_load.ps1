# Test Map Loading Only
# Simplified test that only loads a map from manifest

# ============================================================
# Configuration
# ============================================================

$UEEditor = "D:\Program Files\Epic Games\UE_5.7\Engine\Binaries\Win64\UnrealEditor.exe"
$Project = "F:\UE_Projects\NorthernForest\NorthernForest.uproject"
$TestScript = "$PSScriptRoot\python\test_map_load.py"
$ManifestPath = "$PSScriptRoot\examples\test_map_only.json"

# ============================================================

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Test Map Loading Only" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check files
if (-not (Test-Path $UEEditor)) {
    Write-Host "ERROR: UE Editor not found: $UEEditor" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $Project)) {
    Write-Host "ERROR: Project not found: $Project" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $TestScript)) {
    Write-Host "ERROR: Test script not found: $TestScript" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $ManifestPath)) {
    Write-Host "ERROR: Manifest not found: $ManifestPath" -ForegroundColor Red
    exit 1
}

# Display config
Write-Host "UE Editor:   $UEEditor" -ForegroundColor Yellow
Write-Host "Project:     $Project" -ForegroundColor Yellow
Write-Host "Test Script: $TestScript" -ForegroundColor Yellow
Write-Host "Manifest:    $ManifestPath" -ForegroundColor Yellow
Write-Host ""

# Parse manifest
try {
    $manifest = Get-Content $ManifestPath | ConvertFrom-Json
    Write-Host "Map to load: $($manifest.map)" -ForegroundColor Cyan
} catch {
    Write-Host "WARNING: Cannot parse manifest" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Starting UE Editor..." -ForegroundColor Green
Write-Host "This will:" -ForegroundColor Gray
Write-Host "  1. Start UE Editor" -ForegroundColor Gray
Write-Host "  2. Load map: /Game/Maps/Lvl_FirstPerson" -ForegroundColor Gray
Write-Host "  3. Exit" -ForegroundColor Gray
Write-Host ""
Write-Host "Watch for '[TestWorker]' messages in output..." -ForegroundColor Yellow
Write-Host ""

# Launch UE
& $UEEditor $Project `
    -ExecutePythonScript="$TestScript" `
    -ScriptArgs="--manifest=$ManifestPath" `
    -stdout `
    -unattended `
    -NoSplash `
    -log

$exitCode = $LASTEXITCODE

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
if ($exitCode -eq 0) {
    Write-Host "SUCCESS: Map loaded successfully!" -ForegroundColor Green
} else {
    Write-Host "FAILED: Exit Code: $exitCode" -ForegroundColor Red
    Write-Host ""
    Write-Host "Check the output above for '[TestWorker]' messages" -ForegroundColor Yellow
    Write-Host "Or check UE logs at:" -ForegroundColor Yellow
    Write-Host "  F:\UE_Projects\NorthernForest\Saved\Logs\" -ForegroundColor Gray
}
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
pause
exit $exitCode
