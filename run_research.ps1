param(
    [Parameter(Mandatory = $true)]
    [string]$Topic,

    [int]$Count = 20,

    [int]$PoolSize = 0,

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
    "C:\Users\YQSL\AppData\Local\Python\bin\python.exe",
    "py"
)

$python = $null
foreach ($candidate in $pythonCandidates) {
    $command = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($command) {
        $python = $candidate
        break
    }
}

if (-not $python) {
    throw "Could not find Python. Please install Python or keep using the existing Python launcher."
}

$arguments = @("wechat_research.py", "--topic", $Topic, "--count", $Count)
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
