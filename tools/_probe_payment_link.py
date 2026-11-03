"""Pre-flight for the payment link: does mode, price and redirect agree?

The expensive mistake this prevents: paying with a real card on a live-mode link
while the site verifies with a test-mode key. Stripe would take the money, and
the test key would answer "no such checkout" - charged, and still locked.

Checks, read-only, in order:

  1. which mode is the key (sk_test_ / sk_live_)
  2. which mode is the link in app/site.py (test links contain "/test_")
  3. does the link exist in that mode's API at all
  4. is it a one-off $5, not a subscription
  5. does it redirect to our site, and does the URL carry {CHECKOUT_SESSION_ID}

Run:  .\\.venv\\Scripts\\python.exe tools\\_probe_payment_link.py
Exit 0 only when everything lines up.
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
from app.site import DEFAULT_PAYMENT_URL, SITE  # noqa: E402

settings = get_settings()
key = settings.stripe_secret_key
if not key:
    print("no key configured")
    sys.exit(1)

problems: list[str] = []


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


def money(amount: int | None, currency: str = "usd") -> str:
    if amount is None:
        return "unknown"
    whole, part = divmod(amount, 100)
    return f"${whole}.{part:02d} {currency.upper()}"


# 1. key mode -----------------------------------------------------------------
key_mode = "test" if key.startswith("sk_test_") else "live" if key.startswith("sk_live_") else "?"
print(f"1. key mode          : {key_mode}")

# 2. link mode ----------------------------------------------------------------
url = SITE.payment_url
link_mode = "test" if "/test_" in url else "live"
print(f"2. link in site.py   : {url}")
print(f"   link mode         : {link_mode}")
if url == DEFAULT_PAYMENT_URL:
    print("   (this is the default link in code, not an override from .env)")

if key_mode != link_mode:
    problems.append(
        f"mode mismatch: the key is {key_mode} but the link is {link_mode}. "
        f"Clicking it will either reject the 4242 test card (live link) or take "
        f"real money that cannot then be verified (live charge, test key)."
    )

# 3. does the link exist in that mode -----------------------------------------
listing = get("payment_links?limit=100&expand[]=data.line_items")
links = listing.get("data", [])
print(f"3. payment links visible to this key: {len(links)}")

match = next((link for link in links if link.get("url") == url), None)
if not links:
    problems.append(
        f"this {key_mode}-mode key sees no payment links at all, so the link in "
        f"site.py was not created in {key_mode} mode"
    )
elif match is None:
    problems.append(f"the link in site.py is not among the {key_mode}-mode links")
    for link in links:
        print(f"   visible: {link.get('url')}")
else:
    print(f"   found: {match.get('id')}  active={match.get('active')}")

# 4 & 5. price, cadence, redirect ---------------------------------------------
target = match or (links[0] if len(links) == 1 else None)
if target:
    subscription = bool(target.get("subscription_data"))
    items = (target.get("line_items") or {}).get("data") or []
    price = (items[0].get("price") or {}) if items else {}
    amount = price.get("unit_amount")
    currency = price.get("currency", "usd")

    print(f"4. amount             : {money(amount, currency)}")
    print(f"   cadence            : {'SUBSCRIPTION' if subscription else 'one-off'}")
    if subscription:
        problems.append("the link is a subscription; the product sells one report")
    if amount != 500:
        problems.append(f"the link charges {money(amount, currency)}, site.py says {SITE.price}")

    completion = target.get("after_completion") or {}
    kind = completion.get("type")
    redirect = (completion.get("redirect") or {}).get("url", "")
    print(f"5. on success         : {kind}")
    if kind != "redirect":
        problems.append(
            "after payment Stripe shows its own confirmation page, so the browser "
            "never returns to the site and the report cannot unlock"
        )
    else:
        print(f"   redirect           : {redirect}")
        if "{CHECKOUT_SESSION_ID}" not in redirect:
            problems.append(
                "the redirect has no {CHECKOUT_SESSION_ID}, so the site has no "
                "proof of payment to verify"
            )
        if "localhost:8501" not in redirect and "127.0.0.1:8501" not in redirect:
            print("   note               : not localhost:8501 - fine for production")

print()
if problems:
    print("NOT READY")
    for problem in problems:
        print("  -", problem)
    sys.exit(1)

print("READY: key, link, price and redirect all agree")
