param(
    [Parameter(Mandatory = $true)]
    [string]$Topic,

    [int]$Count = 20,

    [string]$StartDate = "",

    [string]$EndDate = "",

    [ValidateSet("auto", "general", "marketing")]
    [string]$Focus = "auto",

    [string]$ExtraKeywords = "",

    [int]$PoolSize = 0,

    [switch]$OnlyUrls
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$researchArgs = @(
    "-ExecutionPolicy", "Bypass",
    "-File", ".\run_research.ps1",
    "-Topic", $Topic,
    "-Count", $Count,
    "-Focus", $Focus
)

if ($StartDate) {
    $researchArgs += @("-StartDate", $StartDate)
}
if ($EndDate) {
    $researchArgs += @("-EndDate", $EndDate)
}
if ($ExtraKeywords) {
    $researchArgs += @("-ExtraKeywords", $ExtraKeywords)
}
if ($PoolSize -gt 0) {
    $researchArgs += @("-PoolSize", $PoolSize)
}

Write-Host "Auto mode 1/2: searching, screening, and resolving WeChat URLs..."
& powershell @researchArgs

if ($OnlyUrls) {
    Write-Host "Auto mode finished. urls.txt is ready."
    exit 0
}

Write-Host "Auto mode 2/2: parsing urls.txt with MinerU..."
& powershell -ExecutionPolicy Bypass -File ".\run_manual.ps1"
