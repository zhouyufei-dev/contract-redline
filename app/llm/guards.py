"""Guardrails for LLM output.

The rule engine decides WHAT is a risk. The model only writes prose. This module
is the fence between the two: every card the model returns is inspected here,
and if it breaks a rule the card is thrown away.

Three things are being defended against:

  1. **Hallucinated evidence.** The most dangerous failure is a card that quotes
     something the contract does not say. We check every quoted span against the
     actual clause text. A quote that is not in the clause is a fabrication,
     full stop.
  2. **Scope creep.** The model drifting into clauses it was not given, or
     citing a section number that does not exist in this contract.
  3. **Language drift.** The report is English-only (D-001) and must never
     claim to be legal advice.

A card that fails is retried once with the problems listed, then replaced by the
rule's own hand-written `why`/`fix`. The report therefore always renders - the
worst case is losing the model's flavour, never the finding itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Any CJK / kana / hangul block. The product is English-only (D-001).
_NON_LATIN = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff]")

_QUOTED = re.compile(r'["\u201c\u201d\u2018\u2019\']([^"\u201c\u201d\u2018\u2019\']{4,160})["\u201c\u201d\u2018\u2019\']')
_RULE_REF = re.compile(r"\bR\d{2}\b")
_SECTION_REF = re.compile(r"\b(?:section|clause|article|§)\s*(\d+(?:\.\d+)*)", re.I)
_MONEY = re.compile(r"\$\s?([\d,]+(?:\.\d{1,2})?)")
_PUNCT = re.compile(r"[^\w\s]")
_WS = re.compile(r"\s+")

_FORBIDDEN = [
    (re.compile(r"\bas an ai\b|\blanguage model\b|\bi am an ai\b", re.I),
     "mentions being an AI"),
    (re.compile(r"\battorney[- ]client\b", re.I),
     "claims an attorney-client relationship"),
    (re.compile(r"\b(this|it) (is|constitutes) legal advice\b", re.I),
     "claims to be legal advice"),
    (re.compile(r"\b(is|are) (perfectly )?(safe|fine|standard|standard practice)\b", re.I),
     "tells the user a flagged clause is safe"),
    (re.compile(r"\bstatute\b|\bU\.?S\.?C\.?\b|\b§\s*\d", re.I),
     "cites a statute"),
]

MAX_LEN = {
    "why": 420,
    "fix": 340,
    "ask": 240,
    "fallback": 240,
    "walk_away": 160,
}

MIN_LEN = {"why": 30, "fix": 15, "ask": 12, "fallback": 12, "walk_away": 6}


def norm(text: str) -> str:
    """Lower-case, strip punctuation, collapse whitespace — for quote matching."""
    return _WS.sub(" ", _PUNCT.sub(" ", text.lower())).strip()


def money_amounts(text: str) -> set[str]:
    """Dollar figures as bare digits: '$5,000' and '$5000' both become '5000'."""
    return {digits.replace(",", "").rstrip(".") for digits in _MONEY.findall(text)}


@dataclass(frozen=True)
class ContractFacts:
    """What the model is allowed to refer to."""

    clause: str
    rule_id: str
    known_clauses: frozenset[str]


def check_card(card: dict, facts: ContractFacts) -> list[str]:
    """Return a list of human-readable problems. Empty list means it passed."""
    problems: list[str] = []

    for field, field_max in MAX_LEN.items():
        value = card.get(field)
        if not isinstance(value, str) or not value.strip():
            problems.append(f'"{field}" is missing or empty')
            continue
        text = value.strip()
        if len(text) > field_max:
            problems.append(f'"{field}" is {len(text)} chars, limit {field_max}')
        if len(text) < MIN_LEN[field]:
            problems.append(f'"{field}" is too short to be useful')

    joined = " ".join(str(card.get(k, "")) for k in MAX_LEN)

    if _NON_LATIN.search(joined):
        problems.append("contains non-English characters (report is English-only)")

    for pattern, label in _FORBIDDEN:
        if pattern.search(joined):
            problems.append(label)

    for ref in set(_RULE_REF.findall(joined)):
        if ref != facts.rule_id:
            problems.append(f"refers to another rule ({ref})")

    for num in set(_SECTION_REF.findall(joined)):
        if num not in facts.known_clauses:
            problems.append(f"references section {num}, which is not in this contract")

    # Money is the number a freelancer will act on, so inventing one is the same
    # crime as inventing a quote. A dollar figure the model writes must appear
    # in the clause it was given. (Percentages and day counts are advice, not
    # claims about the contract, so those stay free.)
    allowed_money = money_amounts(facts.clause)
    for value in money_amounts(joined):
        if value not in allowed_money:
            problems.append(f"cites ${value}, which does not appear in the clause")

    # The anti-hallucination check: every quoted span must be real text.
    # Checked field by field, so a stray quote in one field cannot pair up with
    # a quote in the next and look like a fabricated quotation.
    clause_norm = norm(facts.clause)
    for field in MAX_LEN:
        text = card.get(field)
        if not isinstance(text, str):
            continue
        for span in _QUOTED.findall(text):
            span_norm = norm(span)
            if len(span_norm.split()) < 3:
                continue  # a 1-2 word emphasis like "per day" is fine
            if span_norm not in clause_norm:
                problems.append(
                    f'{field} quotes text that is not in the clause: "{span.strip()[:60]}"'
                )

    return problems


def repair_instruction(problems: list[str]) -> str:
    listed = "\n".join(f"- {p}" for p in problems)
    return (
        "Your previous answer was rejected for these reasons:\n"
        f"{listed}\n\n"
        "Rewrite it. Return ONLY the same five-key JSON object. "
        "Quote nothing that is not in the clause, mention no other section, "
        "write plain English.\n"
        "Do not go vague to be safe: keep the advice concrete. Percentages, "
        "day counts and phrases like 'cap it at the fee' are always fine. "
        "Only drop dollar amounts you made up as if they were in this contract."
    )
