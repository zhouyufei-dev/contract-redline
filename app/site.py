"""The facts the public pages assert. One place, so they cannot disagree.

Every legal page (Terms, Privacy, Refund) and the footer read their operator
name, address, email, domain and effective date from here. If the entity is
renamed or the domain moves, it is edited once.

The values below are the operator's real trading identity. Two of them are
deliberately coarse and **must be refined before the Stripe review**:

  * ``address`` is region-level, not a deliverable address. A legal notice and a
    refund both need somewhere to arrive, and Stripe compares the site against
    the address on the account.
  * ``operator_type`` mirrors what the Stripe account says (``individual``). If
    the business is later incorporated, this line and the account both change.

Anything still inside [square brackets] is a placeholder: `tools/test_site.py`
prints how many are left, and `tools/test_site.py --strict` fails while any
remain. That is the command to run before submitting the site for review.

Nothing in this file is legal advice. It is configuration.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.config import get_settings

# Bump this when the legal text changes materially. Shown at the top of each page.
# 2026-11-02: fees, refunds and payment handling were rewritten for the $5
# paywall, so the date moved with them.
EFFECTIVE_DATE = "November 2, 2026"

PRODUCT_NAME = "Contract Redline"

#: The live-mode Payment Link. Test mode uses a different URL, and Stripe only
#: issues one inside the dashboard, so it is supplied through .env instead:
#:     STRIPE_PAYMENT_URL=https://buy.stripe.com/test_...
DEFAULT_PAYMENT_URL = "https://buy.stripe.com/7sY00jgD89SQ2bEaXcbfO00"


def resolve_payment_url(override: str | None) -> str:
    """Pick the Payment Link to put in the button.

    Only an https URL is accepted. The value ends up inside an ``href``, and an
    ``href`` that starts with ``javascript:`` is a script injection, not a link;
    a typo in .env must fall back to the live link rather than become one.
    """
    value = (override or "").strip()
    return value if value.startswith("https://") else DEFAULT_PAYMENT_URL


@dataclass(frozen=True)
class Site:
    """Everything a visitor could need in order to know who they are dealing with."""

    product: str = PRODUCT_NAME
    operator: str = "Contract Redline"
    operator_type: str = "Individual (sole proprietor), Hong Kong SAR"
    # Region-level on purpose: see the module docstring. Replace with the full
    # registered address before the Stripe review, and keep it identical to the
    # address on the Stripe account.
    address: str = "Kowloon, Hong Kong SAR"
    email: str = "support@contractredline.io"
    domain: str = "contractredline.io"
    governing_law: str = "Hong Kong SAR"
    effective: str = EFFECTIVE_DATE
    # One price, in three shapes, because three different places need it:
    # prose (pricing page, legal pages), a button label, and a number that the
    # payment check compares the Stripe amount against.
    price_summary: str = "$5 per contract report"
    price: str = "$5"
    price_cents: int = 500
    # Public, non-secret: a Stripe Payment Link is meant to be pasted on a page.
    payment_url: str = DEFAULT_PAYMENT_URL

    def tokens(self) -> dict[str, str]:
        """{{token}} -> value, for the markdown in app/web/legal/."""
        return {
            "product": self.product,
            "operator": self.operator,
            "operator_type": self.operator_type,
            "address": self.address,
            "email": self.email,
            "domain": self.domain,
            "governing_law": self.governing_law,
            "effective": self.effective,
            "price_summary": self.price_summary,
            "price": self.price,
            "payment_url": self.payment_url,
        }

    @property
    def placeholders_left(self) -> list[str]:
        """Field names whose value still contains a [bracket] placeholder."""
        out = []
        for name in ("operator", "operator_type", "address", "email", "domain"):
            if "[" in getattr(self, name):
                out.append(name)
        return out

    @property
    def copyright_year(self) -> str:
        match = re.search(r"\b(20\d{2})\b", self.effective)
        return match.group(1) if match else ""


SITE = Site(payment_url=resolve_payment_url(get_settings().payment_url))


def fill(text: str, site: Site = SITE) -> str:
    """Replace {{tokens}} in a markdown page. Unknown tokens are left alone."""
    for key, value in site.tokens().items():
        text = text.replace("{{" + key + "}}", value)
    return text


@dataclass(frozen=True)
class LegalPage:
    slug: str
    title: str
    filename: str
    summary: str


LEGAL_PAGES: tuple[LegalPage, ...] = (
    LegalPage(
        "terms",
        "Terms of Service",
        "terms.md",
        "The agreement between you and us: what the Service does, what it does "
        "not do, and the limits of our liability.",
    ),
    LegalPage(
        "privacy",
        "Privacy Policy",
        "privacy.md",
        "What happens to the contract you upload, who else sees it, and how to "
        "have your data deleted.",
    ),
    LegalPage(
        "refund",
        "Refund Policy",
        "refund.md",
        "When you get your money back, when you do not, and how to ask.",
    ),
)
