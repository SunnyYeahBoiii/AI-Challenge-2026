param(
    [string]$Bucket = "frameseeker-aic2026-assets",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\..")).Path
$sourceDirectory = (Resolve-Path (Join-Path $projectRoot "data\keyframes")).Path
$destination = "gs://$Bucket/keyframes"

$arguments = @(
    "storage", "rsync", $sourceDirectory, $destination,
    "--recursive",
    "--continue-on-error",
    "--content-type=image/webp",
    "--cache-control=public,max-age=31536000,immutable"
)

if ($DryRun) {
    $arguments += "--dry-run"
}

Write-Host "Source:      $sourceDirectory"
Write-Host "Destination: $destination"
Write-Host ""

& gcloud @arguments
if ($LASTEXITCODE -ne 0) {
    throw "GCS keyframe upload failed with exit code $LASTEXITCODE."
}
