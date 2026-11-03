# Dev helper: render the report to PNG with headless Edge so we can check the
# layout without a human opening a browser. Not part of the product.
param(
    [string]$Url = 'http://127.0.0.1:8765/fake_contract_01.report.html',
    [string]$Out = 'data\outputs\shot.png',
    [int]$Width = 1100,
    [int]$Height = 1600
)

$edge = 'C:\Program Files\Edge\App\msedge.exe'
$root = Split-Path $PSScriptRoot -Parent
$outPath = Join-Path $root $Out
$profile = Join-Path $env:TEMP ('edge-shot-' + [guid]::NewGuid().ToString('N'))

& $edge --headless=new --disable-gpu --no-first-run --no-default-browser-check `
    --hide-scrollbars --user-data-dir="$profile" `
    --window-size="$Width,$Height" --screenshot="$outPath" $Url 2>&1 | Out-String | Write-Verbose
Start-Sleep -Seconds 2

if (Test-Path $outPath) {
    $size = (Get-Item $outPath).Length
    Write-Output "OK $outPath ($size bytes)"
} else {
    Write-Output "FAILED - no file at $outPath"
    exit 1
}
