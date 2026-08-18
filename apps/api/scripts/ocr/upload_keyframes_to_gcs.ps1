param(
    [string]$Bucket = "frameseeker-aic2026-assets",
    [string[]]$Datasets = @("L23", "L24"),
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\..")).Path

foreach ($dataset in $Datasets) {
    $sourceDirectoryPath = Join-Path $projectRoot "data\keyframes\$dataset"
    if (-not (Test-Path -LiteralPath $sourceDirectoryPath -PathType Container)) {
        throw "Keyframe dataset directory does not exist: $sourceDirectoryPath"
    }

    $sourceDirectory = (Resolve-Path -LiteralPath $sourceDirectoryPath).Path
    $destination = "gs://$Bucket/keyframes/$dataset"
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
        throw "GCS keyframe upload failed for $dataset with exit code $LASTEXITCODE."
    }
}
