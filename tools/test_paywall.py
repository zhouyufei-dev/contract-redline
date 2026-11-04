r"""Tests for the $5 gate.

Run:  .\.venv\Scripts\python.exe tools\test_paywall.py

No network, no API key, no browser. Four groups:

  A. The teaser really is a teaser - one card, and *nothing* about the other 19
     appears anywhere in the bytes we send. This is the check that matters: a
     paywall you can read with View Source is not a paywall.
  B. Stripe verification - what counts as paid, what does not, and that the
     secret key never appears in anything a customer can see.
  C. The gate - one payment buys one report, and the id stops working after it
     has been spent.
  D. Copy and price are the same in the report, the page and site.py.

Exit code is non-zero if anything fails.
"""

from __future__ import annotations

import re
import sys
from dataclasses import replace
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import billing  # noqa: E402
from app.config import Settings  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.engine.scoring import summarise  # noqa: E402
from app.pipeline import build_report, scan_contract  # noqa: E402
from app.report import renderer  # noqa: E402
from app.report.html_report import render  # noqa: E402
from app.site import SITE  # noqa: E402
from app.site import DEFAULT_PAYMENT_URL, resolve_payment_url  # noqa: E402
from app.web import paywall as gate  # noqa: E402

SAMPLE = ROOT / "data" / "samples" / "fake_contract_01.docx"
CJK = re.compile(r"[\u4e00-\u9fff]")

passed = failed = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL  {label}" + (f"  [{detail}]" if detail else ""))


# --------------------------------------------------------------------------
# Fixtures: one real report, built without the LLM so the suite stays offline.
# --------------------------------------------------------------------------

REPORT = build_report(scan_contract(SAMPLE), [])
TEASER_REPORT = renderer.preview(REPORT)
FULL_HTML = render(REPORT)
TEASER_HTML = render(TEASER_REPORT, preview=True)

LOCKED = REPORT.cards[1:]


print("A. the teaser is a real teaser")

check("the sample produces a full report", len(REPORT.cards) >= 10, str(len(REPORT.cards)))
check("the free card is the worst one", TEASER_REPORT.cards[0].number == REPORT.cards[0].number)
check("the free card is a deal-breaker", REPORT.cards[0].band == "critical", REPORT.cards[0].band)
check("preview keeps exactly one card", len(TEASER_REPORT.cards) == 1, str(len(TEASER_REPORT.cards)))
check(
    "the summary still tells the truth about the whole contract",
    TEASER_REPORT.summary.cards == REPORT.summary.cards == len(REPORT.cards),
)
check(
    "the summary's own card list is untouched",
    TEASER_REPORT.summary.cards == REPORT.summary.cards,
)

check("the full report has no unlock block", '<section class="paywall"' not in FULL_HTML)
check("the teaser has the unlock block", '<section class="paywall"' in TEASER_HTML)
check(
    "the unlock link opens in a new tab",
    'target="_blank"' in TEASER_HTML and 'rel="noopener' in TEASER_HTML,
)
check("the unlock link points at the live Stripe link", SITE.payment_url in TEASER_HTML)
check("the teaser keeps the disclaimer", "not legal advice" in TEASER_HTML.lower())

rule_leaks = [card.rule_name for card in LOCKED if card.rule_name in TEASER_HTML]
check("no locked rule name appears in the teaser", not rule_leaks, str(rule_leaks))

quote_leaks = [
    quote.sentence
    for card in LOCKED
    for quote in card.quotes
    if quote.sentence and quote.sentence in TEASER_HTML
]
check("no locked sentence is quoted in the teaser", not quote_leaks, str(quote_leaks[:2]))

fix_leaks = [card.rule_id for card in LOCKED if len(card.fix) > 60 and card.fix in TEASER_HTML]
check("no locked suggested wording appears in the teaser", not fix_leaks, str(fix_leaks))

check(
    "the teaser is genuinely smaller than the report",
    len(TEASER_HTML) < len(FULL_HTML) * 0.7,
    f"{len(TEASER_HTML)} vs {len(FULL_HTML)}",
)
check(
    "the teaser counts the clauses still locked",
    f'{REPORT.summary.cards - 1}' in TEASER_HTML,
)

empty = replace(REPORT, cards=[], summary=summarise([]))
check(
    "a report with nothing locked shows no unlock block",
    '<section class="paywall"' not in render(empty, preview=True),
)
check(
    "preview of a full report is a no-op",
    renderer.preview(REPORT, limit=999) is REPORT,
)


print("B. Stripe verification")

check("a test session id is accepted", billing.looks_like_session_id("cs_test_" + "a" * 30))
check("a live session id is accepted", billing.looks_like_session_id("cs_live_" + "b" * 30))
check("a made-up id is rejected", not billing.looks_like_session_id("paid=true"))
check("an empty id is rejected", not billing.looks_like_session_id(""))
check("an id with spaces is rejected", not billing.looks_like_session_id("cs_test_a b"))

try:
    billing.verify_session("nonsense")
    check("a junk id raises PaymentError", False)
except billing.PaymentError as exc:
    check("a junk id raises PaymentError", True)
    check("the message is written for a customer", "receipt" in str(exc).lower())

NO_KEY = Settings(api_key="", stripe_secret_key="")
try:
    billing.verify_session("cs_test_" + "c" * 30, NO_KEY)
    check("a missing key refuses instead of guessing", False)
except billing.PaymentError as exc:
    check("a missing key refuses instead of guessing", True)
    check("the message names the setting", "STRIPE_SECRET_KEY" in str(exc))
    check("the message says nothing was charged twice", "twice" in str(exc))

KEY = Settings(api_key="", stripe_secret_key="sk_test_do_not_print_me")
#: The real network call, kept so the tests below can put it back after faking.
ORIGINAL_FETCH = billing._fetch


def _fake_fetch(payload):
    calls = {"n": 0}

    def fetch(session_id, secret_key):
        calls["n"] += 1
        return payload

    return fetch, calls


PAID_PAYLOAD = {
    "status": "complete",
    "payment_status": "paid",
    "amount_total": 500,
    "currency": "usd",
    "mode": "payment",
}
UNPAID_PAYLOAD = {"status": "open", "payment_status": "unpaid", "amount_total": 500, "currency": "usd"}
FREE_PAYLOAD = {"status": "complete", "payment_status": "paid", "amount_total": 0, "currency": "usd"}
COMP_PAYLOAD = {"status": "complete", "payment_status": "no_payment_required", "amount_total": 0}

fetch, calls = _fake_fetch(PAID_PAYLOAD)
billing._fetch = fetch
sid = "cs_test_" + "d" * 30
payment = billing.verify_session(sid, KEY)
check("a paid session unlocks", payment.paid)
check("the amount is reported as money", payment.amount_label == "$5.00 USD", payment.amount_label)
check("the verdict is cached, not re-fetched", calls["n"] == 1 and billing.verify_session(sid, KEY).paid)

fetch, calls = _fake_fetch(UNPAID_PAYLOAD)
billing._fetch = fetch
check("an abandoned session does not unlock", not billing.verify_session("cs_test_" + "e" * 30, KEY).paid)

fetch, calls = _fake_fetch(FREE_PAYLOAD)
billing._fetch = fetch
check("a $0 session does not unlock", not billing.verify_session("cs_test_" + "f" * 30, KEY).paid)

fetch, calls = _fake_fetch(COMP_PAYLOAD)
billing._fetch = fetch
check("a $0 comp code does not unlock", not billing.verify_session("cs_test_" + "i" * 30, KEY).paid)

with mock.patch("urllib.request.urlopen", side_effect=HTTPError("u", 401, "no", {}, None)):
    billing._fetch = ORIGINAL_FETCH
    try:
        billing.verify_session("cs_test_" + "g" * 30, KEY)
        check("a rejected key raises PaymentError", False)
    except billing.PaymentError as exc:
        check("a rejected key raises PaymentError", True)
        check("a 401 never prints the key", KEY.stripe_secret_key not in str(exc))
        check("a 401 never prints the key fragment", "sk_test_" not in str(exc))

with mock.patch("urllib.request.urlopen", side_effect=URLError("offline")):
    try:
        billing.verify_session("cs_test_" + "h" * 30, KEY)
        check("an offline Stripe raises PaymentError", False)
    except billing.PaymentError as exc:
        check("an offline Stripe raises PaymentError", True)
        check("the offline message promises no double charge", "charged twice" in str(exc).lower())


print("C. the gate: one payment, one report")


class FakeParams(dict):
    def clear(self):  # what st.query_params.clear() does to the URL
        dict.clear(self)


class FakeSt:
    def __init__(self):
        self.session_state = {}
        self.query_params = FakeParams()


REAL_ST = gate.st
fake = FakeSt()
gate.st = fake
try:
    check("nothing is unlocked to begin with", not gate.is_unlocked("abc"))
    check("an empty fingerprint never unlocks", not gate.is_unlocked(""))

    fake.session_state[gate.CREDIT_KEY] = payment
    check("a verified payment is held as credit", gate.credit() is payment)

    fake.query_params["session_id"] = "cs_test_" + "d" * 30
    check("the session id is read from the URL", gate.session_id_from_url().startswith("cs_test_"))
    fake.query_params.clear()
    check("no session id means no claim", gate.session_id_from_url() == "")

    gate.bind("abc")
    check("spending the credit unlocks that report", gate.is_unlocked("abc"))
    check("spending the credit empties it", gate.credit() is None)
    check("a different contract is not unlocked", not gate.is_unlocked("def"))
    check("the fingerprint is stable", gate.fingerprint(b"x") == gate.fingerprint(b"x"))
    check("different bytes give a different fingerprint", gate.fingerprint(b"x") != gate.fingerprint(b"y"))
finally:
    gate.st = REAL_ST


print("E. the payment reference survives a browser that drops it")


class FakeContext:
    """Just enough of `st.context` for the Referer lookup."""

    def __init__(self, headers):
        self.headers = dict(headers)


BUG_REPORT_ID = ("cs_live_a146vUO294RCnaf4wTM0SzN5OxtOeAydidhiB2ibzoZNOP4J"
                 "!X0a8s1")
BUG_REPORT_URL = "https://contractredline.io/?session_id=" + BUG_REPORT_ID

# The exact link from the bug report. `!` is legal inside a live session id and
# survives a copy-paste from the address bar, so it has to survive us too.
check("the live link from the bug report is readable",
      gate.parse_session_id(BUG_REPORT_URL) == BUG_REPORT_ID,
      gate.parse_session_id(BUG_REPORT_URL))
check("a bare id is accepted",
      gate.parse_session_id(BUG_REPORT_ID) == BUG_REPORT_ID)
ENCODED = "cs_live_" + "a" * 20 + "!X0a8s1"
check("an encoded ! is decoded",
      gate.parse_session_id("https://x/?session_id=" + ENCODED.replace("!", "%21"))
      == ENCODED)
check("extra parameters do not leak into the id",
      gate.parse_session_id("https://x/?session_id=cs_live_" + "c" * 40 + "&paid=true")
      == "cs_live_" + "c" * 40)
check("trailing punctuation is dropped",
      gate.parse_session_id("cs_live_" + "b" * 40 + ".") == "cs_live_" + "b" * 40)
check("quoting from an email is tolerated",
      gate.parse_session_id('"' + BUG_REPORT_ID + '"') == BUG_REPORT_ID)
check("prose is rejected", gate.parse_session_id("I paid yesterday") == "")
check("an empty box is rejected", gate.parse_session_id("   ") == "")
check("a non-Stripe id is rejected", gate.parse_session_id("https://x/?session_id=paid%3Dtrue") == "")

# The iframe case: the app's own URL has no parameters, the embedding page's URL
# is the only place the id exists, and it reaches the server as `Referer`.
fake = FakeSt()
gate.st = fake
try:
    fake.context = FakeContext({"referer": BUG_REPORT_URL})
    check("the embedding page's URL is read from Referer",
          gate.session_id_from_referer() == BUG_REPORT_ID,
          gate.session_id_from_referer())
    check("the app's own query string is empty in that case",
          gate.session_id_from_url() == "")

    fake.context = FakeContext({"host": "contractredline.io"})
    check("no Referer means no claim", gate.session_id_from_referer() == "")

    fake.context = FakeContext({"referer": "https://google.com/"})
    check("an unrelated Referer is not a payment", gate.session_id_from_referer() == "")

    # A missing `st.context` (older Streamlit, bare mode) must not raise.
    del fake.context
    check("a missing st.context is not an error", gate.session_id_from_referer() == "")

    # One payment, one report - including when the receipt is pasted twice.
    fake.session_state[gate.CREDIT_KEY] = payment
    check("the first contract unlocks", gate.spend_credit("contract-one"))
    check("the payment is recorded as spent", gate.already_spent(payment.session_id))

    fake.session_state[gate.CREDIT_KEY] = payment
    check("the same receipt does not unlock a second contract",
          not gate.spend_credit("contract-two"))
    check("and the stale credit is dropped", gate.credit() is None)
    check("the first contract is still unlocked", gate.is_unlocked("contract-one"))
    check("the second one is not", not gate.is_unlocked("contract-two"))
finally:
    gate.st = REAL_ST


print("D. one price, everywhere")

check("site.py holds the price", SITE.price == "$5", SITE.price)
check("the payment link is https", SITE.payment_url.startswith("https://"))
check("the payment link is a Stripe link", "buy.stripe.com" in SITE.payment_url)
check(
    "a test-mode link can be set from .env",
    resolve_payment_url("https://buy.stripe.com/test_abc123")
    == "https://buy.stripe.com/test_abc123",
)
check(
    "an empty override falls back to the live link",
    resolve_payment_url("") == DEFAULT_PAYMENT_URL,
)
check(
    "a javascript: payload cannot reach the href",
    resolve_payment_url("javascript:alert(1)") == DEFAULT_PAYMENT_URL,
)
check(
    "a plain http link is refused",
    resolve_payment_url("http://buy.stripe.com/x") == DEFAULT_PAYMENT_URL,
)
check(
    "the resolved link is what the page and report use",
    SITE.payment_url == resolve_payment_url(get_settings().payment_url),
)
check("the report quotes the site price", SITE.price in TEASER_HTML)
check("the pricing page quotes the site price", SITE.price in __import__("app.web.pages", fromlist=["x"]).pricing_text())

source = (ROOT / "app" / "web" / "paywall.py").read_text(encoding="utf-8")
report_source = (ROOT / "app" / "report" / "html_report.py").read_text(encoding="utf-8")
check("the page button reads the link from site.py", "SITE.payment_url" in source)
check("the report button reads the link from site.py", "SITE.payment_url" in report_source)
check(
    "no hardcoded Stripe URL in the report template",
    "buy.stripe.com" not in report_source,
)
check("no CJK leaks into the English teaser", not CJK.search(TEASER_HTML))
check("no CJK in the gate module", not CJK.search(source))

print()
print(f"{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
