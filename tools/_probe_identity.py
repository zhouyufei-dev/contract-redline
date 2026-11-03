"""Read the business identity Stripe already has on file, read-only.

Terms of Service, Privacy and Refund all print the operator's name, entity type
and address. Guessing those is worse than leaving them blank: a made-up address
in a legal document is a false statement, and Stripe's reviewer compares the site
against the account anyway.

If the account has this information, it is the truthful answer and it is what the
reviewer will check against. Prints no key. Nothing is written.
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
request = urllib.request.Request(
    "https://api.stripe.com/v1/account",
    headers={
        "Authorization": "Basic " + base64.b64encode(f"{key}:".encode()).decode("ascii"),
        "Stripe-Version": "2024-06-20",
    },
)
try:
    with urllib.request.urlopen(request, timeout=20) as response:
        account = json.loads(response.read().decode("utf-8"))
except urllib.error.HTTPError as exc:
    print("HTTP", exc.code, exc.read().decode("utf-8", "replace")[:200])
    sys.exit(1)

print("business_type      :", account.get("business_type"))
print("country            :", account.get("country"))
print("email              :", account.get("email"))

profile = account.get("business_profile") or {}
for field in ("name", "url", "support_email", "support_phone", "support_address", "product_description"):
    value = profile.get(field)
    if isinstance(value, dict):
        value = {k: v for k, v in value.items() if v}
    print(f"{field:19}:", value)

for block in ("individual", "company"):
    data = account.get(block) or {}
    if not data:
        continue
    print(f"\n[{block}]")
    for field in ("first_name", "last_name", "business_name", "address", "email", "phone"):
        value = data.get(field)
        if isinstance(value, dict):
            value = {k: v for k, v in value.items() if v}
        if value:
            print(f"  {field:13}:", value)

requirements = account.get("requirements") or {}
print("\nrequirements.disabled_reason:", requirements.get("disabled_reason"))
print("currently_due        :", requirements.get("currently_due"))
print("eventually_due       :", requirements.get("eventually_due"))
