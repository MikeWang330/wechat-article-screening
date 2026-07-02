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
    $value = Get-JsonValue $paramsData "exclude_keywords"; if ($null -ne $value) { $ExcludeKeywords = [string]$value }
    $value = Get-JsonValue $paramsData "min_rating"; if ($value -in @("weak", "maybe", "strong")) { $MinRating = [string]$value }
    $value = Get-JsonValue $paramsData "start_date"; if ($null -ne $value) { $StartDate = [string]$value }
    $value = Get-JsonValue $paramsData "end_date"; if ($null -ne $value) { $EndDate = [string]$value }
    $value = Get-JsonValue $paramsData "write_urls"; if ($null -ne $value) { $NoWriteUrls = -not [bool]$value }
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
