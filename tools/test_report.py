"""Tests for the report layer: merging, summary and the HTML output.

Run from the project root:
    .\\.venv\\Scripts\\python.exe tools\\test_report.py

The rule engine has its own suite (tools/test_rules.py). This one checks the
things that only exist once findings become a document a human reads:

  A. Merging       - the same rule on 4.1 + 4.2 becomes one card, never two
  B. Summary       - the headline matches the worst finding, counts add up
  C. Report model  - cards are ordered worst-first, quotes stay verbatim
  D. HTML safety   - escaping, no remote resources, no CJK
  E. HTML structure- anchors resolve, disclaimer is last, print CSS present
  F. Degraded runs - no API key, LLM fallback, review-only findings

Exit code is non-zero if anything fails.
"""

from __future__ import annotations

import html as html_lib
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.engine.matcher import STATUS_CONFIRMED, STATUS_REVIEW, Finding, scan  # noqa: E402
from app.engine.scoring import (  # noqa: E402
    MAX_MERGE,
    band_label,
    display_order,
    group_findings,
    summarise,
)
from app.engine.textnorm import prepare  # noqa: E402
from app.parsers.extractor import extract_text  # noqa: E402
from app.report import renderer  # noqa: E402
from app.report.disclaimer import DISCLAIMER, DISCLAIMER_SHORT  # noqa: E402
from app.report.html_report import render  # noqa: E402
from app.rules.redlines_us import RULES  # noqa: E402

SAMPLE = ROOT / "data" / "samples" / "fake_contract_01.docx"

failures: list[str] = []
total_checks = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global total_checks
    total_checks += 1
    mark = "PASS" if condition else "FAIL"
    extra = f"  <- {detail}" if detail and not condition else ""
    print(f"  [{mark}] {label}{extra}")
    if not condition:
        failures.append(label)


def section(title: str) -> None:
    print(f"\n{title}")
    print("-" * 74)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def finding(rule_id: str, clause: str, sentence: str, severity: int = 10,
            rule_name: str = "Test rule", status: str = STATUS_CONFIRMED,
            matched: str = "", offset: int = 0) -> Finding:
    return Finding(
        rule_id=rule_id,
        rule_name=rule_name,
        severity=severity,
        status=status,
        matched_text=matched or sentence[:24],
        sentence=sentence,
        clause=clause,
        offset=offset,
        pattern_label="test pattern",
    )


def run_sample() -> tuple[list, list]:
    text = extract_text(str(SAMPLE))
    sentences = prepare(text)
    return sentences, scan(sentences, RULES)


def build_report(cards=None) -> renderer.Report:
    sentences, findings = run_sample()
    groups = group_findings(findings)
    return renderer.build(
        groups,
        cards,
        source_name=SAMPLE.name,
        sentence_count=len(sentences),
        rule_count=len(RULES),
    )


def strip_tags(doc: str) -> str:
    return re.sub(r"<[^>]+>", " ", doc)


def collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
             "link", "meta", "source", "track", "wbr"}


class Balance(HTMLParser):
    """Minimal well-formedness check: every element closed, in the right order.

    We do not ship a validator, but an unclosed <div> silently changes the
    layout of an email-ready document, so it is worth one cheap check.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag not in VOID_TAGS:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in VOID_TAGS:
            return
        if not self.stack:
            self.errors.append(f"stray </{tag}>")
            return
        if self.stack[-1] != tag:
            self.errors.append(f"</{tag}> closes <{self.stack[-1]}>")
            while self.stack and self.stack.pop() != tag:
                pass
            return
        self.stack.pop()


# ---------------------------------------------------------------------------
# A. Merging
# ---------------------------------------------------------------------------

section("A. Merging duplicate clauses")

f41 = finding("R08", "4.1", "Contractor assigns all right, title and interest in the Work.", 10, offset=10)
f42 = finding("R08", "4.2", "All Deliverables shall be deemed work made for hire.", 10, offset=20)
groups = group_findings([f41, f42])
check("4.1 + 4.2 under one rule merge into a single card", len(groups) == 1, f"got {len(groups)}")
check("the merged card keeps both quotes", len(groups[0].findings) == 2)
check("the merged card reads as 'Sections 4.1 and 4.2'",
      groups[0].section_label == "Sections 4.1 and 4.2", groups[0].section_label)

f51 = finding("R08", "5.1", "Contractor assigns the Work.", 10, offset=40)
groups = group_findings([f41, f42, f51])
check("consecutive numbers in a different section are not merged", len(groups) == 2)

f43 = finding("R08", "4.3", "Contractor waives all moral rights.", 10, offset=30)
groups = group_findings([f41, f42, f43, f51])
check("merging stops at three clauses, the fourth starts a new card",
      len(groups[0].findings) == MAX_MERGE, f"got {len(groups[0].findings)}")

f21 = finding("R01", "2.1", "Client pays in sixty days.", 7, offset=10)
f23 = finding("R01", "2.3", "Client pays the final invoice in ninety days.", 7, offset=30)
check("a gap in numbering (2.1 then 2.3) is not merged", len(group_findings([f21, f23])) == 2)

f44 = finding("R08", "4.4", "Contractor assigns the Work.", 10, offset=50)
check("an exact duplicate sentence is not merged", len(group_findings([f41, f44])) == 2)

check("two different rules on the same section stay separate",
      len(group_findings([
          finding("R08", "4.1", "Contractor assigns the Work.", 10, offset=10),
          finding("R09", "4.2", "Contractor waives moral rights.", 5, offset=20),
      ])) == 2)

check("un-numbered clauses are never merged",
      len(group_findings([
          finding("R05", "", "Unlimited revisions apply.", 10, offset=10),
          finding("R05", "", "Unlimited revisions apply again.", 10, offset=20),
      ])) == 2)

check("a suppressed finding never becomes a card",
      not group_findings([finding("R05", "3.1", "x", status="suppressed")]))

sentences, findings = run_sample()
sample_groups = group_findings(findings)
sample_report = renderer.build(sample_groups, None, source_name=SAMPLE.name,
                               sentence_count=len(sentences), rule_count=len(RULES))
reportable = [f for f in findings if f.is_reportable]
check(f"the sample contract still yields {len(reportable)} findings", len(reportable) == 24,
      f"got {len(reportable)}")
check("those findings collapse into 20 cards", len(sample_groups) == 20,
      f"got {len(sample_groups)}")
check("every finding is represented exactly once",
      sum(len(g.findings) for g in sample_groups) == len(reportable))
check("merged_away counts what was folded away",
      sample_report.summary.merged_away == len(reportable) - len(sample_groups))


# ---------------------------------------------------------------------------
# B. Summary
# ---------------------------------------------------------------------------

section("B. Summary and headline")

summary = sample_report.summary
check("counts add up to the number of cards",
      sum(summary.counts.values()) == summary.cards, str(summary.counts))
check("a contract with a severity-10 clause gets the hardest verdict",
      summary.tone == "critical" and "not sign" in summary.verdict.lower(), summary.verdict)
check("the headline never claims the contract is safe", "safe" not in summary.verdict.lower())

only_mild = summarise(group_findings([
    finding("R19", "9.1", "Keep it secret forever.", 3, offset=1)
]))
check("a low-severity-only contract does not get the walk-away verdict",
      only_mild.tone == "moderate", only_mild.tone)

clean = summarise([])
check("an empty scan still says it cannot see what is missing",
      clean.tone == "clean" and "missing" in clean.detail.lower(), clean.detail)

check("severity bands are named for consequences, not numbers",
      band_label(10) == "Deal-breaker" and band_label(3) == "Watch",
      f"{band_label(10)} / {band_label(3)}")

order = display_order(sample_groups)
check("cards are ordered worst first",
      all(order[i].severity >= order[i + 1].severity for i in range(len(order) - 1)))


# ---------------------------------------------------------------------------
# C. Report model
# ---------------------------------------------------------------------------

section("C. Report model")

cards = sample_report.cards
check("card numbering is 1..n with no gaps",
      [c.number for c in cards] == list(range(1, len(cards) + 1)))

merged_cards = [c for c in cards if len(c.quotes) > 1]
check("merged cards keep every verbatim quote", all(len(c.quotes) > 1 for c in merged_cards)
      and len(merged_cards) >= 3, f"{len(merged_cards)} merged cards")

check("every card carries a why and a fix",
      all(c.why and c.fix for c in cards))
check("every card names the rule that produced it",
      all(c.rule_id.startswith("R") for c in cards))

primary_group = sample_groups[0]
check("the longest sentence in a group is the one explained",
      len(primary_group.primary.sentence) == max(len(f.sentence) for f in primary_group.findings))

# A quote must be the contract's own words, character for character.
source_text = collapse(extract_text(str(SAMPLE)))
missing = [
    q.sentence for c in cards for q in c.quotes
    if collapse(q.sentence) not in source_text
]
check("every quoted sentence exists verbatim in the contract", not missing, str(missing[:1]))


# ---------------------------------------------------------------------------
# D. HTML safety
# ---------------------------------------------------------------------------

section("D. HTML output: safety")

doc = render(sample_report)
plain = collapse(strip_tags(doc))

check("the disclaimer appears word for word", collapse(DISCLAIMER) in plain)
check("the report is a complete document",
      doc.startswith("<!doctype html>") and doc.rstrip().endswith("</html>"))
check("it declares English", 'lang="en"' in doc)
check("no remote stylesheet, font or image",
      "src=" not in doc and "http://" not in doc and "https://" not in doc,
      "found an external reference")
check("no external script", "<script src" not in doc)
check("no CJK characters reach the page",
      not re.search(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]", doc))

# A hostile contract must not be able to inject markup.
evil = finding("R05", "3.1", 'Contractor agrees <script>alert("x")</script> to revise.', 10,
               offset=1, matched="<script>")
evil_groups = group_findings([evil])
evil_report = renderer.build(evil_groups, None, source_name="<img src=x onerror=alert(1)>.docx",
                             sentence_count=1, rule_count=20)
evil_doc = render(evil_report)
check("a script tag inside the contract is escaped, not executed",
      "<script>alert" not in evil_doc and "&lt;script&gt;" in evil_doc)
check("a hostile file name is escaped",
      "<img src=x" not in evil_doc and "&lt;img" in evil_doc)
check("the matched span is highlighted, and the highlight is escaped",
      "<mark>&lt;script&gt;</mark>" in evil_doc)

blockquotes = re.findall(r"<blockquote>(.*?)</blockquote>", doc, flags=re.S)
quotes = [q for c in cards for q in c.quotes]
check("every quote is rendered, one blockquote per quoted sentence",
      len(blockquotes) == len(quotes), f"{len(blockquotes)} vs {len(quotes)}")
check("highlighting never drops or adds a space",
      [collapse(html_lib.unescape(re.sub(r"</?mark>", "", b))) for b in blockquotes]
      == [collapse(q.sentence) for q in quotes])


# ---------------------------------------------------------------------------
# E. HTML structure
# ---------------------------------------------------------------------------

section("E. HTML output: structure")

check("there is one card element per card",
      doc.count('<article class="card') == len(cards), f"{doc.count('<article class=\"card')} vs {len(cards)}")
check("every internal link points at a real card",
      all(f'id="card-{n}"' in doc for n in re.findall(r'href="#card-(\d+)"', doc)))
check("the overview comes before the first card",
      doc.index('class="hero') < doc.index('<article class="card'))
check("the disclaimer comes after the last card",
      doc.index('class="disclaimer') > doc.index('id="card-%d"' % len(cards)))
check("the disclaimer is the second to last thing on the page, before the footer",
      doc.index('class="disclaimer') < doc.index('class="footer'))
check("the short disclaimer sits in the header, above every card",
      collapse(html_lib.unescape(DISCLAIMER_SHORT)) in collapse(html_lib.unescape(doc[:doc.index('class="hero')]))
      and doc.index('masthead__legal') < doc.index('id="card-1"'))
check("print rules are present", "@media print" in doc and "@page" in doc)
check("cards are told not to split across printed pages",
      "break-inside: avoid" in doc)
check("the whole thing is one file with its CSS inline",
      "<style>" in doc and "</style>" in doc)
parser = Balance()
parser.feed(doc)
check("every HTML element is closed in the right order",
      not parser.errors and not parser.stack,
      f"{parser.errors[:3]} unclosed={parser.stack[:3]}")
check("total size stays shareable (< 200 KB)", len(doc.encode("utf-8")) < 200_000,
      f"{len(doc.encode('utf-8')) // 1024} KB")
check("four severity counters are shown up front",
      doc.count('class="stats__n') + doc.count('stats__n stats__n--zero') >= 4)


# ---------------------------------------------------------------------------
# F. Degraded runs
# ---------------------------------------------------------------------------

section("F. Degraded runs")

check("a report builds with no LLM cards at all", "Why it matters" in doc)
check("it still explains every card with the rule engine's own wording",
      all(c.source == "rule" for c in sample_report.cards))

fake_card = renderer.ReportCard(
    number=1, group=sample_groups[0], why="w", fix="f", source="fallback"
)
fallback_report = renderer.build(
    [sample_groups[0]], [fake_card], source_name="x.docx", sentence_count=1, rule_count=20
)
check("a fallback card is labelled in the report",
      any("standard guidance" in n for n in fallback_report.cards[0].notes))

review_group = group_findings([finding("R12", "8.1", "Liability shall be unlimited.", 10,
                                       status=STATUS_REVIEW, offset=1)])
review_report = renderer.build(review_group, None, source_name="x.docx",
                               sentence_count=1, rule_count=20)
check("a borderline match is flagged for the reader, not hidden",
      any("borderline" in n for n in review_report.cards[0].notes))

text = renderer.to_text(sample_report)
check("the terminal summary is English-only",
      not re.search(r"[\u4e00-\u9fff]", text))
check("the terminal summary lists every card",
      len(re.findall(r"^\[\d\d\] ", text, flags=re.MULTILINE)) == len(cards),
      str(len(re.findall(r"^\[\d\d\] ", text, flags=re.MULTILINE))))


# ---------------------------------------------------------------------------

print()
if failures:
    print(f"RESULT: {len(failures)} of {total_checks} check(s) FAILED")
    for item in failures:
        print(f"  - {item}")
    raise SystemExit(1)

print(f"RESULT: all {total_checks} checks passed")
