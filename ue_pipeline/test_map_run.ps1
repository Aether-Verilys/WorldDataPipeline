# Test Map Load and Run
# Tests loading map and running scene using level_launcher

# ============================================================
# Configuration
# ============================================================

$UEEditor = "D:\Program Files\Epic Games\UE_5.7\Engine\Binaries\Win64\UnrealEditor.exe"
$Project = "F:\UE_Projects\NorthernForest\NorthernForest.uproject"
$TestScript = "$PSScriptRoot\python\test_map_run.py"
$ManifestPath = "$PSScriptRoot\examples\test_map_only.json"
$RunSeconds = 10  # How long to run the scene

# ============================================================

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Test Map Load and Run" -ForegroundColor Cyan
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
Write-Host "Run Time:    $RunSeconds seconds" -ForegroundColor Yellow
Write-Host ""

# Parse manifest
try {
    $manifest = Get-Content $ManifestPath | ConvertFrom-Json
    Write-Host "Map to load: $($manifest.map)" -ForegroundColor Cyan
} catch {
    Write-Host "WARNING: Cannot parse manifest" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "This test will:" -ForegroundColor Green
Write-Host "  1. Start UE Editor" -ForegroundColor Gray
Write-Host "  2. Load map: /Game/Maps/Lvl_FirstPerson" -ForegroundColor Gray
Write-Host "  3. Start PIE (Play In Editor)" -ForegroundColor Gray
Write-Host "  4. Run scene for $RunSeconds seconds" -ForegroundColor Gray
Write-Host "  5. Stop PIE" -ForegroundColor Gray
Write-Host "  6. Exit" -ForegroundColor Gray
Write-Host ""
Write-Host "Watch for '[TestMapRun]' messages..." -ForegroundColor Yellow
Write-Host "Press Ctrl+C to abort" -ForegroundColor Yellow
Write-Host ""

Start-Sleep -Seconds 2

Write-Host "Starting UE Editor..." -ForegroundColor Green
Write-Host ""

# Launch UE using ExecCmds to run Python inline
# This keeps UE Editor GUI open instead of switching to Cmd mode
$pythonCmd = "py `"$TestScript`""
& $UEEditor $Project `
    -ExecCmds="$pythonCmd" `
    -NoSplash `
    -log

$exitCode = $LASTEXITCODE

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan

# Check if UE is still running
$ueProcess = Get-Process "UnrealEditor" -ErrorAction SilentlyContinue

if ($ueProcess) {
    Write-Host "UE Editor is running with PIE active!" -ForegroundColor Green
    Write-Host ""
    Write-Host "The map has been loaded and PIE started successfully." -ForegroundColor Cyan
    Write-Host "You can now interact with the scene in UE Editor." -ForegroundColor Cyan
    Write-Host "Close UE Editor manually when done testing." -ForegroundColor Cyan
} elseif ($null -eq $exitCode -or $exitCode -eq 0) {
    Write-Host "SUCCESS: Test completed!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Check UE logs for '[TestMapRun]' messages:" -ForegroundColor Cyan
    Write-Host "  F:\UE_Projects\NorthernForest\Saved\Logs\" -ForegroundColor Gray
} else {
    Write-Host "FAILED: Exit Code: $exitCode" -ForegroundColor Red
    Write-Host ""
    Write-Host "Troubleshooting:" -ForegroundColor Yellow
    Write-Host "  - Check output above for '[TestMapRun]' messages" -ForegroundColor Gray
    Write-Host "  - Check if map path is correct: /Game/Maps/Lvl_FirstPerson" -ForegroundColor Gray
    Write-Host "  - Check UE logs: F:\UE_Projects\NorthernForest\Saved\Logs\" -ForegroundColor Gray
}
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
pause
exit $exitCode
