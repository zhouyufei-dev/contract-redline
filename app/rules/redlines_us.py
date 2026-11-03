"""The red-flag rules for the US market. DATA, not logic.

Step 5d implements all twenty rules: R01-R20. The set is now frozen (D-005);
further work goes into the LLM layer and the report, not into new rules.

Schema (see app/engine/matcher.Rule)
------------------------------------
    id / name / severity / why / fix
    patterns              - one or more regexes that indicate the clause
    context_any           - must also appear in the sentence
    context_none          - if present, the hit is a different construct
    min_value             - numeric threshold (e.g. days > 30)
    negation_exceptions   - negations that REINFORCE the risk

Wording for `why` / `fix` is anchored to docs/01-合同红线清单.md. The LLM is
given these strings and must not contradict them; keeping them in sync is a
manual step, not an automatic one.
"""

from __future__ import annotations

import re

from app.engine.matcher import Pattern, Rule


def _p(regex: str, label: str, days_group: str | None = None) -> Pattern:
    return Pattern(regex=re.compile(regex, re.IGNORECASE), label=label, days_group=days_group)


# --------------------------------------------------------------------------
# Shared: boilerplate disclaimers that cancel a clause at any distance
# --------------------------------------------------------------------------
#
# The negation gate only looks 8 words back, which is right for "shall not
# request unlimited revisions" but too short for the drafting habit of
# disclaiming a whole sentence up front:
#
#   "Nothing in this Agreement shall be construed as a pay-when-paid
#    arrangement."
#
# "Nothing" sits 9 tokens away, so the window misses it and the clause is
# reported as a false positive. This phrase is narrow on purpose: a blanket
# sentence-level "nothing" check would also swallow
#
#   "Nothing in this Agreement limits Client's right to terminate at will."
#
# which is a REAL risk. So the pattern requires the "construed/deemed as"
# tail that marks a pure disclaimer.
DISCLAIMER_NEGATION = (
    re.compile(
        r"\bnothing\s+(?:in|herein|in\s+this\s+agreement|in\s+this\s+section)\b"
        r".{0,80}?\b(?:construed|deemed|interpreted|considered)\b",
        re.I,
    ),
    re.compile(r"\b(?:is|shall\s+be)\s+not\s+(?:intended\s+to|meant\s+to)\s+(?:create|constitute)\b", re.I),
)


# --------------------------------------------------------------------------
# R01 - Payment terms longer than 30 days
# --------------------------------------------------------------------------
#
# Trap this rule must survive:
#   "Contractor may suspend work if any undisputed invoice remains unpaid for
#    more than thirty (30) days after written notice to Client."
# That is a cure period / right to stop work (a *good* clause), not a payment
# term. Two independent guards stop it: min_value=31 rejects "30", and
# context_none rejects the "after written notice" construction in case the
# number were 45 or 60.

R01 = Rule(
    id="R01",
    name="Long payment terms",
    severity=7,
    why=(
        "Payment terms longer than 30 days mean you are financing the client's "
        "business for free. Net 60 means you wait two months for money you "
        "already earned, and every extra day is another day the client can "
        "change their mind about paying."
    ),
    fix=(
        "Ask for Net 15 or Net 30. For anything larger, split the fee into "
        "milestones with 30% up front."
    ),
    patterns=(
        _p(r"\bnet[-\s]?(?P<days>\d{2,3})\b", "net terms", "days"),
        # "Net sixty (60)" - legal templates spell the number out and then
        # put the numeral in brackets. The plain net pattern cannot see this.
        _p(r"\bnet[-\s]+[a-z][a-z\s-]{0,20}\(\s*(?P<days>\d{2,3})\s*\)",
           "net word plus numeral", "days"),
        _p(r"\(\s*(?P<days>\d{2,3})\s*\)\s*days?\b", "word plus numeral days", "days"),
        _p(r"\bwithin\s+(?P<days>\d{2,3})\s+days?\b", "within N days", "days"),
        _p(r"\b(?:payment|terms)\s+(?:period|terms)?\s*(?:of|within)\s+(?P<days>\d{2,3})\s+days?\b",
           "payment period of N days", "days"),
        # "45 days from receipt of invoice" - no "within", no brackets.
        _p(r"\b(?P<days>\d{2,3})\s*days?\s+(?:from|after|following)\s+"
           r"(?:the\s+)?(?:date\s+of\s+)?(?:invoice|receipt|delivery)",
           "N days from invoice", "days"),
    ),
    context_any=(
        re.compile(r"\binvoice", re.I),
        re.compile(r"\bpayment", re.I),
        re.compile(r"\bpay\b", re.I),
        re.compile(r"\bremit", re.I),
        re.compile(r"\bnet[-\s]?\d", re.I),
    ),
    context_none=(
        re.compile(r"(?:cure|curing|curative|grace|notice)\s+period", re.I),
        re.compile(r"days?\s+after\s+(?:written\s+)?notice", re.I),
        re.compile(r"days?\s+(?:prior|before)\s+(?:to\s+)?(?:written\s+)?notice", re.I),
    ),
    min_value=31,
)


# --------------------------------------------------------------------------
# R02 - Payment conditioned on the client's acceptance / satisfaction
# --------------------------------------------------------------------------
#
# Reinforcing negation handled here:
#   "Deliverables shall NOT be deemed accepted until Client issues written
#    acceptance."
# The "not" does not make the clause harmless - it is the trap. Without the
# exception below, the gate would suppress the strongest sentence in 2.3.
#
# Context guard: the hit must be about money or acceptance in the same sentence.
# "satisfied" alone is not enough - R05's revision clause ends with "until
# Client is satisfied", and an early version of this rule fired on it. Same for
# "sole discretion", which appears in the portfolio clause (4.4).

R02 = Rule(
    id="R02",
    name="Payment tied to acceptance",
    severity=10,
    why=(
        "This makes the date you get paid depend on the client deciding they "
        "are happy. 'Satisfied' has no standard attached to it, so there is no "
        "point at which the client is obligated to pay you."
    ),
    fix=(
        "Replace it with an objective test plus deemed acceptance: if the "
        "client does not raise specific written objections within 5 business "
        "days of delivery, the work is accepted and the invoice is due."
    ),
    patterns=(
        _p(r"\bupon\s+(?:the\s+)?(?:client'?s?\s+)?(?:final\s+|written\s+|formal\s+)?acceptance\b",
           "payment upon acceptance"),
        _p(r"\b(?:final|written|formal)\s+acceptance\b", "final/written acceptance"),
        _p(r"\bdeemed\s+accepted\b", "deemed accepted"),
        _p(r"\bwithhold(?:ing)?\s+(?:any\s+)?(?:payment|amount)", "withhold payment"),
        _p(r"\buntil\s+.{0,40}?\bsatisf(?:ied|actory)\b", "until satisfied"),
        _p(r"\bsubject\s+to\s+(?:the\s+)?(?:client'?s?\s+)?acceptance\b", "subject to acceptance"),
        _p(r"\bsole\s+discretion\b", "client sole discretion"),
        # "payment is due until ... acceptance" / "paid until ... acceptance"
        # Catches the wordings where the acceptance gate is the whole point.
        _p(r"\b(?:pay|paid|payment|payable)\b.{0,40}?\buntil\b.{0,40}?\baccept",
           "payment gated on acceptance"),
    ),
    # Must be about money or acceptance, not just "satisfied". Without this,
    # R05's revision clause ("... until Client is satisfied ...") trips R02,
    # which is exactly the cross-rule false positive we saw on the first run.
    context_any=(
        re.compile(r"\baccept", re.I),
        re.compile(r"\bpayment", re.I),
        re.compile(r"\bpay\b", re.I),
        re.compile(r"\binvoice", re.I),
        re.compile(r"\bremit", re.I),
    ),
    negation_exceptions=(
        # "shall not be deemed accepted until ..." is the risk, not a cure.
        re.compile(r"not\s+be\s+deemed\s+accepted", re.I),
        re.compile(r"not\s+deemed\s+accepted", re.I),
        # A negation attached to PAYMENT reinforces the risk: the client is
        # telling you in advance that you will not be paid until they say so.
        re.compile(r"not\s+(?:be\s+)?(?:paid|payable)\s+until", re.I),
        re.compile(r"no\s+obligation\s+to\s+pay\s+until", re.I),
        re.compile(r"no\s+payment\s+(?:shall\s+)?(?:be\s+)?(?:due|made)\s+until", re.I),
        re.compile(r"payment\s+shall\s+not\s+(?:be\s+)?(?:due|made)\s+until", re.I),
    ),
)


# --------------------------------------------------------------------------
# R03 - Pay-when-paid (client only pays you once the end client pays them)
# --------------------------------------------------------------------------
#
# Target (fake contract 2.4):
#   "... Client's payment obligations hereunder are funded by Client's end
#    client, and Client shall pay Contractor within fifteen (15) days after
#    Client's receipt of payment from the end client ..."
#
# R01 does NOT fire here, and that is correct: 15 days is a fine term. The
# clause is fatal for a different reason - the clock only starts when money
# reaches the client.
#
# Trap this rule must survive:
#   "Nothing in this Section shall be construed as pay-when-paid."
#   "Contractor's fees are not subject to Client's receipt of payment from the
#    end client."
# Both are generic-negation cases; the gate handles them.
#
# Collision watch: R01 owns "N days". If a clause says "pay within 60 days
# after receipt from the end client", BOTH fire - correctly. They are two
# separate problems and the user should hear both.

R03 = Rule(
    id="R03",
    name="Pay-when-paid",
    severity=10,
    why=(
        "Your invoice only gets paid after the client gets paid by somebody "
        "else. That somebody is invisible to you and outside your control: if "
        "they pay late, dispute the work, or never pay at all, you are still "
        "paid nothing - even though you did the work."
    ),
    fix=(
        "Delete the pass-through language. If the client insists (for example "
        "a subcontract), cap it: 'payment is due within 45 days of invoice, "
        "whether or not Client has been paid by its client.'"
    ),
    patterns=(
        _p(r"\bpay[-\s]when[-\s]paid\b", "pay when paid"),
        _p(r"\bpay[-\s]if[-\s]paid\b", "pay if paid"),
        # "after Client's receipt of payment from the end client"
        _p(r"\b(?:upon|after|following|on)\s+(?:the\s+)?(?:client'?s?\s+)?receipt\s+of\s+payment\s+from\b",
           "after receipt of payment from"),
        _p(r"\breceipt\s+of\s+payment\s+from\s+(?:the\s+)?(?:end\s+client|owner|prime\s+contractor|general\s+contractor)\b",
           "receipt of payment from end client"),
        # "Client's payment obligations are funded by Client's end client"
        _p(r"\bfunded\s+by\s+.{0,60}?\bend[-\s]client\b", "funded by end client"),
        _p(r"\bsubject\s+to\s+(?:the\s+)?(?:client'?s?\s+)?(?:prior\s+)?receipt\s+of\s+payment\b",
           "subject to receipt of payment"),
        _p(r"\bend[-\s]client\b", "end client"),
        _p(r"\b(?:prime|general)\s+contractor\s+(?:has\s+)?(?:paid|pays)\b", "prime contractor paid"),
    ),
    # Must be about money. "end client" alone is not a red flag - a designer
    # may legitimately be told which end brand the work is for.
    context_any=(
        re.compile(r"\bpay", re.I),
        re.compile(r"\bpayment", re.I),
        re.compile(r"\binvoice", re.I),
        re.compile(r"\bfee", re.I),
        re.compile(r"\bfunded\b", re.I),
        re.compile(r"\bremit", re.I),
    ),
    # A clause that says "regardless of whether the end client pays" is the
    # CURE for this problem, not the problem. Let R01 handle the timing.
    context_none=(
        *DISCLAIMER_NEGATION,
        re.compile(r"(?:whether\s+or\s+not|regardless\s+of\s+whether)\s+.{0,40}?\b(?:end[-\s]client|paid)\b", re.I),
        re.compile(r"\bnot\s+subject\s+to\b", re.I),
    ),
)


# --------------------------------------------------------------------------
# R04 - Unilateral set-off / deduction
# --------------------------------------------------------------------------
#
# Target (fake contract 2.5):
#   "Client may set off against any amount owed to Contractor any amount that
#    Client believes in good faith it is owed by Contractor, including amounts
#    relating to delays, third-party claims, chargebacks, or reputational harm."
#
# DELIBERATE OMISSION - "withhold"
# The keyword list for R04 says `withhold`, and the obvious move is to add it.
# That would be a bug. Section 2.3 already says "Client may withhold payment
# until Client is satisfied", which is R02's acceptance trap. Adding a bare
# "withhold" here would report 2.3 twice under two different headings, and the
# user would think there are two problems. "Withholding payment pending
# acceptance" and "deducting money from an amount already owed" are different
# legal moves. So R04 only takes `withhold` when the object is money already
# owed (`withhold any amount owed`), never `withhold payment until ...`.

R04 = Rule(
    id="R04",
    name="Unilateral set-off",
    severity=5,
    why=(
        "This lets the client decide on their own that they are owed something "
        "and simply deduct it from your invoice. No agreement from you, no "
        "proof, no court. Your invoice total becomes whatever the client "
        "believes it should be."
    ),
    fix=(
        "Delete the unilateral right, or limit it to amounts that are both "
        "undisputed and already past due under a written agreement - and "
        "require written notice before any deduction."
    ),
    patterns=(
        _p(r"\bset[-\s]?off\b", "set-off"),
        _p(r"\boffset\b", "offset"),
        _p(r"\bright\s+to\s+(?:deduct|set[-\s]?off|offset)", "right to deduct"),
        _p(r"\bdeduct\b.{0,60}?\bfrom\b", "deduct from"),
        _p(r"\bcharge[-\s]?backs?\b", "chargeback"),
        # Only money already owed - never "withhold payment until acceptance".
        _p(r"\bwithhold\b.{0,40}?\b(?:amount|sum|portion)s?\s+(?:owed|due|payable)\b",
           "withhold amounts owed"),
    ),
    context_any=(
        re.compile(r"\bamount", re.I),
        re.compile(r"\binvoice", re.I),
        re.compile(r"\bpayment", re.I),
        re.compile(r"\bpay\b", re.I),
        re.compile(r"\bfee", re.I),
        re.compile(r"\bowed\b", re.I),
        re.compile(r"\bcompensation", re.I),
        re.compile(r"\bcharge", re.I),
    ),
    context_none=(
        # Direction: a right that belongs to the CONTRACTOR is a protection,
        # not a trap. Only the client's unilateral right is a red flag.
        re.compile(r"\bcontractor\s+(?:may|shall\s+be\s+entitled\s+to|is\s+entitled\s+to)\s+"
                   r"(?:set[-\s]?off|offset|deduct)", re.I),
        # "set off" inside a fire-safety or office-lease boilerplate is rare in
        # freelancer contracts, but "tax offset" / "offset printing" are not.
        re.compile(r"\boffset\s+print", re.I),
        re.compile(r"\btax(?:es)?\s+offset", re.I),
    ),
)


# --------------------------------------------------------------------------
# R05 - Unlimited revisions
# --------------------------------------------------------------------------
#
# Trap this rule must survive:
#   "Notwithstanding Section 3.1, Client shall NOT request unlimited revisions
#    to Deliverables that have been formally approved in a signed change
#    order."
# ("not" sits 3 tokens before "unlimited revisions" -> suppressed.)
#
# Context guard: "until Client is satisfied" also appears in R02's acceptance
# clause. Requiring revision vocabulary in the same sentence keeps R05 off it.

R05 = Rule(
    id="R05",
    name="Unlimited revisions",
    severity=10,
    why=(
        "There is no ceiling on how many times you must redo the work. As long "
        "as the client is not satisfied, the project never ends and your "
        "effective hourly rate falls toward zero."
    ),
    fix=(
        "Fix the number of rounds in writing (for example, two rounds "
        "included), and bill anything beyond that at an hourly or per-round "
        "rate."
    ),
    patterns=(
        _p(r"\bunlimited\s+(?:rounds?\s+of\s+)?(?:revisions?|changes?|iterations?)\b",
           "unlimited revisions"),
        _p(r"\b(?:revisions?|rounds?)\s+until\s+.{0,60}?\bsatisf", "revisions until satisfied"),
        _p(r"\buntil\s+.{0,40}?\bsatisf(?:ied|actory)\b", "until satisfied"),
        _p(r"\bas\s+many\s+(?:revisions?|times|rounds?)\s+as\s+(?:necessary|required|needed)",
           "as many times as necessary"),
        _p(r"\brevisions?\s+(?:in\s+perpetuity|indefinitely|without\s+limit)", "revisions indefinitely"),
    ),
    context_any=(
        re.compile(r"\brevis", re.I),
        re.compile(r"\brounds?\b", re.I),
        re.compile(r"\biterations?\b", re.I),
        re.compile(r"\bchanges?\b", re.I),
    ),
    context_none=DISCLAIMER_NEGATION,
)


# --------------------------------------------------------------------------
# R06 - Open-ended scope
# --------------------------------------------------------------------------
#
# Target (fake contract 1.1):
#   "... including but not limited to logo design, ... and such other services
#    as Client may reasonably request from time to time."
#
# THE BIG FALSE-POSITIVE RISK IN THIS RULE
# "including but not limited to" appears in nearly every commercial contract,
# most often inside the indemnity clause ("any and all claims, including but
# not limited to..."). Reporting that as "open scope" is wrong - it widens
# liability, which is R11's job, not scope creep. So this rule needs BOTH:
#   1. scope vocabulary in the sentence (services / deliverables / work / SOW)
#   2. no liability vocabulary in the sentence (indemnify / hold harmless)
#
# Trap this rule must survive:
#   "Section 1.1 lists the Deliverables. This Agreement does not include any
#    other services except by written change order."
# Negation + "other services" is close; the gate suppresses it.

R06 = Rule(
    id="R06",
    name="Open-ended scope",
    severity=5,
    why=(
        "The scope has no edge. 'Such other services as Client may request' "
        "means the client decides how much work the fixed price buys. You "
        "quoted for a logo; you can end up delivering a brand system."
    ),
    fix=(
        "Make the scope a closed list in the SOW. Add: 'any work outside this "
        "SOW requires a signed change order and additional fees.' Delete "
        "'including but not limited to' and 'from time to time'."
    ),
    patterns=(
        _p(r"\bincluding\s+(?:but\s+)?not\s+limited\s+to\b", "including but not limited to"),
        _p(r"\bincluding\s+without\s+limitation\b", "including without limitation"),
        _p(r"\bsuch\s+other\s+(?:services|work|duties|tasks|items)\b", "such other services"),
        _p(r"\b(?:and\s+)?(?:any\s+)?other\s+(?:duties|tasks)\s+as\s+(?:may\s+be\s+)?assigned\b",
           "other duties as assigned"),
        _p(r"\bany\s+other\s+(?:work|services)\b", "any other work"),
        _p(r"\bas\s+(?:may\s+be\s+)?(?:reasonably\s+)?requested\s+(?:by\s+Client\s+)?from\s+time\s+to\s+time\b",
           "as requested from time to time"),
    ),
    context_any=(
        re.compile(r"\bservices?\b", re.I),
        re.compile(r"\bdeliverables?\b", re.I),
        re.compile(r"\bwork\b", re.I),
        re.compile(r"\bscope\b", re.I),
        re.compile(r"\bsow\b", re.I),
        re.compile(r"\bstatement\s+of\s+work\b", re.I),
        re.compile(r"\bduties\b", re.I),
        re.compile(r"\btasks?\b", re.I),
        re.compile(r"\bengagement\b", re.I),
    ),
    # Liability widening is R11, not scope creep. Keep out.
    context_none=(
        *DISCLAIMER_NEGATION,
        re.compile(r"\bindemnif", re.I),
        re.compile(r"\bhold\s+harmless\b", re.I),
        re.compile(r"\bdefend\b", re.I),
        re.compile(r"\bliabilit", re.I),
        re.compile(r"\bdamages\b", re.I),
        re.compile(r"\bclaims\b.*\bexpenses\b", re.I),
    ),
)


# --------------------------------------------------------------------------
# R07 - Free extra work / unpaid warranty tail
# --------------------------------------------------------------------------
#
# Target (fake contract 1.2):
#   "Client may request additional work at any time ... and Contractor shall
#    perform such additional work at no additional cost where Client determines
#    in good faith that the work falls within the general spirit of the
#    engagement."
#
# DIRECTION MATTERS
# "at no additional cost" is only a red flag when it is the CONTRACTOR who
# works for free. "Client shall supply brand assets at no additional cost to
# Contractor" is a clause in your favour. So:
#   - require Contractor to be in the sentence
#   - veto "at no additional cost to Contractor"

R07 = Rule(
    id="R07",
    name="Free extra work",
    severity=5,
    why=(
        "You agree to do extra work for the same money, and the client gets to "
        "decide what counts as 'extra'. A fixed fee with an open door next to "
        "it is not a fixed fee."
    ),
    fix=(
        "Strike 'at no additional cost'. New requests become a written change "
        "order with its own price. If you want to be generous, cap it: 'one "
        "round of minor tweaks per milestone, at no charge.'"
    ),
    patterns=(
        _p(r"\bat\s+no\s+(?:additional|extra|further)\s+(?:cost|charge|fee|compensation|expense)s?\b",
           "at no additional cost"),
        _p(r"\bat\s+no\s+cost\b", "at no cost"),
        _p(r"\bat\s+no\s+charge\b", "at no charge"),
        _p(r"\bfree\s+of\s+(?:charge|cost)\b", "free of charge"),
        _p(r"\bwithout\s+(?:additional|further|any)\s+compensation\b", "without additional compensation"),
        _p(r"\bwithout\s+(?:additional|extra)\s+(?:cost|fee|charge)s?\b", "without additional cost"),
        _p(r"\bbug\s*fix(?:es)?\s+for\s+(?:\w+\s+){0,3}(?:months?|days?|years?)\b", "bug fixes for N months"),
        _p(r"\b(?:free|complimentary|no[-\s]cost)\s+(?:ongoing\s+)?(?:support|maintenance)\s+for\b",
           "free support for"),
        _p(r"\bat\s+(?:contractor'?s?|your)\s+(?:sole\s+)?(?:expense|cost)\b", "at contractor's expense"),
        _p(r"\bat\s+its\s+own\s+(?:expense|cost)\b", "at its own expense"),
    ),
    context_any=(
        re.compile(r"\bcontractor\b", re.I),
        re.compile(r"\bprovider\b", re.I),
        re.compile(r"\bfreelancer\b", re.I),
        # Passive drafting often drops the actor: "such work shall be performed
        # at no additional charge". The work verb is the only anchor left.
        re.compile(r"\bperform", re.I),
        re.compile(r"\brender", re.I),
        re.compile(r"\bdeliver", re.I),
        re.compile(r"\bservices?\b", re.I),
        re.compile(r"\bwork\b", re.I),
    ),
    # Someone else paying nothing is not your problem.
    context_none=(
        re.compile(r"no\s+(?:additional|extra|further)\s+(?:cost|charge|fee)s?\s+to\s+(?:the\s+)?contractor\b", re.I),
        re.compile(r"at\s+client'?s?\s+(?:sole\s+)?(?:expense|cost)\b", re.I),
    ),
)


# --------------------------------------------------------------------------
# R08 - Assignment of everything, including work the client did not buy
# --------------------------------------------------------------------------
#
# Target (fake contract 4.1 + 4.2):
#   4.1 "... irrevocably assigns to Client all right, title and interest in and
#        to the Deliverables and all materials created in connection with the
#        Services, including all concepts, drafts, sketches, and unused
#        directions, throughout the world and in perpetuity."
#   4.2 "All Deliverables shall be deemed 'work made for hire' ..."
#
# THE LINE THIS RULE MUST NOT CROSS
# Assigning the copyright of the FINAL deliverable to the client is normal,
# expected, and often exactly what the freelancer wants to sell:
#
#   "Contractor assigns all right, title and interest in the final Deliverables
#    to Client upon receipt of full payment."
#
# That sentence is a GOOD clause - it is literally the fix this rule
# recommends. Flagging it would put a red card on almost every real contract
# and destroy trust on first use. So R08 does NOT key on "assignment" as such.
#
# What it keys on is the SWEEP - taking more than the client paid for:
#   - unused / rejected / exploratory directions  (the expensive part)
#   - "all materials created in connection with the Services"  (working files,
#     templates, tooling - broader than deliverables)
#   - work made for hire  (used to deny authorship outright)
#
# Keyword-list note - two deliberate omissions from docs/01:
#   `assign all right, title and interest`  and  `in perpetuity` / `worldwide`
# are NOT patterns here. "Contractor hereby assigns all right, title and
# interest in the Deliverables to Client, in perpetuity, throughout the world"
# is the single most common IP clause in existence and it is NORMAL: the client
# bought the deliverable, so they get the copyright. Firing on it would put a
# FATAL card on nearly every real contract. The sweep patterns below catch the
# part that actually costs the freelancer money.
#
# Trap this rule must survive:
#   "Contractor retains ownership of all preliminary concepts and unused
#    directions."
#   "Nothing in this Section transfers ownership of Contractor's pre-existing
#    tools or templates."
#   "Contractor grants Client a perpetual, worldwide, non-exclusive licence to
#    use the Deliverables."
# None of these may be reported - see context_none.

R08 = Rule(
    id="R08",
    name="Full IP assignment (including unused work)",
    severity=10,
    why=(
        "This transfers ownership of everything you produce - not just what "
        "the client bought, but also the concepts they rejected and the "
        "working files behind them. Those unused directions are your method "
        "and your next pitch to someone else."
    ),
    fix=(
        "Limit the transfer to the final deliverables, and make it effective "
        "only once you have been paid in full. Keep ownership of unused "
        "concepts, drafts, pre-existing tools and templates, and grant the "
        "client a licence to the rest."
    ),
    patterns=(
        # Ordered: the first pattern to hit wins the card for a given clause,
        # so the most expensive harm is the one quoted.
        _p(r"\bunused\s+(?:concepts?|directions?|drafts?|sketches?|designs?|materials?|iterations?|options?)\b",
           "unused concepts assigned"),
        _p(r"\b(?:concepts?|drafts?|sketches?|directions?|iterations?)\b.{0,60}?\bunused\b",
           "unused concepts assigned"),
        _p(r"\ball\s+(?:materials?|work\s+product|documents?|files?|assets?)\s+"
           r"(?:created|developed|prepared|produced)\b",
           "all materials created"),
        _p(r"\bwork\s+(?:made\s+)?for\s+hire\b", "work made for hire"),
    ),
    context_any=(
        re.compile(r"\bdeliverables?\b", re.I),
        re.compile(r"\bmaterials?\b", re.I),
        re.compile(r"\bconcepts?\b", re.I),
        re.compile(r"\bdrafts?\b", re.I),
        re.compile(r"\bsketches?\b", re.I),
        re.compile(r"\bdesigns?\b", re.I),
        re.compile(r"\brights?\b", re.I),
        re.compile(r"\bownership\b", re.I),
        re.compile(r"\bintellectual\s+property\b", re.I),
        re.compile(r"\bcopyright\b", re.I),
        re.compile(r"\bwork\b", re.I),
    ),
    context_none=(
        # The freelancer keeping their own stuff is the cure, not the disease.
        re.compile(r"\bcontractor\s+(?:hereby\s+)?(?:retains?|reserves?)\b", re.I),
        re.compile(r"\b(?:retains?|reserves?)\s+(?:all\s+)?(?:ownership|right|title|interest)", re.I),
        re.compile(r"\bretains?\s+(?:ownership|all\s+rights?)\b", re.I),
        # A licence is not an assignment.
        re.compile(r"\bnon[-\s]exclusive\s+licen[cs]e\b", re.I),
        re.compile(r"\bdoes\s+not\s+(?:transfer|assign|convey)\b", re.I),
        # Handing material back to the freelancer is a cure, not a grab.
        re.compile(r"\breturn\b.{0,40}?\bto\s+(?:the\s+)?contractor\b", re.I),
        *DISCLAIMER_NEGATION,
    ),
)


# --------------------------------------------------------------------------
# R09 - Moral rights waiver / portfolio ban
# --------------------------------------------------------------------------
#
# Target (fake contract 4.3 + 4.4):
#   4.3 "Contractor waives, and agrees not to assert, any moral rights or
#        rights of attribution in the Deliverables."
#   4.4 "Contractor shall not display the Deliverables ... in any portfolio,
#        case study, website, or social media post without Client's prior
#        written consent, which Client may withhold in its sole discretion."
#
# TWO DIFFERENT TRAPS, ONE RULE - and that is fine, because both are "you lose
# the right to be credited / to show your work". They will show as two cards
# (4.3 and 4.4), which is correct: two separate sentences to strike.
#
# THE FALSE POSITIVE TO AVOID
# "Contractor may display the Deliverables in its portfolio after publication."
# is the GOOD clause. It contains "portfolio" and nothing else suspicious, so
# no pattern matches - the rule needs the BAN ("shall not display") or the
# PERMISSION GATE ("without prior written consent"), never the bare noun.
#
# Second false positive to avoid: "Contractor may not assign this Agreement
# without Client's prior written consent" (12.2) contains the consent phrase.
# The context_any fence (portfolio / display / moral rights vocabulary) keeps
# R09 off it.

R09 = Rule(
    id="R09",
    name="Moral rights waiver / portfolio ban",
    severity=5,
    why=(
        "You lose the right to be credited, and the right to show the work. "
        "For a designer or developer the portfolio is the sales channel - "
        "one year of your best work can become invisible, which weakens your "
        "pricing on every future job. A consent gate that the client can "
        "refuse at will is the same as a ban."
    ),
    fix=(
        "Keep a non-exclusive right to display the work in your portfolio and "
        "on your own site, optionally after a 3-6 month delay and with "
        "confidential details removed. Strike the moral rights waiver, or "
        "limit it to what the client actually needs."
    ),
    patterns=(
        _p(r"\b(?:waive[sd]?|waiving)\b.{0,80}?"
           r"\b(?:moral\s+rights?|rights?\s+of\s+attribution|right\s+of\s+integrity)\b",
           "moral rights waiver"),
        _p(r"\bnot\s+to\s+assert\b.{0,40}?\b(?:moral\s+rights?|attribution)\b",
           "agrees not to assert moral rights"),
        # A ban is a NEGATION ("shall not display") - so the match deliberately
        # starts at "shall"/"may", which puts the "not" INSIDE the match and
        # keeps the negation gate from reading the ban as a disclaimer.
        _p(r"\b(?:shall|may|will|must)\s+not\s+"
           r"(?:display|showcase|include|publish|show|use|post|feature)\b"
           r".{0,90}?\b(?:portfolio|case\s+stud(?:y|ies)?|website|social\s+media|"
           r"behance|dribbble)\b",
           "portfolio ban"),
        # Same ban, other wording: "shall not appear in any portfolio without
        # Client's consent" - the article sits between the verb and the noun,
        # so the pattern above cannot chain them.
        _p(r"\b(?:portfolio|case\s+stud(?:y|ies)|social\s+media)\b.{0,80}?"
           r"\bwithout\s+(?:the\s+)?client'?s?\s+(?:prior\s+)?(?:written\s+)?consent\b",
           "portfolio needs consent"),
    ),
    context_any=(
        re.compile(r"\bmoral\s+rights?\b", re.I),
        re.compile(r"\battribution\b", re.I),
        re.compile(r"\bportfolio\b", re.I),
        re.compile(r"\bcase\s+stud", re.I),
        re.compile(r"\bdisplay\b", re.I),
        re.compile(r"\bshowcase\b", re.I),
        re.compile(r"\bsocial\s+media\b", re.I),
        re.compile(r"\bcredit\b", re.I),
    ),
    negation_exceptions=(
        # "without Client's prior written consent" does not cancel the clause -
        # it is the moat around it: "you may not show your work unless I agree".
        # The gate sees "without" four words past the match and would otherwise
        # drop the single most common form of portfolio ban.
        re.compile(r"\bwithout\s+(?:the\s+)?client'?s?\s+(?:prior\s+)?(?:written\s+)?consent\b", re.I),
    ),
    context_none=(
        # Permission granted TO the freelancer is the cure. Without this,
        # "Contractor may display the work in its portfolio without Client's
        # prior written consent" would be read as the ban it is the opposite of.
        # Note the deliberate absence of a "portfolio ... prior written consent"
        # pattern: it cannot tell "with consent" (a licence) from "without"
        # (a ban), and firing on a licence would be a false positive.
        re.compile(r"\bcontractor\s+(?:may|is\s+entitled\s+to|shall\s+be\s+entitled\s+to|"
                   r"retains?\s+(?:the\s+)?right\s+to)\s+"
                   r"(?:display|showcase|include|use|post|feature)\b", re.I),
        *DISCLAIMER_NEGATION,
    ),
)


# --------------------------------------------------------------------------
# R10 - Sublicence / resale / AI training
# --------------------------------------------------------------------------
#
# Target (fake contract 4.5):
#   "Client may modify and adapt the Deliverables, create derivative works
#    from them, sublicense and resell them, and use them to train, fine-tune,
#    or otherwise develop machine learning and generative artificial
#    intelligence models."
#
# WHY "create derivative works" ALONE IS NOT ENOUGH
# A client adapting the logo they bought is normal. The harm appears when the
# same sentence also says resell / sublicense / train - i.e. the client turns
# your work into a product or into training data. That is why docs/01 marks
# this rule as type B (needs context): the rule requires exploitation
# vocabulary in the same sentence.
#
# WHY AI IS CALLED OUT SEPARATELY
# "train ... machine learning models" is the 2024+ failure mode: once your work
# is in a training set, your style can be reproduced forever and you cannot
# trace it. It deserves its own pattern rather than hiding inside "sublicense".
#
# Direction traps (must NOT fire):
#   "Contractor may sublicense its pre-existing tools to other clients."
#   "Contractor shall not use Client Data to train AI models."
#   "Client may not resell the Deliverables."

R10 = Rule(
    id="R10",
    name="Resale / sublicence / AI training rights",
    severity=5,
    why=(
        "The client is not just allowed to use the work - they are allowed to "
        "sell it on, license it to others, or feed it into an AI model. "
        "Resale means your work competes with you. AI training means your "
        "style can be reproduced forever, with no way for you to trace it."
    ),
    fix=(
        "Limit use to the client's own business. Add: 'Client may not "
        "sublicense, resell, or distribute the Deliverables as a product, "
        "template, or stock asset, and may not use them to train, fine-tune, "
        "or evaluate machine learning or generative AI models.'"
    ),
    patterns=(
        _p(r"\btrain\b.{0,60}?\b(?:ai\b|a\.i\.|artificial\s+intelligence|machine\s+learning|"
           r"generative|neural|models?\b)",
           "train AI models"),
        _p(r"\b(?:machine\s+learning|artificial\s+intelligence|generative\s+ai|ai\s+models?|"
           r"large\s+language\s+models?)\b.{0,60}?\b(?:train|training|fine[-\s]?tun)",
           "AI training"),
        _p(r"\bfine[-\s]?tun\w*\b.{0,50}?\b(?:model|ai)\b", "fine-tune models"),
        _p(r"\bsub[-\s]?licen[cs]\w*", "sublicense"),
        _p(r"\bresell\b|\bresale\b|\breselling\b", "resell"),
        _p(r"\bcreate\s+(?:derivative|derived)\s+works?\b", "derivative works"),
    ),
    context_any=(
        re.compile(r"\bsub[-\s]?licen", re.I),
        re.compile(r"\bresell|\bresale|\breselling", re.I),
        re.compile(r"\bdistribut", re.I),
        re.compile(r"\btrain", re.I),
        re.compile(r"\bfine[-\s]?tun", re.I),
        re.compile(r"\bmachine\s+learning\b", re.I),
        re.compile(r"\bartificial\s+intelligence\b", re.I),
        re.compile(r"\bgenerative\b", re.I),
        re.compile(r"\bdata\s*set", re.I),
        re.compile(r"\bmodel", re.I),
    ),
    context_none=(
        # The freelancer's own right to reuse their tools is not a trap.
        re.compile(r"\bcontractor\s+(?:may|shall\s+be\s+entitled\s+to|is\s+entitled\s+to)\s+"
                   r"(?:sub[-\s]?licen|resell)", re.I),
        # A restriction ON the contractor protects the client's data; it is not
        # a clause that takes your rights away.
        re.compile(r"\bcontractor\s+shall\s+not\s+(?:use|train|feed)", re.I),
        re.compile(r"\bpre[-\s]existing\b", re.I),
        *DISCLAIMER_NEGATION,
    ),
)


# --------------------------------------------------------------------------
# R11 - Uncapped indemnity
# --------------------------------------------------------------------------
#
# Target (fake contract 6.1):
#   "Contractor shall indemnify, defend and hold harmless Client and its
#    officers, directors, employees, and affiliates from and against any and
#    all claims, losses, damages, liabilities, costs and expenses, including
#    reasonable attorneys' fees, arising out of or relating to the Services,
#    the Deliverables, or Contractor's performance under this Agreement."
#
# WHY THE PATTERNS ARE ONLY THE VERB
# docs/01 lists `any and all claims`, `including reasonable attorneys' fees`
# and `third-party claims` as R11 keywords. Using any of them as a PATTERN
# would be a false-positive machine, because those exact phrases also appear in
# clauses that have nothing to do with indemnity:
#
#   11.3 "The prevailing party ... shall be entitled to recover its reasonable
#         attorneys' fees and costs."                        <- R17, not R11
#   11.2 "Any dispute arising out of or relating to this Agreement ..."
#                                                            <- arbitration
#
# So `arising out of or relating to` and `attorneys' fees` live in
# context_any as STRENGTHENERS. They can only amplify a hit that the indemnity
# verb already made; they can never create one. Section 11.2 and 11.3 stay
# silent, and the two-card overlap with R06 is avoided at the root.
#
# THE LINE THIS RULE MUST NOT CROSS
# A NARROW, FAULT-SCOPED indemnity is normal and appears in almost every
# contract a freelancer signs:
#
#   "Contractor shall indemnify Client against third-party claims that the
#    Deliverables infringe a third party's IP rights."
#
#   "Each Party shall indemnify the other against third-party claims arising
#    from its own breach."
#
# Neither is a fatal trap - the first is limited to one defined risk, the
# second is mutual. Both are excluded via context_none. What makes 6.1 fatal is
# that it is broad (`any and all`), fault-free (`arising out of or relating to
# the Services` - no negligence required) and one-way.

R11 = Rule(
    id="R11",
    name="Uncapped one-way indemnity",
    severity=10,
    why=(
        "Indemnity means: if the client is sued, you pay and you hire the "
        "lawyers. This one has no ceiling and does not require you to have "
        "done anything wrong - it triggers on anything 'relating to' the "
        "services. A $5,000 project can turn into a $500,000 claim, and your "
        "fee is irrelevant to the size of the loss."
    ),
    fix=(
        "Limit it three ways: only your own gross negligence or willful "
        "misconduct; only third-party IP infringement caused by your work; "
        "and subject to the same liability cap as the rest of the agreement. "
        "Make it mutual, and exclude indirect and consequential losses."
    ),
    patterns=(
        # Longest form first: it is the phrase the user should see quoted.
        _p(r"\bindemnif\w*\s*,?\s*defend\s*,?\s*and\s+hold\s+harmless\b",
           "indemnify, defend and hold harmless"),
        _p(r"\bindemnif\w*\s+and\s+hold\s+harmless\b", "indemnify and hold harmless"),
        _p(r"\bhold\s+harmless\b", "hold harmless"),
        _p(r"\bindemnif(?:y|ies|ied|ication)\b", "indemnify"),
    ),
    context_any=(
        # The clause must be sweeping, not surgical. Each of these is a
        # broadening signal - and none of them is allowed to be a pattern.
        re.compile(r"\bany\s+and\s+all\b", re.I),
        re.compile(r"\bfrom\s+and\s+against\b", re.I),
        re.compile(r"\barising\s+out\s+of\s+or\s+relating\s+to\b", re.I),
        re.compile(r"\battorneys?'?\s+fees\b", re.I),
        re.compile(r"\ball\s+claims\b", re.I),
        re.compile(r"\bthird[-\s]party\s+claims\b", re.I),
        re.compile(r"\bincluding\s+but\s+not\s+limited\s+to\b", re.I),
        re.compile(r"\bdefend\b", re.I),
    ),
    context_none=(
        # Fault-scoped: the freelancer only pays for its own wrongdoing. Normal.
        re.compile(r"\bgross\s+negligence\b", re.I),
        re.compile(r"\bwillful\s+misconduct\b", re.I),
        re.compile(r"\bto\s+the\s+extent\s+caused\s+by\b", re.I),
        re.compile(r"\b(?:caused|arising)\s+solely\s+(?:by|from)\b", re.I),
        re.compile(r"\bits\s+own\s+(?:breach|negligence|acts|omissions|wrongdoing)\b", re.I),
        # A one-risk IP indemnity (infringement) is standard, not fatal.
        re.compile(r"\binfring", re.I),
        # Mutual indemnities are the negotiated, acceptable shape.
        re.compile(r"\beach\s+party\s+shall\s+indemnif", re.I),
        re.compile(r"\bmutual(?:ly)?\s+indemn", re.I),
        # Already capped elsewhere in the same sentence.
        re.compile(r"\bshall\s+not\s+exceed\b", re.I),
        re.compile(r"\bsubject\s+to\s+(?:the\s+)?(?:limitation|cap)", re.I),
        *DISCLAIMER_NEGATION,
    ),
    negation_exceptions=(
        # "without limitation as to amount" REINFORCES an indemnity; it removes
        # the one thing that would have made it safe.
        re.compile(r"\bwithout\s+limitation\s+as\s+to\b", re.I),
    ),
)


# --------------------------------------------------------------------------
# R12 - No ceiling on liability (downgraded for batch 1, see D-004)
# --------------------------------------------------------------------------
#
# Target (fake contract 6.2):
#   "No Cap. The obligations set forth in Section 6.1 apply without limitation
#    as to amount, duration, or number of claims."
#
# WHAT THIS RULE DELIBERATELY DOES NOT DO
# docs/01 defines R12 as type D - "no limitation of liability anywhere in the
# document" - which needs document-level counting and is postponed to batch 2.
# Batch 1 only reports the POSITIVE wording: a clause that says out loud there
# is no cap. A contract that is simply silent falls through, and the report
# must not pretend otherwise (D-004).
#
# THE TRAP IN THE KEYWORD LIST
# docs/01 lists `in no event shall` as an R12 keyword. That phrase is almost
# always the OPENING of a cap, not its absence:
#
#   "In no event shall either party's aggregate liability exceed the fees paid."
#
# Using it as a pattern would flag the single most protective sentence a
# freelancer can get. It is deliberately NOT a pattern here, and
# `shall not exceed` is in context_none for the same reason.

R12 = Rule(
    id="R12",
    name="Liability stated to be uncapped",
    severity=10,
    why=(
        "The contract says out loud that the obligation has no ceiling - no "
        "limit on the amount, how long it lasts, or how many claims can be "
        "brought. Whatever you earn on the project, the exposure is unbounded."
    ),
    fix=(
        "Add a mutual cap: each party's total liability shall not exceed the "
        "fees paid or payable under this Agreement. Exclude indirect, "
        "incidental and consequential damages on both sides."
    ),
    patterns=(
        _p(r"\bwithout\s+limitation\s+as\s+to\s+(?:the\s+)?"
           r"(?:amount|liability|duration|number\s+of\s+claims|time)\b",
           "without limitation as to amount"),
        # "no cap on Contractor's liability" - the possessive must be allowed
        # through, or the rule only works on the drafting style we imagined.
        _p(r"\bno\s+(?:cap|ceiling|limit)\s+(?:on|as\s+to)\s+"
           r"(?:(?:the|any|its|either\s+party's|\w+'s)\s+)?"
           r"(?:liability|damages|amount|exposure)\b",
           "no cap on liability"),
        _p(r"\bno\s+limitation\s+of\s+liability\b", "no limitation of liability"),
        _p(r"\bunlimited\s+liability\b", "unlimited liability"),
        _p(r"\bnot\s+subject\s+to\s+any\s+(?:limitation|cap)\b", "not subject to any cap"),
    ),
    context_any=(
        re.compile(r"\bliabilit", re.I),
        re.compile(r"\bobligations?\b", re.I),
        re.compile(r"\bclaims?\b", re.I),
        re.compile(r"\bdamages?\b", re.I),
        re.compile(r"\bamount\b", re.I),
        re.compile(r"\bindemnif", re.I),
    ),
    context_none=(
        # A cap that exists is the opposite of this rule.
        re.compile(r"\bshall\s+not\s+exceed\b", re.I),
        re.compile(r"\baggregate\s+liability\b", re.I),
        re.compile(r"\bliability\s+(?:is|shall\s+be)\s+limited\s+to\b", re.I),
        *DISCLAIMER_NEGATION,
    ),
    negation_exceptions=(
        # "no cap" / "without limitation" are the risk, not a disclaimer. The
        # gate would otherwise read every one of these patterns as negated.
        re.compile(r"\bno\s+(?:cap|ceiling|limit)\b", re.I),
        re.compile(r"\bno\s+limitation\s+of\s+liability\b", re.I),
        re.compile(r"\bwithout\s+limitation\s+as\s+to\b", re.I),
    ),
)


# --------------------------------------------------------------------------
# R13 - The client can walk away at any time
# --------------------------------------------------------------------------
#
# Target (fake contract 7.2):
#   "Client may terminate this Agreement or any SOW at any time, for any reason
#    or for no reason, upon five (5) days' written notice, without further
#    obligation or payment of any kind, including any fee for work in progress."
#
# THE DIRECTION PROBLEM AGAIN
# Termination-for-convenience is not automatically a trap. This is:
#
#   "Either party may terminate this Agreement for convenience on thirty (30)
#    days' written notice."
#
# Mutual, with notice - that is a normal, balanced clause, and the freelancer
# may well be the one who uses it. What makes 7.2 a serious trap is that the
# right is ONE-WAY and the exit is FREE ("without further obligation or payment
# of any kind"). So `either party` is in context_none, and the one-way subject
# is what the patterns key on.
#
# Note also 7.3 - "Contractor may terminate only in the event of Client's
# uncured material breach" - which is a restriction on the freelancer but not a
# trap for them. It is excluded both by the absence of "at any time" and by the
# `contractor may terminate` guard.

R13 = Rule(
    id="R13",
    name="Client may terminate at any time, without paying",
    severity=7,
    why=(
        "The client can stop the project at any moment for no reason, and the "
        "clause says they owe you nothing further - not even for work already "
        "in progress. You have already turned down other work and blocked out "
        "the weeks; that money and time are simply gone."
    ),
    fix=(
        "Add a kill fee: all work completed to date is payable in full, plus "
        "25-50% of the remaining fee. Make the right mutual, and require "
        "14-30 days' written notice."
    ),
    patterns=(
        _p(r"\bterminate\s+(?:this\s+\w+\s+)?for\s+convenience\b",
           "terminate for convenience"),
        _p(r"\b(?:may|shall\s+be\s+entitled\s+to|reserves?\s+the\s+right\s+to)\s+"
           r"terminate\b.{0,60}?\bat\s+any\s+time\b", "terminate at any time"),
        _p(r"\bat\s+any\s+time\b.{0,40}?\bterminate\b", "at any time terminate"),
        _p(r"\bfor\s+any\s+reason\s+or\s+for\s+no\s+reason\b",
           "for any reason or for no reason"),
        _p(r"\bwithout\s+further\s+obligation\b", "without further obligation"),
        _p(r"\bsole\s+discretion\s+to\s+terminate\b", "sole discretion to terminate"),
        _p(r"\bterminate\b.{0,40}?\bwithout\s+cause\b", "terminate without cause"),
    ),
    context_any=(
        re.compile(r"\bterminat", re.I),
        re.compile(r"\bcancel", re.I),
        re.compile(r"\bengagement\b", re.I),
        re.compile(r"\bSOW\b", re.I),
        re.compile(r"\bAgreement\b", re.I),
    ),
    context_none=(
        # Mutual rights are balanced, not a trap.
        re.compile(r"\beither\s+party\b", re.I),
        re.compile(r"\beach\s+party\b", re.I),
        # The freelancer's own termination right is not a risk to them.
        re.compile(r"\bcontractor\s+may\s+terminate\b", re.I),
        # Cause-based termination is the normal, correct shape.
        re.compile(r"\bfor\s+cause\b", re.I),
        re.compile(r"\buncured\s+material\s+breach\b", re.I),
        re.compile(r"\bmaterial\s+breach\b", re.I),
        # A kill fee turns the same clause into a fair one.
        re.compile(r"\bkill\s+fee\b", re.I),
        *DISCLAIMER_NEGATION,
    ),
    negation_exceptions=(
        # Every one of these negations IS the risk: it is what removes the
        # client's obligation to pay for the work already done.
        re.compile(r"\bfor\s+no\s+reason\b", re.I),
        re.compile(r"\bwithout\s+further\s+obligation\b", re.I),
        re.compile(r"\bwithout\s+cause\b", re.I),
        re.compile(r"\bwithout\s+(?:any\s+)?(?:payment|compensation|liability)\b", re.I),
    ),
)


# --------------------------------------------------------------------------
# Shared fragments for the restrictive-covenant rules (R14 / R15)
# --------------------------------------------------------------------------
#
# A prohibition aimed at the contractor. Shared, because both rules need it
# INSIDE the pattern rather than in negation_exceptions:
#
#   "Contractor shall not ... provide services to a competitor"
#
# The negation gate would read that "not" as a disclaimer and silently drop the
# sentence - the exact failure the whole engine exists to avoid. Putting the
# prohibition inside the match keeps the gate out of the decision entirely, and
# the quote the user sees begins with "shall not", which is the part they strike.
_PROHIBIT = r"(?:(?:shall|will|may|must)\s+not|(?:agrees?|undertakes?|covenants?)\s+not\s+to)"

_CONTRACTOR = re.compile(
    r"\b(?:contractor|consultant|freelancer|designer|developer|"
    r"service\s+provider|provider)\b",
    re.I,
)

# "Nothing in this Agreement shall prevent Contractor from working with other
# clients" is a permission, not a restriction. The negation gate only catches
# it while "Nothing" sits inside its 8-word window; this catches it at any
# distance, including the 9+ word sentences that broke R03 back in 5a.
_PERMISSION_CARVEOUT = re.compile(
    r"\bnothing\s+(?:in|herein)\b[^.;]{0,90}?"
    r"\b(?:shall\s+)?(?:prevents?|restricts?|prohibits?|limits?)\b",
    re.I,
)


# --------------------------------------------------------------------------
# R14 - Non-compete
# --------------------------------------------------------------------------
#
# Target (fake contract 8.1):
#   "During the term of this Agreement and for twelve (12) months thereafter,
#    Contractor shall not directly or indirectly provide services similar to the
#    Services to any competitor of Client, or to any person or entity engaged in
#    a similar line of business."
#
# WHY "shall not" IS PART OF THE PATTERN
# See _PROHIBIT above. A non-compete is written as a prohibition, so the naive
# reading of the negation gate is exactly backwards here.
#
# WHERE THE LINE IS
# A one-way ban on stealing the client's customers during the engagement is a
# normal conflict-of-interest clause. What makes 8.1 serious is the tail
# ("and for twelve (12) months thereafter") plus the width ("any person or
# entity engaged in a similar line of business"). But the tail is not required
# before we report: any bar on serving competitors is a commercial restriction
# the freelancer has to price in, and it is listed in docs/01 as R14.
# Bare `exclusively` is NOT a pattern - it appears in harmless licence scopes
# ("use the Deliverables exclusively for internal purposes"). Only the
# "provide services exclusively to Client" shape counts.

R14 = Rule(
    id="R14",
    name="Non-compete (cannot serve similar clients)",
    severity=7,
    why=(
        "You are barred from working for anyone who competes with this client - "
        "not only during the project, but for months afterwards, and the ban "
        "covers 'any person engaged in a similar line of business'. That can "
        "cut away a large part of your client pool, and nobody pays you for "
        "giving it up."
    ),
    fix=(
        "Ask for the non-compete to be deleted. If the client insists: limit it "
        "to the term of the engagement only, to named direct competitors listed "
        "in an exhibit, and to work substantially the same as the Services - "
        "and ask for a fee for the restriction."
    ),
    patterns=(
        _p(
            _PROHIBIT + r"[^.;]{0,80}?\b(?:provid|perform|render|offer)\w*\s+"
            r"[^.;]{0,60}?\bservices?\b[^.;]{0,40}?\bto\s+(?:any\s+)?"
            r"(?:competitor|competing|competitive)",
            "no services to a competitor",
        ),
        _p(
            r"\bservices?\b[^.;]{0,30}?\b(?:similar|substantially\s+similar)\b"
            r"[^.;]{0,60}?\b(?:competitor|competing\s+business)",
            "similar services to a competitor",
        ),
        _p(r"\bnon-?compet(?:e|ition|itive)\b", "non-compete"),
        _p(
            r"\b(?:provid|perform|render)\w*\s+[^.;]{0,25}?\bservices?\s+"
            r"exclusively\s+(?:to|for)\s+(?:the\s+)?client\b",
            "services exclusively for the client",
        ),
        _p(
            _PROHIBIT + r"[^.;]{0,40}?\b(?:work|be\s+employed|engage)\b[^.;]{0,20}?"
            r"\b(?:for|with)\b[^.;]{0,25}?\b(?:competitor|competing|competitive)\b",
            "no working for a competitor",
        ),
    ),
    context_any=(_CONTRACTOR,),
    context_none=(
        # The mirror image: a bar on the CLIENT serving the contractor's
        # competitors takes nothing away from the freelancer.
        re.compile(
            r"\bclient\s+(?:shall|will|may|must)\s+not\b[^.;]{0,80}?"
            r"\b(?:provid|perform|render|offer|solicit)\w*",
            re.I,
        ),
        _PERMISSION_CARVEOUT,
    ),
)


# --------------------------------------------------------------------------
# R15 - Non-solicitation of the client's clients
# --------------------------------------------------------------------------
#
# Target (fake contract 8.2):
#   "Contractor shall not, directly or indirectly, solicit, engage, or accept
#    work from any client, customer, vendor, employee, or contact of Client that
#    Contractor became aware of during the engagement."
#
# WHY ONLY THE CLIENT LIST
# The same clause usually also bans poaching the client's employees. An
# employee non-solicit is standard, mutual in practice, and does not cost a
# freelancer work - so it is excluded. The trap is the client/customer list:
# "any contact of Client you became aware of during the engagement" can mean
# you may never invoice that company again, through no fault of your own.
#
# The exclusions below are shaped for that: "employee of Client" and
# "Client's employees" drop out, while "any client, customer, vendor, employee,
# or contact of Client" (8.2's actual list) does not, because there the client
# word is the object of the ban, not the possessor of it.

R15 = Rule(
    id="R15",
    name="Cannot work for the client's clients",
    severity=5,
    why=(
        "You cannot solicit or accept work from anyone you met through this "
        "engagement - including the client's own customers, vendors and "
        "contacts. One introduction can therefore cost you a whole account, "
        "and the ban does not pay you anything."
    ),
    fix=(
        "Limit it to a named list of the client's direct customers, for twelve "
        "months, and only for work that competes with what you did here. "
        "Carve out anyone who approaches you first, and any client you already "
        "had before this engagement."
    ),
    patterns=(
        _p(
            _PROHIBIT + r"[^.;]{0,60}?\bsolicit\w*[^.;]{0,90}?"
            r"\b(?:clients?|customers?|accounts?)\b",
            "no soliciting the client's clients",
        ),
        _p(
            _PROHIBIT + r"[^.;]{0,60}?\b(?:accept|take)\s+(?:any\s+)?work\s+from\b"
            r"[^.;]{0,40}?\b(?:clients?|customers?)\b",
            "no work from the client's clients",
        ),
        _p(r"\bnon-?solicit(?:ation)?\b", "non-solicitation"),
    ),
    context_any=(_CONTRACTOR,),
    context_none=(
        # Employee-only non-solicits: normal, and not a loss of income.
        re.compile(r"\bclient'?s?\s+(?:employees?|personnel|staff)\b", re.I),
        re.compile(r"\b(?:employees?|personnel|staff)\s+of\s+(?:the\s+)?client\b", re.I),
        re.compile(r"\bclient\s+(?:shall|will|may|must)\s+not\s+solicit\b", re.I),
        _PERMISSION_CARVEOUT,
    ),
)


# --------------------------------------------------------------------------
# R16 - Unilateral amendment
# --------------------------------------------------------------------------
#
# Target (fake contract 12.1):
#   "Client may modify these terms at any time by posting an updated version on
#    its supplier portal, and Contractor's continued performance constitutes
#    acceptance of the revised terms."
#
# THE NORMAL CLAUSE THIS MUST NOT TOUCH
#   "This Agreement may be amended only by a written instrument signed by both
#    parties." / "No amendment shall be effective unless in writing and signed
#    by both parties."
# Those are the good ones - they are the fix R16 recommends. None of the
# patterns can reach them, and the context_none entries make sure of it.

R16 = Rule(
    id="R16",
    name="Client can change the contract unilaterally",
    severity=5,
    why=(
        "The client can rewrite the terms whenever it likes - posting a new "
        "version is enough - and carrying on with the work counts as agreeing "
        "to it. Nothing in the contract stops them changing the payment terms, "
        "the scope or the IP clause after you have signed."
    ),
    fix=(
        "Require changes to be in writing and signed by both parties. Delete "
        "any 'continued performance constitutes acceptance' wording, and make "
        "clear that no posted or online terms apply unless you agree to them."
    ),
    patterns=(
        _p(
            r"\b(?:client|company)\s+(?:may|reserves?\s+the\s+right\s+to)\s+"
            r"(?:unilaterally\s+)?(?:modify|amend|change|update|revise)\b",
            "client may modify the terms",
        ),
        _p(
            r"\bcontinued\s+(?:performance|use|acceptance)\b[^.;]{0,50}?"
            r"\b(?:constitutes?|shall\s+constitute)\b[^.;]{0,30}?\bacceptance\b",
            "continued performance = acceptance",
        ),
        _p(
            r"\breserves?\s+the\s+right\s+to\s+(?:modify|amend|change|update)\b"
            r"[^.;]{0,60}?\b(?:at\s+any\s+time|from\s+time\s+to\s+time)\b",
            "right to change at any time",
        ),
        _p(
            r"\b(?:modify|amend|change|update)\w*\b[^.;]{0,40}?"
            r"\bin\s+(?:its|their)\s+sole\s+discretion\b",
            "amend at sole discretion",
        ),
    ),
    # Only about the contract itself - stops "Client may modify the Deliverables
    # at any time before final delivery" from being read as an amendment power.
    context_any=(
        re.compile(
            r"\b(?:terms|agreement|polic(?:y|ies)|rates?|fees?|sow|"
            r"statement\s+of\s+work|revised|amended|provisions?)\b",
            re.I,
        ),
    ),
    context_none=(
        re.compile(r"\b(?:signed|executed)\s+by\s+both\s+part(?:y|ies)\b", re.I),
        re.compile(r"\b(?:signed|executed)\s+by\s+each\s+party\b", re.I),
        re.compile(r"\bno\s+amendment\b[^.;]{0,60}?\bunless\b", re.I),
        re.compile(r"\bamend(?:ed|ment)?\s+(?:only\s+)?(?:in\s+writing|by\s+written)\b", re.I),
    ),
)


# --------------------------------------------------------------------------
# R17 - Forum, arbitration and who pays the lawyers
# --------------------------------------------------------------------------
#
# Target (fake contract 11.2):
#   "Any dispute ... shall be resolved by binding arbitration administered in
#    Wilmington, Delaware ..."
# 11.3 / 11.4 are the MUTUAL shapes of the same two ideas and are not reported;
# only the one-way versions (client recovers, contractor pays) are.
#
# WHY 11.1 AND 11.4 ARE DELIBERATELY NOT REPORTED
# 11.1 is "governed by the laws of the State of Delaware, without regard to its
# conflict of laws principles." A governing-law clause appears in essentially
# every commercial contract and, on its own, costs the freelancer nothing. Rule
# 5b's lesson applies: report every one of these and every upload carries a
# card the user cannot act on. The forum burden is carried by 11.2 (arbitration
# seated in Wilmington) - that is the sentence that decides where and how you
# have to sue, and it is reported.
#
# 11.3 is "The prevailing party in any arbitration or proceeding shall be
# entitled to recover its reasonable attorneys' fees and costs." That is the
# MUTUAL shape - either side can be the prevailing party - and it sits in
# essentially every commercial contract. Reporting it fired on the clean
# boilerplate corpus, and a card the user cannot act on is worse than no card
# (the 5b lesson). Only fee-shifting that runs one way is reported.
#
# 11.4 is "Each Party waives any right to a trial by jury." A MUTUAL jury waiver
# is standard commercial drafting and, inside an arbitration clause, moot.
# Only a one-way waiver (contractor waives, client does not) is reported, which
# is why `each party` / `both parties` are in context_none.
#
# FOREIGN LAW
# A governing-law clause naming a non-US jurisdiction is unambiguously fatal
# for a US freelancer regardless of where they live, so it IS a pattern - the
# one place where governing law is judged directly. The list is hardcoded on
# purpose: deterministic, reviewable, and no LLM guessing.

_NON_US_LAW = (
    r"\bgoverned\s+by\s+(?:and\s+construed\s+in\s+accordance\s+with\s+)?the\s+laws\s+of\s+"
    r"(?:england(?:\s+and\s+wales)?|wales|scotland|ireland|canada|australia|"
    r"new\s+zealand|india|singapore|hong\s+kong|japan|south\s+korea|korea|china|"
    r"the\s+people'?s\s+republic\s+of\s+china|germany|france|spain|italy|"
    r"the\s+netherlands|netherlands|belgium|switzerland|sweden|norway|denmark|"
    r"finland|poland|portugal|austria|brazil|mexico|argentina|chile|colombia|"
    r"south\s+africa|israel|turkey|the\s+united\s+arab\s+emirates|"
    r"united\s+arab\s+emirates|saudi\s+arabia|russia|ukraine|nigeria|kenya|egypt|"
    r"pakistan|bangladesh|vietnam|thailand|malaysia|indonesia|the\s+philippines|"
    r"philippines|taiwan)\b"
)

R17 = Rule(
    id="R17",
    name="Distant forum or you pay their lawyers",
    severity=5,
    why=(
        "Disputes are decided somewhere specific - an arbitrator seated in "
        "another state, or a named court - and one side can be ordered to pay "
        "the other side's lawyers. Chasing a $3,000 unpaid invoice across the "
        "country can cost more than the invoice, and you cannot net it out."
    ),
    fix=(
        "Ask for the courts of your own city or county, or for arbitration in a "
        "neutral place with a small-claims carve-out. Delete the one-way or "
        "prevailing-party fee clause, or make it apply only to the party that "
        "wins on the core claim; each side should bear its own fees."
    ),
    patterns=(
        _p(r"\bbinding\s+arbitration\b", "binding arbitration"),
        _p(
            r"\bexclusive\s+jurisdiction\s+of\s+the\s+(?:state\s+and\s+federal\s+)?courts\b",
            "exclusive jurisdiction of a named court",
        ),
        _p(r"\bvenue\s+(?:shall\s+(?:be|lie)|lies|is)\b[^.;]{0,20}?\bin\b",
           "exclusive venue"),
        # One-way fee shifting only. "The prevailing party ... shall recover its
        # fees" is mutual and standard; it belongs in context, not on a card.
        _p(
            r"\bclient\s+(?:shall|will|may|is\s+entitled\s+to)\b[^.;]{0,60}?"
            r"\b(?:recover|collect)\b[^.;]{0,40}?"
            r"\b(?:attorneys?'?\s+fees|legal\s+fees)\b",
            "client recovers its legal fees",
        ),
        _p(
            r"\bcontractor\s+(?:shall|will)\s+(?:be\s+liable\s+for|pay|reimburse)\b"
            r"[^.;]{0,80}?\b(?:attorneys?'?\s+fees|legal\s+fees|collection\s+costs)\b",
            "you pay their legal fees",
        ),
        _p(r"\bwaives?\b[^.;]{0,40}?\btrial\s+by\s+jury\b", "jury trial waiver"),
        _p(_NON_US_LAW, "non-US governing law"),
    ),
    context_none=(
        # Mutual waiver: standard, and worth nothing to report.
        re.compile(r"\beach\s+party\s+waives?\b", re.I),
        re.compile(r"\bboth\s+part(?:y|ies)\s+waive\b", re.I),
        re.compile(r"\bparties\s+each\s+waive\b", re.I),
        # A small-claims carve-out is the fix, not the trap.
        re.compile(r"\bmay\b[^.;]{0,40}?\bsmall\s+claims\b", re.I),
    ),
)


# --------------------------------------------------------------------------
# R18 - Liquidated damages per day of delay
# --------------------------------------------------------------------------
#
# Target (fake contract 10.1 / 10.2):
#   "Time is of the essence with respect to all delivery dates ..."
#   "For each day of delay ... Contractor shall pay to Client liquidated damages
#    of five hundred dollars ($500.00) per day."
#
# THE MIRROR-IMAGE TRAP
# Freelancers also write "per day" language - in their own favour:
#
#   "Client shall pay interest at 1.5% per month on overdue invoices."
#   "A late fee of $50 per day applies to invoices unpaid after 30 days."
#
# That is a protection for the freelancer and must never be reported. The
# invoice/interest entries in context_none exist for exactly those sentences.

R18 = Rule(
    id="R18",
    name="Penalty per day of delay",
    severity=5,
    why=(
        "Every day the work is late costs you a fixed sum, and 'time is of the "
        "essence' means even one day late is a breach. A two-week slip on a "
        "$5,000 job can wipe out the whole fee - and the clock does not stop "
        "for feedback you are still waiting on."
    ),
    fix=(
        "Delete the per-day penalty, or cap it (for example at 10% of the fee, "
        "or the unpaid balance) and make it apply only to delays caused by you. "
        "Add that client-caused delay extends the deadline automatically."
    ),
    patterns=(
        # Money first: "liquidated damages of $500 per day" is the quote that
        # tells the user how much, which bare "liquidated damages" does not.
        # `[^;]` rather than `[^.;]` because these patterns must cross money:
        # "$500.00" contains a period, and `[^.;]` stops dead at it.
        _p(r"\bliquidated\s+damages?\b[^;]{0,70}?\bper\s+day\b",
           "liquidated damages per day"),
        _p(r"\bliquidated\s+damages?\b", "liquidated damages"),
        _p(r"\btime\s+is\s+of\s+the\s+essence\b", "time is of the essence"),
        _p(r"\b(?:penalt(?:y|ies)|damages?)\b[^;]{0,50}?\bper\s+day\b",
           "penalty per day"),
        _p(r"\bper\s+day\b[^.;]{0,50}?\b(?:penalt(?:y|ies)|damages?)\b",
           "per day of delay"),
        _p(r"\blate\s+(?:fee|charge|penalty)\b[^;]{0,40}?\bper\s+day\b",
           "late fee per day"),
    ),
    # Only makes sense about delivery, not about a payment deadline.
    context_any=(
        re.compile(
            # No bare "schedule": the section title "SCHEDULE AND LIQUIDATED
            # DAMAGES" is an all-caps heading with no clause number, so it
            # inherits the previous clause and would fire on nothing but the
            # title. Every real delivery sentence below also says delivered,
            # delayed, due date, deadline or completion.
            r"\b(?:deliver\w*|due\s+date|deadline|milestones?|"
            r"late|delay\w*|completion)\b",
            re.I,
        ),
    ),
    context_none=(
        # The freelancer's own late-payment protection.
        re.compile(r"\binvoices?\b[^.;]{0,60}?\b(?:interest|late\s+(?:fee|charge))\b", re.I),
        re.compile(r"\b(?:interest|late\s+(?:fee|charge))\b[^.;]{0,60}?\binvoices?\b", re.I),
        re.compile(
            r"\btime\s+is\s+of\s+the\s+essence\s+with\s+respect\s+to\s+(?:the\s+)?"
            r"client'?s?\s+(?:payment|obligations?)\b",
            re.I,
        ),
    ),
)


# --------------------------------------------------------------------------
# R19 - Confidentiality with no end
# --------------------------------------------------------------------------
#
# Target (fake contract 9.1 / 9.2):
#   "... keep confidential all information disclosed by Client, whether or not
#    marked as confidential ..."
#   "The obligations in this Section 9 shall survive in perpetuity and shall
#    continue indefinitely after termination of this Agreement."
#
# WHY THE CONTEXT SITS INSIDE THE PATTERNS
# "in perpetuity" also appears in the IP clause (4.1: "assigns ... in
# perpetuity"), where it belongs to R08. If `in perpetuity` were a bare pattern
# with a rule-level context check, an IP sentence that happens to contain the
# word "information" would be reported twice. Binding the noun into the regex
# ("obligations ... in perpetuity") makes that collision impossible rather than
# merely unlikely.
#
# 7.4 ("Sections 4, 5, 6, 8, 9, and 11 survive any termination") must stay
# silent: survival of a section is not a perpetual obligation, and none of the
# patterns can reach it.

R19 = Rule(
    id="R19",
    name="Confidentiality with no time limit",
    severity=3,
    why=(
        "You must keep everything confidential forever, including material that "
        "was never marked confidential - which in practice means everything you "
        "saw. Ten years from now you can still be accused of breaking this, and "
        "you have no way of proving what was and was not 'information'."
    ),
    fix=(
        "Limit the duty to material marked confidential, or identified in "
        "writing within 30 days, and give it a finite term (three to five years "
        "after termination). Standard exclusions should apply: public "
        "information, and anything you already knew."
    ),
    patterns=(
        _p(r"\bwhether\s+or\s+not\s+(?:marked|labeled|designated)\b",
           "whether or not marked confidential"),
        _p(
            r"\b(?:obligations?|confidentiality|restrictions?|duties)\b"
            r"[^.;]{0,60}?\bin\s+perpetuity\b",
            "confidentiality in perpetuity",
        ),
        _p(r"\bindefinitely\b[^.;]{0,40}?\bafter\s+(?:the\s+)?termination\b",
           "indefinitely after termination"),
        _p(r"\bperpetual\w*\s+confidential\w*", "perpetual confidentiality"),
        _p(
            r"\bconfidential\w*\s+obligations?\b[^.;]{0,40}?\b(?:perpetual|indefinite|forever)\b",
            "perpetual confidentiality obligations",
        ),
    ),
    context_none=(*DISCLAIMER_NEGATION,),
)


# --------------------------------------------------------------------------
# R20 - Absolute quality warranty
# --------------------------------------------------------------------------
#
# Target (fake contract 5.1):
#   "Contractor warrants that the Deliverables will be error-free, free from
#    defects, fit for Client's particular purpose, and compliant with all
#    applicable laws and regulations."
#
# "compliant with all applicable laws" is NOT a pattern even though docs/01
# lists it: almost every contract contains "each party shall comply with all
# applicable laws" as a general covenant, and flagging that would fire on
# nearly every upload. The warranty that actually traps a freelancer is
# "error-free" and "fit for ... particular purpose" - standards no software
# meets and no designer can promise.
#
# `fitness for a particular purpose` is likewise not a pattern: that phrase is
# how a freelancer DISCLAIMS warranties, and it is the fix, not the risk.

R20 = Rule(
    id="R20",
    name="Absolute quality warranty",
    severity=3,
    why=(
        "'Error-free' and 'fit for the client's particular purpose' are "
        "standards nothing ever meets. Read literally, any bug, any change of "
        "mind about the design, or any use the client finds for the work is a "
        "breach - which turns a fixed fee into an open-ended repair obligation."
    ),
    fix=(
        "Warrant only that the work will substantially conform to the agreed "
        "specifications, performed in a professional manner. Delete "
        "'error-free' and 'fit for particular purpose', and add a warranty "
        "period with a fix-or-refund remedy as the sole remedy."
    ),
    patterns=(
        _p(r"\berror[-\s]?free\b", "error-free"),
        _p(r"\bfit\s+for\s+(?:\w+'s\s+)?(?:a\s+)?particular\s+purpose\b",
           "fit for a particular purpose"),
        _p(r"\bfree\s+(?:from|of)\s+(?:all\s+)?(?:\w+\s+)?(?:defects?|errors?|bugs?)\b",
           "free from defects"),
        _p(r"\bmerchantab(?:le|ility)\b", "merchantability"),
        _p(r"\buninterrupted\s+(?:and\s+error[-\s]?free\s+)?(?:service|operation|availability)\b",
           "uninterrupted service"),
    ),
    context_any=(
        re.compile(r"\b(?:warrant\w*|guarantee\w*|represent\w*|deliverables?|services?)\b", re.I),
    ),
    context_none=(
        # "free from material defects" is a reasonable, bounded standard.
        re.compile(r"\bmaterial(?:ly)?\s+(?:defects?|errors?|bugs?)\b", re.I),
        # A disclaimer is the freelancer's protection, not a warranty.
        re.compile(r"\bdisclaims?\b[^.;]{0,60}?\bwarrant", re.I),
        re.compile(r"\bno\s+warrant(?:y|ies)\b", re.I),
    ),
)


# Step 5d ships all twenty rules. The set is frozen (D-005).
RULES: list[Rule] = [
    R01, R02, R03, R04, R05, R06, R07, R08, R09, R10,
    R11, R12, R13, R14, R15, R16, R17, R18, R19, R20,
]
