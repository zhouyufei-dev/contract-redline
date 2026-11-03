"""One raw call to Stripe, with the key redacted from everything printed.

The 401 tells us the key was not accepted; it does not tell us why. Stripe's own
error body does, and the difference decides what the user has to fix:

  "Invalid API Key provided"        -> the string is wrong: truncated, from
                                       another account, or not a secret key.
  "You did not provide an API key"  -> the header never arrived.
  something from a proxy            -> not Stripe at all.

Every occurrence of a key-shaped token is replaced before printing.
"""

from __future__ import annotations

import base64
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402

KEY_SHAPE = re.compile(r"(?:sk|pk|rk)_(?:test|live)_[A-Za-z0-9]+")

key = get_settings().stripe_secret_key
if not key:
    print("no key configured")
    sys.exit(1)


def scrub(text: str) -> str:
    return KEY_SHAPE.sub("[REDACTED]", text)


request = urllib.request.Request(
    "https://api.stripe.com/v1/balance",
    method="GET",
    headers={
        "Authorization": "Basic "
        + base64.b64encode(f"{key}:".encode("utf-8")).decode("ascii"),
        "Stripe-Version": "2024-06-20",
        "Accept": "application/json",
    },
)

print("key length  :", len(key))
print("segments    :", len(key.split("_")), "->", [len(p) for p in key.split("_")])
print("charset ok  :", bool(re.fullmatch(r"[A-Za-z0-9_]+", key)))
print("looks live  :", "51" == key.split("_")[2][:2] if len(key.split("_")) > 2 else "?")
print()

try:
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
        print("HTTP 200 - key accepted")
        print("livemode:", payload.get("livemode"))
        sys.exit(0)
except urllib.error.HTTPError as exc:
    body = exc.read().decode("utf-8", "replace")
    print("HTTP", exc.code)
    try:
        error = json.loads(body).get("error", {})
        for field in ("type", "code", "param", "message"):
            if error.get(field):
                print(f"{field:8}:", scrub(str(error[field])))
    except ValueError:
        print("body:", scrub(body[:400]))
    sys.exit(1)
except Exception as exc:  # noqa: BLE001
    print("no HTTP response:", scrub(f"{type(exc).__name__}: {exc}"))
    sys.exit(2)
