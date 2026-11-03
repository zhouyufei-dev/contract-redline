"""Post-commit verification: what exactly is in the commit, and what is not.

Run after tools/git_first_commit.ps1, before pushing to a public remote.
"""

import subprocess
import sys
from pathlib import Path


def git(*args: str) -> str:
    r = subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8")
    return (r.stdout or "").strip()


failures = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label} {detail}")
        failures.append(label)


print("1. commit identity and message")
check("exactly one commit", len(git("log", "--oneline").splitlines()) == 1)
author = git("log", "-1", "--format=%an <%ae>")
check("author recorded", author == "Contract Redline <support@contractredline.io>", author)
print(f"       {git('log', '-1', '--format=%h %s')}")

print("2. secrets are absent from the tracked tree")
tracked = git("ls-files").splitlines()
for name in (".env", ".streamlit/secrets.toml"):
    check(f"{name} not tracked", name not in tracked)
check("no .venv files", not any(p.startswith(".venv/") for p in tracked))
check("no data/cache files", not any(p.startswith("data/cache/") for p in tracked))
check("no .pem/.pfx", not any(p.endswith((".pem", ".pfx")) for p in tracked))
check("working tree clean", git("status", "--porcelain") == "",
      git("status", "--porcelain")[:200])

print("3. the templates that SHOULD be there")
for name in (".env.example", ".streamlit/secrets.toml.example"):
    check(f"{name} tracked", name in tracked)

print("4. .env.example holds placeholders, not values")
text = Path(".env.example").read_text(encoding="utf-8")
for line in text.splitlines():
    s = line.strip()
    if not s or s.startswith("#") or "=" not in s:
        continue
    key, _, value = s.partition("=")
    value = value.strip().strip('"').strip("'")
    looks_real = (
        value.startswith("sk_test_51")
        or (value.startswith("sk-") and len(value) > 20 and "your" not in value.lower())
    )
    check(f"{key.strip()} is a placeholder", not looks_real, f"value len={len(value)}")

print("5. size sanity")
print(f"       {len(tracked)} tracked files")
big = [p for p in tracked if Path(p).exists() and Path(p).stat().st_size > 1_000_000]
check("no tracked file over 1 MB", not big, str(big))

print()
if failures:
    print(f"RESULT: {len(failures)} FAILED")
    sys.exit(1)
print("RESULT: commit verified")
