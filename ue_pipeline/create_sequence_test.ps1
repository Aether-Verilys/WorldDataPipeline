# Convenience wrapper to test LevelSequence creation in headless mode

param(
    [Parameter(Mandatory=$false)]
    [string]$ManifestPath = "$PSScriptRoot\examples\job_create_sequence.json"
)

$Executor = "$PSScriptRoot\run_create_sequence_job.ps1"

if (-not (Test-Path $Executor)) {
    Write-Host "ERROR: Executor not found: $Executor" -ForegroundColor Red
    exit 1
}

Write-Host "Testing LevelSequence creation (headless mode)" -ForegroundColor Cyan
Write-Host ""

& $Executor -ManifestPath $ManifestPath
exit $LASTEXITCODE
