r"""Checks for the legal pages and the public site structure.

Two kinds of check, and the second is the one that matters:

  1. **Does the site work?** Every route renders, every internal link resolves,
     no `{{token}}` is left visible, no placeholder bracket reaches a customer.

  2. **Is the text true?** A privacy policy is a promise about behaviour. Each
     claim in the documents is checked against the code that actually behaves
     that way - files are deleted, reports are not stored, the AI sees one
     sentence at a time, the card number never reaches us. If the code changes
     and the policy does not, this file fails.

Run:  .\.venv\Scripts\python.exe tools\test_site.py            (no browser, no key)
      .\.venv\Scripts\python.exe tools\test_site.py --strict   (pre-launch gate:
                                     also fails on leftover placeholders)
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.site import (  # noqa: E402
    LEGAL_PAGES,
    SITE,
    SUPPORT_EMAIL_FALLBACK,
    Site,
    fill,
)

LEGAL_DIR = ROOT / "app" / "web" / "legal"
STRICT = "--strict" in sys.argv

passed = failed = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL  {label}" + (f"  [{detail}]" if detail else ""))


def doc(name: str) -> str:
    return (LEGAL_DIR / name).read_text(encoding="utf-8")


def filled(name: str) -> str:
    return fill(doc(name), SITE)


TERMS = filled("terms.md")
PRIVACY = filled("privacy.md")
REFUND = filled("refund.md")
ALL = {"terms": TERMS, "privacy": PRIVACY, "refund": REFUND}


print("1. configuration")
check("site config imports", SITE.product == "Contract Redline")
# Built explicitly rather than from Site()'s defaults: the defaults are the real
# identity now, so relying on them would make this self-test pass only while the
# site is unfinished. What is being tested is the *detector*, not the defaults.
_bracketed = Site(
    operator="[YOUR REGISTERED COMPANY NAME]",
    operator_type="[SOLE PROPRIETORSHIP / LIMITED COMPANY, JURISDICTION]",
    address="[REGISTERED BUSINESS ADDRESS]",
    email="[SUPPORT EMAIL]",
    domain="[YOUR DOMAIN, e.g. contractredline.io]",
)
check("placeholder detection works on a bracketed site",
      len(_bracketed.placeholders_left) == 5, str(_bracketed.placeholders_left))
check("a half-filled site is still caught",
      Site(operator="[FILL THIS IN]", operator_type="Ltd, HK", address="1 Road",
           email="a@b.co", domain="b.co").placeholders_left == ["operator"])
check("a filled site reports none",
      Site(operator="Acme Ltd", operator_type="Ltd, HK", address="1 Road",
           email="a@b.co", domain="b.co").placeholders_left == [])
check("copyright year comes from the effective date",
      SITE.copyright_year.isdigit() and len(SITE.copyright_year) == 4,
      SITE.copyright_year)

print("2. every token resolves")
for name, text in ALL.items():
    left = re.findall(r"\{\{[a-z_]+\}\}", text)
    check(f"{name}: no unresolved tokens", not left, str(left))

print("3. required sections are present")
REQUIRED = {
    "terms": [
        "not a law firm",
        "does not provide legal advice",
        "attorney–client",
        "Eligibility",
        "Limitation of liability",
        "Governing law",
        "Refund Policy",
        "Privacy Policy",
    ],
    "privacy": [
        "data controller",
        "What we collect",
        "What we do not collect",
        "legal basis",
        "International transfers",
        "How long we keep it",
        "Your rights",
        "Cookies",
        "Children",
        "Contact",
    ],
    "refund": [
        "When we refund in full",
        "When we do not refund",
        "How to ask",
        "statutory rights",
        "Chargebacks",
    ],
}
for name, needles in REQUIRED.items():
    for needle in needles:
        check(f"{name}: mentions '{needle}'", needle.lower() in ALL[name].lower())

print("4. identity appears in every document")
for name, text in ALL.items():
    check(f"{name}: operator name", SITE.operator in text, SITE.operator)
    check(f"{name}: support email", SITE.email in text, SITE.email)
    check(f"{name}: address", SITE.address in text)
    check(f"{name}: effective date", SITE.effective in text)
    check(f"{name}: english only",
          not any("\u4e00" <= ch <= "\u9fff" for ch in text))

# The domain moved from .com to .io once already. A support address on a domain
# we do not own is a dead end for the customer and a mismatch for the reviewer,
# and it is invisible on screen because the address still looks plausible. These
# two checks make the relationship explicit: the email lives on our domain, and
# no document keeps the old one.
#
# While Cloudflare Email Routing is not live, mail goes through one named fallback
# (see SUPPORT_EMAIL_FALLBACK in app/site.py). The check stays strict: our domain,
# or exactly that address - any third domain is still a failure, so a typo or a
# half-finished edit cannot ship a mailbox nobody reads.
check("the support address is on our own domain, or the one documented fallback",
      SITE.email_on_own_domain or SITE.email == SUPPORT_EMAIL_FALLBACK,
      f"{SITE.email} vs {SITE.domain}")
if not SITE.email_on_own_domain:
    print(f"  note  mail uses the temporary fallback {SUPPORT_EMAIL_FALLBACK}; "
          f"switch to support@contractredline.io once routing is live")
for name, text in ALL.items():
    check(f"{name}: no stale .com address", "contractredline.com" not in text)
    check(f"{name}: names the real domain", SITE.domain in text)

print("5. internal links resolve to a real route")
from app.web.pages import ROUTES, pricing_text  # noqa: E402

routes = {path for _, path, _ in ROUTES}
check("scanner is the default route", ROUTES[0][1] == "scan")
for page in LEGAL_PAGES:
    check(f"route exists for /{page.slug}", page.slug in routes, str(routes))
check("pricing route exists", "pricing" in routes)

LINK = re.compile(r"\]\(([^)]+)\)")
for name, text in list(ALL.items()) + [("pricing", pricing_text())]:
    targets = LINK.findall(text)
    check(f"{name}: has links", bool(targets), str(targets))
    for target in targets:
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        check(f"{name}: link '{target}' is a known route", target in routes, target)

print("6. the text matches the code")
imports = (ROOT / "app" / "web" / "uploads.py").read_text(encoding="utf-8")
deepseek = (ROOT / "app" / "llm" / "deepseek_client.py").read_text(encoding="utf-8")
guards = (ROOT / "app" / "llm" / "guards.py").read_text(encoding="utf-8")

check("claim 'deleted when the scan finishes' matches a finally-block delete",
      "shutil.rmtree" in imports and "finally:" in imports)
check("claim 'temporary storage' matches tempfile use", "mkdtemp" in imports)
check("claim 'no report stored' matches: nothing writes the html to disk in web/",
      not any("write_text" in p.read_text(encoding="utf-8")
              for p in (ROOT / "app" / "web").glob("*.py")
              if p.name != "uploads.py"))
check("claim 'AI gets one matched sentence' matches the enrich signature",
      "def enrich(" in deepseek and "findings" in deepseek)
check("claim 'not permitted to decide' matches the guards module existing",
      "def " in guards)
payment_code = [
    p for p in (ROOT / "app").rglob("*.py")
    if re.search(r"^\s*(import stripe|from stripe)", p.read_text(encoding="utf-8"), re.M)
]
check("claim 'we never see the full card number' matches: no payment code yet",
      not payment_code, str([p.name for p in payment_code]))

print("7. payment wording matches what the code does")
check("the price in the terms is the price on the site", SITE.price in TERMS)
check("the price is on the pricing page", SITE.price in pricing_text())
check("the refund policy names the price", SITE.price in REFUND)
check("terms no longer promise a free service", "no charge is made" not in TERMS.lower())
check("nothing still promises a free beta", "free while in beta" not in REFUND.lower())
check("stripe is named where money is discussed",
      "stripe" in TERMS.lower() and "stripe" in REFUND.lower()
      and "stripe" in PRIVACY.lower())

billing_src = (ROOT / "app" / "billing.py").read_text(encoding="utf-8")
# "We never see your card number" is only true while our code reads the session
# status and nothing else. If a card field ever appears here, this fails.
check("claim 'we never see your card number' matches: no card field is read",
      not re.search(r"\bcard_number\b|\blast4\b|exp_month|exp_year|\bcvc\b", billing_src))
check("we ask Stripe only whether it was paid, and how much",
      "payment_status" in billing_src and "amount_total" in billing_src)
check("the payment code never prints or logs anything",
      not re.search(r"^\s*(print|import logging|logging\.)", billing_src, re.M))
check("refund policy covers a paid report that never unlocked",
      "never unlocked" in REFUND)
check("pricing page says what the free part is",
      "free" in pricing_text().lower() and SITE.price in pricing_text())

print("8. every page renders")
from streamlit.testing.v1 import AppTest  # noqa: E402

HARNESS = """
import sys
sys.path.insert(0, {root!r})
import streamlit as st
from app.web import pages, ui
st.markdown(ui.CSS, unsafe_allow_html=True)
pages.{func}()
ui.footer()
"""

tmp = Path(tempfile.mkdtemp())
for title, path, func in ROUTES:
    name = func.__name__
    script = tmp / f"{name}.py"
    script.write_text(HARNESS.format(root=str(ROOT), func=name), encoding="utf-8")
    at = AppTest.from_file(str(script), default_timeout=90)
    at.run()
    joined = " ".join(m.value for m in at.markdown)
    check(f"/{path} renders without an exception", not at.exception, str(at.exception))
    check(f"/{path} shows the footer", "cr-footer" in joined)
    check(f"/{path} has no visible token", "{{" not in joined)
    if name != "scanner":
        check(f"/{path} names the operator", SITE.operator in joined)
        check(f"/{path} links back to the scanner", 'href="./"' in joined)

print("9. the entry point wires every route")
entry = (ROOT / "app" / "web" / "streamlit_app.py").read_text(encoding="utf-8")
check("entry uses the route table", "pages.ROUTES" in entry)
check("entry hides the sidebar nav", 'position="hidden"' in entry)
check("entry applies the stylesheet before routing",
      entry.index("ui.CSS") < entry.index("nav.run()"))
check("entry draws the footer after the page", entry.index("nav.run()") < entry.index("ui.footer()"))

print()
if SITE.placeholders_left:
    missing = ", ".join(SITE.placeholders_left)
    if STRICT:
        failed += 1
        print(f"  FAIL  5.1 of the launch checklist: placeholders left in app/site.py "
              f"({missing})")
    else:
        print(f"NOTE: {len(SITE.placeholders_left)} placeholder(s) still in "
              f"app/site.py: {missing}")
        print("      Fine while developing. Run with --strict before submitting "
              "the site for review.")
print(f"{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
