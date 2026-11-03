"""Check .env shape WITHOUT printing any secret value.

Prints only: key name, value length, and the first 3 characters masked.
"""
from __future__ import annotations

import pathlib

p = pathlib.Path(".env")
if not p.exists():
    raise SystemExit(".env not found")

for raw in p.read_text(encoding="utf-8-sig").splitlines():
    line = raw.strip()
    if not line or line.startswith("#"):
        continue
    if "=" not in line:
        print(f"[odd line, no '='] len={len(line)}")
        continue
    k, v = line.split("=", 1)
    v = v.strip().strip('"').strip("'")
    print(f"{k.strip():24s} value_len={len(v):3d} starts_with={v[:3]!r}***")
