param(
    [Parameter(Mandatory = $true)]
    [string]$Topic,

    [int]$Count = 20,

    [string]$StartDate = "",

    [string]$EndDate = "",

    [ValidateSet("auto", "general", "marketing")]
    [string]$Focus = "general",

    [ValidateSet("weak", "maybe", "strong")]
    [string]$MinRating = "maybe",

    [string]$ExtraKeywords = "",

    [int]$PoolSize = 0,

    [int]$RecentDays = 365,

    [switch]$OnlyUrls
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not $StartDate -and -not $EndDate -and $RecentDays -gt 0) {
    $EndDate = (Get-Date).ToString("yyyy-MM-dd")
    $StartDate = (Get-Date).AddDays(-1 * $RecentDays).ToString("yyyy-MM-dd")
    Write-Host "No date range provided. Defaulting to the most recent $RecentDays days: $StartDate to $EndDate"
}

$researchArgs = @(
    "-ExecutionPolicy", "Bypass",
    "-File", ".\run_research.ps1",
    "-Topic", $Topic,
    "-Count", $Count,
    "-Focus", $Focus,
    "-MinRating", $MinRating
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
