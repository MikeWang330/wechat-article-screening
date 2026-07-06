param(
    [string]$Topic = "",

    [string]$ParamsFile = "",

    [int]$Count = 20,

    [string]$StartDate = "",

    [string]$EndDate = "",

    [ValidateSet("weak", "maybe", "strong")]
    [string]$MinRating = "maybe",

    [string]$ExtraKeywords = "",

    [int]$PoolSize = 0,

    [int]$MaxQueries = 0,

    [int]$TopPerQuery = 0,

    [ValidateSet("fast", "slow")]
    [string]$Mode = "slow",

    [int]$RecentDays = 365,

    [string]$ExcludeKeywords = "",

    [string]$MemoryFile = "research_memory.json",

    [switch]$NoMemory,

    [ValidateSet("all", "search", "mineru", "retry")]
    [string]$Stage = "all",

    [int]$SogouVerifyTimeout = 180,

    [switch]$NoBrowser,

    [string]$ChromePath = "",

    [double]$MinDelay = 1.0,

    [double]$MaxDelay = 3.0,

    [double]$CacheTtlHours = 12,

    [switch]$ContinueAfterBlock,

    [int]$StopAfterEmptyRounds = 2,

    [switch]$OnlyUrls
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$boundParameters = @{} + $PSBoundParameters

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
    $value = Get-JsonValue $paramsData "topic"; if ($null -ne $value) { $Topic = [string]$value; $boundParameters["Topic"] = $true }
    $value = Get-JsonValue $paramsData "count"; if ($null -ne $value) { $Count = [int]$value; $boundParameters["Count"] = $true }
    $value = Get-JsonValue $paramsData "start_date"; if ($null -ne $value) { $StartDate = [string]$value; $boundParameters["StartDate"] = $true }
    $value = Get-JsonValue $paramsData "end_date"; if ($null -ne $value) { $EndDate = [string]$value; $boundParameters["EndDate"] = $true }
    $value = Get-JsonValue $paramsData "min_rating"; if ($value -in @("weak", "maybe", "strong")) { $MinRating = [string]$value; $boundParameters["MinRating"] = $true }
    $value = Get-JsonValue $paramsData "extra_keywords"; if ($null -ne $value) { $ExtraKeywords = [string]$value; $boundParameters["ExtraKeywords"] = $true }
    $value = Get-JsonValue $paramsData "pool_size"; if ($null -ne $value) { $PoolSize = [int]$value; $boundParameters["PoolSize"] = $true }
    $value = Get-JsonValue $paramsData "max_queries"; if ($null -ne $value) { $MaxQueries = [int]$value; $boundParameters["MaxQueries"] = $true }
    $value = Get-JsonValue $paramsData "top_per_query"; if ($null -ne $value) { $TopPerQuery = [int]$value; $boundParameters["TopPerQuery"] = $true }
    $value = Get-JsonValue $paramsData "mode"; if ($value -in @("fast", "slow")) { $Mode = [string]$value; $boundParameters["Mode"] = $true }
    $value = Get-JsonValue $paramsData "recent_days"; if ($null -ne $value) { $RecentDays = [int]$value; $boundParameters["RecentDays"] = $true }
    $value = Get-JsonValue $paramsData "exclude_keywords"; if ($null -ne $value) { $ExcludeKeywords = [string]$value; $boundParameters["ExcludeKeywords"] = $true }
    $value = Get-JsonValue $paramsData "memory_file"; if ($null -ne $value) { $MemoryFile = [string]$value; $boundParameters["MemoryFile"] = $true }
    $value = Get-JsonValue $paramsData "no_memory"; if ($null -ne $value) { $NoMemory = [bool]$value; $boundParameters["NoMemory"] = $true }
    $value = Get-JsonValue $paramsData "stage"; if ($value -in @("all", "search", "mineru", "retry")) { $Stage = [string]$value; $boundParameters["Stage"] = $true }
    $value = Get-JsonValue $paramsData "sogou_verify_timeout"; if ($null -ne $value) { $SogouVerifyTimeout = [int]$value; $boundParameters["SogouVerifyTimeout"] = $true }
    $value = Get-JsonValue $paramsData "no_browser"; if ($null -ne $value) { $NoBrowser = [bool]$value; $boundParameters["NoBrowser"] = $true }
    $value = Get-JsonValue $paramsData "chrome_path"; if ($null -ne $value) { $ChromePath = [string]$value; $boundParameters["ChromePath"] = $true }
    $value = Get-JsonValue $paramsData "min_delay"; if ($null -ne $value) { $MinDelay = [double]$value; $boundParameters["MinDelay"] = $true }
    $value = Get-JsonValue $paramsData "max_delay"; if ($null -ne $value) { $MaxDelay = [double]$value; $boundParameters["MaxDelay"] = $true }
    $value = Get-JsonValue $paramsData "cache_ttl_hours"; if ($null -ne $value) { $CacheTtlHours = [double]$value; $boundParameters["CacheTtlHours"] = $true }
    $value = Get-JsonValue $paramsData "continue_after_block"; if ($null -ne $value) { $ContinueAfterBlock = [bool]$value; $boundParameters["ContinueAfterBlock"] = $true }
    $value = Get-JsonValue $paramsData "stop_after_empty_rounds"; if ($null -ne $value) { $StopAfterEmptyRounds = [int]$value; $boundParameters["StopAfterEmptyRounds"] = $true }
    $value = Get-JsonValue $paramsData "only_urls"; if ($null -ne $value) { $OnlyUrls = [bool]$value; $boundParameters["OnlyUrls"] = $true }
}

function Join-Terms {
    param([object[]]$Values)

    $seen = @{}
    $result = @()

    foreach ($value in $Values) {
        if ($null -eq $value) {
            continue
        }
        $items = @()
        if ($value -is [System.Array]) {
            $items = $value
        } else {
            $items = @($value)
        }
        foreach ($item in $items) {
            if ($null -eq $item) {
                continue
            }
            $normalizedItem = $item.ToString().Replace([char]0xFF0C, ",").Replace([char]0xFF1B, ";")
            foreach ($part in ($normalizedItem -split "[,;]")) {
                $term = $part.Trim()
                if ($term -and -not $seen.ContainsKey($term)) {
                    $seen[$term] = $true
                    $result += $term
                }
            }
        }
    }

    return ($result -join ",")
}

function Get-MemoryValues {
    param(
        [object]$Memory,
        [string[]]$Names
    )

    $values = @()
    foreach ($name in $Names) {
        $property = $Memory.PSObject.Properties[$name]
        if ($property -and $null -ne $property.Value) {
            $values += $property.Value
        }
    }
    return $values
}

if (-not $NoMemory -and $MemoryFile -and (Test-Path -LiteralPath $MemoryFile)) {
    try {
        $memory = Get-Content -LiteralPath $MemoryFile -Raw -Encoding UTF8 | ConvertFrom-Json
        Write-Host "Loaded local research memory: $MemoryFile"

        if (-not $boundParameters.ContainsKey("Mode") -and $memory.default_mode -in @("fast", "slow")) {
            $Mode = $memory.default_mode
        }
        if (-not $boundParameters.ContainsKey("MinRating") -and $memory.default_min_rating -in @("weak", "maybe", "strong")) {
            $MinRating = $memory.default_min_rating
        }
        if (-not $boundParameters.ContainsKey("RecentDays") -and $memory.default_recent_days) {
            $RecentDays = [int]$memory.default_recent_days
        }

        $memoryExtra = Get-MemoryValues $memory @("include_keywords")
        if ($memoryExtra.Count -gt 0) {
            $ExtraKeywords = Join-Terms @($ExtraKeywords, $memoryExtra)
        }

        $memoryExclude = Get-MemoryValues $memory @("default_exclusions", "exclude_keywords")
        if ($memoryExclude.Count -gt 0) {
            $ExcludeKeywords = Join-Terms @($ExcludeKeywords, $memoryExclude)
        }
    } catch {
        Write-Warning "Could not read local research memory from ${MemoryFile}: $($_.Exception.Message)"
    }
}

Write-Host "Auto mode: Stage=$Stage, Mode=$Mode, RecentDays=$RecentDays, ResultCap=$Count."
if ($MaxQueries -gt 0 -or $TopPerQuery -gt 0) {
    Write-Host "Search budget: MaxQueries=$MaxQueries, TopPerQuery=$TopPerQuery, PoolSize=$PoolSize."
}
Write-Host "Quality rule: return accurate results only; do not pad weak matches."

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

if ($Count -le 0) {
    throw "Count must be greater than 0."
}

if (-not $StartDate -and -not $EndDate -and $RecentDays -gt 0) {
    $EndDate = (Get-Date).ToString("yyyy-MM-dd")
    $StartDate = (Get-Date).AddDays(-1 * $RecentDays).ToString("yyyy-MM-dd")
    Write-Host "No date range provided. Defaulting to the most recent $RecentDays days: $StartDate to $EndDate"
}

$workDir = Join-Path $PSScriptRoot "work"
New-Item -ItemType Directory -Force -Path $workDir | Out-Null
$researchParamsPath = Join-Path $workDir ("run-auto-params-{0}.json" -f (Get-Date -Format "yyyyMMdd-HHmmss-fff"))
$researchParams = [ordered]@{
    topic = $Topic
    count = $Count
    mode = $Mode
    min_rating = $MinRating
    start_date = $StartDate
    end_date = $EndDate
    extra_keywords = $ExtraKeywords
    exclude_keywords = $ExcludeKeywords
    pool_size = $PoolSize
    max_queries = $MaxQueries
    top_per_query = $TopPerQuery
    sogou_verify_timeout = $SogouVerifyTimeout
    no_browser = [bool]$NoBrowser
    chrome_path = $ChromePath
    min_delay = $MinDelay
    max_delay = $MaxDelay
    cache_ttl_hours = $CacheTtlHours
    continue_after_block = [bool]$ContinueAfterBlock
    stop_after_empty_rounds = $StopAfterEmptyRounds
    write_urls = $true
}
$researchParams | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $researchParamsPath -Encoding UTF8

$researchArgs = @(
    "-ExecutionPolicy", "Bypass",
    "-File", ".\run_research.ps1",
    "-ParamsFile", $researchParamsPath
)

Write-Host "Auto mode 1/2: searching, screening, and resolving WeChat URLs..."
& powershell @researchArgs
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if ($OnlyUrls -or $Stage -eq "search") {
    Write-Host "Auto mode finished. urls.txt is ready."
    exit 0
}

$usableUrls = @()
if (Test-Path -LiteralPath "urls.txt") {
    $usableUrls = Get-Content -LiteralPath "urls.txt" -Encoding UTF8 | Where-Object { $_ -match "mp\.weixin\.qq\.com" }
}
if ($usableUrls.Count -eq 0) {
    Write-Host "Auto mode stopped before MinerU: no usable WeChat URLs were written to urls.txt."
    Write-Host "Check candidates/ for the screened search results, then retry after browser verification works or add URLs manually."
    exit 0
}

Write-Host "Auto mode 2/2: parsing urls.txt with MinerU..."
& powershell -ExecutionPolicy Bypass -File ".\run_manual.ps1"
exit $LASTEXITCODE
