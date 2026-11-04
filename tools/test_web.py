r"""Checks for the web layer. No browser, no Streamlit runtime, no API key needed.

What is actually being verified here:

  * the upload gate rejects the things a user will really try (a .doc renamed
    to .docx, an empty file, a 30 MB scan, a path-traversal filename) with a
    message that makes sense to a non-lawyer-non-programmer;
  * the upload -> pipeline -> HTML path produces the same report the CLI does,
    including the hardcoded disclaimer, for both real sample files;
  * nothing is left on disk afterwards;
  * the Streamlit script itself runs top to bottom without an exception
    (AppTest), so a syntax or attribute error cannot reach the user.

Run:  .\.venv\Scripts\python.exe tools\test_web.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.pipeline import analyze  # noqa: E402
from app.report.disclaimer import DISCLAIMER  # noqa: E402
from app.web import uploads  # noqa: E402

SAMPLES = ROOT / "data" / "samples"
DOCX = SAMPLES / "fake_contract_01.docx"
PDF = SAMPLES / "fake_contract_01.pdf"

passed = failed = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL  {label}" + (f"  [{detail}]" if detail else ""))


def expect_upload_error(label: str, name: str, data: bytes, needle: str) -> None:
    try:
        uploads.validate(name, data)
    except uploads.UploadError as exc:
        check(label, needle.lower() in str(exc).lower(), str(exc))
    else:
        check(label, False, "no error raised")


print("1. upload gate")
p = PDF.read_bytes()
d = DOCX.read_bytes()

check("pdf accepted", uploads.validate("Contract.PDF", p) == ".pdf")
check("docx accepted", uploads.validate("contract.docx", d) == ".docx")
expect_upload_error("empty file", "x.pdf", b"", "empty")
expect_upload_error("wrong type", "contract.txt", b"hello", "pdf")
expect_upload_error("no extension", "contract", b"hello", "pdf")
expect_upload_error(
    "doc renamed to docx", "contract.docx", b"\xd0\xcf\x11\xe0 old word doc", "not a word document"
)
expect_upload_error("pdf renamed from image", "scan.pdf", b"\xff\xd8\xff\xe0", "not a pdf")
expect_upload_error(
    "oversize", "big.pdf", b"%PDF-" + b"0" * (uploads.MAX_BYTES + 10), "limit"
)

print("2. filenames")
check("strips windows path", uploads.safe_name("..\\..\\etc\\passwd.docx") == "passwd.docx",
      uploads.safe_name("..\\..\\etc\\passwd.docx"))
check("strips posix path", uploads.safe_name("../../secrets/x.pdf") == "x.pdf",
      uploads.safe_name("../../secrets/x.pdf"))
check("keeps spaces and dashes",
      uploads.safe_name("Acme - Design Contract (v2).docx") == "Acme - Design Contract (v2).docx",
      uploads.safe_name("Acme - Design Contract (v2).docx"))
check("caps length", len(uploads.safe_name("a" * 300 + ".pdf")) <= 90,
      str(len(uploads.safe_name("a" * 300 + ".pdf"))))
check("empty name survives", uploads.safe_name("") == "contract.pdf", uploads.safe_name(""))
check("download name", uploads.download_name("Acme.docx") == "Acme.report.html",
      uploads.download_name("Acme.docx"))

print("3. temp file is cleaned up")
before = set(Path(tempfile.gettempdir()).glob("contract-redline-*"))
with uploads.saved_upload("contract.docx", d) as path:
    check("file written", path.exists() and path.read_bytes() == d)
    holder = path
check("folder removed", not holder.exists())
after = set(Path(tempfile.gettempdir()).glob("contract-redline-*"))
check("no new temp folders", after == before, f"{len(before)} -> {len(after)}")

print("4. full pipeline from upload bytes (docx)")
analysis = uploads.analyze_upload("fake_contract_01.docx", d, use_llm=False)
html = analysis.html
check("cards produced", len(analysis.report.cards) == 20, str(len(analysis.report.cards)))
check("source name is the upload name",
      analysis.outcome.source_name == "fake_contract_01.docx",
      analysis.outcome.source_name)
check("html is a full document", html[:15].lower() == "<!doctype html>", html[:15])
check("html has no placeholders left",
      "{" not in html.split("</style>")[1][:200] and "None" not in html[:2000])
check("disclaimer is in the html", DISCLAIMER.strip()[:60] in html)
check("english only", not any("\u4e00" <= ch <= "\u9fff" for ch in html))
check("source name appears in the report", "fake_contract_01.docx" in html)
check("reports are deterministic", analyze(DOCX, use_llm=False).html == html)

print("5. full pipeline from upload bytes (pdf)")
pdf_analysis = uploads.analyze_upload("fake_contract_01.pdf", p, use_llm=False)
check("pdf cards produced", len(pdf_analysis.report.cards) == 20,
      str(len(pdf_analysis.report.cards)))
check("pdf report carries the disclaimer", DISCLAIMER.strip()[:60] in pdf_analysis.html)

print("6. steps are announced")
labels: list[str] = []
uploads.analyze_upload("fake_contract_01.docx", d, use_llm=False, on_step=labels.append)
check("two steps without AI", len(labels) == 2, str(labels))
check("step 1 mentions the rules", "red-flag" in labels[0].lower(), labels[0])
check("step 2 mentions the report", "report" in labels[1].lower(), labels[1])
check("labels are english only",
      not any("\u4e00" <= ch <= "\u9fff" for s in labels for ch in s))
check("no file path in any step",
      not any("\\" in s or "/" in s for s in labels), str(labels))
check("no key material in any step", not any("sk-" in s for s in labels))

print("7. the page renders")
from streamlit.testing.v1 import AppTest  # noqa: E402

at = AppTest.from_file(str(ROOT / "app" / "web" / "streamlit_app.py"), default_timeout=90)
at.run()
check("script ran", not at.exception, str(at.exception))
check("title present", any("Know what you are signing" in m.value for m in at.markdown))
check("scan button present", any(b.label == "Scan My Contract" for b in at.button))
check("uploader present", len(at.get("file_uploader")) == 1)

# What a visitor sees in the footer. These were placeholders until launch prep,
# and a placeholder that reaches a customer is worse than no page at all.
from app.site import SITE  # noqa: E402

page_blob = "\n".join(m.value for m in at.markdown)
check("footer names the operator", SITE.operator in page_blob)
check("footer shows a reachable address", SITE.address in page_blob, SITE.address)
check("footer shows the support email", SITE.email in page_blob, SITE.email)
for legacy in ("[YOUR REGISTERED", "[REGISTERED BUSINESS ADDRESS]", "[SUPPORT EMAIL]",
               "[YOUR DOMAIN"):
    check(f"no leftover {legacy}", legacy not in page_blob)
# Whether the mailbox sits on our own domain (or the one documented fallback) is
# decided in tools/test_site.py, section 4. Keeping a second copy of that rule
# here meant two places to edit every time the address moved, and this copy went
# stale the moment mail started going through the fallback. What belongs here is
# only that the footer shows something usable.
_domain = SITE.email.rsplit("@", 1)[-1] if "@" in SITE.email else ""
check("footer address is well formed",
      SITE.operator == "Contract Redline" and "." in _domain and " " not in SITE.email,
      SITE.email)

print("8. the 20 MB limit is stated the same way everywhere")
# Three places have to agree or the page contradicts itself, which is what a
# "200MB per file" uploader under a "up to 20 MB" line looked like. The config
# file wins at runtime, so a mismatch means the site accepts what the page
# denies (or the reverse).
import tomllib  # noqa: E402

config = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
configured = config["server"]["maxUploadSize"]
check("config.toml limit equals MAX_MB", configured == uploads.MAX_MB,
      f"config={configured} code={uploads.MAX_MB}")
check("MAX_BYTES is MAX_MB in bytes", uploads.MAX_BYTES == uploads.MAX_MB * 1024 * 1024)

# Two settings that look harmless in a tutorial and break this particular app.
check("config.toml does not pin browser.serverAddress",
      "serverAddress" not in config.get("browser", {}),
      str(config.get("browser", {}).get("serverAddress")))
check("config.toml leaves CORS on (Streamlit ties XSRF to it)",
      config.get("server", {}).get("enableCORS", True) is not False,
      str(config.get("server", {}).get("enableCORS")))

page_text = " ".join(m.value for m in at.markdown)
check("page text states the limit in MB", f"up to {uploads.MAX_MB} MB" in page_text,
      page_text[:200])
check("no stale 200 MB claim anywhere in the page",
      "200 MB" not in page_text and "200MB" not in page_text)

# The refusal message must quote the same number the uploader advertises.
expect_upload_error(
    "oversize message quotes the limit",
    "big.pdf",
    b"%PDF-1.4" + b"\0" * (uploads.MAX_BYTES + 1024),
    str(uploads.MAX_MB),
)

print("9. the web path leaves no contract text on disk")
# The page tells the customer the file is deleted when the scan finishes. The
# LLM cache would quietly keep every clause it explained, so the web path must
# not use it. Caught via the pipeline call, not by running the LLM.
import app.web.uploads as uploads_mod  # noqa: E402

captured: dict[str, object] = {}


class _FakeAnalysis:
    html = ""
    report = None


def _fake_analyze(path, **kwargs):
    captured.update(kwargs)
    return _FakeAnalysis()


original_analyze = uploads_mod.analyze
uploads_mod.analyze = _fake_analyze
try:
    uploads_mod.analyze_upload("contract.docx", d, use_llm=True)
finally:
    uploads_mod.analyze = original_analyze

check("the web path asks the pipeline for no cache", captured.get("use_cache") is False,
      str(captured.get("use_cache")))
check("the web path still explains with the AI", captured.get("use_llm") is True)

print("10. Streamlit's own chrome is hidden, from one place")
# The product page must not show the dev toolbar, the "..." menu, the footer or
# the running-status widget. These four were spread over two rules once, and an
# edit could quietly leave half of them on - so the stylesheet is now the single
# source and this pins it.
from app.web import ui  # noqa: E402

css = ui.CSS
for selector in ('#MainMenu', 'footer', 'header[data-testid="stHeader"]',
                 'div[data-testid="stStatusWidget"]'):
    check(f"{selector} is hidden", selector in css)
check("the hide rules cannot be overridden",
      css.count("visibility: hidden !important") == 1,
      str(css.count("visibility: hidden !important")))
check("the status widget is not styled twice",
      css.count('data-testid="stStatusWidget"') == 1,
      str(css.count('data-testid="stStatusWidget"')))
check("the design itself is still in the stylesheet",
      ".cr-footer" in css and "--critical" in css)

print("11. a paid customer can always get in, without the URL")
# The bug that cost real money: the customer paid, was redirected to their own
# domain, and this app lives inside an iframe there, so its own URL never carried
# `?session_id=`. The reference was on the page the browser could see, the app
# could not. Everything automatic is a best effort - so there is a box, and it
# has to work from a fresh page with nothing but a pasted link.
from app import billing as _billing  # noqa: E402

PAID_SESSION = _billing.Payment(
    session_id="cs_live_a146vUO294RCnaf4wTM0SzN5OxtOeAydidhiB2ibzoZNOP4J!X0a8s1",
    paid=True, amount_total=500, currency="usd", mode="payment", status="complete",
)
_real_verify = _billing.verify_session


def _fake_verify(session_id, secret_key=None):
    if session_id == PAID_SESSION.session_id:
        return PAID_SESSION
    raise _billing.PaymentError("Stripe has no record of that checkout.")


try:
    _billing.verify_session = _fake_verify
    # Force a fresh session: the app under test has to behave like a stranger's
    # first visit, not like a continuation of the run above.
    at = AppTest.from_file(str(ROOT / "app" / "web" / "streamlit_app.py"),
                           default_timeout=90)
    at.run()
    check("a fresh page still runs", not at.exception, str(at.exception))

    boxes = [e for e in at.get("expander")]
    check("the manual unlock box is on the page",
          any("Already paid" in str(e.label) for e in boxes),
          str([str(e.label) for e in boxes]))
    check("nothing is unlocked before pasting",
          at.session_state.get("payment_credit") is None)

    at.text_input(key="unlock-value-scan").set_value(
        "https://contractredline.io/?session_id=" + PAID_SESSION.session_id)
    at.button(key="unlock-go-scan").click()
    at.run()
    check("pasting the receipt runs without error", not at.exception, str(at.exception))
    check("the payment is verified and held",
          getattr(at.session_state.get("payment_credit"), "session_id", "")
          == PAID_SESSION.session_id)
    check("the customer is told the amount",
          any("Payment confirmed" in str(s.value) and "$5.00" in str(s.value)
              for s in at.success),
          str([str(s.value) for s in at.success]))

    # And a made-up reference unlocks nothing.
    at2 = AppTest.from_file(str(ROOT / "app" / "web" / "streamlit_app.py"),
                            default_timeout=90)
    at2.run()
    at2.text_input(key="unlock-value-scan").set_value("cs_live_" + "z" * 40)
    at2.button(key="unlock-go-scan").click()
    at2.run()
    check("an invented reference unlocks nothing",
          at2.session_state.get("payment_credit") is None)
    check("and the customer is told why",
          any("no record" in str(e.value) for e in at2.error),
          str([str(e.value) for e in at2.error]))
finally:
    _billing.verify_session = _real_verify

print()
print(f"{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
