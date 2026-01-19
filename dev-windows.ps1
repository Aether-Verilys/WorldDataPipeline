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

# 3. Display BOS configuration
Write-Host ""
Write-Host "BOS Configuration:" -ForegroundColor Yellow
$BOS_COPY_CONFIG = Join-Path $REPO_ROOT "ue_pipeline\config\bos_copy_config.json"
if (Test-Path $BOS_COPY_CONFIG) {
    try {
        $config = Get-Content $BOS_COPY_CONFIG -Raw -Encoding UTF8 | ConvertFrom-Json
        Write-Host "  Source:  " -NoNewline -ForegroundColor Gray
        Write-Host "bos:/$($config.source_bucket)/$($config.source_prefix)/" -ForegroundColor Cyan
        Write-Host "  Target:  " -NoNewline -ForegroundColor Gray
        Write-Host "bos:/$($config.target_bucket)/$($config.target_prefix)/" -ForegroundColor Cyan
    } catch {
        Write-Host "  WARNING Failed to load BOS config: $_" -ForegroundColor Red
    }
} else {
    Write-Host "  WARNING BOS copy config not found" -ForegroundColor Red
}

Write-Host ""
Write-Host "  Environment Ready!" -ForegroundColor Green
Write-Host ""

# Define shortcut functions
function ue-bake {
    if ($args.Count -eq 0) {
        python app.py bake_navmesh
    } elseif ($args[0] -eq "--manifest") {
        python app.py bake_navmesh --manifest $args[1]
    } else {
        python app.py bake_navmesh --manifest $args[0]
    }
}

function ue-sequence {
    if ($args.Count -eq 0) {
        python app.py create_sequence
    } elseif ($args[0] -eq "--manifest") {
        python app.py create_sequence --manifest $args[1]
    } else {
        python app.py create_sequence --manifest $args[0]
    }
}

function ue-render {
    if ($args.Count -eq 0) {
        python app.py render
    } elseif ($args[0] -eq "--manifest") {
        python app.py render --manifest $args[1]
    } else {
        python app.py render --manifest $args[0]
    }
}

function ue-export {
    if ($args.Count -eq 0) {
        python app.py export
    } elseif ($args[0] -eq "--manifest") {
        python app.py export --manifest $args[1]
    } else {
        python app.py export --manifest $args[0]
    }
}

function ue-upload {
    Write-Host ""
    Write-Host "[Upload] Upload scene to BOS..." -ForegroundColor Yellow
    
    # 读取 bos.json 获取上传配置
    $BOS_CONFIG = Join-Path $REPO_ROOT "ue_pipeline\config\bos.json"
    if (Test-Path $BOS_CONFIG) {
        try {
            $config = Get-Content $BOS_CONFIG -Raw -Encoding UTF8 | ConvertFrom-Json
            $upload_config = $config.operations.upload
            $bucket = $upload_config.target_bucket
            $prefix = $upload_config.target_prefix
            Write-Host "  Target: " -NoNewline -ForegroundColor Gray
            Write-Host "bos://$bucket/$prefix/" -ForegroundColor Cyan
        } catch {
            Write-Host "  Target: " -NoNewline -ForegroundColor Gray
            Write-Host "bos:/world-data/baked/" -ForegroundColor Cyan
        }
    } else {
        Write-Host "  Target: " -NoNewline -ForegroundColor Gray
        Write-Host "bos:/world-data/baked/" -ForegroundColor Cyan
    }
    
    Write-Host ""
    
    if ($args.Count -eq 0) {
        # 交互式模式
        python app.py upload_scene
    } elseif ($args[0] -eq "--list" -or $args[0] -eq "-l") {
        # 列出场景
        python app.py upload_scene --list
    } elseif ($args[0] -eq "--scene") {
        # 指定场景名
        python app.py upload_scene --scene $args[1]
    } elseif ($args[0] -eq "--dry-run") {
        # 模拟运行
        python app.py upload_scene --dry-run
    } else {
        # 直接传递场景名
        python app.py upload_scene --scene $args[0]
    }
}

function ue-download {
    if ($args.Count -eq 0) {
        Write-Host ""
        Write-Host "[Download] Interactive Mode" -ForegroundColor Yellow
        Write-Host "  Source: " -NoNewline -ForegroundColor Gray
        Write-Host "bos:/world-data/raw/" -ForegroundColor Cyan
        Write-Host ""
        python app.py download_scene
    } elseif ($args[0] -eq "--list" -or $args[0] -eq "-l") {
        Write-Host ""
        Write-Host "[Download] Listing available scenes..." -ForegroundColor Yellow
        Write-Host "  Source: " -NoNewline -ForegroundColor Gray
        Write-Host "bos:/world-data/raw/" -ForegroundColor Cyan
        Write-Host ""
        python app.py download_scene --list
    } elseif ($args[0] -eq "--search" -or $args[0] -eq "-s") {
        Write-Host ""
        Write-Host "[Download] Searching scenes: $($args[1])" -ForegroundColor Yellow
        Write-Host "  Source: " -NoNewline -ForegroundColor Gray
        Write-Host "bos:/world-data/raw/" -ForegroundColor Cyan
        Write-Host ""
        python app.py download_scene --search $args[1]
    } elseif ($args[0] -eq "--scene") {
        Write-Host ""
        Write-Host "[Download] Downloading scene: $($args[1])" -ForegroundColor Yellow
        Write-Host "  Source: " -NoNewline -ForegroundColor Gray
        Write-Host "bos:/world-data/raw/$($args[1])/" -ForegroundColor Cyan
        Write-Host "  Target: " -NoNewline -ForegroundColor Gray
        Write-Host "Local Content folder" -ForegroundColor Cyan
        Write-Host ""
        python app.py download_scene --scene $args[1]
    } else {
        Write-Host ""
        Write-Host "[Download] Downloading scene: $($args[0])" -ForegroundColor Yellow
        Write-Host "  Source: " -NoNewline -ForegroundColor Gray
        Write-Host "bos:/world-data/raw/$($args[0])/" -ForegroundColor Cyan
        Write-Host "  Target: " -NoNewline -ForegroundColor Gray
        Write-Host "Local Content folder" -ForegroundColor Cyan
        Write-Host ""
        python app.py download_scene --scene $args[0]
    }
}

function ue-copy {
    $BOS_COPY_CONFIG = Join-Path $REPO_ROOT "ue_pipeline\config\bos_copy_config.json"
    $sourceInfo = "bos:/baidu-download-new/cdy-video-data/UnrealAssets/"
    $targetInfo = "bos:/world-data/raw/"
    
    if (Test-Path $BOS_COPY_CONFIG) {
        try {
            $config = Get-Content $BOS_COPY_CONFIG -Raw -Encoding UTF8 | ConvertFrom-Json
            $sourceInfo = "bos:/$($config.source_bucket)/$($config.source_prefix)/"
            $targetInfo = "bos:/$($config.target_bucket)/$($config.target_prefix)/"
        } catch {}
    }
    
    if ($args.Count -eq 0) {
        Write-Host ""
        Write-Host "[Copy] Listing available scenes..." -ForegroundColor Yellow
        Write-Host "  Source: " -NoNewline -ForegroundColor Gray
        Write-Host $sourceInfo -ForegroundColor Cyan
        Write-Host "  Target: " -NoNewline -ForegroundColor Gray
        Write-Host $targetInfo -ForegroundColor Cyan
        Write-Host ""
        python app.py copy_scene --list
    } elseif ($args[0] -eq "--list" -or $args[0] -eq "-l") {
        Write-Host ""
        Write-Host "[Copy] Listing available scenes..." -ForegroundColor Yellow
        Write-Host "  Source: " -NoNewline -ForegroundColor Gray
        Write-Host $sourceInfo -ForegroundColor Cyan
        Write-Host "  Target: " -NoNewline -ForegroundColor Gray
        Write-Host $targetInfo -ForegroundColor Cyan
        Write-Host ""
        python app.py copy_scene --list
    } else {
        Write-Host ""
        Write-Host "[Copy] Copying scene(s): $($args -join ', ')" -ForegroundColor Yellow
        Write-Host "  Source: " -NoNewline -ForegroundColor Gray
        Write-Host $sourceInfo -ForegroundColor Cyan
        Write-Host "  Target: " -NoNewline -ForegroundColor Gray
        Write-Host $targetInfo -ForegroundColor Cyan
        Write-Host ""
        python app.py copy_scene --scene @args
    }
}

function ue-help {
    Write-Host ""
    Write-Host "Available shortcut commands:" -ForegroundColor Yellow
    Write-Host "  ue-bake       - Bake NavMesh" -ForegroundColor White
    Write-Host "  ue-sequence   - Create sequences" -ForegroundColor White
    Write-Host "  ue-render     - Render" -ForegroundColor White
    Write-Host "  ue-export     - Export" -ForegroundColor White
    Write-Host "  ue-upload     - Upload scenes to BOS" -ForegroundColor White
    Write-Host "  ue-download   - Download scene from BOS" -ForegroundColor White
    Write-Host "  ue-copy       - Copy scene between BOS buckets" -ForegroundColor White
    Write-Host "  ue-help       - Show this help" -ForegroundColor White
    Write-Host ""
    Write-Host "Examples:" -ForegroundColor Yellow
    Write-Host "  ue-sequence                                  # Use config/job_config.json" -ForegroundColor Gray
    Write-Host "  ue-sequence custom_job.json                  # Use custom config file" -ForegroundColor Gray
    Write-Host "  ue-download --list                           # List available scenes" -ForegroundColor Gray
    Write-Host "  ue-download Seaside_Town                     # Download a scene" -ForegroundColor Gray
    Write-Host "  ue-copy --list                               # List scenes to copy" -ForegroundColor Gray
    Write-Host "  ue-copy Scene1 Scene2                        # Copy multiple scenes" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Or use app.py directly:" -ForegroundColor Yellow
    Write-Host "  python app.py --help" -ForegroundColor Gray
    Write-Host "  python app.py download_scene --scene Seaside_Town" -ForegroundColor Gray
    Write-Host ""
}

# Show help
ue-help

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Functions loaded! You can now use:" -ForegroundColor Green
Write-Host "  ue-bake, ue-sequence, ue-render," -ForegroundColor Cyan
Write-Host "  ue-export, ue-upload, ue-download, ue-copy" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
