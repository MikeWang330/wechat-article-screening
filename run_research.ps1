param(
    [Parameter(Mandatory = $true)]
    [string]$Topic,

    [int]$Count = 20,

    [int]$PoolSize = 0,

    [ValidateSet("fast", "slow")]
    [string]$Mode = "slow",

    [switch]$NoWriteUrls,

    [string]$ExtraKeywords = "",

    [ValidateSet("auto", "general", "marketing")]
    [string]$Focus = "auto",

    [ValidateSet("weak", "maybe", "strong")]
    [string]$MinRating = "maybe",

    [string]$StartDate = "",

    [string]$EndDate = ""
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

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

$arguments = @("wechat_research.py", "--topic", $Topic, "--count", $Count, "--mode", $Mode)
if ($PoolSize -gt 0) {
    $arguments += @("--pool-size", $PoolSize)
}
if ($ExtraKeywords) {
    $arguments += @("--extra-keywords", $ExtraKeywords)
}
if ($Focus) {
    $arguments += @("--focus", $Focus)
}
if ($MinRating) {
    $arguments += @("--min-rating", $MinRating)
}
if ($StartDate) {
    $arguments += @("--start-date", $StartDate)
}
if ($EndDate) {
    $arguments += @("--end-date", $EndDate)
}
if (-not $NoWriteUrls) {
    $arguments += "--write-urls"
}

& $python @arguments
exit $LASTEXITCODE
