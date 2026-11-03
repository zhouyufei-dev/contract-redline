"""The $5 gate, as the Streamlit page sees it.

Three rules decide every branch here, and none of them is about looks:

1. **The browser is never trusted.** ``?paid=true`` is a string a stranger can
   type. The only thing that unlocks a report is `app.billing.verify_session`,
   which asks Stripe about the Checkout Session id that Stripe itself appended
   to the success URL.

2. **A payment buys one report.** Not one browser, not one hour. The verified
   payment is attached to a fingerprint of the file that was scanned, so
   uploading a second contract asks for a second payment - and re-uploading the
   same contract stays unlocked, because that is the same report.

3. **The unlock is spent, then the URL stops carrying it.** When the paid
   report is first shown, the session id is removed from the address bar
   (decision: user chose one-time unlock). Reloading after that returns to the
   paywall, which is what "refresh goes back to the paywall" means in practice.

Nothing here writes to disk and nothing identifies the visitor: the gate is a
dictionary key in `st.session_state`, and `st.session_state` dies with the tab.
"""

from __future__ import annotations

import hashlib

import streamlit as st

from app import billing
from app.site import SITE

SESSION_PARAM = "session_id"

#: Fingerprint (sha256 hex) of the file that has already been paid for.
PAID_KEY = "paid_for"
#: A verified payment that has not been attached to a report yet.
CREDIT_KEY = "payment_credit"

_BAND_CHIPS = (
    ("critical", "deal-breaker", "deal-breakers"),
    ("serious", "serious", "serious"),
    ("moderate", "costly", "costly"),
    ("minor", "to watch", "to watch"),
)


def fingerprint(data: bytes) -> str:
    """Identify a report by what is in the file, not by its name.

    The same bytes always produce the same report, so hashing the bytes is the
    honest way to say "this is the thing you paid for".
    """
    return hashlib.sha256(data).hexdigest()


def _first(value) -> str:
    """`st.query_params` returns str, a list (repeated key), or None."""
    if isinstance(value, (list, tuple)):
        return str(value[0]) if value else ""
    return str(value) if value is not None else ""


def session_id_from_url() -> str:
    try:
        return _first(st.query_params.get(SESSION_PARAM)).strip()
    except Exception:
        # A malformed query string must not take the whole page down.
        return ""


def credit() -> billing.Payment | None:
    """The verified payment waiting to be spent, if there is one."""
    payment = st.session_state.get(CREDIT_KEY)
    return payment if isinstance(payment, billing.Payment) else None


def is_unlocked(key: str) -> bool:
    """True only for the exact report that was paid for."""
    return bool(key) and st.session_state.get(PAID_KEY) == key


def bind(key: str) -> None:
    """Spend the credit on this report, then take the id out of the URL."""
    st.session_state[PAID_KEY] = key
    st.session_state.pop(CREDIT_KEY, None)
    try:
        st.query_params.clear()
    except Exception:
        # Cosmetic only. A paid report must render even if the URL cannot be
        # tidied; the worst case is that the address bar keeps a spent id.
        pass


def check_return() -> None:
    """Call once per run: turn a Stripe redirect into a pending credit.

    Deliberately loud about the three outcomes. A customer who has just paid
    must never be left guessing whether it worked.
    """
    session_id = session_id_from_url()
    if not session_id:
        return

    try:
        payment = billing.verify_session(session_id)
    except billing.PaymentError as exc:
        st.error(str(exc))
        return

    if not payment.paid:
        st.warning(
            "Stripe says that checkout was not completed, so there is nothing to "
            "unlock yet. You can pay again from the button below - you have not "
            "been charged for the unfinished attempt."
        )
        return

    st.session_state[CREDIT_KEY] = payment
    st.success(
        f"Payment received: {payment.amount_label}. "
        "Upload the contract again below and the full report opens immediately - "
        "same file, same result, no second charge."
    )


def page_block(total: int, shown: int, counts: dict[str, int], shown_band: str) -> None:
    """The unlock panel under the preview, on the page itself.

    It sits outside the report iframe on purpose: Streamlit sandboxes that
    iframe, and a sandboxed `target="_blank"` link can be swallowed silently.
    A link the customer cannot click is a lost sale, so the real button lives
    here, and the copy inside the report is there for when it is printed.
    """
    hidden = total - shown
    if hidden <= 0:
        return

    chips = []
    for band, singular, plural in _BAND_CHIPS:
        remaining = counts.get(band, 0) - (1 if band == shown_band else 0)
        if remaining > 0:
            word = singular if remaining == 1 else plural
            chips.append(f"<li><strong>{remaining}</strong> more {word}</li>")

    st.markdown(
        f"""
        <div class="cr-paywall">
          <p class="cr-paywall-kicker">Preview &middot; {shown} of {total} clauses</p>
          <h3 class="cr-paywall-title">The other {hidden} are already analysed.</h3>
          <p class="cr-paywall-body">Each one comes with the sentence quoted from your
            contract, a plain-English explanation of what it costs you, and the exact
            wording to send back to your client.</p>
          <ul class="cr-paywall-counts">{"".join(chips)}</ul>
          <a class="cr-paywall-cta" href="{SITE.payment_url}" target="_blank"
             rel="noopener noreferrer">Unlock the full report &mdash; {SITE.price}</a>
          <p class="cr-paywall-fine">One-time payment &middot; Stripe handles the card,
            we never see it &middot; refundable for 7 days &middot; no account needed</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
