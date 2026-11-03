"""Ensure the PowerShell helpers are UTF-8 with a BOM.

Windows PowerShell 5.1 decodes a .ps1 as ANSI/CP936 unless it starts with a BOM,
so any non-ASCII byte (a Chinese message, a path) turns into mojibake at runtime.
Idempotent: run it after editing any of these files.
"""

import sys
from pathlib import Path

BOM = b"\xef\xbb\xbf"
targets = sys.argv[1:] or [
    "tools/git_guard.ps1",
    "tools/test_git_guard.ps1",
    "tools/git_first_commit.ps1",
]

for name in targets:
    p = Path(name)
    raw = p.read_bytes()
    if not raw.startswith(BOM):
        p.write_bytes(BOM + raw)
        print(f"{name}: BOM added")
    else:
        print(f"{name}: already has BOM")
