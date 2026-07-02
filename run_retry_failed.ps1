param(
    [string]$RunDir = "",
    [string]$FailedUrls = "",
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not $RunDir -and (Test-Path "latest_run.txt")) {
    $RunDir = (Get-Content "latest_run.txt" -Raw).Trim()
}

if (-not $FailedUrls) {
    if (-not $RunDir) {
        throw "No run directory was provided, and latest_run.txt was not found."
    }
    $FailedUrls = Join-Path $RunDir "failed_urls.txt"
}

if (-not (Test-Path $FailedUrls)) {
    throw "Failed URL file was not found: $FailedUrls"
}

$urlCount = (Get-Content $FailedUrls | Where-Object { $_.Trim() -and -not $_.Trim().StartsWith("#") }).Count
if ($urlCount -eq 0) {
    Write-Host "No failed URLs to retry."
    exit 0
}

if (-not $OutputDir) {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path "runs" "$timestamp-retry-failed"
}

Write-Host "Retry mode: parsing $urlCount failed URLs with MinerU..."
Write-Host "Failed URLs: $FailedUrls"
Write-Host "Retry output: $OutputDir"

& powershell -ExecutionPolicy Bypass -File ".\run_mineru_html_file.ps1" -Urls $FailedUrls -OutputDir $OutputDir
exit $LASTEXITCODE
