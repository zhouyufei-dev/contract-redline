# Prompt: suggest a negotiation fix

Status: DRAFT — finalised in step 6.

---

The user is about to reply to their client about the clause below. Give them
the exact ask, not general advice.

CLAUSE:
"""
{clause}
"""

OUR STANDARD POSITION (anchor — do not weaken it, do not invent stronger claims):
{fix}

Return exactly this structure, nothing else:

ASK: one sentence they can paste into an email to the client, in first person.
FALLBACK: one sentence — what to accept if the client refuses the ask above.
WALK-AWAY: one short clause — the point at which they should not sign.

Rules:
- at most 40 words per line
- no legal citations, no statute numbers
- never state or imply that this is legal advice
