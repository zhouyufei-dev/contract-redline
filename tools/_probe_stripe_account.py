"""Which Stripe account does this key belong to, and in which mode?

Payment Links are mode-specific: a test-mode key can only see test-mode links.
If the $5 link was made in live mode (in the dashboard's normal view rather than
with the "Test mode" switch on), this key will never see it - and a live link
will refuse the 4242 test card.

Read-only. Prints no key.
"""

from __future__ import annotations

import base64
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402

key = get_settings().stripe_secret_key


def get(path: str) -> dict:
    request = urllib.request.Request(
        f"https://api.stripe.com/v1/{path}",
        method="GET",
        headers={
            "Authorization": "Basic "
            + base64.b64encode(f"{key}:".encode("utf-8")).decode("ascii"),
            "Stripe-Version": "2024-06-20",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            message = json.loads(body).get("error", {}).get("message", "")
        except ValueError:
            message = body[:300]
        print(f"  HTTP {exc.code}: {message}")
        return {}


print("account")
account = get("account")
for field in ("id", "business_profile", "country", "default_currency", "charges_enabled", "payouts_enabled"):
    if field in account:
        value = account[field]
        if isinstance(value, dict):
            value = {k: v for k, v in value.items() if v}
        print(f"  {field:18}: {value}")

print("\nbalance (livemode of the key shows here)")
balance = get("balance")
print("  livemode          :", balance.get("livemode"))

for path, label in (
    ("payment_links?limit=100", "payment links, test mode"),
    ("products?limit=100", "products, test mode"),
    ("prices?limit=100", "prices, test mode"),
    ("checkout/sessions?limit=5", "recent checkout sessions, test mode"),
):
    data = get(path)
    items = data.get("data", [])
    print(f"\n{label}: {len(items)}")
    for item in items[:5]:
        bits = []
        if item.get("url"):
            bits.append(item["url"])
        if item.get("id"):
            bits.append(item["id"])
        if item.get("amount") is not None:
            bits.append(f"amount={item['amount']}")
        if item.get("unit_amount") is not None:
            bits.append(f"unit={item['unit_amount']}")
        if item.get("payment_status"):
            bits.append(item["payment_status"])
        print("  " + "  ".join(str(b) for b in bits))
