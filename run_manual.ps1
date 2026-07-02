$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path "urls.txt")) {
    throw "urls.txt was not found. Create urls.txt first, one WeChat article URL per line."
}

$urlCount = (Get-Content "urls.txt" | Where-Object { $_.Trim() -and -not $_.Trim().StartsWith("#") }).Count
if ($urlCount -eq 0) {
    throw "urls.txt is empty. Add one WeChat article URL per line."
}

Write-Host "Manual mode: parsing $urlCount URLs from urls.txt with MinerU..."
& powershell -ExecutionPolicy Bypass -File ".\run_mineru_html_file.ps1"
exit $LASTEXITCODE
