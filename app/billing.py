"""Proof of payment, and the only thing allowed to unlock a full report.

Why this module exists
----------------------
A success URL that says ``?paid=true`` is not evidence of anything: it is a
string anyone can type into the address bar. The only trustworthy claim that
money changed hands is the Checkout Session id Stripe itself appends to the
success URL, checked back against the Stripe API with our own secret key.

    success URL:  http://localhost:8501/?session_id={CHECKOUT_SESSION_ID}
    this module:  GET https://api.stripe.com/v1/checkout/sessions/<id>
                  -> payment_status == "paid"

No SDK, on purpose
------------------
This is one GET request. ``urllib`` ships with Python and cannot break a fresh
install; the ``stripe`` package would add a dependency, a release cadence and a
second way to configure a key. The project rule is that a dependency has to earn
its place (see app/config.py for the same argument about python-dotenv).

What never leaves this module
-----------------------------
The secret key. It goes into an Authorization header and nowhere else: not into
an exception message, not into a log line, not into the UI. Every error raised
here is written for a customer to read.
"""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from app.config import Settings, get_settings

API_ROOT = "https://api.stripe.com/v1/checkout/sessions"
TIMEOUT_SECONDS = 15.0

# A session is only "paid" for our purposes above this. Guards against a $0 or
# test session being replayed at us, and still tolerates a future discount code.
MIN_PAID_CENTS = 100

# Checkout Sessions are immutable once complete, so caching a verdict is safe.
# Small and time-bounded: Streamlit re-runs the script on every click, and we do
# not want a network round-trip (or a Stripe rate limit) on each one.
_CACHE: dict[str, tuple[float, "Payment"]] = {}
_CACHE_TTL = 30 * 60
_CACHE_MAX = 128


class PaymentError(RuntimeError):
    """A payment could not be verified. The message is safe to show a user."""


@dataclass(frozen=True)
class Payment:
    """The verified facts about one Checkout Session."""

    session_id: str
    paid: bool
    amount_total: int
    currency: str
    mode: str
    status: str

    @property
    def amount_label(self) -> str:
        """``$5.00`` - built from integers, never from a float."""
        whole, cents = divmod(max(self.amount_total, 0), 100)
        symbol = "$" if self.currency.lower() == "usd" else ""
        return f"{symbol}{whole}.{cents:02d} {self.currency.upper()}".strip()


def looks_like_session_id(value: str | None) -> bool:
    """Cheap shape check before we spend a network call on it.

    Stripe ids are ``cs_test_...`` / ``cs_live_...``; anything else in the query
    string is not a session and must not be forwarded to the API.
    """
    text = (value or "").strip()
    return text.startswith("cs_") and 20 <= len(text) <= 200 and " " not in text


def configured(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return bool(settings.stripe_secret_key)


def _cache_get(session_id: str) -> Payment | None:
    hit = _CACHE.get(session_id)
    if not hit:
        return None
    stamp, payment = hit
    if time.time() - stamp > _CACHE_TTL:
        _CACHE.pop(session_id, None)
        return None
    return payment


def _cache_put(session_id: str, payment: Payment) -> None:
    if len(_CACHE) >= _CACHE_MAX:
        oldest = min(_CACHE, key=lambda k: _CACHE[k][0])
        _CACHE.pop(oldest, None)
    _CACHE[session_id] = (time.time(), payment)


def forget(session_id: str) -> None:
    """Drop one cached verdict. Used by tests; harmless in production."""
    _CACHE.pop(session_id, None)


def _fetch(session_id: str, secret_key: str) -> dict:
    """One GET against the Stripe API. Returns the decoded session object."""
    request = urllib.request.Request(
        f"{API_ROOT}/{session_id}",
        method="GET",
        headers={
            # Stripe uses HTTP Basic with the secret key as the username and an
            # empty password. Never put this in a URL - URLs end up in logs.
            "Authorization": "Basic "
            + base64.b64encode(f"{secret_key}:".encode("utf-8")).decode("ascii"),
            "Stripe-Version": "2024-06-20",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            payload = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        # 404 = made up / from another Stripe account. 401 = our key is wrong.
        if exc.code == 404:
            raise PaymentError(
                "Stripe has no record of that checkout. If you were charged, "
                "email us with your receipt and we will unlock the report by hand."
            ) from None
        if exc.code in (401, 403):
            raise PaymentError(
                "Payments are not being verified right now: the Stripe key was "
                "rejected. This is our problem, not yours - please email support."
            ) from None
        raise PaymentError(
            "Stripe did not answer properly just now (HTTP "
            f"{exc.code}). Wait a moment and reload the page."
        ) from None
    except urllib.error.URLError as exc:
        raise PaymentError(
            "Could not reach Stripe to confirm the payment. Check your connection "
            "and reload the page - you will not be charged twice."
        ) from exc
    except TimeoutError:
        raise PaymentError(
            "Stripe took too long to answer. Reload the page and we will check "
            "the same payment again."
        ) from None

    try:
        return json.loads(payload)
    except ValueError:
        raise PaymentError(
            "Stripe sent something we could not read. Reload the page; if it "
            "keeps happening, email support."
        ) from None


def verify_session(session_id: str, settings: Settings | None = None) -> Payment:
    """Ask Stripe whether this Checkout Session was paid.

    Raises PaymentError only for things the customer can act on (bad id, key
    not configured, network). A session that exists but was *not* paid is a
    normal answer: return Payment(paid=False).
    """
    session_id = (session_id or "").strip()
    if not looks_like_session_id(session_id):
        raise PaymentError(
            "That link is missing a valid Stripe checkout reference. "
            "Open the confirmation link from your Stripe receipt."
        )

    cached = _cache_get(session_id)
    if cached is not None:
        return cached

    settings = settings or get_settings()
    if not settings.stripe_secret_key:
        # Deliberately explicit: silently unlocking here would hand out free
        # reports, and silently locking would look like we kept the money.
        raise PaymentError(
            "Payments cannot be verified on this copy of the site yet: "
            "STRIPE_SECRET_KEY is not set in .env. Nothing has been charged twice."
        )

    data = _fetch(session_id, settings.stripe_secret_key)

    status = str(data.get("status") or "")
    payment_status = str(data.get("payment_status") or "")
    amount_total = data.get("amount_total")
    amount_total = int(amount_total) if isinstance(amount_total, int) else 0

    paid = (
        status == "complete"
        and payment_status in ("paid", "no_payment_required")
        # The amount check is unconditional, including when Stripe says no
        # payment was required: that status also covers a 100%-off coupon, and a
        # free session must not open a $5 report. A genuine comp gets unlocked by
        # hand from the receipt.
        and amount_total >= MIN_PAID_CENTS
    )

    payment = Payment(
        session_id=session_id,
        paid=paid,
        amount_total=amount_total,
        currency=str(data.get("currency") or "usd"),
        mode=str(data.get("mode") or ""),
        status=payment_status or status,
    )
    _cache_put(session_id, payment)
    return payment
