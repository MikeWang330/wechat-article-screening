param(
    [string]$Topic = "",

    [string]$ParamsFile = "",

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

try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
    $env:PYTHONIOENCODING = "utf-8"
} catch {
}

function Get-JsonValue {
    param(
        [object]$Object,
        [string]$Name
    )

    $property = $Object.PSObject.Properties[$Name]
    if (-not $property) {
        return $null
    }
    if ($property.Value -is [string] -and $property.Value -eq "") {
        return $null
    }
    return $property.Value
}

if ($ParamsFile) {
    if (-not (Test-Path -LiteralPath $ParamsFile)) {
        throw "ParamsFile was not found: $ParamsFile"
    }
    $paramsData = Get-Content -LiteralPath $ParamsFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $value = Get-JsonValue $paramsData "topic"; if ($null -ne $value) { $Topic = [string]$value }
    $value = Get-JsonValue $paramsData "count"; if ($null -ne $value) { $Count = [int]$value }
    $value = Get-JsonValue $paramsData "pool_size"; if ($null -ne $value) { $PoolSize = [int]$value }
    $value = Get-JsonValue $paramsData "mode"; if ($value -in @("fast", "slow")) { $Mode = [string]$value }
    $value = Get-JsonValue $paramsData "extra_keywords"; if ($null -ne $value) { $ExtraKeywords = [string]$value }
    $value = Get-JsonValue $paramsData "start_date"; if ($null -ne $value) { $StartDate = [string]$value }
    $value = Get-JsonValue $paramsData "end_date"; if ($null -ne $value) { $EndDate = [string]$value }
    $value = Get-JsonValue $paramsData "skip_mineru"; if ($null -ne $value) { $SkipMinerU = [bool]$value }
}

if (-not $Topic) {
    throw "Topic is required."
}

if ($Count -le 0) {
    throw "Count must be greater than 0."
}

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
