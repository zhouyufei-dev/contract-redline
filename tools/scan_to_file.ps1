# Run the scanner and save output as UTF-8 (PowerShell's default redirect
# writes UTF-16, which is unreadable in editors).
param(
    [string]$File = 'data/samples/fake_contract_01.docx',
    [string]$Out = 'data/outputs/scan.txt',
    [switch]$ShowSuppressed
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    $python = Join-Path $root '.venv\Scripts\python.exe'
    $args = @('-m', 'app.main', $File, '--scan')
    if ($ShowSuppressed) { $args += '--show-suppressed' }

    $lines = & $python @args 2>&1
    $code = $LASTEXITCODE
    $lines | Out-File -FilePath $Out -Encoding utf8
    Write-Output "exit=$code  lines=$($lines.Count)  -> $Out"
}
finally {
    Pop-Location
}
