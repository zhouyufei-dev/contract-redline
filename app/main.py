"""Command-line entry point.

    python -m app.main <file>                      # dump the extracted text
    python -m app.main <file> --scan               # run the 20 rules
    python -m app.main <file> --scan --explain     # + plain-English cards
    python -m app.main <file> --scan --html        # + a shareable HTML report

Everything below the scan shares one model: findings are merged into cards by
app/engine/scoring.py, then filled in by DeepSeek, then rendered. The terminal
and the HTML cannot disagree about what the report says.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from app.engine.matcher import STATUS_REVIEW, STATUS_SUPPRESSED
from app.parsers.extractor import ExtractionError, extract_text
from app import pipeline
from app.report import renderer
from app.rules.redlines_us import RULES

SEVERITY_LABEL = {10: "FATAL", 7: "SERIOUS", 5: "HIGH", 3: "MEDIUM"}
RULE = "=" * 78
DEFAULT_OUTPUT_DIR = Path("data/outputs")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="contract-redline",
        description="Read a freelance service contract and list its red flags.",
    )
    parser.add_argument("file", help="Path to a .pdf, .docx or .txt contract")
    parser.add_argument("--save", action="store_true",
                        help="Also write the extracted text to data/outputs/")
    parser.add_argument("--chars", type=int, default=0,
                        help="Only print the first N characters (default: everything)")
    parser.add_argument("--scan", action="store_true",
                        help="Run the red-flag rules instead of dumping the text")
    parser.add_argument("--explain", action="store_true",
                        help="Ask DeepSeek to explain each finding (needs .env)")
    parser.add_argument("--html", nargs="?", const="auto", metavar="PATH",
                        help="Write an HTML report (default: data/outputs/<name>.report.html)")
    parser.add_argument("--open", action="store_true",
                        help="Open the HTML report in the default browser")
    parser.add_argument("--no-llm", action="store_true",
                        help="Force a rules-only report: no API calls at all")
    parser.add_argument("--no-cache", action="store_true",
                        help="Ignore cached explanations and call the API every time")
    parser.add_argument("--save-report", nargs="?", const="auto", metavar="PATH",
                        help="Write the plain-text transcript (default: data/outputs/<name>.scan.txt)")
    parser.add_argument("--show-suppressed", action="store_true",
                        help="Also list hits that the negation gate suppressed")
    return parser


class Sink:
    """Prints to the terminal and, optionally, remembers every line for a file."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def __call__(self, text: str = "") -> None:
        print(text)
        self.lines.append(text)

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"


def _print_findings(findings, show_suppressed: bool, out: Sink) -> None:
    """The evidence view: every raw hit, with the pattern and the gate verdict."""
    reportable = [f for f in findings if f.is_reportable]
    suppressed = [f for f in findings if f.status == STATUS_SUPPRESSED]

    out(RULE)
    out(f"RED FLAGS FOUND: {len(reportable)}")
    out(RULE)

    if not reportable:
        out("\nNo matches for the rules currently implemented "
            f"({', '.join(r.id for r in RULES)}).")
        out("This does NOT mean the contract is safe.")

    for i, f in enumerate(reportable, start=1):
        label = SEVERITY_LABEL.get(f.severity, "?")
        clause = f"Section {f.clause}" if f.clause else "un-numbered clause"
        out(f"\n[{i}] {f.rule_id} {f.rule_name}  -  {label} ({f.severity})")
        out(f"    Where : {clause}")
        out(f"    Quote : \"{f.sentence}\"")
        out(f"    Match : \"{f.matched_text}\"  ({f.pattern_label})")
        if f.value is not None:
            out(f"    Value : {f.value} days")
        if f.status == STATUS_REVIEW:
            out(f"    Note  : needs a human look - {f.reason}")

    out("")
    out(RULE)
    out(f"GATE: {len(suppressed)} hit(s) suppressed by the negation check")
    out(RULE)
    if suppressed or show_suppressed:
        for f in suppressed:
            clause = f"Section {f.clause}" if f.clause else "un-numbered"
            out(f"\n  x {f.rule_id} {clause} \"{f.matched_text}\"")
            out(f"    reason: {f.reason}")


def _print_cards(report: renderer.Report, out: Sink) -> None:
    summary = report.summary
    out("")
    out(RULE)
    out(f"REPORT: {summary.cards} card(s) from {summary.findings} finding(s)")
    out(RULE)
    out()
    out(summary.verdict.upper())
    out(summary.detail)
    out()
    if summary.merged_away:
        out(f"{summary.merged_away} duplicate clause(s) folded into neighbouring "
            "cards (same rule, consecutive sections).")
        out()

    for card in report.cards:
        out("-" * 78)
        out(f"[{card.number:02d}] {card.badge.upper()}  {card.rule_name}")
        out(f"     {card.section_label}  ({card.rule_id}, severity {card.severity})")
        for quote in card.quotes:
            out(f"     {quote.section}: \"{quote.sentence}\"")
        out()
        out(f"  Why    : {card.why}")
        out(f"  Change : {card.fix}")
        if card.ask:
            out(f"  Ask    : {card.ask}")
        if card.fallback:
            out(f"  If no  : {card.fallback}")
        if card.walk_away:
            out(f"  Walk   : {card.walk_away}")
        for note in card.notes:
            out(f"  Note   : {note}")
        out()


def _print_llm_stats(stats, out: Sink) -> None:
    out(RULE)
    out("LLM RUN SUMMARY")
    out(RULE)
    out(f"  findings explained : {stats.findings}")
    out(f"  API calls          : {stats.api_calls}  "
        f"(cached: {stats.cached}, repaired after a rejected answer: {stats.repaired}, "
        f"fell back to rule text: {stats.fallbacks})")
    out(f"  tokens             : {stats.prompt_tokens:,} in / "
        f"{stats.completion_tokens:,} out / {stats.total_tokens:,} total "
        f"({stats.tokens_per_finding:.0f} per finding)")
    if stats.cached:
        out(f"  served from cache  : {stats.cached} card(s), "
            f"~{stats.tokens_saved_estimate:,} tokens not re-billed")
    out(f"  wall clock         : {stats.wall_seconds:.2f}s "
        f"(slowest single call {stats.slowest:.2f}s)")
    if stats.problems:
        out("  guardrail notes    :")
        for problem in stats.problems:
            out(f"    - {problem}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out = Sink()

    try:
        text = extract_text(args.file)
    except ExtractionError as exc:
        print(f"\n[ERROR] {exc}\n", file=sys.stderr)
        return 1

    source = Path(args.file)
    out(RULE)
    out(f"FILE       : {source.name}")
    out(f"CHARACTERS : {len(text):,}")
    out(f"WORDS      : {len(text.split()):,}")
    out(RULE)
    out()

    if not args.scan and not args.html:
        body = text if not args.chars else text[: args.chars]
        out(body)
        if args.chars and len(text) > args.chars:
            out(f"\n... [{len(text) - args.chars:,} more characters]")
        out()
        out(RULE)
        if args.save:
            _save_text(source, text, out)
        return 0

    outcome = pipeline.scan_text(text, source_name=source.name)
    sentences = outcome.sentences
    findings = outcome.findings
    scan_seconds = outcome.seconds

    out(f"Parsed into {len(sentences)} sentences.")
    out(f"Running {len(RULES)} rule(s): {', '.join(r.id for r in RULES)}")
    out(f"Rule engine took {scan_seconds:.3f}s\n")

    _print_findings(findings, args.show_suppressed, out)

    groups = outcome.groups
    if groups and len(groups) < sum(len(g.findings) for g in groups):
        out("")
        out(f"Merged: {sum(len(g.findings) for g in groups)} findings -> "
            f"{len(groups)} cards (same rule, consecutive clauses).")

    # --- explanations -----------------------------------------------------
    cards = None
    stats = None
    wants_explain = (args.explain or args.html is not None) and not args.no_llm
    if wants_explain and groups:
        def announce(count: int, settings) -> None:
            out("")
            out(f"Explaining {count} card(s) with {settings.model} "
                f"({settings.max_workers} at a time)...")

        explanation = pipeline.explain(
            outcome, use_cache=not args.no_cache, on_start=announce
        )
        if explanation.skipped_reason:
            out("")
            out(f"[SKIPPED] {explanation.skipped_reason}")
        elif explanation.error:
            out("")
            out(f"[LLM ERROR] {explanation.error}")
            out("Falling back to the rule engine's own wording.")
        else:
            cards = explanation.cards
            stats = explanation.stats

    report = pipeline.build_report(outcome, cards)

    if args.explain:
        _print_cards(report, out)
    if stats is not None:
        _print_llm_stats(stats, out)

    # --- HTML -------------------------------------------------------------
    if args.html is not None:
        target = _output_path(source, args.html, ".report.html")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(pipeline.render_html(report), encoding="utf-8")
        out("")
        out(RULE)
        out(f"HTML REPORT: {target.resolve()}")
        out(f"  {report.summary.cards} cards, worst first, disclaimer appended by code.")
        out(RULE)
        if args.open:
            _open_in_browser(target)

    if args.save or args.save_report:
        _save_text(source, text, out, report=args.save_report)

    return 0


def _output_path(source: Path, requested: str, suffix: str) -> Path:
    if requested == "auto":
        return DEFAULT_OUTPUT_DIR / f"{source.stem}{suffix}"
    path = Path(requested)
    if not path.is_absolute() and path.parent == Path("."):
        return DEFAULT_OUTPUT_DIR / path
    return path


def _open_in_browser(path: Path) -> None:
    import os
    import webbrowser

    try:
        if sys.platform == "win32":
            os.startfile(str(path.resolve()))  # type: ignore[attr-defined]
        else:
            webbrowser.open(path.resolve().as_uri())
    except Exception as exc:  # pragma: no cover - environment specific
        print(f"[NOTE] could not open the browser automatically: {exc}")


def _save_text(source: Path, text: str, out: Sink, report: str | None = None) -> None:
    out_dir = DEFAULT_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    extracted = out_dir / f"{source.stem}.extracted.txt"
    extracted.write_text(text, encoding="utf-8")
    out(f"\nExtracted text saved to: {extracted}")

    if report:
        target = _output_path(source, report, ".scan.txt")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(out.text(), encoding="utf-8")
        out(f"Scan transcript saved to: {target}")


if __name__ == "__main__":
    raise SystemExit(main())
