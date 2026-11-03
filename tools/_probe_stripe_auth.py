"""Control test: is the 401 about the key, or about how we send it?

Stripe accepts the secret key either as HTTP Basic (username = key, empty
password) or as a Bearer token. If Basic fails and Bearer succeeds, the bug is
ours; if both fail, Stripe is rejecting the string in .env. Also tests a key with
one character removed, to be sure 401 means "this exact string", not "any string".

Prints status codes and Stripe's error text with the key redacted.
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

KEY_SHAPE = re.compile(r"(?:sk|pk|rk)_(?:test|live)_\**[A-Za-z0-9]*")
key = get_settings().stripe_secret_key
if not key:
    print("no key configured")
    sys.exit(1)


def call(headers: dict[str, str], label: str) -> int:
    request = urllib.request.Request(
        "https://api.stripe.com/v1/balance", method="GET", headers=headers
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
            print(f"{label:16} HTTP 200  livemode={payload.get('livemode')}")
            return 200
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            message = json.loads(body).get("error", {}).get("message", "")
        except ValueError:
            message = body[:200]
        print(f"{label:16} HTTP {exc.code}  {KEY_SHAPE.sub('[REDACTED]', message)[:160]}")
        return exc.code
    except Exception as exc:  # noqa: BLE001
        print(f"{label:16} no response: {type(exc).__name__}")
        return 0


basic = {
    "Authorization": "Basic "
    + base64.b64encode(f"{key}:".encode("utf-8")).decode("ascii"),
    "Stripe-Version": "2024-06-20",
}
bearer = {"Authorization": f"Bearer {key}", "Stripe-Version": "2024-06-20"}

a = call(basic, "Basic (ours)")
b = call(bearer, "Bearer (control)")
c = call(
    {
        "Authorization": "Basic "
        + base64.b64encode(f"{key[:-1]}:".encode("utf-8")).decode("ascii"),
        "Stripe-Version": "2024-06-20",
    },
    "mangled-key ctrl",
)

print()
if a == 200:
    print("VERDICT: our header is fine and the key works - nothing to do")
elif b == 200:
    print("VERDICT: ours is broken, Bearer works - a bug in billing._fetch")
elif a == 401 and c == 401:
    print("VERDICT: Stripe rejects this exact string, and rejects a mangled one")
    print("         the same way -> the key in .env is not a valid Stripe key")
    print("         the header we send is standard; the value is the problem")
else:
    print("VERDICT: inconclusive, see the codes above")
