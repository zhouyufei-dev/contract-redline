# One-command launcher for the web UI.
#
#   .\web.ps1              # start on http://localhost:8501
#   .\web.ps1 -Port 8600   # start on another port
#   .\web.ps1 -Headless    # do not open a browser tab
#
# The CLI still works exactly as before (.\run.ps1 ...). This file only starts
# Streamlit and opens the browser for you.

param(
    [int]$Port = 8501,
    [switch]$Headless
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'

if (-not (Test-Path $python)) {
    Write-Host "The virtual environment is missing. Create it first:" -ForegroundColor Yellow
    Write-Host "  python -m venv .venv"
    Write-Host "  .\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-web.txt"
    exit 1
}

Push-Location $root
try {
    # One-time install of the web stack (Streamlit + its dependencies).
    # Presence is checked on disk rather than by running `python -c "import
    # streamlit"`: PowerShell 5.1 both strips the nested quotes out of that
    # command and aborts the script when a native command writes to stderr,
    # so the two failure modes there would hide each other.
    $hasStreamlit = Test-Path (Join-Path $root '.venv\Lib\site-packages\streamlit')

    if (-not $hasStreamlit) {
        Write-Host "Installing the web UI for the first time (about 50 MB, one time only)..." -ForegroundColor Yellow
        & $python -m pip install -r requirements-web.txt
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Install failed. Check your internet connection and try again." -ForegroundColor Red
            exit 1
        }
    }

    $env:PYTHONIOENCODING = 'utf-8'

    $stArgs = @(
        '-m', 'streamlit', 'run', 'app/web/streamlit_app.py',
        '--server.port', $Port,
        '--server.address', 'localhost',
        '--browser.gatherUsageStats', 'false',
        '--server.headless', ($(if ($Headless) { 'true' } else { 'false' }))
    )

    Write-Host ""
    Write-Host "  Contract Redline is starting." -ForegroundColor Green
    Write-Host "  Open http://localhost:$Port in your browser."
    Write-Host "  Press Ctrl+C in this window to stop it."
    Write-Host ""

    & $python @stArgs
    $code = $LASTEXITCODE
}
finally {
    Pop-Location
}

# Double-clicked from Explorer, the window would close before you could read the
# error. Stop only on failure, so a normal Ctrl+C still exits immediately.
if ($code -ne 0 -and $Host.Name -eq 'ConsoleHost') {
    Write-Host ""
    Write-Host "The server stopped with an error (exit code $code)." -ForegroundColor Red
    Write-Host "Press Enter to close this window."
    [void](Read-Host)
}

exit $code
