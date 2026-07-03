param(
    [int]$Port = 8787
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

$env:WEB_PORT = [string]$Port
Write-Host "Starting local web app on http://127.0.0.1:$Port"
Write-Host "Keep this window open while using the website. Do not start it with WindowStyle Hidden; Chrome verification can fail on Windows."
& $python ".\web_app.py"
