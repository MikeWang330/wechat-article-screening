param(
    [string]$Topic = "",

    [int]$Count = 20,

    [string]$StartDate = "",

    [string]$EndDate = "",

    [ValidateSet("weak", "maybe", "strong")]
    [string]$MinRating = "maybe",

    [string]$ExtraKeywords = "",

    [int]$PoolSize = 0,

    [ValidateSet("fast", "slow")]
    [string]$Mode = "slow",

    [int]$RecentDays = 365,

    [string]$ExcludeKeywords = "",

    [string]$MemoryFile = "research_memory.json",

    [switch]$NoMemory,

    [ValidateSet("all", "search", "mineru", "retry")]
    [string]$Stage = "all",

    [switch]$OnlyUrls
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

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
            foreach ($part in ($item.ToString() -split "[,，;；]")) {
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

        if (-not $PSBoundParameters.ContainsKey("Mode") -and $memory.default_mode -in @("fast", "slow")) {
            $Mode = $memory.default_mode
        }
        if (-not $PSBoundParameters.ContainsKey("MinRating") -and $memory.default_min_rating -in @("weak", "maybe", "strong")) {
            $MinRating = $memory.default_min_rating
        }
        if (-not $PSBoundParameters.ContainsKey("RecentDays") -and $memory.default_recent_days) {
            $RecentDays = [int]$memory.default_recent_days
        }

        $memoryExtra = Get-MemoryValues $memory @("preferred_article_types", "default_extra_keywords", "include_keywords")
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

Write-Host "Auto mode tip: give a detailed topic when possible, for example: topic + date range + target type."
Write-Host "Auto mode defaults: Screening=general, MinRating=$MinRating, RecentDays=$RecentDays, Stage=$Stage, Mode=$Mode."
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

Write-Host "Auto mode 2/2: parsing urls.txt with MinerU..."
& powershell -ExecutionPolicy Bypass -File ".\run_manual.ps1"
exit $LASTEXITCODE
