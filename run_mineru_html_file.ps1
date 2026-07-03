param(
    [string]$Urls = "urls.txt",
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
    $env:PYTHONIOENCODING = "utf-8"
} catch {
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

$arguments = @("mineru_batch_wechat.py", "--urls", $Urls, "--submit-source", "html-file")
if ($OutputDir) {
    $arguments += @("--output-dir", $OutputDir)
}

& $python @arguments
exit $LASTEXITCODE
