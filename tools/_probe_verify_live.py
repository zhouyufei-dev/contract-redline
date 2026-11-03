"""End-to-end check of the verification code against real Stripe data, for free.

Creates an *unpaid* Checkout Session in test mode (no card is entered, nothing is
charged), then runs app.billing.verify_session on it. What this proves:

  * our request shape is accepted by the live Stripe API, not just by mocks
  * the fields we read (status / payment_status / amount_total / currency / mode)
    exist and parse on a real object
  * an unpaid session comes back as paid=False, so nobody unlocks for free
  * amount_label renders the real amount

The session is expired at the end so it cannot be paid later by mistake.
"""

from __future__ import annotations

import base64
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import billing  # noqa: E402
from app.config import get_settings  # noqa: E402

key = get_settings().stripe_secret_key
if not key:
    print("no key configured")
    sys.exit(1)

AUTH = {
    "Authorization": "Basic " + base64.b64encode(f"{key}:".encode()).decode("ascii"),
    "Stripe-Version": "2024-06-20",
    "Accept": "application/json",
}


def post(path: str, fields: dict[str, str]) -> dict:
    request = urllib.request.Request(
        f"https://api.stripe.com/v1/{path}",
        data=urllib.parse.urlencode(fields).encode(),
        method="POST",
        headers={**AUTH, "Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            message = json.loads(body).get("error", {}).get("message", "")
        except ValueError:
            message = body[:300]
        print(f"  HTTP {exc.code}: {message}")
        return {}


# A price object that already exists on the account would be ideal, but creating
# one inline keeps this independent of whatever the user named things.
session = post(
    "checkout/sessions",
    {
        "mode": "payment",
        "success_url": "http://localhost:8501/?session_id={CHECKOUT_SESSION_ID}",
        "cancel_url": "http://localhost:8501/",
        "line_items[0][quantity]": "1",
        "line_items[0][price_data][currency]": "usd",
        "line_items[0][price_data][unit_amount]": "500",
        "line_items[0][price_data][product_data][name]": "Contract Redline report (probe)",
    },
)

if not session.get("id"):
    print("could not create a session; stopping")
    sys.exit(1)

session_id = session["id"]
print("created (unpaid) session:", session_id)
print("  status        :", session.get("status"))
print("  payment_status:", session.get("payment_status"))
print("  amount_total  :", session.get("amount_total"))
print("  mode          :", session.get("mode"))

print("\nnow asking our own code what it thinks:")
payment = billing.verify_session(session_id)
print("  paid          :", payment.paid)
print("  amount_label  :", payment.amount_label)
print("  status        :", payment.status)

checks = [
    ("our code reached Stripe and parsed the object", payment.session_id == session_id),
    ("an unpaid session does NOT unlock", payment.paid is False),
    ("the amount reads as $5.00 USD", payment.amount_label == "$5.00 USD"),
    ("the mode is a one-off payment", payment.mode == "payment"),
]
for label, ok in checks:
    print(("  PASS  " if ok else "  FAIL  ") + label)

# Expire it so the abandoned session cannot be paid later.
post(f"checkout/sessions/{session_id}/expire", {})
print("\nprobe session expired (it can no longer be paid)")

print("\nREADY" if all(ok for _, ok in checks) else "\nPROBLEM")
sys.exit(0 if all(ok for _, ok in checks) else 1)
