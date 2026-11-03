"""One contract in, one report out - the pipeline, with no UI in it.

The terminal (`app/main.py`) and the web UI (`app/web/streamlit_app.py`) both
call this module. Neither of them is allowed to know the order of the steps:
if the order ever changes, it changes in exactly one place.

The four steps are deliberately separate rather than one `analyze()` call,
because the CLI prints between them ("Parsed into 124 sentences...") and the
web UI shows a different progress line at each one.

    1. scan_contract(path)     extract text -> normalise -> 20 rules -> merge
    2. explain(groups)         DeepSeek writes prose for the merged cards
    3. build_report(...)       assemble the Report model
    4. render_html(report)     paint it

Step 2 is the only one allowed to fail without losing the report: a dead API,
a bad key or a rate limit must still produce a usable rules-only report.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from app.engine.matcher import Finding, scan
from app.engine.scoring import RiskGroup, Summary, group_findings
from app.engine.textnorm import prepare
from app.parsers.extractor import extract_text
from app.report import renderer
from app.rules.redlines_us import RULES


@dataclass
class ScanOutcome:
    """Everything the rule engine produced, before any prose exists."""

    source_name: str
    text: str
    sentences: list[str]
    findings: list[Finding]
    groups: list[RiskGroup]
    seconds: float

    @property
    def reportable(self) -> list[Finding]:
        return [f for f in self.findings if f.is_reportable]

    @property
    def merged_away(self) -> int:
        return sum(len(g.findings) for g in self.groups) - len(self.groups)


@dataclass
class Explanation:
    """What step 2 produced, including why it produced nothing."""

    cards: list | None = None
    stats: object | None = None
    skipped_reason: str | None = None
    error: str | None = None

    @property
    def used_llm(self) -> bool:
        return bool(self.cards)


def scan_contract(path: str | Path, *, source_name: str | None = None) -> ScanOutcome:
    """Step 1, from a file: extract the text, then run the rules on it."""
    file = Path(path)
    text = extract_text(file)
    return scan_text(text, source_name=source_name or file.name)


def scan_text(text: str, *, source_name: str) -> ScanOutcome:
    """Step 1, from text that is already extracted.

    Split out so a caller that has already parsed the file (the CLI prints the
    extracted text before scanning it) does not pay to parse a PDF twice.
    """
    started = time.perf_counter()
    sentences = prepare(text)
    findings = scan(sentences, RULES)
    seconds = time.perf_counter() - started
    return ScanOutcome(
        source_name=source_name,
        text=text,
        sentences=sentences,
        findings=findings,
        groups=group_findings(findings),
        seconds=seconds,
    )


def explain(
    outcome: ScanOutcome,
    *,
    use_cache: bool = True,
    on_start=None,
) -> Explanation:
    """Step 2: ask DeepSeek for the prose. Never raises.

    `is_reportable` filtering happens inside `enrich`; the cards come back in
    document order, one per group, which is what `build_report` expects.

    `on_start(count, settings)` is called once, immediately before the API
    calls begin - the CLI prints its progress line from there, so the message
    still appears while the work is running rather than after it.
    """
    from app.config import ConfigError, get_settings

    if not outcome.groups:
        return Explanation(skipped_reason="nothing to explain")

    settings = get_settings()
    if not settings.api_key:
        return Explanation(
            skipped_reason="DEEPSEEK_API_KEY is not set, so this report uses "
            "the rule engine's own wording instead of tailored explanations."
        )

    if on_start is not None:
        on_start(len(outcome.groups), settings)

    try:
        from app.llm.deepseek_client import enrich

        cards, stats = enrich(
            [g.primary for g in outcome.groups],
            settings=settings,
            use_cache=use_cache,
        )
        return Explanation(cards=cards, stats=stats)
    except ConfigError as exc:
        return Explanation(skipped_reason=str(exc))
    except Exception as exc:  # network/auth must not lose the scan
        return Explanation(error=f"{type(exc).__name__}: {exc}")


def build_report(
    outcome: ScanOutcome,
    cards: list | None = None,
    *,
    generated_at: datetime | None = None,
) -> renderer.Report:
    """Step 3."""
    return renderer.build(
        outcome.groups,
        cards,
        source_name=outcome.source_name,
        sentence_count=len(outcome.sentences),
        rule_count=len(RULES),
        generated_at=generated_at,
    )


def render_html(report: renderer.Report, *, preview: bool = False) -> str:
    """Step 4. `preview=True` adds the unlock block after the cards."""
    from app.report.html_report import render

    return render(report, preview=preview)


# --------------------------------------------------------------------------
# Convenience: all four steps, for callers that want one call
# --------------------------------------------------------------------------

@dataclass
class Analysis:
    outcome: ScanOutcome
    report: renderer.Report
    explanation: Explanation = field(default_factory=Explanation)
    html: str = ""

    @property
    def summary(self) -> Summary:
        return self.report.summary

    @property
    def preview_html(self) -> str:
        """The free teaser: the worst card only, plus the unlock block.

        Built on demand and from a trimmed Report, so the cards that were not
        paid for are never serialised at all.
        """
        return render_html(renderer.preview(self.report), preview=True)


def analyze(
    path: str | Path,
    *,
    use_llm: bool = True,
    use_cache: bool = True,
    source_name: str | None = None,
    on_step=None,
) -> Analysis:
    """The whole pipeline. Raises ExtractionError / ConfigError, nothing else.

    `on_step(label)` is called before each phase, for a UI that wants to say
    what it is doing. The labels are plain English and safe to show a user;
    never put a file path or a key in them.
    """
    def step(label: str) -> None:
        if on_step is not None:
            on_step(label)

    step(f"Reading the document and checking {len(RULES)} red-flag clauses")
    outcome = scan_contract(path, source_name=source_name)
    if use_llm:
        step("Writing plain-English explanations for each problem")
        explanation = explain(outcome, use_cache=use_cache)
    else:
        explanation = Explanation(
            skipped_reason="explanations were switched off for this run"
        )
    step("Laying out your report")
    report = build_report(outcome, explanation.cards)
    return Analysis(
        outcome=outcome,
        report=report,
        explanation=explanation,
        html=render_html(report),
    )
