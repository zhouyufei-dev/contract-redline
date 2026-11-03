<#
.SYNOPSIS
    Unit tests for tools\git_guard.ps1.

.DESCRIPTION
    The guard is the only thing standing between a public GitHub repo and a live
    Stripe key, so its rules get tested directly instead of being trusted.

    Run: powershell -ExecutionPolicy Bypass -File tools\test_git_guard.ps1
    Exit code 0 = all passed.
#>

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "git_guard.ps1")

$script:passed = 0
$script:failed = 0

function Check {
    param([string]$Name, [bool]$Condition, [string]$Detail = "")
    if ($Condition) {
        $script:passed++
        Write-Host "  ok   $Name"
    } else {
        $script:failed++
        Write-Host "  FAIL $Name $Detail" -ForegroundColor Red
    }
}

Write-Host "1. files that must be blocked"
$mustBlock = @(
    ".env",
    "backend/.env",
    ".env.bak",
    ".env.local",
    ".env.prod.backup",
    ".streamlit/secrets.toml",
    "secrets.toml",
    ".venv/Lib/site-packages/x.py",
    "data/cache/llm/abc.json",
    "deploy/server.key.pem",
    "cert.pfx",
    "id_rsa",
    "C:\Users\someone\.ssh\id_ed25519"
)
foreach ($file in $mustBlock) {
    $bad = Get-ForbiddenStagedFile -Paths @($file)
    Check "blocks $file" ($bad.Count -eq 1) "(got $($bad.Count))"
}

Write-Host "2. files that must go through"
$mustAllow = @(
    ".env.example",
    ".env.sample",
    ".streamlit/secrets.toml.example",
    "app/config.py",
    "app/rules/redlines_us.py",
    "app/web/streamlit_app.py",
    "docs/11-第11步-部署上线手册.md",
    "data/samples/fake_contract_01.docx",
    "tools/test_paywall.py",
    "requirements.txt",
    ".gitignore"
)
foreach ($file in $mustAllow) {
    $bad = Get-ForbiddenStagedFile -Paths @($file)
    Check "allows $file" ($bad.Count -eq 0) "(got $($bad -join ', '))"
}

Write-Host "3. mixed list reports only the offenders"
$mixed = @(".env", "app/config.py", "secrets.toml", "docs/readme.md")
$bad = Get-ForbiddenStagedFile -Paths $mixed
Check "count is 2" ($bad.Count -eq 2) "(got $($bad.Count))"
Check "names .env" ($bad -contains ".env")
Check "names secrets.toml" ($bad -contains "secrets.toml")

Write-Host "4. empty input is not an error"
$bad = Get-ForbiddenStagedFile -Paths @()
Check "empty list returns nothing" ($bad.Count -eq 0)

Write-Host ""
if ($script:failed -gt 0) {
    Write-Host "RESULT: $($script:passed) passed, $($script:failed) FAILED" -ForegroundColor Red
    exit 1
}
Write-Host "RESULT: all $($script:passed) checks passed" -ForegroundColor Green
exit 0
