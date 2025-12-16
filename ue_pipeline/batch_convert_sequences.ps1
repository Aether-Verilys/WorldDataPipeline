# Batch Convert Image Sequences to MP4
# Automatically finds and converts all image sequences in output directory

param(
    [Parameter(Mandatory=$false)]
    [string]$OutputRoot = "D:\WorldDataPipeline\output",
    
    [Parameter(Mandatory=$false)]
    [int]$Framerate = 30,
    
    [Parameter(Mandatory=$false)]
    [string]$Quality = "high"
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Batch Image Sequence to MP4 Converter" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $OutputRoot)) {
    Write-Host "ERROR: Output root directory not found: $OutputRoot" -ForegroundColor Red
    exit 1
}

Write-Host "Scanning: $OutputRoot" -ForegroundColor Yellow
Write-Host ""

# Find all directories with image sequences
$imageDirs = Get-ChildItem -Path $OutputRoot -Recurse -Directory | Where-Object {
    $pngCount = (Get-ChildItem -Path $_.FullName -Filter "*.png" -ErrorAction SilentlyContinue).Count
    $jpgCount = (Get-ChildItem -Path $_.FullName -Filter "*.jpg" -ErrorAction SilentlyContinue).Count
    $exrCount = (Get-ChildItem -Path $_.FullName -Filter "*.exr" -ErrorAction SilentlyContinue).Count
    
    ($pngCount -gt 1) -or ($jpgCount -gt 1) -or ($exrCount -gt 1)
}

if ($imageDirs.Count -eq 0) {
    Write-Host "No image sequences found" -ForegroundColor Yellow
    exit 0
}

Write-Host "Found $($imageDirs.Count) image sequences to convert" -ForegroundColor Green
Write-Host ""

$converted = 0
$failed = 0

foreach ($dir in $imageDirs) {
    Write-Host "----------------------------------------" -ForegroundColor Cyan
    Write-Host "Processing: $($dir.FullName)" -ForegroundColor Yellow
    
    # Check if MP4 already exists
    $parentDirName = Split-Path $dir.FullName -Leaf
    $mp4File = Join-Path $dir.FullName "$parentDirName.mp4"
    
    if (Test-Path $mp4File) {
        Write-Host "  ⊘ Skipping (MP4 already exists): $mp4File" -ForegroundColor Gray
        continue
    }
    
    try {
        & "$PSScriptRoot\image_sequence_to_mp4.ps1" `
            -InputDir $dir.FullName `
            -Framerate $Framerate `
            -Quality $Quality
        
        if ($LASTEXITCODE -eq 0) {
            $converted++
            Write-Host "  ✓ Converted successfully" -ForegroundColor Green
        } else {
            $failed++
            Write-Host "  ✗ Conversion failed" -ForegroundColor Red
        }
    } catch {
        $failed++
        Write-Host "  ✗ Error: $_" -ForegroundColor Red
    }
    
    Write-Host ""
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Summary:" -ForegroundColor Cyan
Write-Host "  Total: $($imageDirs.Count)" -ForegroundColor White
Write-Host "  Converted: $converted" -ForegroundColor Green
Write-Host "  Failed: $failed" -ForegroundColor Red
Write-Host "========================================" -ForegroundColor Cyan
