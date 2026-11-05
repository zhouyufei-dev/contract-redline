"""The pages themselves: the scanner, then the pages a reviewer looks for.

Each function is a page. `streamlit_app.py` registers them with `st.navigation`,
which gives each one a real URL (`/terms`, `/privacy`, `/refund`, `/pricing`) -
that matters, because a link an automated review cannot open is the same as a
missing page.

The scanner page keeps the behaviour it had in step 8; the only change is that
it now ends with a footer linking to the legal pages.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from app.parsers.extractor import ExtractionError
from app.site import SITE, fill
from app.web import paywall, ui, uploads

LEGAL_DIR = Path(__file__).resolve().parent / "legal"

BAND_WORDS = (
    ("critical", "deal-breaker"),
    ("serious", "serious"),
    ("moderate", "costly"),
    ("minor", "to watch"),
)


# --------------------------------------------------------------------------
# Scanner
# --------------------------------------------------------------------------

def _frame_height(cards: int) -> int:
    """Rough page height so the iframe opens on a full screen, not a slit."""
    return max(1200, min(4200, 1150 + 160 * cards))


def _band_line(counts: dict[str, int]) -> str:
    parts = [
        f"{counts[band]} {word}{'' if counts[band] == 1 else 's'}"
        for band, word in BAND_WORDS
        if counts.get(band)
    ]
    return " · ".join(parts) if parts else "no red flags"


def _render_result() -> None:
    result = st.session_state.get("result")
    if not result:
        return

    # A payment can arrive while a locked report is already on screen: the
    # customer paid in another tab, or has just pasted the receipt link into the
    # box under this report. Spend it before deciding what to draw, otherwise the
    # report stays locked until the file is scanned a second time - which is the
    # exact shape of "I paid and nothing happened".
    paywall.spend_credit(result.get("key", ""))

    html = result["html"]
    total = result["cards"]
    src = result["source"]
    used_llm = result["used_llm"]
    band_line = _band_line(result["counts"])
    unlocked = paywall.is_unlocked(result.get("key", ""))
    shown = total if unlocked else min(1, total)

    st.markdown('<hr class="cr-rule">', unsafe_allow_html=True)

    note = "written by AI from the matched clause, checked against the text" if used_llm \
        else "from our rule library"
    if total == 0:
        head = "nothing flagged"
        tail = ("No red-flag clause matched our library. The report explains what "
                "that does and does not mean.")
    elif unlocked:
        head = f"{total} card{'s' if total != 1 else ''}, worst first"
        tail = "The report below is the same file you can download."
    else:
        head = f"1 of {total} cards &middot; the rest is locked"
        tail = ("You are seeing the single most dangerous clause. The rest is "
                "already analysed and waiting below.")
    st.markdown(
        f"""
        <div class="cr-result-head">
          <p class="cr-result-title">{head}</p>
          <p class="cr-result-meta">{src}</p>
        </div>
        <p class="cr-result-sub">{band_line}. Explanations {note}. {tail}</p>
        """,
        unsafe_allow_html=True,
    )

    if unlocked:
        st.download_button(
            "Download the report",
            data=html,
            file_name=uploads.download_name(src),
            mime="text/html",
            type="primary",
            key="download-report",
        )

    label = "Your report" if unlocked else "Your report \u2014 preview"
    st.markdown(f'<p class="cr-frame-label">{label}</p>', unsafe_allow_html=True)
    components.html(
        html if unlocked else result["preview"],
        # The teaser is shorter than a full report but taller than one card:
        # the unlock block has to be visible without hunting for it.
        height=_frame_height(shown) + (0 if unlocked else 480),
        scrolling=True,
    )

    if not unlocked:
        paywall.page_block(total, shown, result["counts"], result["worst_band"])
        paywall.unlock_box("report")

    if st.button("Scan another contract", key="reset"):
        for key in ("result", "upload_sig"):
            st.session_state.pop(key, None)
        # Bumping the uploader's key is the only way to empty Streamlit's
        # file widget; without it the old file stays selected after a reset.
        st.session_state["upload_nonce"] = st.session_state.get("upload_nonce", 0) + 1
        st.rerun()


def _run(uploaded, use_llm: bool) -> None:
    data = uploaded.getvalue()

    with st.status("Analyzing your contract…", expanded=True) as status:
        status.write("Reading the file")
        try:
            analysis = uploads.analyze_upload(
                uploaded.name,
                data,
                use_llm=use_llm,
                on_step=lambda label: status.write(label),
            )
        except uploads.UploadError as exc:
            status.update(label="That file could not be used", state="error")
            st.error(str(exc))
            return
        except ExtractionError as exc:
            status.update(label="That file could not be read", state="error")
            st.error(str(exc))
            return
        except Exception as exc:  # never show a traceback to a paying user
            status.update(label="Something went wrong", state="error")
            st.error(
                "The scan stopped unexpectedly. Nothing was saved. "
                f"Technical detail: {type(exc).__name__}."
            )
            return

        status.update(
            label=f"Done — {len(analysis.report.cards)} cards",
            state="complete",
            expanded=False,
        )

    summary = analysis.report.summary
    key = paywall.fingerprint(data)
    st.session_state["result"] = {
        "html": analysis.html,
        "preview": analysis.preview_html,
        "cards": len(analysis.report.cards),
        "counts": dict(summary.counts),
        "worst_band": analysis.report.cards[0].band if analysis.report.cards else "",
        "key": key,
        "source": analysis.outcome.source_name,
        "used_llm": analysis.explanation.used_llm,
    }

    if analysis.explanation.skipped_reason and use_llm:
        st.info(
            "No AI explanations this time — the report uses our standard wording "
            "for each clause instead. It is still complete and accurate."
        )

    # Spend a verified payment on the report it is first shown against. Doing it
    # last matters: `bind` clears the Stripe id out of the address bar, and the
    # paid report must already be sitting in session_state when that happens.
    paywall.spend_credit(key)


def scanner() -> None:
    ui.hero()
    paywall.check_return()

    # The automatic paths had nothing to work with: either no reference came
    # through at all, or the one that did was already spent. Offer the manual one
    # before the uploader, so a customer who has just paid sees a way forward
    # immediately instead of uploading and meeting the paywall again.
    if paywall.credit() is None and not st.session_state.get("result"):
        paywall.unlock_box("scan")

    # Sits directly above the box it describes. The price is read from SITE so
    # this line cannot drift from the Stripe link, the paywall and the legal
    # pages, which all quote the same number.
    st.markdown(
        f'<p class="cr-offer">Your first risk check is <strong>free</strong>. '
        f'Unlock the complete 20-point report for just '
        f'<strong>{SITE.price}</strong> &mdash; one-time payment, no subscription.</p>',
        unsafe_allow_html=True,
    )

    nonce = st.session_state.get("upload_nonce", 0)
    uploaded = st.file_uploader(
        "Your contract",
        type=["pdf", "docx"],
        accept_multiple_files=False,
        label_visibility="collapsed",
        help=f"Text-based PDF or Word .docx, up to {uploads.MAX_MB} MB.",
        key=f"upload-{nonce}",
    )

    # A different file means the report on screen is about the wrong document.
    if uploaded is not None:
        signature = (uploaded.name, uploaded.size)
        if st.session_state.get("upload_sig") != signature:
            st.session_state["upload_sig"] = signature
            st.session_state.pop("result", None)

    use_llm = st.toggle(
        "Write plain-English explanations",
        value=True,
        help="Turn off to see the rule engine's own wording instead. "
             "Both versions find exactly the same clauses.",
    )

    pressed = st.button("Scan My Contract", type="primary", key="scan")

    # Verified, not aspirational: uploads.py writes the bytes to a temp folder and
    # removes that folder in a finally block, and the web path passes
    # use_cache=False so no clause is kept by the LLM cache either.
    # tools/verify_upload_disposal.py proves it; keep this sentence true or drop it.
    st.markdown(
        '<p class="cr-trust">No account required. Your uploaded file is deleted '
        'after the scan finishes.</p>',
        unsafe_allow_html=True,
    )

    st.markdown(
        f'<p class="cr-fine"><strong>PDF or DOCX</strong> &middot; up to '
        f'{uploads.MAX_MB} MB<br>'
        'This is software, not a law firm — it is not legal advice.</p>',
        unsafe_allow_html=True,
    )

    if pressed:
        if uploaded is None:
            st.warning("Choose a PDF or DOCX file first, then press Scan.")
        else:
            _run(uploaded, use_llm)

    _render_result()


# --------------------------------------------------------------------------
# Legal pages
# --------------------------------------------------------------------------

def _legal(filename: str) -> None:
    """Render one markdown document, with the site tokens filled in."""
    path = LEGAL_DIR / filename
    st.markdown(fill(path.read_text(encoding="utf-8"), SITE))


def _legal_page(filename: str) -> None:
    ui.crumb()
    _legal(filename)


def terms() -> None:
    _legal_page("terms.md")


def privacy() -> None:
    _legal_page("privacy.md")


def refund() -> None:
    _legal_page("refund.md")


def pricing_text() -> str:
    """The pricing page as markdown, with the site tokens filled."""
    return fill(_PRICING, SITE)


def pricing() -> None:
    ui.crumb()
    st.markdown(pricing_text())


# --------------------------------------------------------------------------
# The route table. `streamlit_app.py` builds st.navigation from this, and
# tools/test_site.py asserts that every link in the legal documents resolves to
# a path listed here - a broken legal link is a failed review, not a typo.
# --------------------------------------------------------------------------

ROUTES: tuple[tuple[str, str, object], ...] = (
    ("Scan a contract", "scan", scanner),
    ("Pricing", "pricing", pricing),
    ("Terms of Service", "terms", terms),
    ("Privacy Policy", "privacy", privacy),
    ("Refund Policy", "refund", refund),
)


_PRICING = """
# Pricing

**{{price}} per contract report. Charged once. No subscription, no account.**

## What it costs

- **Price per report:** {{price}}, one payment for one contract
- **What you get:** every flagged clause, the sentence quoted from your contract,
  why it matters, the wording to send back to your client, and a report you can
  download and print
- **What you get free:** a real preview before you pay — the single most serious
  problem we found, with its quote and explanation
- **Account required:** no
- **Subscription:** none
- **Recurring charge:** none

## How it works

1. Upload a PDF or DOCX. It is read on our server and matched against 20
   red-flag clause types, plus a language model that explains each hit.
2. You see the worst problem straight away, free.
3. If you want the other 19, pay {{price}} with Stripe. Nothing is charged until
   you confirm on Stripe's own checkout page.
4. Because we never store your contract, you then attach the same file once more
   and the full report opens. The second scan is the same scan — no extra charge,
   and no second payment.

## What the money does not buy

Not legal advice, and not a guarantee. The report tells you which clauses match a
fixed library of patterns that commonly work against freelancers. It is a
screening tool: it helps you see what you are signing and what to ask for, and it
is not a substitute for a lawyer on a contract that matters.

## Payments

Payments are processed by [Stripe](https://stripe.com). We never see or store your
card number — Stripe handles the card and tells us only that the payment
succeeded. See the [Refund Policy](refund) and the [Terms of Service](terms).
"""

