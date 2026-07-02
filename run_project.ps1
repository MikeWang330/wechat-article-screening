param(
    [Parameter(Mandatory = $true)]
    [string]$Topic,

    [int]$Count = 20,

    [int]$PoolSize = 0,

    [ValidateSet("fast", "slow")]
    [string]$Mode = "slow",

    [string]$ExtraKeywords = "",

    [string]$StartDate = "",

    [string]$EndDate = "",

    [switch]$SkipMinerU
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$workDir = Join-Path $PSScriptRoot "work"
New-Item -ItemType Directory -Force -Path $workDir | Out-Null
$researchParamsPath = Join-Path $workDir ("run-project-params-{0}.json" -f (Get-Date -Format "yyyyMMdd-HHmmss-fff"))
$researchParams = [ordered]@{
    topic = $Topic
    count = $Count
    mode = $Mode
    pool_size = $PoolSize
    extra_keywords = $ExtraKeywords
    start_date = $StartDate
    end_date = $EndDate
    write_urls = $true
}
$researchParams | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $researchParamsPath -Encoding UTF8

$researchArgs = @(
    "-ExecutionPolicy", "Bypass",
    "-File", ".\run_research.ps1",
    "-ParamsFile", $researchParamsPath
)

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
