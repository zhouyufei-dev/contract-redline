$ErrorActionPreference = "Continue"
$python = ".\.venv\Scripts\python.exe"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONWARNINGS = "ignore"

$suites = @("test_rules", "test_config", "test_llm", "test_report", "test_web", "test_site", "test_paywall")
$bad = @()

foreach ($suite in $suites) {
    Write-Host "=== $suite ===" -ForegroundColor Cyan
    & $python "tools\$suite.py" 2>&1 | Select-String -Pattern "FAIL|passed|error|Error" | ForEach-Object { $_.Line }
    if ($LASTEXITCODE -ne 0) { $bad += $suite }
}

Write-Host ""
if ($bad.Count -eq 0) {
    Write-Host "ALL SUITES PASSED" -ForegroundColor Green
} else {
    Write-Host ("FAILED: " + ($bad -join ", ")) -ForegroundColor Red
    exit 1
}
