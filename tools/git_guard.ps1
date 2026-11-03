<#
.SYNOPSIS
    Decides whether a staged file is allowed to be committed.

.DESCRIPTION
    Dot-sourced by tools\git_first_commit.ps1 and exercised by
    tools\test_git_guard.ps1. Kept in its own file so the rule can be tested
    without a git binary and without touching a real repository.

    Rules are patterns rather than an exact list on purpose: the realistic leak
    is not ".env", it is ".env.bak", "secrets.toml" downloaded from the Streamlit
    dashboard, or a "prod.env" someone made at 1am.

    Deliberately allowed: .env.example and *.toml.example. They hold placeholders
    only, and they are the documentation of what the secrets are called - blocking
    them would make the repo harder to set up for no security gain.
#>

$script:ForbiddenPatterns = @(
    '(^|/)\.env$',
    '(^|/)\.env\.[^.]+$',          # .env.bak, .env.prod, .env.local
    '(^|/)\.env\.[^.]+\.',         # .env.prod.backup
    '(^|/)secrets\.toml$',
    '(^|/)\.venv/',
    '(^|/)data/cache/',
    '\.pem$',
    '\.pfx$',
    '(^|/)id_rsa',
    '(^|/)id_ed25519'
)

# Explicit allow-list, applied first. Anything matching here is never forbidden,
# even if a pattern above would match it.
$script:AlwaysAllowed = @(
    '(^|/)\.env\.example$',
    '(^|/)\.env\.sample$',
    '\.toml\.example$'
)

function Get-ForbiddenStagedFile {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [string[]]$Paths
    )

    $bad = @()
    foreach ($file in $Paths) {
        # git reports forward slashes even on Windows; normalise in case a
        # caller passes native separators.
        $normalised = $file -replace '\\', '/'

        $allowed = $false
        foreach ($pattern in $script:AlwaysAllowed) {
            if ($normalised -match $pattern) { $allowed = $true; break }
        }
        if ($allowed) { continue }

        foreach ($pattern in $script:ForbiddenPatterns) {
            if ($normalised -match $pattern) { $bad += $file; break }
        }
    }
    return $bad
}
