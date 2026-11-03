"""Diagnose the Stripe key without ever printing it.

Three outcomes, and the difference matters:

  * 404 "no record"  -> the key is valid (Stripe authenticated us), the session
                        id simply does not exist. This is the pass case.
  * 401 "rejected"   -> the key is wrong: a publishable key, a live key with a
                        test URL (or the reverse), or a truncated paste.
  * not configured   -> .env was not picked up: wrong name, wrong file, or the
                        server was started before the line was added.

Prints lengths and prefixes only. Run:
    .\\.venv\\Scripts\\python.exe tools\\_probe_stripe_key.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import billing  # noqa: E402
from app.config import get_settings  # noqa: E402

settings = get_settings()
key = settings.stripe_secret_key

print("stripe_key configured:", bool(key))
if not key:
    print("VERDICT: missing -> add STRIPE_SECRET_KEY=sk_test_... to .env and restart")
    sys.exit(1)

kind = (
    "publishable (pk_) - WRONG, this cannot read a session"
    if key.startswith("pk_")
    else "live (sk_live_)"
    if key.startswith("sk_live_")
    else "test (sk_test_)"
    if key.startswith("sk_test_")
    else "unrecognised prefix"
)
print("prefix       :", key.split("_")[0] + "_" + (key.split("_")[1] if "_" in key else ""))
print("kind         :", kind)
print("length       :", len(key), "chars")
print("whitespace   :", "none" if key == key.strip() else "present - strip it, a trailing space breaks the header")

if not key.startswith("sk_"):
    print("VERDICT: not a secret key")
    sys.exit(1)

# A session id that cannot exist. Stripe still has to authenticate the request
# before it can say 404, which is exactly what we want to learn.
try:
    billing.verify_session("cs_test_" + "0" * 32)
    print("VERDICT: unexpected - a non-existent session verified as paid")
    sys.exit(1)
except billing.PaymentError as exc:
    message = str(exc)
    if "no record" in message:
        print("VERDICT: key accepted by Stripe (404 on a fake id, as expected)")
        sys.exit(0)
    if "rejected" in message:
        print("VERDICT: Stripe rejected the key (401/403) - check test vs live")
        sys.exit(1)
    print("VERDICT: could not reach Stripe:", message)
    sys.exit(2)
