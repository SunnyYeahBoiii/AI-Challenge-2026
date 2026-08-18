param(
    [string]$Project = "hcmc-aichallenge2026",
    [string]$Bucket = "frameseeker-aic2026-assets",
    [string]$Dataset = "L24",
    [string]$Model = "gemini-3.5-flash-lite",
    [string]$Location = "global",
    [string]$RunId = ("l24-gemini-3-5-flash-lite-" + (Get-Date -Format "yyyyMMdd-HHmmss")),
    [switch]$Wait
)

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\..")).Path
$apiDirectory = Join-Path $projectRoot "apps\api"
$requestsPath = Join-Path $projectRoot "data\captions\$Dataset\requests.jsonl"
$submitScript = Join-Path $projectRoot "apps\api\scripts\ocr\submit_gemini_batch_ocr.py"

if (-not (Test-Path -LiteralPath $requestsPath -PathType Leaf)) {
    throw "Batch request file does not exist: $requestsPath"
}
if (-not (Test-Path -LiteralPath $submitScript -PathType Leaf)) {
    throw "Batch submit script does not exist: $submitScript"
}

$inputUri = "gs://$Bucket/caption-batch/requests/$Dataset/requests.jsonl"
$outputUri = "gs://$Bucket/caption-batch/output/$Dataset/$RunId/"
$displayName = "gemini-caption-$Dataset-$RunId"

Write-Host "Local requests: $requestsPath"
Write-Host "Input URI:      $inputUri"
Write-Host "Output URI:     $outputUri"
Write-Host "Model:          $Model"
Write-Host "Run ID:         $RunId"

& gcloud storage cp $requestsPath $inputUri "--project=$Project" "--content-type=application/x-ndjson"
if ($LASTEXITCODE -ne 0) {
    throw "GCS request upload failed with exit code $LASTEXITCODE."
}

$submitArguments = @(
    "run",
    "python",
    $submitScript,
    "--project",
    $Project,
    "--location",
    $Location,
    "--model",
    $Model,
    "--display-name",
    $displayName,
    "--input-uri",
    $inputUri,
    "--output-uri",
    $outputUri
)
if ($Wait) {
    $submitArguments += "--wait"
}

Push-Location $apiDirectory
try {
    & uv @submitArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Batch job submission failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
