# UE Worker Daemon Launcher
# Start long-running worker daemon to process jobs in jobs/inbox

# ============================================================
# Configuration - Modify paths according to your environment
# ============================================================

# UE Editor executable path
$UEEditor = "C:\Program Files\Epic Games\UE_5.7\Engine\Binaries\Win64\UnrealEditor.exe"

# UE Project file path
$Project = "F:\UE_Projects\NorthernForest\NorthernForest.uproject"

# Worker Daemon script path
$WorkerDaemon = "$PSScriptRoot\python\worker_daemon.py"

# Watch directory (job inbox)
$WatchDir = "$PSScriptRoot\jobs\inbox"

# Poll interval (seconds)
$PollInterval = 2

# ============================================================

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "UE Worker Daemon Launcher" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "UE Editor:    $UEEditor" -ForegroundColor Yellow
Write-Host "Project:      $Project" -ForegroundColor Yellow
Write-Host "Watch Dir:    $WatchDir" -ForegroundColor Yellow
Write-Host "Poll:         ${PollInterval}s" -ForegroundColor Yellow
Write-Host ""

# Check if files exist
if (-not (Test-Path $UEEditor)) {
    Write-Host "ERROR: UE Editor not found: $UEEditor" -ForegroundColor Red
    Write-Host "Please modify the `$UEEditor path in this script" -ForegroundColor Red
    pause
    exit 1
}

if (-not (Test-Path $Project)) {
    Write-Host "ERROR: UE Project file not found: $Project" -ForegroundColor Red
    Write-Host "Please modify the `$Project path in this script" -ForegroundColor Red
    pause
    exit 1
}

if (-not (Test-Path $WorkerDaemon)) {
    Write-Host "ERROR: Worker Daemon script not found: $WorkerDaemon" -ForegroundColor Red
    pause
    exit 1
}

# Ensure watch directory exists
New-Item -ItemType Directory -Path $WatchDir -Force | Out-Null

Write-Host "Starting Worker Daemon..." -ForegroundColor Green
Write-Host "TIP: Keep this window open to see real-time logs" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop the worker" -ForegroundColor Green
Write-Host ""

# 启动 UE Editor with Worker Daemon
& $UEEditor $Project `
    -unattended `
    -NoSplash `
    -ExecutePythonScript="$WorkerDaemon" `
    -ScriptArgs="--watch-dir=$WatchDir --poll=$PollInterval" `
    -log

Write-Host ""
Write-Host "Worker Daemon stopped" -ForegroundColor Yellow
pause
