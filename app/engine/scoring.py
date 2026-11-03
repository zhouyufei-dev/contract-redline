"""De-duplication, severity banding and the report summary.

Two jobs, both deterministic:

1. **Merge.** The same rule often fires on two consecutive clauses of the same
   section - 4.1 assigns all IP, 4.2 calls the same work "work made for hire";
   they are one problem with two handles. Showing both gives the user a card
   they cannot act on twice. We merge them into one card that lists both
   sentences, so the fix is stated once and the evidence is still complete.

   The rule is deliberately narrow: same rule id, same top-level section,
   consecutive sub-clause numbers, at most three sentences. Anything less
   certain stays a separate card - a wrong merge hides a distinct problem,
   which is worse than a slightly repetitive report.

2. **Summarise.** Counts by band, a verdict sentence, and the ordered list of
   cards the report should show. No invented 0-100 score: twenty hits summed
   into "82/100" tells the user nothing and makes every contract look equally
   terrible (see the note at the top of this file's history in D-003).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.engine.matcher import STATUS_CONFIRMED, Finding

# Severity value -> band key. Every rule uses one of these four values.
BANDS = {
    10: "critical",
    7: "serious",
    5: "moderate",
    3: "minor",
}

BAND_LABEL = {
    "critical": "Deal-breaker",
    "serious": "Serious",
    "moderate": "Costly",
    "minor": "Watch",
}

# One line per band, shown in the legend. Written for the user, not for us.
BAND_MEANING = {
    "critical": "Can cost you the whole fee, or the ownership of your work. "
                "Do not sign until it is changed.",
    "serious": "Will cost you money or time on a normal project. "
               "Change it before you sign.",
    "moderate": "Adds risk you can live with if you price it in. "
                "Worth one line in your reply.",
    "minor": "Small print that limits you. Fix it if the client is easy to talk to.",
}

MAX_MERGE = 3

_CLAUSE = re.compile(r"^\s*(\d+)(?:\.(\d+))?")


def band_of(severity: int) -> str:
    return BANDS.get(severity, "minor")


def band_label(severity: int) -> str:
    return BAND_LABEL[band_of(severity)]


@dataclass
class RiskGroup:
    """One card in the report: a rule plus every clause it fired on."""

    rule_id: str
    rule_name: str
    severity: int
    findings: list[Finding] = field(default_factory=list)

    @property
    def band(self) -> str:
        return band_of(self.severity)

    @property
    def sections(self) -> list[str]:
        return [f.clause for f in self.findings if f.clause]

    @property
    def section_label(self) -> str:
        sections = self.sections
        if not sections:
            return "Un-numbered clause"
        if len(sections) == 1:
            return f"Section {sections[0]}"
        return "Sections " + " and ".join(sections)

    @property
    def primary(self) -> Finding:
        """The finding whose card text we use.

        Longest sentence wins: in a pair like "10.1 Time is of the essence" and
        "10.2 ... shall pay $500 per day", the long one is the operative
        language and the card written for it is the specific one.
        """
        return max(self.findings, key=lambda f: (len(f.sentence), -f.offset))

    @property
    def offset(self) -> int:
        return min(f.offset for f in self.findings)

    @property
    def is_merged(self) -> bool:
        return len(self.findings) > 1

    @property
    def needs_review(self) -> bool:
        """Any part of this group was only a hedged match, not a certain one."""
        return any(f.status != STATUS_CONFIRMED for f in self.findings)


def _clause_key(clause: str) -> tuple[int, int] | None:
    match = _CLAUSE.match(clause or "")
    if not match:
        return None
    major = int(match.group(1))
    minor = int(match.group(2)) if match.group(2) is not None else -1
    return major, minor


def _can_merge(group: RiskGroup, finding: Finding) -> bool:
    """Narrow, explainable rule. Anything uncertain stays separate."""
    if group.rule_id != finding.rule_id:
        return False
    if len(group.findings) >= MAX_MERGE:
        return False

    last = group.findings[-1]
    if finding.offset <= last.offset:
        return False  # not in document order
    if finding.sentence.strip() == last.sentence.strip():
        return False  # exact duplicate sentence, not a second clause

    a, b = _clause_key(last.clause), _clause_key(finding.clause)
    if a is None or b is None:
        return False  # no numbering: cannot prove they are siblings
    if a[0] != b[0]:
        return False  # different section
    if a[1] < 0 or b[1] < 0:
        return False  # bare section number, no sub-clause
    return b[1] - a[1] == 1  # consecutive: 4.1 then 4.2


def group_findings(findings: list[Finding]) -> list[RiskGroup]:
    """Merge consecutive same-rule findings. Input order is document order."""
    reportable = sorted(
        (f for f in findings if f.is_reportable), key=lambda f: f.offset
    )
    groups: list[RiskGroup] = []

    for finding in reportable:
        if groups and _can_merge(groups[-1], finding):
            groups[-1].findings.append(finding)
            continue
        groups.append(
            RiskGroup(
                rule_id=finding.rule_id,
                rule_name=finding.rule_name,
                severity=finding.severity,
                findings=[finding],
            )
        )
    return groups


def display_order(groups: list[RiskGroup]) -> list[RiskGroup]:
    """Worst first, then in contract order. The user reads the top three."""
    return sorted(groups, key=lambda g: (-g.severity, g.offset))


@dataclass
class Summary:
    findings: int
    cards: int
    merged_away: int
    counts: dict[str, int]
    verdict: str
    detail: str
    tone: str

    @property
    def worst(self) -> str:
        for band in ("critical", "serious", "moderate", "minor"):
            if self.counts.get(band):
                return band
        return "clean"

    @property
    def total_issues(self) -> int:
        return sum(self.counts.values())


def summarise(groups: list[RiskGroup]) -> Summary:
    counts = {band: 0 for band in ("critical", "serious", "moderate", "minor")}
    for group in groups:
        counts[band_of(group.severity)] += 1

    findings = sum(len(g.findings) for g in groups)
    merged_away = findings - len(groups)
    critical, serious = counts["critical"], counts["serious"]

    if critical:
        verdict = "Do not sign this contract as it stands."
        detail = (
            f"{critical} clause{'s' if critical != 1 else ''} can cost you the "
            "entire fee, the rights to your own work, or more than the project "
            "is worth. Ask for the changes below in writing before you sign."
        )
        tone = "critical"
    elif serious:
        verdict = "Sign only after these clauses are changed."
        detail = (
            f"{serious} clause{'s' if serious != 1 else ''} will cost you money "
            "or time on a normal project. None of them is unusual to negotiate."
        )
        tone = "serious"
    elif counts["moderate"] or counts["minor"]:
        verdict = "Signable, but ask for these changes first."
        detail = (
            "Nothing here is a walk-away problem. The items below are worth one "
            "short reply to the client before you sign."
        )
        tone = "moderate"
    else:
        verdict = "No red flags in the clauses we check."
        detail = (
            "That is not a clean bill of health: this scan looks for 20 specific "
            "problems that are written into the contract. It cannot see what is "
            "missing from it."
        )
        tone = "clean"

    return Summary(
        findings=findings,
        cards=len(groups),
        merged_away=merged_away,
        counts=counts,
        verdict=verdict,
        detail=detail,
        tone=tone,
    )
