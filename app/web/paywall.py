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

4. **The id is looked for in three places, because the browser does not always
   hand it over.** A real customer paid, was sent back with ``?session_id=...``
   on the address they could see, and the report stayed locked: the app was
   running inside an iframe on the company's own domain, so the Streamlit page's
   own URL carried no parameters at all. The order is:

     1. the app's own query string  - correct for a direct deployment;
     2. the embedding page's URL, as sent in the ``Referer`` header - this is the
        case that broke, and it needs no JavaScript and no change to the page
        that embeds us;
     3. the customer pastes the receipt link into `unlock_box` - always works,
        including behind a proxy that rewrites URLs.

   All three end in the same server-side check. A pasted id is not trusted any
   more than a URL parameter: it is only believed because Stripe says it was
   paid. What the manual path costs is one paste; what it buys is that no paying
   customer can ever be stranded by an embedding decision made months earlier.

Nothing here writes to disk and nothing identifies the visitor: the gate is a
dictionary key in `st.session_state`, and `st.session_state` dies with the tab.
"""

from __future__ import annotations

import hashlib
import urllib.parse

import streamlit as st

from app import billing
from app.site import SITE

SESSION_PARAM = "session_id"

#: Fingerprint (sha256 hex) of the file that has already been paid for.
PAID_KEY = "paid_for"
#: A verified payment that has not been attached to a report yet.
CREDIT_KEY = "payment_credit"
#: Session ids already shown to the customer, so a reload does not repeat itself.
SEEN_KEY = "session_seen"
#: Session ids already spent on a report. One payment never buys a second one.
SPENT_KEY = "session_spent"

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


def parse_session_id(value: str | None) -> str:
    """Pull a ``cs_...`` id out of whatever the browser or the customer supplies.

    Accepts a bare id, a whole redirect URL, and an id whose ``!`` was encoded as
    ``%21`` on the way through a query string. Returns "" when nothing in the
    text looks like a Stripe checkout reference, so the caller can tell the
    difference between "no payment mentioned" and "a payment we cannot read".
    """
    text = (value or "").strip().strip("\"'")
    if not text:
        return ""

    marker = SESSION_PARAM + "="
    if marker in text:
        text = text.split(marker, 1)[1]
        text = text.split("&", 1)[0].split("#", 1)[0]

    text = urllib.parse.unquote(text).strip().strip("\"'")
    # A link copied out of a chat or an email often keeps the punctuation that
    # followed it. Session ids never end in these.
    text = text.rstrip(".,;:)]}>\"'")

    return text if billing.looks_like_session_id(text) else ""


def _raw_from_url() -> str:
    """Whatever sits in `?session_id=`, unexamined."""
    try:
        return _first(st.query_params.get(SESSION_PARAM)).strip()
    except Exception:
        # A malformed query string must not take the whole page down.
        return ""


def session_id_from_url() -> str:
    return parse_session_id(_raw_from_url())


def session_id_from_referer() -> str:
    """Recover the id from the embedding page's address, via `Referer`.

    When the app is inside an iframe, the address bar belongs to the parent page:
    `st.query_params` sees the iframe's own URL and finds nothing, which is
    exactly how a paid customer ended up looking at a locked report. The parent's
    URL is still delivered to the server in the ``Referer`` header on the request
    that loads the iframe, so the id is usually recoverable with no JavaScript
    and no change to the page doing the embedding.

    Returns "" when there is no header, no referer, or no id in it - every one of
    which is normal on a direct deployment.
    """
    try:
        headers = list(st.context.headers.items())
    except Exception:
        # No `st.context` (older Streamlit) or a bare-mode test double.
        return ""

    referer = ""
    for name, value in headers:
        if str(name).lower() == "referer":
            referer = str(value)
            break

    return parse_session_id(referer) if SESSION_PARAM + "=" in referer else ""


def credit() -> billing.Payment | None:
    """The verified payment waiting to be spent, if there is one."""
    payment = st.session_state.get(CREDIT_KEY)
    return payment if isinstance(payment, billing.Payment) else None


def already_spent(session_id: str) -> bool:
    """True once this payment has opened a report."""
    spent = st.session_state.get(SPENT_KEY) or set()
    return session_id in spent


def is_unlocked(key: str) -> bool:
    """True only for the exact report that was paid for."""
    return bool(key) and st.session_state.get(PAID_KEY) == key


def bind(key: str) -> None:
    """Spend the credit on this report, then take the id out of the URL."""
    payment = credit()
    st.session_state[PAID_KEY] = key
    st.session_state.pop(CREDIT_KEY, None)
    # Remember which payment bought which report. Without this, re-entering the
    # same receipt link would leave a fresh credit lying around, and the next
    # contract uploaded would unlock on a payment that was already spent.
    if payment is not None:
        spent = st.session_state.get(SPENT_KEY) or set()
        spent.add(payment.session_id)
        st.session_state[SPENT_KEY] = spent
    try:
        st.query_params.clear()
    except Exception:
        # Cosmetic only. A paid report must render even if the URL cannot be
        # tidied; the worst case is that the address bar keeps a spent id.
        pass


def spend_credit(key: str) -> bool:
    """Attach a waiting payment to this report. True if it unlocked it."""
    payment = credit()
    if not key or payment is None or is_unlocked(key):
        return False
    if already_spent(payment.session_id):
        # Re-entering the same receipt creates a credit that has already been
        # used. Drop it rather than let it open a second contract.
        st.session_state.pop(CREDIT_KEY, None)
        return False
    bind(key)
    return True


def check_return() -> None:
    """Call once per run: turn a Stripe redirect into a pending credit.

    Deliberately loud about the three outcomes. A customer who has just paid
    must never be left guessing whether it worked.
    """
    raw = _raw_from_url()
    session_id = parse_session_id(raw) or session_id_from_referer()

    if not session_id:
        if raw:
            st.error(
                "The link you came back on carries a payment reference that could "
                "not be read - it looks like it was shortened or cut off. Your "
                "payment is safe. Open the receipt Stripe emailed you and paste "
                "its link into \"Already paid?\" below."
            )
        return

    seen = st.session_state.get(SEEN_KEY) or set()
    if session_id in seen:
        return

    try:
        payment = billing.verify_session(session_id)
    except billing.PaymentError as exc:
        st.error(str(exc))
        return

    seen.add(session_id)
    st.session_state[SEEN_KEY] = seen

    if not payment.paid:
        st.warning(
            "Stripe says that checkout was not completed, so there is nothing to "
            "unlock yet. You can pay again from the button below - you have not "
            "been charged for the unfinished attempt."
        )
        return

    if already_spent(session_id):
        st.info(
            "That payment has already unlocked a report. One payment covers one "
            "contract; scan the same file again to see it."
        )
        return

    st.session_state[CREDIT_KEY] = payment
    st.success(
        f"Payment received: {payment.amount_label}. "
        "Upload the contract again below and the full report opens immediately - "
        "same file, same result, no second charge."
    )


def unlock_box(where: str) -> None:
    """The manual path: paste the receipt and let Stripe decide.

    `where` only disambiguates the widget keys, so the box can appear both on a
    fresh page and under a report that is already on screen.
    """
    with st.expander("Already paid? Unlock with your Stripe receipt", expanded=False):
        st.caption(
            "Use this if the report stayed locked after paying - some browsers, "
            "and any page that embeds this app in a frame, drop the reference "
            "when they redirect. Paste the address Stripe sent you back to, or "
            "just the `cs_live_...` reference from the receipt email. The "
            "reference is checked with Stripe directly, so an invented one opens "
            "nothing."
        )
        value = st.text_input(
            "Stripe receipt link or checkout reference",
            key=f"unlock-value-{where}",
            placeholder="https://contractredline.io/?session_id=cs_live_...",
            label_visibility="collapsed",
        )
        if not st.button("Unlock my report", key=f"unlock-go-{where}"):
            return

        session_id = parse_session_id(value)
        if not session_id:
            st.error(
                "That does not contain a Stripe checkout reference. It starts "
                "with `cs_live_` and is in the receipt email, or at the end of "
                "the link you were sent back on."
            )
            return

        try:
            payment = billing.verify_session(session_id)
        except billing.PaymentError as exc:
            st.error(str(exc))
            return

        if not payment.paid:
            st.warning(
                "Stripe says that checkout was not completed, so there is nothing "
                "to unlock. Nothing was charged for an unfinished checkout."
            )
            return

        if already_spent(session_id):
            st.info(
                "That payment has already unlocked a report. One payment covers "
                "one contract; scan the same file again to see it."
            )
            return

        st.session_state[CREDIT_KEY] = payment
        st.success(
            f"Payment confirmed: {payment.amount_label}. "
            "Upload your contract below and press Scan - the full report opens, "
            "no second charge."
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
