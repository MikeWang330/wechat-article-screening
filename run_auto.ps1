param(
    [string]$Topic = "",

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

    [ValidateSet("all", "search", "mineru", "retry")]
    [string]$Stage = "all",

    [switch]$OnlyUrls
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Auto mode tip: give a detailed topic when possible, for example: topic + date range + target type."
Write-Host "Auto mode defaults: Focus=$Focus, MinRating=$MinRating, RecentDays=$RecentDays, Stage=$Stage."
Write-Host "Quality rule: if there are not enough accurate articles, the program returns fewer instead of padding weak matches."

if ($Stage -eq "retry") {
    Write-Host "Auto mode retry: rerunning the failed URLs from the latest run..."
    & powershell -ExecutionPolicy Bypass -File ".\run_retry_failed.ps1"
    exit $LASTEXITCODE
}

if ($Stage -eq "mineru") {
    Write-Host "Auto mode MinerU-only: parsing the existing urls.txt..."
    & powershell -ExecutionPolicy Bypass -File ".\run_manual.ps1"
    exit $LASTEXITCODE
}

if (-not $Topic) {
    throw "Topic is required when Stage is all or search."
}

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
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if ($OnlyUrls -or $Stage -eq "search") {
    Write-Host "Auto mode finished. urls.txt is ready."
    exit 0
}

Write-Host "Auto mode 2/2: parsing urls.txt with MinerU..."
& powershell -ExecutionPolicy Bypass -File ".\run_manual.ps1"
