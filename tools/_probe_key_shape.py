"""Show the *shape* of the key in .env, never the key itself.

Keeps the first 14 and last 4 characters and replaces the middle, so the paste
can be compared with what the Stripe dashboard shows without the secret ending up
in a chat log or a screenshot.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402

key = get_settings().stripe_secret_key
print("masked       :", key[:14] + "*" * 24 + key[-4:])
print("total length :", len(key), "(a test secret key is normally 107)")

parts = key.split("_")
print("underscores  :", key.count("_"), "-> group lengths", [len(p) for p in parts])
print("body after prefix:", "clean, no underscores" if len(parts) == 3 else "EXTRA UNDERSCORES")

env_line = [
    line for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines()
    if line.strip().startswith("STRIPE_SECRET_KEY")
]
print("env lines    :", len(env_line))
for line in env_line:
    head, _, value = line.partition("=")
    value = value.strip()
    print(f"  {head.strip()} = {value[:14]}{'*' * 12}{value[-4:]}  (len {len(value)})")
    if value != value.strip('"').strip("'"):
        print("  ^ value is wrapped in quotes - our parser keeps them literally")
    if re.search(r"\s", value):
        print("  ^ contains whitespace")
