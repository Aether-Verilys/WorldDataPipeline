param (
    [string]$ConfigPath
)

# ----------------------------------------
if (-not $ConfigPath -or $ConfigPath -eq "") {
    if ($args.Count -gt 0) {
        $ConfigPath = $args[0]
    } else {
        $ConfigPath = ".\cook_config.json"
    }
}

Write-Host "========================================"
Write-Host " Unreal Engine Linux Cook Tool"
Write-Host "========================================"
Write-Host "Config file: $ConfigPath"
Write-Host ""

# ----------------------------------------
# Load config
# ----------------------------------------
if (!(Test-Path $ConfigPath)) {
    Write-Error "Config file not found: $ConfigPath"
    Read-Host "Press Enter to exit"
    exit 1
}

$config = Get-Content $ConfigPath | ConvertFrom-Json

$EngineDir   = $config.EngineDir
$ProjectDir  = $config.ProjectDir
$Platform    = $config.TargetPlatform
$CookAll     = $config.CookAll
$Unversioned = $config.Unversioned
$LogFile     = $config.OutputLog

# ----------------------------------------
# Resolve paths
# ----------------------------------------
$ProjectName = Split-Path $ProjectDir -Leaf
$UProject    = Join-Path $ProjectDir "$ProjectName.uproject"
$EditorCmd   = Join-Path $EngineDir "Engine\Binaries\Win64\UnrealEditor-Cmd.exe"

Write-Host "EngineCmd : $EditorCmd"
Write-Host "UProject  : $UProject"
Write-Host ""

# ----------------------------------------
# Validation
# ----------------------------------------
if (!(Test-Path $EditorCmd)) {
    Write-Error "UnrealEditor-Cmd not found: $EditorCmd"
    Read-Host "Press Enter to exit"
    exit 2
}

if (!(Test-Path $UProject)) {
    Write-Error "uproject not found: $UProject"
    Read-Host "Press Enter to exit"
    exit 3
}

# ----------------------------------------
# Build command
# ----------------------------------------
$argsUE = @(
    "`"$UProject`"",
    "-run=Cook",
    "-TargetPlatform=$Platform",
    "-BuildMachine",
    "-NoLogTimes",
    "-UTF8Output"
)

if ($CookAll) {
    $argsUE += "-CookAll"
}

if ($Unversioned) {
    $argsUE += "-Unversioned"
}

Write-Host "----------------------------------------"
Write-Host " Start Cooking"
Write-Host "----------------------------------------"

# ----------------------------------------
# Execute
# ----------------------------------------
& $EditorCmd $argsUE 2>&1 | Tee-Object -FilePath $LogFile
$ExitCode = $LASTEXITCODE

Write-Host ""
Write-Host "----------------------------------------"

if ($ExitCode -eq 0) {
    Write-Host " Cook SUCCESS" -ForegroundColor Green
    Write-Host " Output: $LogFile"
} else {
    Write-Host " Cook FAILED (ExitCode=$ExitCode)" -ForegroundColor Red
    Write-Host " Check log: $LogFile"
}

Write-Host "----------------------------------------"
Read-Host "Press Enter to exit"
exit $ExitCode
