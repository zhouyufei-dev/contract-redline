<#
.SYNOPSIS
    Create the first Git commit, with a hard stop if a secret is about to be
    committed.

.DESCRIPTION
    Written for one specific risk: this repository is about to be pushed to a
    **public** GitHub repo, and it contains .env with a live Stripe-capable key
    and a DeepSeek key. .gitignore is supposed to prevent that. This script does
    not take .gitignore's word for it - it asks git what is actually staged and
    aborts before the commit exists, because a secret that reaches a public repo
    is compromised the moment it lands (deleting the commit afterwards does not
    help; the key is already in someone's clone and in GitHub's caches).

    Two independent gates:
      1. path rules   - .env, secrets.toml, .pem, .venv, ... (git_guard.ps1)
      2. content scan - an actual key pasted into a test fixture, a doc or a
                        screenshot transcript, where the filename says nothing

    Safe to run more than once: it only commits when there is something to
    commit, and it never rewrites history.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\git_first_commit.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\git_first_commit.ps1 -Message "Add refund policy" -Name "Your Name" -Email "you@example.com"
#>
param(
    [string]$Message = "Contract Redline MVP: rule engine, report, web UI, paywall",
    [string]$Name,
    [string]$Email
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "git_guard.ps1")

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Fail($text) {
    Write-Host ""
    Write-Host $text -ForegroundColor Red
    Write-Host ""
    exit 1
}

# --- 1. find git -----------------------------------------------------------
$git = (Get-Command git -ErrorAction SilentlyContinue).Source
if (-not $git -and (Test-Path "C:\Program Files\Git\cmd\git.exe")) {
    $git = "C:\Program Files\Git\cmd\git.exe"
}
if (-not $git) {
    Fail @"
Git is not installed yet.

Install it, then CLOSE THIS WINDOW and open a new PowerShell:

    winget install --id Git.Git -e --source winget

(or download the installer from https://git-scm.com/download/win and keep the
default options). Then run this script again.
"@
}
Write-Host "git: $(& $git --version)"

# --- 2. init (must happen before any --local config) ----------------------
if (-not (Test-Path ".git")) {
    & $git init -b main
    if ($LASTEXITCODE -ne 0) { Fail "git init failed." }
    Write-Host "created a new repository (branch: main)"
} else {
    Write-Host "repository exists - reusing it"
}

# --- 3. author identity ----------------------------------------------------
# git refuses to commit without one, and the failure arrives at the very end
# after all the checks have passed - so resolve it now.
$userName = (& $git config user.name) 2>$null
$userEmail = (& $git config user.email) 2>$null
if ($Name -and $Email) {
    & $git config --local user.name $Name
    & $git config --local user.email $Email
    $userName = & $git config --local user.name
    $userEmail = & $git config --local user.email
}
if (-not $userName -or -not $userEmail) {
    Fail @"
Git does not know who you are yet. Set your name and email once
(they appear in every commit - use the address you want public on GitHub):

    git config --global user.name  "Your Name"
    git config --global user.email "you@example.com"

Then run this script again. Or pass them in one go:

    powershell -ExecutionPolicy Bypass -File tools\git_first_commit.ps1 -Name "Your Name" -Email "you@example.com"
"@
}
Write-Host "author: $userName <$userEmail>"

# --- 4. prove the secrets are ignored before staging anything --------------
# check-ignore exits 0 when the path IS ignored. Asking git is stronger than
# reading .gitignore ourselves: it accounts for nested rules and negation.
$mustBeIgnored = @(".env", ".venv", ".streamlit/secrets.toml", "data/cache")
$leaky = @()
foreach ($path in $mustBeIgnored) {
    if (-not (Test-Path $path)) { continue }   # nothing there, nothing to leak
    & $git check-ignore -q $path
    if ($LASTEXITCODE -ne 0) { $leaky += $path }
}
if ($leaky.Count -gt 0) {
    Fail @"
STOP: these exist and are NOT ignored by Git:

$($leaky -join "`n")

Committing them would put them in a public repository. Fix .gitignore first,
then run this script again.
"@
}
Write-Host ".env, .venv, .streamlit/secrets.toml, data/cache are ignored  [ok]"

# The negation rules in .gitignore (!.env.example) are the fragile part: get
# them wrong and the template silently vanishes from the repo, which is how a
# new clone ends up not knowing which keys are required.
if (Test-Path ".env.example") {
    & $git check-ignore -q ".env.example"
    if ($LASTEXITCODE -eq 0) {
        Fail @"
STOP: .env.example is being ignored, but it must be committed.

It holds the key NAMES with placeholder values - it is the only documentation
of what has to be configured. Check the "!.env.example" line in .gitignore.
"@
    }
    Write-Host ".env.example is tracked (template stays in the repo)  [ok]"
}

# --- 5. stage --------------------------------------------------------------
& $git add -A
if ($LASTEXITCODE -ne 0) { Fail "git add failed." }

$staged = @(& $git diff --cached --name-only)
if ($staged.Count -eq 0) {
    Write-Host ""
    Write-Host "Nothing to commit - the working tree matches the last commit." -ForegroundColor Yellow
    exit 0
}

# --- 6. gate 1: refuse forbidden paths ------------------------------------
$bad = @(Get-ForbiddenStagedFile -Paths $staged)
if ($bad.Count -gt 0) {
    & $git reset -q
    Fail @"
STOP - these files were about to be committed and are not allowed:

$($bad -join "`n")

Nothing was committed and the staging area has been cleared.
Add them to .gitignore, then run this script again.
"@
}

# --- 7. gate 2: scan the staged content for key-shaped strings ------------
# Filenames cannot see a key pasted into a test fixture or a markdown note.
# -I skips binaries; --cached reads the index, i.e. exactly what is about to be
# committed (not the working tree).
$keyPatterns = @(
    @{ Name = "Stripe secret key";  Regex = 'sk_(test|live)_[0-9A-Za-z]{20,}' },
    @{ Name = "Stripe webhook";     Regex = 'whsec_[0-9A-Za-z]{20,}' },
    @{ Name = "DeepSeek/OpenAI key"; Regex = 'sk-[0-9A-Za-z]{24,}' },
    @{ Name = "AWS access key";     Regex = 'AKIA[0-9A-Z]{16}' }
)
$found = @()
foreach ($p in $keyPatterns) {
    $hits = @(& $git grep --cached -I -n -E -e $p.Regex)
    if ($LASTEXITCODE -eq 0 -and $hits.Count -gt 0) {
        $found += "[$($p.Name)]"
        $found += $hits
    }
    $global:LASTEXITCODE = 0
}
if ($found.Count -gt 0) {
    & $git reset -q
    Fail @"
STOP - a real-looking key is inside a staged file:

$($found -join "`n")

Nothing was committed; the staging area has been cleared.
Replace the value with a placeholder (sk-xxxx) before committing.
Remember: a key in a public repo is public forever, even if the commit is
deleted later.
"@
}
Write-Host "no key-shaped strings in the staged content  [ok]"

Write-Host ""
Write-Host "$($staged.Count) file(s) staged:" -ForegroundColor Cyan
$staged | ForEach-Object { "  $_" }

# --- 8. commit -------------------------------------------------------------
Write-Host ""
& $git commit -m $Message
if ($LASTEXITCODE -ne 0) { Fail "git commit failed (see the message above)." }

Write-Host ""
Write-Host "Done. Latest commit:" -ForegroundColor Green
& $git log --oneline -1
Write-Host ""
Write-Host "Next: create the empty repository on GitHub, then run the two commands"
Write-Host "it shows you (git remote add origin ... / git push -u origin main)."
Write-Host "Full walkthrough: docs\11 - deployment handbook (section 4)."
