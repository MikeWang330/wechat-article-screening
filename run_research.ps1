param(
    [string]$Topic,

    [string]$ParamsFile = "",

    [int]$Count = 20,

    [int]$PoolSize = 0,

    [ValidateSet("fast", "slow")]
    [string]$Mode = "slow",

    [switch]$NoWriteUrls,

    [string]$ExtraKeywords = "",

    [string]$ExcludeKeywords = "",

    [ValidateSet("weak", "maybe", "strong")]
    [string]$MinRating = "maybe",

    [string]$StartDate = "",

    [string]$EndDate = ""
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if ($ParamsFile) {
    if (-not (Test-Path -LiteralPath $ParamsFile)) {
        throw "ParamsFile was not found: $ParamsFile"
    }
    $paramsData = Get-Content -LiteralPath $ParamsFile -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($paramsData.topic) { $Topic = [string]$paramsData.topic }
    if ($paramsData.count) { $Count = [int]$paramsData.count }
    if ($paramsData.pool_size) { $PoolSize = [int]$paramsData.pool_size }
    if ($paramsData.mode -in @("fast", "slow")) { $Mode = [string]$paramsData.mode }
    if ($paramsData.extra_keywords) { $ExtraKeywords = [string]$paramsData.extra_keywords }
    if ($paramsData.exclude_keywords) { $ExcludeKeywords = [string]$paramsData.exclude_keywords }
    if ($paramsData.min_rating -in @("weak", "maybe", "strong")) { $MinRating = [string]$paramsData.min_rating }
    if ($paramsData.start_date) { $StartDate = [string]$paramsData.start_date }
    if ($paramsData.end_date) { $EndDate = [string]$paramsData.end_date }
    if ($null -ne $paramsData.write_urls) { $NoWriteUrls = -not [bool]$paramsData.write_urls }
}

if (-not $Topic) {
    throw "Topic is required."
}

$pythonCandidates = @(
    "$env:LOCALAPPDATA\Python\bin\python.exe",
    "$env:LOCALAPPDATA\Python\pythoncore-3.14-64\python.exe",
    "python",
    "py"
)

$python = $null
foreach ($candidate in $pythonCandidates) {
    try {
        $command = Get-Command $candidate -ErrorAction Stop
        if ($command.Source -like "*Microsoft\WindowsApps\python.exe") {
            continue
        }
        $python = $candidate
        break
    } catch {
    }
}

if (-not $python) {
    throw "No usable Python was found. Please install Python or add it to PATH."
}

$workDir = Join-Path $PSScriptRoot "work"
New-Item -ItemType Directory -Force -Path $workDir | Out-Null
$pythonParamsPath = Join-Path $workDir ("wechat-research-params-{0}.json" -f (Get-Date -Format "yyyyMMdd-HHmmss-fff"))
$pythonParams = [ordered]@{
    topic = $Topic
    count = $Count
    mode = $Mode
    pool_size = $PoolSize
    extra_keywords = $ExtraKeywords
    exclude_keywords = $ExcludeKeywords
    min_rating = $MinRating
    start_date = $StartDate
    end_date = $EndDate
    write_urls = (-not $NoWriteUrls)
}
$pythonParams | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $pythonParamsPath -Encoding UTF8

$arguments = @("wechat_research.py", "--params-file", $pythonParamsPath)

& $python @arguments
exit $LASTEXITCODE
