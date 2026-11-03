"""The core matcher: regex over normalised text, plus the negation gate.

The problem this file solves
----------------------------
Contracts are full of sentences that *look* like a red flag and mean the
opposite:

    "Client shall NOT request unlimited revisions to Deliverables that have
     been formally approved in a signed change order."

A naive keyword scanner reports "unlimited revisions" and destroys the user's
trust on first use. So every hit passes through `_negated()` before it is
allowed to become a finding.

Three outcomes per hit
----------------------
  CONFIRMED  - the clause is in the contract and means what the rule says.
  REVIEW     - matched, but something nearby makes it ambiguous
               (hedged language). Shown to the user as "worth a look",
               never as a fatal risk.
  SUPPRESSED - a negation cancels the clause. Dropped from the report
               entirely; kept in the result for regression testing.

Two kinds of negation
---------------------
  CANCELLING  ("shall not request", "shall not be liable", "no obligation to")
              -> the risk does not exist. SUPPRESSED.
  REINFORCING ("shall not be deemed accepted until Client issues written
              acceptance")
              -> the negation IS the risk; removing it would make the clause
                 harmless. CONFIRMED. Declared per rule via `negation_exceptions`.

Getting these two backwards is the single most likely way to ship a product
that lies in both directions at once.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from app.engine.textnorm import Sentence

# --------------------------------------------------------------------------
# Negation vocabulary
# --------------------------------------------------------------------------

# Single tokens that flip the meaning of what follows. Matched against
# punctuation-stripped, lower-cased tokens.
NEGATORS = {
    "not", "no", "never", "none", "nobody", "nothing", "neither", "nor",
    "cannot", "without", "except", "excepting", "excluding", "excludes",
    "unless", "absent", "excluding",
}

# How far back / forward to look. 8 words covers "shall not request",
# "to the extent permitted by applicable law shall not", and similar padding,
# without reaching into a neighbouring clause.
WINDOW_BEFORE = 8
WINDOW_AFTER = 4

# A hit next to these is not cancelled, but is not certain either:
# the drafter hedged, so a human should read it.
HEDGES = {
    "notwithstanding", "provided", "however", "subject", "solely",
    "reasonably", "materially",
}

# Idioms that CONTAIN a negator-looking word but do not negate the clause.
# This matters more than it looks: "without limitation" is the signature phrase
# of an uncapped indemnity (R11). Leaving it in the negation vocabulary means
# the gate silently drops one of the most dangerous clauses in the contract.
# "no later than 60 days" is a deadline, not a prohibition.
NON_NEGATING_IDIOMS = re.compile(
    r"\b(?:"
    r"including\s+without\s+limitation|without\s+limitation|"
    r"no\s+(?:later|less|more|fewer)\s+than|"
    r"not\s+(?:later|less|more|fewer)\s+than|"
    r"whether\s+or\s+not|if\s+not|or\s+not"
    r")\b",
    re.I,
)

_WORD = re.compile(r"\S+")
_STRIP = re.compile(r"^[^\w']+|[^\w']+$")

STATUS_CONFIRMED = "confirmed"
STATUS_REVIEW = "review"
STATUS_SUPPRESSED = "suppressed"


@dataclass
class Pattern:
    """One regex belonging to a rule."""

    regex: re.Pattern[str]
    label: str
    days_group: str | None = None


@dataclass
class Rule:
    """A red flag. Pure data; no matching logic lives here."""

    id: str
    name: str
    severity: int
    why: str
    fix: str
    patterns: Sequence[Pattern]
    # At least one of these must appear in the same sentence, or the hit is
    # treated as out-of-context noise. Empty means "no context needed".
    context_any: Sequence[re.Pattern[str]] = field(default_factory=tuple)
    # If any of these appear in the same sentence, the hit belongs to a
    # different legal construct and must be dropped. Example: "thirty (30)
    # days after written notice" is a cure period, not a payment term.
    context_none: Sequence[re.Pattern[str]] = field(default_factory=tuple)
    # Numeric threshold, e.g. only flag payment terms longer than 30 days.
    min_value: int | None = None
    # Negation phrases that REINFORCE the risk instead of cancelling it.
    negation_exceptions: Sequence[re.Pattern[str]] = field(default_factory=tuple)


@dataclass
class Finding:
    """One matched clause, with the evidence required to prove it."""

    rule_id: str
    rule_name: str
    severity: int
    status: str
    matched_text: str
    sentence: str
    clause: str
    offset: int
    pattern_label: str
    # Position of the pattern within its rule. Rules list their most specific
    # (most damning) pattern first, so this decides which quote to show when
    # one sentence trips several of a rule's patterns.
    pattern_index: int = 0
    value: int | None = None
    reason: str = ""

    @property
    def is_reportable(self) -> bool:
        return self.status in (STATUS_CONFIRMED, STATUS_REVIEW)

    def __str__(self) -> str:  # pragma: no cover - debugging aid
        loc = f"{self.clause} " if self.clause else ""
        return f"{self.rule_id} [{self.status}] {loc}\"{self.matched_text}\""


# --------------------------------------------------------------------------
# Negation gate
# --------------------------------------------------------------------------

def _tokens(sentence: str) -> list[tuple[int, int, str]]:
    """Word-level tokens with offsets and cleaned, lower-cased text."""
    out = []
    for m in _WORD.finditer(sentence):
        cleaned = _STRIP.sub("", m.group()).lower()
        out.append((m.start(), m.end(), cleaned))
    return out


def _is_negator(token: str) -> bool:
    if not token:
        return False
    if token in NEGATORS:
        return True
    # "isn't", "don't", "doesn't" -> the token still carries the negation
    return token.endswith("n't")


def _window(sentence: str, start: int, end: int) -> tuple[str, bool]:
    """Text of the negation window around a match, and whether it fired.

    Returns (window_text, has_negator).
    """
    tokens = _tokens(sentence)
    before = [t for t in tokens if t[1] <= start][-WINDOW_BEFORE:]
    after = [t for t in tokens if t[0] >= end][:WINDOW_AFTER]

    window_text = " ".join(t[2] for t in before + after)
    # Strip idioms that only look like negations before judging.
    judged = NON_NEGATING_IDIOMS.sub(" ", window_text).split()
    has_negator = any(_is_negator(t) for t in judged)
    return window_text, has_negator


def _has_hedge(sentence: str, start: int, end: int) -> bool:
    window_text, _ = _window(sentence, start, end)
    return any(word in window_text.split() for word in HEDGES)


def _negation_verdict(
    sentence: str,
    start: int,
    end: int,
    rule: Rule,
) -> tuple[str, str]:
    """Apply the negation gate. Returns (status, reason)."""
    window_text, has_negator = _window(sentence, start, end)

    if not has_negator:
        status = STATUS_REVIEW if _has_hedge(sentence, start, end) else STATUS_CONFIRMED
        return status, "" if status == STATUS_CONFIRMED else "hedged language nearby"

    # A negator is present. Does this rule consider it reinforcing instead?
    for exc in rule.negation_exceptions:
        if exc.search(sentence):
            return STATUS_CONFIRMED, "negation is part of the risk itself"

    return STATUS_SUPPRESSED, f"negated nearby: ...{window_text}..."


# --------------------------------------------------------------------------
# Matching
# --------------------------------------------------------------------------

# A standalone clause title: an optional section number, then Title Case words,
# then a full stop, with no lowercase words other than short connectors.
#   "4.2 Work Made for Hire."            -> heading
#   "6.2 No Cap."                        -> heading
#   "All Deliverables shall be deemed ..." -> not a heading (has lowercase verbs)
_HEADING = re.compile(
    r"^\s*(?:\d+(?:\.\d+){0,2}\.?\s+)?"
    r"(?:[A-Z][\w'&-]*(?:\s+(?:of|and|for|the|to|in|on)\b)?\s*){1,6}"
    r"(?:\d+)?\.?\s*$"
)


def _is_heading_like(sentence: str) -> bool:
    """True for a bare clause title such as '4.2 Work Made for Hire.'."""
    text = sentence.strip()
    if len(text) > 80:
        return False
    # Any lowercase word that is not a connector means this is real prose.
    words = text.split()
    connectors = {"of", "and", "for", "the", "to", "in", "on", "a", "an", "or"}
    for i, w in enumerate(words):
        core = w.strip(".,;:()\"'")
        if not core:
            continue
        if i == 0 and re.fullmatch(r"\d+(?:\.\d+){0,2}\.?", core):
            continue
        if core[0].islower() and core not in connectors:
            return False
    return bool(_HEADING.match(text))


def _context_ok(rule: Rule, sentence: str) -> bool:
    # Hard exclusion first: a cure period or notice window is not a payment term.
    if any(p.search(sentence) for p in rule.context_none):
        return False
    if not rule.context_any:
        return True
    return any(p.search(sentence) for p in rule.context_any)


def match_sentence(sentence: Sentence, rule: Rule) -> list[Finding]:
    """Run one rule against one sentence. Returns every hit it produced."""
    if not _context_ok(rule, sentence.text):
        return []

    findings: list[Finding] = []

    for pattern_index, pattern in enumerate(rule.patterns):
        for m in pattern.regex.finditer(sentence.text):
            value = None
            if pattern.days_group:
                raw = m.groupdict().get(pattern.days_group)
                if raw and raw.isdigit():
                    value = int(raw)

            if rule.min_value is not None and value is not None:
                if value < rule.min_value:
                    continue

            status, reason = _negation_verdict(
                sentence.text, m.start(), m.end(), rule
            )

            findings.append(
                Finding(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    severity=rule.severity,
                    status=status,
                    matched_text=m.group(),
                    sentence=sentence.text,
                    clause=sentence.clause,
                    offset=sentence.start + m.start(),
                    pattern_label=pattern.label,
                    pattern_index=pattern_index,
                    value=value,
                    reason=reason,
                )
            )

    return findings


def dedupe(findings: Iterable[Finding]) -> list[Finding]:
    """One finding per (rule, clause/sentence).

    A single bad clause often trips three of the same rule's patterns
    ("unlimited revisions" + "until satisfied" + "as many times as
    necessary"). The user must see one entry, not three.

    Ranking, in order:
      1. a CONFIRMED hit beats a SUPPRESSED one, so a sentence that is partly
         negated is judged by its strongest surviving signal. That is the case
         in section 2.3, where "shall not be deemed accepted until" is a
         reinforcing negation while the rest of the sentence is plainly bad.
      2. a substantive sentence beats a bare heading. Contracts put the clause
         title on its own line ("4.2 Work Made for Hire."), and that title can
         contain the keyword without containing the trap. Quoting only the
         heading produces a card the user cannot act on.
      3. the rule's earlier pattern beats a later one: rules list their most
         specific pattern first, so section 4.1 is quoted as "unused
         directions" rather than the vaguer "all materials created".
      4. earliest offset, so the order inside a clause is stable.
    """
    best: dict[tuple[str, str], Finding] = {}
    rank = {STATUS_CONFIRMED: 0, STATUS_REVIEW: 1, STATUS_SUPPRESSED: 2}

    for f in findings:
        # One entry per clause. A numbered clause can span several sentences
        # ("2.3" above is three), and the user must see one line, not three.
        key = (f.rule_id, f.clause or f.sentence)
        current = best.get(key)
        if current is None:
            best[key] = f
            continue
        new_rank = (rank[f.status], _is_heading_like(f.sentence), f.pattern_index, f.offset)
        old_rank = (rank[current.status], _is_heading_like(current.sentence),
                    current.pattern_index, current.offset)
        if new_rank < old_rank:
            best[key] = f

    ordered = sorted(best.values(), key=lambda f: (f.offset, f.rule_id))
    return ordered


def scan(sentences: Sequence[Sentence], rules: Sequence[Rule]) -> list[Finding]:
    """Run every rule against every sentence. Returns deduped findings."""
    raw: list[Finding] = []
    for sentence in sentences:
        for rule in rules:
            raw.extend(match_sentence(sentence, rule))
    return dedupe(raw)
