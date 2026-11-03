"""Show the shape of STRIPE_PAYMENT_URL in .env, not its exact value.

A pasted-twice link is the failure mode to catch: two URLs glued together still
*starts* with https://, so a naive check passes it and the button goes nowhere.
This prints the length, how many "https://" occurrences there are, and how many
Stripe paths are present.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.site import DEFAULT_PAYMENT_URL, SITE  # noqa: E402

raw_lines = [
    line for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines()
    if line.strip().startswith("STRIPE_PAYMENT_URL")
]
print("STRIPE_PAYMENT_URL lines in .env:", len(raw_lines))

value = get_settings().payment_url
print("value length        :", len(value))
print("https:// occurrences:", value.count("https://"))
print("buy.stripe.com count:", value.count("buy.stripe.com"))
print("whitespace inside   :", bool(re.search(r"\s", value)))
print("quotes              :", value[:1] + "..." + value[-1:] if value[:1] in "\"'" else "none")
print("contains /test_     :", "/test_" in value)
print("masked              :", (value[:38] + "*" * 6 + value[-6:]) if len(value) > 48 else value)
print()
print("resolved (what the button uses):")
print("  ", SITE.payment_url)
print("  is the code default:", SITE.payment_url == DEFAULT_PAYMENT_URL)

ok = (
    len(raw_lines) == 1
    and value.startswith("https://buy.stripe.com/")
    and value.count("https://") == 1
    and value.count("buy.stripe.com") == 1
    and not re.search(r"\s", value)
)
print()
print("SHAPE OK" if ok else "SHAPE SUSPECT - fix .env before testing")
sys.exit(0 if ok else 1)
