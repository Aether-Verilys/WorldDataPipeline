param(
    [string]$Config,
    [switch]$DryRun,
    [switch]$List
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonScript = Join-Path $scriptDir "python/copy_scene_assets.py"

if (-not (Test-Path $pythonScript)) {
    Write-Host "Error: Python script not found: $pythonScript" -ForegroundColor Red
    exit 1
}

# Check if config is provided
if ([string]::IsNullOrWhiteSpace($Config)) {
    Write-Host "Error: Configuration file is required" -ForegroundColor Red
    Write-Host "`nUsage:" -ForegroundColor Yellow
    Write-Host "  1. Specify config: .\world_01_scene_assets.ps1 -Config path\to\config.json" -ForegroundColor Gray
    Write-Host "  2. Drag and drop config file onto this script" -ForegroundColor Gray
    Write-Host "`nExample:" -ForegroundColor Yellow
    Write-Host "  .\world_01_scene_assets.ps1 -Config config\world_01_scene_config.json" -ForegroundColor Gray
    exit 1
}

$configPath = $Config.Trim('"').Trim("'")

# If not an absolute path, resolve relative to script directory
if (-not [System.IO.Path]::IsPathRooted($configPath)) {
    $configPath = Join-Path $scriptDir $configPath
}

# Normalize path
$configPath = [System.IO.Path]::GetFullPath($configPath)

if (-not (Test-Path $configPath)) {
    Write-Host "Error: Config file not found: $configPath" -ForegroundColor Red
    Write-Host "`nPlease provide a valid configuration JSON file." -ForegroundColor Yellow
    Write-Host "Usage:" -ForegroundColor Yellow
    Write-Host "  .\copy_scene_assets.ps1 -Config path\to\config.json" -ForegroundColor Gray
    exit 1
}

$pythonArgs = @($pythonScript, "--config", $configPath)

if ($DryRun) {
    $pythonArgs += "--dry-run"
}

if ($List) {
    $pythonArgs += "--list"
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logDir = Join-Path $scriptDir "logs"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}
$logFile = Join-Path $logDir "world_01_scene_assets_$timestamp.log"

Write-Host "Executing scene asset copy..." -ForegroundColor Cyan
Write-Host "Config file: $configPath" -ForegroundColor Gray
Write-Host "Log file: $logFile" -ForegroundColor Gray

python @pythonArgs 2>&1 | Tee-Object -FilePath $logFile

if ($LASTEXITCODE -ne 0) {
    Write-Host "`nScript execution failed" -ForegroundColor Red
    Write-Host "Log saved to: $logFile" -ForegroundColor Yellow
    Read-Host -Prompt "Press Enter to exit"
    exit $LASTEXITCODE
}

Write-Host "`nScript execution completed" -ForegroundColor Green
Write-Host "Log saved to: $logFile" -ForegroundColor Cyan
Read-Host -Prompt "Press Enter to exit"
