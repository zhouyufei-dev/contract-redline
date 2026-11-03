"""Assemble the report model.

The renderers (HTML now, PDF later) take this model and do no thinking of their
own. Everything a reader sees is decided here, once:

    findings -> groups (scoring.group_findings) -> cards (with LLM prose)

so the HTML, the terminal summary and a future PDF cannot drift apart.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import datetime

from app.engine.matcher import Finding
from app.engine.scoring import RiskGroup, Summary, band_label, display_order, summarise

_LEADING_NUMBER = re.compile(r"^(\d+(?:\.\d+)*)[.)]?\s+")


def clean_quote(sentence: str, clause: str) -> str:
    """Drop the clause's own number from the front of a quoted sentence.

    The PDF/DOCX text runs "10.1 Time is of the essence ...", and the sentence
    splitter keeps the number. The card already prints "Section 10.1" above the
    quote, so leaving it in reads like a stutter. Only an exact match is
    removed; nothing else about the quote is touched.
    """
    text = (sentence or "").strip()
    if not clause:
        return text
    match = _LEADING_NUMBER.match(text)
    if match and match.group(1) == clause:
        return text[match.end():].strip()
    return text


@dataclass
class Quote:
    """One verbatim sentence from the contract, with the words that matched."""

    section: str
    sentence: str
    matched: str


@dataclass
class ReportCard:
    number: int
    group: RiskGroup
    why: str
    fix: str
    ask: str = ""
    fallback: str = ""
    walk_away: str = ""
    source: str = "rule"        # "llm" | "cache" | "fallback"
    notes: tuple[str, ...] = ()

    @property
    def rule_id(self) -> str:
        return self.group.rule_id

    @property
    def rule_name(self) -> str:
        return self.group.rule_name

    @property
    def severity(self) -> int:
        return self.group.severity

    @property
    def band(self) -> str:
        return self.group.band

    @property
    def badge(self) -> str:
        return band_label(self.severity)

    @property
    def section_label(self) -> str:
        return self.group.section_label

    @property
    def quotes(self) -> list[Quote]:
        return [
            Quote(
                section=f"Section {f.clause}" if f.clause else "Un-numbered clause",
                sentence=clean_quote(f.sentence, f.clause),
                matched=f.matched_text,
            )
            for f in self.group.findings
        ]


@dataclass
class Report:
    source_name: str
    generated_at: datetime
    sentence_count: int
    rule_count: int
    summary: Summary
    cards: list[ReportCard] = field(default_factory=list)

    @property
    def top_three(self) -> list[ReportCard]:
        return self.cards[:3]

    @property
    def date_label(self) -> str:
        # "1 November 2026" - unambiguous for a US reader, no mm/dd confusion.
        return f"{self.generated_at.day} {self.generated_at:%B %Y}"

    def card_for(self, rule_id: str, offset: int) -> ReportCard | None:
        for card in self.cards:
            if card.rule_id == rule_id and card.group.offset == offset:
                return card
        return None


def _fallback_text(group: RiskGroup, attr: str) -> str:
    """The rule's own words, used when the LLM layer contributed nothing."""
    from app.rules.redlines_us import RULES

    for rule in RULES:
        if rule.id == group.rule_id:
            return getattr(rule, attr, "") or ""
    return ""


def build(
    groups: list[RiskGroup],
    cards: list | None = None,
    *,
    source_name: str,
    sentence_count: int,
    rule_count: int,
    generated_at: datetime | None = None,
) -> Report:
    """Turn merged groups + LLM cards into the model the renderers consume.

    `cards` must be aligned with `groups` in document order (that is the order
    `deepseek_client.enrich` returns). Passing None produces a rules-only
    report, which is what runs without an API key.
    """
    ordered = display_order(groups)
    by_group = {}
    if cards:
        for group, card in zip(groups, cards):
            by_group[id(group)] = card
        # display_order returns the same objects, so identity still holds.

    report_cards: list[ReportCard] = []
    for number, group in enumerate(ordered, start=1):
        card = by_group.get(id(group))
        notes: list[str] = []
        if group.needs_review:
            notes.append(
                "This one was a borderline match. Read the sentence yourself "
                "before you quote it back to the client."
            )
        if card is not None and card.source == "fallback":
            notes.append(
                "We could not generate a custom explanation for this clause, "
                "so this is our standard guidance for it."
            )

        report_cards.append(
            ReportCard(
                number=number,
                group=group,
                why=(card.why if card and card.why else _fallback_text(group, "why")),
                fix=(card.fix if card and card.fix else _fallback_text(group, "fix")),
                ask=(card.ask if card else ""),
                fallback=(card.fallback if card else ""),
                walk_away=(card.walk_away if card else ""),
                source=(card.source if card else "rule"),
                notes=tuple(notes),
            )
        )

    return Report(
        source_name=source_name,
        generated_at=generated_at or datetime.now(),
        sentence_count=sentence_count,
        rule_count=rule_count,
        summary=summarise(groups),
        cards=report_cards,
    )


def preview(report: Report, limit: int = 1) -> Report:
    """The free teaser: the worst `limit` cards, with the real totals kept.

    This deliberately returns a *smaller Report* rather than a flag the HTML
    layer could forget to honour. The cards nobody paid for are not in the
    object, so they are not in the template, so they are not in the bytes sent
    to the browser. A paywall you can read with View Source is not a paywall.

    `summary` is left alone on purpose: "24 problems in 20 cards" is the truth
    about the contract, and it belongs at the top of the teaser. It is the
    cards, not the count, that the $5 buys.
    """
    if limit >= len(report.cards):
        return report
    return replace(report, cards=report.cards[: max(limit, 0)])


def to_text(report: Report) -> str:
    """Plain-text rendering, for the terminal and for diffing two runs."""
    lines = [
        "=" * 78,
        report.summary.verdict.upper(),
        "=" * 78,
        report.summary.detail,
        "",
        f"{report.summary.cards} card(s) from {report.summary.findings} finding(s), "
        f"worst first. {report.rule_count} rules, {report.sentence_count} sentences.",
        "",
    ]
    for card in report.cards:
        lines.append("-" * 78)
        lines.append(f"[{card.number:02d}] {card.badge.upper()}  {card.rule_name}")
        lines.append(f"     {card.section_label}  ({card.rule_id}, severity {card.severity})")
        for quote in card.quotes:
            lines.append(f"     {quote.section}: \"{quote.sentence}\"")
        lines.append("")
        lines.append(f"  Why   : {card.why}")
        lines.append(f"  Change: {card.fix}")
        if card.ask:
            lines.append(f"  Ask   : {card.ask}")
        if card.fallback:
            lines.append(f"  If no : {card.fallback}")
        if card.walk_away:
            lines.append(f"  Never : {card.walk_away}")
        for note in card.notes:
            lines.append(f"  Note  : {note}")
        lines.append("")
    return "\n".join(lines) + "\n"
