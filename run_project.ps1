param(
    [Parameter(Mandatory = $true)]
    [string]$Topic,

    [int]$Count = 20,

    [int]$PoolSize = 0,

    [string]$ExtraKeywords = "",

    [ValidateSet("auto", "general", "marketing")]
    [string]$Focus = "auto",

    [string]$StartDate = "",

    [string]$EndDate = "",

    [switch]$SkipMinerU
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$researchArgs = @(
    "-ExecutionPolicy", "Bypass",
    "-File", ".\run_research.ps1",
    "-Topic", $Topic,
    "-Count", $Count
)

if ($PoolSize -gt 0) {
    $researchArgs += @("-PoolSize", $PoolSize)
}
if ($ExtraKeywords) {
    $researchArgs += @("-ExtraKeywords", $ExtraKeywords)
}
if ($Focus) {
    $researchArgs += @("-Focus", $Focus)
}
if ($StartDate) {
    $researchArgs += @("-StartDate", $StartDate)
}
if ($EndDate) {
    $researchArgs += @("-EndDate", $EndDate)
}

Write-Host "Step 1/2: searching, screening, and resolving WeChat URLs..."
& powershell @researchArgs
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if ($SkipMinerU) {
    Write-Host "SkipMinerU is set. urls.txt is ready."
    exit 0
}

Write-Host "Step 2/2: parsing urls.txt with MinerU..."
& powershell -ExecutionPolicy Bypass -File ".\run_mineru_html_file.ps1"
exit $LASTEXITCODE
