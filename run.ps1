# One-command runner. Uses the project's own venv, so you never have to
# activate it or fight with PATH.
#
#   .\run.ps1 data/samples/fake_contract_01.docx
#   .\run.ps1 data/samples/fake_contract_01.pdf -Save
#   .\run.ps1 data/samples/fake_contract_01.docx -Scan
#   .\run.ps1 data/samples/fake_contract_01.docx -Scan -ShowSuppressed
#   .\run.ps1 data/samples/fake_contract_01.docx -Scan -Explain
#   .\run.ps1 data/samples/fake_contract_01.docx -Scan -Html -Open
#   .\run.ps1 data/samples/fake_contract_01.docx -Scan -Html report.html
#   .\run.ps1 data/samples/fake_contract_01.docx -Scan -Explain -NoCache -SaveReport
#
# If PowerShell blocks the script, run once:
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$File,

    [Parameter(Position = 1)]
    [string]$ReportPath = 'auto',

    [switch]$Save,
    [switch]$Scan,
    [switch]$Explain,
    [switch]$Html,
    [switch]$Open,
    [switch]$NoLlm,
    [switch]$NoCache,
    [switch]$SaveReport,
    [switch]$ShowSuppressed
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'

if (-not (Test-Path $python)) {
    Write-Host "Virtual environment missing. Run this first:" -ForegroundColor Yellow
    Write-Host "  python -m venv .venv"
    exit 1
}

$extra = @()
if ($Save)           { $extra += '--save' }
if ($Scan)           { $extra += '--scan' }
if ($Explain)        { $extra += '--explain' }
if ($Html) {
    if ($ReportPath -and $ReportPath -ne 'auto') { $extra += @('--html', $ReportPath) }
    else { $extra += '--html' }
}
if ($Open)           { $extra += '--open' }
if ($NoLlm)          { $extra += '--no-llm' }
if ($NoCache)        { $extra += '--no-cache' }
if ($SaveReport)     { $extra += '--save-report' }
if ($ShowSuppressed) { $extra += '--show-suppressed' }

Push-Location $root
try {
    # Make Python emit UTF-8 regardless of the console code page, so quoted
    # contract text with curly quotes / dashes is not mangled.
    $env:PYTHONIOENCODING = 'utf-8'
    & $python -m app.main $File @extra
    $code = $LASTEXITCODE
}
finally {
    Pop-Location
}

exit $code
