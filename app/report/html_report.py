"""Render a Report as a single self-contained HTML file.

Design constraints, in order of importance:

1. **It must be honest.** No invented score, no "you are 82% safe". The numbers
   are counts of clauses the user can point at. Where we could not see something
   (clauses that are missing from the contract) the report says so out loud.
2. **It must print.** A freelancer will send this to a client or a lawyer. One
   file, no external CSS, no web fonts, no JS required to read it. Cards never
   split across pages.
3. **It must be safe to email.** No scripts except an optional copy button that
   degrades to nothing, no remote resources, no tracking, so it opens from a
   `file://` path and behind any corporate mail scanner.
4. English only (D-001), and the disclaimer is appended by code, always.

The visual language: editorial, not dashboard. Serif for the contract's own
words (so a quote reads as a quote), sans for everything we say about it.
"""

from __future__ import annotations

import html
import re

from app.report.disclaimer import DISCLAIMER, DISCLAIMER_SHORT
from app.report.renderer import Report, ReportCard
from app.site import SITE

# What the unlock button says. Kept next to the template, but sourced from
# site.py so the button, the pricing page and the Terms cannot drift apart.
PRICE = SITE.price

# --------------------------------------------------------------------------
# Escaping helpers
# --------------------------------------------------------------------------

_WS = re.compile(r"\s+")


def _e(text: str | None) -> str:
    return html.escape((text or "").strip(), quote=True)


def _raw(text: str) -> str:
    """Escape without trimming - used when re-joining split fragments."""
    return html.escape(text, quote=True)


def _sentence_html(sentence: str, matched: str) -> str:
    """Escape a sentence, wrapping the words that triggered the rule in <mark>.

    The highlight is cosmetic but it is also proof: it points at the exact span
    the rule engine matched, so a sceptical reader can check us in one glance.
    """
    sentence = _WS.sub(" ", sentence or "").strip()
    if not matched:
        return _e(sentence)
    needle = _WS.sub(" ", matched).strip()
    idx = sentence.lower().find(needle.lower())
    if idx < 0:
        return _e(sentence)
    end = idx + len(needle)
    return (
        _raw(sentence[:idx])
        + "<mark>"
        + _raw(sentence[idx:end])
        + "</mark>"
        + _raw(sentence[end:])
    )


def _plural(n: int, singular: str, plural: str | None = None) -> str:
    return singular if n == 1 else (plural or singular + "s")


# --------------------------------------------------------------------------
# Stylesheet
# --------------------------------------------------------------------------

CSS = """
:root {
  --ink: #14161b;
  --body: #3b424c;
  --muted: #6b7280;
  --line: #e4e4e0;
  --paper: #ffffff;
  --wash: #f6f5f2;
  --critical: #b42318;
  --critical-wash: #fef4f3;
  --serious: #b54708;
  --serious-wash: #fffaf0;
  --moderate: #475467;
  --moderate-wash: #f4f5f7;
  --minor: #667085;
  --minor-wash: #fafafa;
  --radius: 10px;
  --sans: ui-sans-serif, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --serif: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, "Times New Roman", serif;
}

* { box-sizing: border-box; }

html { -webkit-text-size-adjust: 100%; }

body {
  margin: 0;
  background: var(--wash);
  color: var(--body);
  font-family: var(--sans);
  font-size: 16px;
  line-height: 1.62;
  -webkit-font-smoothing: antialiased;
}

.page {
  max-width: 880px;
  margin: 0 auto;
  padding: 28px 20px 64px;
}

/* ---------- masthead ---------- */

.masthead {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--line);
  margin-bottom: 26px;
}

.wordmark {
  font-weight: 650;
  letter-spacing: -0.01em;
  color: var(--ink);
  font-size: 15px;
}

.wordmark span {
  display: inline-block;
  width: 9px;
  height: 9px;
  border-radius: 2px;
  background: var(--critical);
  margin-right: 8px;
}

.masthead__meta {
  font-size: 12.5px;
  color: var(--muted);
  text-align: right;
  line-height: 1.45;
}

.masthead__meta strong {
  display: block;
  color: var(--ink);
  font-weight: 550;
  font-size: 13px;
}

.masthead__legal {
  display: block;
  margin-top: 3px;
  font-size: 11px;
  letter-spacing: 0.01em;
  color: var(--muted);
}

/* ---------- hero ---------- */

.hero {
  background: var(--paper);
  border: 1px solid var(--line);
  border-top: 4px solid var(--critical);
  border-radius: var(--radius);
  padding: 34px 34px 28px;
  margin-bottom: 34px;
}

.hero--serious { border-top-color: var(--serious); }
.hero--moderate { border-top-color: var(--moderate); }
.hero--clean { border-top-color: #067647; }

.kicker {
  margin: 0 0 14px;
  font-size: 11.5px;
  font-weight: 650;
  letter-spacing: 0.13em;
  text-transform: uppercase;
  color: var(--critical);
}

.hero--serious .kicker { color: var(--serious); }
.hero--moderate .kicker { color: var(--moderate); }
.hero--clean .kicker { color: #067647; }

.hero h1 {
  margin: 0 0 14px;
  font-size: clamp(27px, 4.6vw, 40px);
  line-height: 1.12;
  letter-spacing: -0.025em;
  font-weight: 680;
  color: var(--ink);
  max-width: 21ch;
}

.hero__detail {
  margin: 0 0 28px;
  font-size: 17px;
  color: var(--body);
  max-width: 62ch;
}

.stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1px;
  background: var(--line);
  border: 1px solid var(--line);
  border-radius: 8px;
  overflow: hidden;
  margin: 0 0 20px;
  padding: 0;
  list-style: none;
}

.stats li {
  background: var(--paper);
  padding: 14px 14px 12px;
}

.stats__n {
  display: block;
  font-size: 30px;
  line-height: 1;
  font-weight: 640;
  letter-spacing: -0.03em;
  color: var(--ink);
  font-variant-numeric: tabular-nums;
}

.stats__n--zero { color: #b8bcc4; }

.stats__l {
  display: block;
  margin-top: 6px;
  font-size: 11.5px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--muted);
}

.dist {
  display: flex;
  height: 7px;
  border-radius: 99px;
  overflow: hidden;
  background: var(--wash);
  margin-bottom: 14px;
}

.dist span { display: block; height: 100%; }
.dist .b-critical { background: #d92d20; }
.dist .b-serious { background: #f79009; }
.dist .b-moderate { background: #98a2b3; }
.dist .b-minor { background: #d0d5dd; }

.hero__note {
  margin: 0;
  font-size: 12.5px;
  color: var(--muted);
}

/* ---------- generic section ---------- */

.section {
  margin-bottom: 36px;
}

.section > h2 {
  font-size: 12px;
  font-weight: 650;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--muted);
  margin: 0 0 16px;
}

/* ---------- fix these first ---------- */

.first {
  display: grid;
  gap: 1px;
  background: var(--line);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  overflow: hidden;
}

.first a {
  display: grid;
  grid-template-columns: 34px 1fr auto;
  align-items: baseline;
  gap: 12px;
  padding: 14px 18px;
  background: var(--paper);
  color: inherit;
  text-decoration: none;
}

.first a:hover { background: #fbfaf8; }

.first__n {
  font-size: 12px;
  font-weight: 650;
  color: var(--critical);
  font-variant-numeric: tabular-nums;
}

.first__t { color: var(--ink); font-weight: 550; }

.first__s {
  font-size: 12.5px;
  color: var(--muted);
  white-space: nowrap;
}

/* ---------- index table ---------- */

.index {
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  overflow: hidden;
}

.index table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

.index th {
  text-align: left;
  font-size: 10.5px;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--muted);
  font-weight: 600;
  padding: 10px 14px;
  background: #fbfaf8;
  border-bottom: 1px solid var(--line);
}

.index td {
  padding: 10px 14px;
  border-bottom: 1px solid #f0efec;
  vertical-align: baseline;
}

.index tr:last-child td { border-bottom: 0; }

.index a { color: var(--ink); text-decoration: none; font-weight: 500; }
.index a:hover { text-decoration: underline; }

.index__n { color: var(--muted); font-variant-numeric: tabular-nums; width: 34px; }
.index__sec { color: var(--muted); white-space: nowrap; width: 110px; }

/* ---------- cards ---------- */

.card {
  background: var(--paper);
  border: 1px solid var(--line);
  border-left: 4px solid var(--moderate);
  border-radius: var(--radius);
  padding: 26px 30px 24px;
  margin-bottom: 18px;
  position: relative;
}

.card--critical { border-left-color: var(--critical); }
.card--serious { border-left-color: #f79009; }
.card--moderate { border-left-color: #98a2b3; }
.card--minor { border-left-color: #d0d5dd; }

.card__ord {
  position: absolute;
  top: 20px;
  right: 26px;
  font-size: 12px;
  font-weight: 600;
  color: #c9ccd3;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.06em;
}

.badge {
  display: inline-block;
  font-size: 10.5px;
  font-weight: 650;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  padding: 3px 8px;
  border-radius: 4px;
  margin-bottom: 10px;
}

.badge--critical { background: var(--critical-wash); color: var(--critical); }
.badge--serious { background: var(--serious-wash); color: var(--serious); }
.badge--moderate { background: var(--moderate-wash); color: var(--moderate); }
.badge--minor { background: var(--minor-wash); color: var(--minor); }

.card h3 {
  margin: 0 0 6px;
  font-size: 21px;
  line-height: 1.25;
  letter-spacing: -0.015em;
  font-weight: 620;
  color: var(--ink);
  max-width: 34ch;
}

.card__where {
  margin: 0 0 18px;
  font-size: 12.5px;
  color: var(--muted);
}

.card__where span { color: #9aa0a9; }

.quotes { margin: 0 0 22px; }

.quote {
  margin: 0 0 10px;
  border-left: 2px solid #e0dfda;
  padding: 2px 0 2px 16px;
}

.quote:last-child { margin-bottom: 0; }

.quote__label {
  display: block;
  font-size: 10.5px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 4px;
}

.quote blockquote {
  margin: 0;
  font-family: var(--serif);
  font-size: 17px;
  line-height: 1.55;
  color: #22262d;
}

.quote mark {
  background: #fdeecd;
  color: inherit;
  padding: 1px 2px;
  border-radius: 2px;
}

.blocks { display: grid; gap: 16px; margin-bottom: 20px; }

.block h4 {
  margin: 0 0 4px;
  font-size: 11px;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--muted);
  font-weight: 650;
}

.block p { margin: 0; font-size: 15.5px; color: var(--body); }

.ask {
  background: #fbfaf7;
  border: 1px solid #eae8e2;
  border-radius: 8px;
  padding: 16px 18px;
  margin-bottom: 18px;
  position: relative;
}

.ask__label {
  margin: 0 0 6px;
  font-size: 11px;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--muted);
  font-weight: 650;
}

.ask__text {
  margin: 0;
  font-size: 15.5px;
  color: var(--ink);
  padding-right: 64px;
}

.copy {
  position: absolute;
  top: 14px;
  right: 14px;
  font: inherit;
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--muted);
  background: var(--paper);
  border: 1px solid #dcdad3;
  border-radius: 5px;
  padding: 4px 10px;
  cursor: pointer;
}

.copy:hover { color: var(--ink); border-color: #c4c1b8; }

.terms {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
  padding-top: 16px;
  border-top: 1px solid #f0efec;
}

.terms h5 {
  margin: 0 0 3px;
  font-size: 11px;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--muted);
  font-weight: 650;
}

.terms p { margin: 0; font-size: 14px; color: var(--body); }

.card__note {
  margin: 16px 0 0;
  font-size: 12.5px;
  color: var(--muted);
  font-style: italic;
  padding-top: 14px;
  border-top: 1px solid #f0efec;
}

/* ---------- limits + disclaimer ---------- */

.limits {
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 26px 30px;
  margin-bottom: 18px;
}

.limits h2 {
  margin: 0 0 12px;
  font-size: 16px;
  font-weight: 620;
  letter-spacing: -0.01em;
  color: var(--ink);
}

.limits ul { margin: 0; padding-left: 20px; }
.limits li { margin-bottom: 7px; font-size: 14.5px; }
.limits li:last-child { margin-bottom: 0; }

.disclaimer {
  background: #fbfaf7;
  border: 1px solid #e6e3da;
  border-radius: var(--radius);
  padding: 24px 30px;
  margin-bottom: 24px;
}

.disclaimer h2 {
  margin: 0 0 8px;
  font-size: 11px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  font-weight: 650;
  color: var(--muted);
}

.disclaimer p {
  margin: 0;
  font-size: 13.5px;
  line-height: 1.65;
  color: #4a5058;
}

.footer {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  font-size: 11.5px;
  color: #9aa0a9;
  border-top: 1px solid var(--line);
  padding-top: 14px;
}

/* ---------- responsive ---------- */

@media (max-width: 560px) {
  .page { padding: 18px 14px 48px; }
  .hero { padding: 24px 20px 20px; }
  .card { padding: 22px 20px; }
  .stats { grid-template-columns: repeat(2, 1fr); }
  .terms { grid-template-columns: 1fr; }
  .first a { grid-template-columns: 28px 1fr; }
  .first__s { display: none; }
  .index__sec { display: none; }
  .masthead { flex-direction: column; align-items: flex-start; gap: 4px; }
  .masthead__meta { text-align: left; }
  .copy { position: static; margin-top: 10px; }
  .ask__text { padding-right: 0; }
}

/* ---------- print ---------- */

@media print {
  @page { size: letter; margin: 15mm 14mm 16mm; }

  body { background: #fff; font-size: 10.5pt; }

  .page { max-width: none; padding: 0; }

  .no-print { display: none !important; }

  .hero {
    border-top-width: 3px;
    box-shadow: none;
    page-break-after: avoid;
  }

  .card, .limits, .disclaimer, .first, .index {
    break-inside: avoid;
    page-break-inside: avoid;
  }

  .card { margin-bottom: 12pt; padding: 14pt 16pt; }
  .card h3 { font-size: 14pt; }
  .quote blockquote { font-size: 11pt; }
  .block p { font-size: 10pt; }

  .section > h2 { break-after: avoid; page-break-after: avoid; }

  a { color: inherit !important; text-decoration: none !important; }

  .stats, .badge, .dist span, .quote mark, .ask, .disclaimer, .hero {
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
}

/* ---------- paywall (preview reports only) ---------- */

.paywall {
  margin: 34px 0 8px;
  padding: 26px 26px 24px;
  background: var(--ink);
  color: #e9e6dd;
  border-radius: var(--radius);
  border: 1px solid #000;
}

.paywall__kicker {
  margin: 0 0 10px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #b9b4a6;
}

.paywall__title {
  margin: 0 0 12px;
  font-family: var(--serif);
  font-size: 27px;
  line-height: 1.22;
  letter-spacing: -0.01em;
  color: #ffffff;
}

.paywall__body {
  margin: 0 0 16px;
  max-width: 60ch;
  font-size: 15px;
  color: #d3d0c6;
}

.paywall__counts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0 0 20px;
  padding: 0;
  list-style: none;
}

.paywall__counts li {
  padding: 5px 12px;
  border: 1px solid #3b3e46;
  border-radius: 999px;
  font-size: 12.5px;
  color: #e9e6dd;
}

.paywall__counts strong { color: #ffffff; font-weight: 650; }

.paywall__cta {
  display: inline-block;
  padding: 13px 24px;
  background: #ffffff;
  color: var(--ink) !important;
  border-radius: 8px;
  font-size: 15px;
  font-weight: 650;
  text-decoration: none !important;
}

.paywall__cta:hover { background: #efece3; }

.paywall__fine {
  margin: 14px 0 0;
  font-size: 12px;
  color: #9c988d;
}

.paywall__fine a { color: #c9c4b4 !important; }

@media print {
  /* The button is meaningless on paper; the headline and the counts are not -
     a printed preview should still say that it is a preview. */
  .paywall__cta { display: none; }
  .paywall { break-inside: avoid; page-break-inside: avoid; }
}
"""

JS = """
(function () {
  var buttons = document.querySelectorAll('[data-copy]');
  Array.prototype.forEach.call(buttons, function (button) {
    button.addEventListener('click', function () {
      var box = button.parentElement.querySelector('[data-copy-text]');
      if (!box) { return; }
      var text = box.textContent.replace(/\\s+/g, ' ').trim();
      var done = function () {
        var old = button.textContent;
        button.textContent = 'Copied';
        window.setTimeout(function () { button.textContent = old; }, 1600);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, fallback);
      } else {
        fallback();
      }
      function fallback() {
        var area = document.createElement('textarea');
        area.value = text;
        area.setAttribute('readonly', '');
        area.style.position = 'absolute';
        area.style.left = '-9999px';
        document.body.appendChild(area);
        area.select();
        try { document.execCommand('copy'); done(); } catch (e) { /* select it manually */ }
        document.body.removeChild(area);
      }
    });
  });
})();
"""


# --------------------------------------------------------------------------
# Fragments
# --------------------------------------------------------------------------

def _masthead(report: Report) -> str:
    return f"""
    <header class="masthead">
      <div class="wordmark"><span></span>Contract Redline</div>
      <div class="masthead__meta">
        <strong>{_e(report.source_name)}</strong>
        Report generated {_e(report.date_label)}
        <span class="masthead__legal">{_e(DISCLAIMER_SHORT)}</span>
      </div>
    </header>"""


def _stats(report: Report) -> str:
    counts = report.summary.counts
    cells = []
    for band, label in (
        ("critical", "Deal-breakers"),
        ("serious", "Serious"),
        ("moderate", "Costly"),
        ("minor", "Watch"),
    ):
        n = counts.get(band, 0)
        cls = "stats__n stats__n--zero" if n == 0 else "stats__n"
        cells.append(
            f'<li><span class="{cls}">{n}</span>'
            f'<span class="stats__l">{label}</span></li>'
        )
    return '<ul class="stats">' + "".join(cells) + "</ul>"


def _dist(report: Report) -> str:
    counts = report.summary.counts
    total = sum(counts.values()) or 1
    parts = []
    for band in ("critical", "serious", "moderate", "minor"):
        n = counts.get(band, 0)
        if n:
            width = n / total * 100
            parts.append(f'<span class="b-{band}" style="width:{width:.2f}%"></span>')
    if not parts:
        return ""
    return '<div class="dist" aria-hidden="true">' + "".join(parts) + "</div>"


def _hero(report: Report) -> str:
    summary = report.summary
    cards = summary.cards
    findings = summary.findings
    merged = summary.merged_away

    meta = (
        f"{findings} problem {_plural(findings, 'clause')} in "
        f"{cards} {_plural(cards, 'card')}"
    )
    if merged:
        meta += f" ({merged} duplicate {_plural(merged, 'clause')} folded together)"
    meta += (
        f" &middot; {report.rule_count} clause types checked across "
        f"{report.sentence_count} sentences"
    )

    return f"""
    <section class="hero hero--{summary.tone}">
      <p class="kicker">Contract risk report</p>
      <h1>{_e(summary.verdict)}</h1>
      <p class="hero__detail">{_e(summary.detail)}</p>
      {_stats(report)}
      {_dist(report)}
      <p class="hero__note">{meta}</p>
    </section>"""


def _top_three(report: Report) -> str:
    picks = report.top_three
    if len(picks) < 2:
        return ""
    rows = []
    for card in picks:
        rows.append(
            f'<a href="#card-{card.number}">'
            f'<span class="first__n">{card.number:02d}</span>'
            f'<span class="first__t">{_e(card.rule_name)}</span>'
            f'<span class="first__s">{_e(card.section_label)}</span>'
            f"</a>"
        )
    return f"""
    <section class="section">
      <h2>Start with these</h2>
      <div class="first">{"".join(rows)}</div>
    </section>"""


def _index_table(report: Report) -> str:
    if len(report.cards) < 3:
        return ""
    rows = []
    for card in report.cards:
        sections = ", ".join(card.group.sections) or "\u2014"
        rows.append(
            "<tr>"
            f'<td class="index__n">{card.number:02d}</td>'
            f'<td class="index__sec">{_e(sections)}</td>'
            f'<td><a href="#card-{card.number}">{_e(card.rule_name)}</a></td>'
            f'<td><span class="badge badge--{card.band}">{_e(card.badge)}</span></td>'
            "</tr>"
        )
    return f"""
    <section class="section">
      <h2>Everything we found</h2>
      <div class="index">
        <table>
          <thead>
            <tr>
              <th scope="col">#</th>
              <th scope="col">Clause</th>
              <th scope="col">Problem</th>
              <th scope="col">Severity</th>
            </tr>
          </thead>
          <tbody>{"".join(rows)}</tbody>
        </table>
      </div>
    </section>"""


def _quotes(card: ReportCard) -> str:
    blocks = []
    for quote in card.quotes:
        blocks.append(
            '<figure class="quote">'
            f'<span class="quote__label">{_e(quote.section)}</span>'
            f"<blockquote>{_sentence_html(quote.sentence, quote.matched)}</blockquote>"
            "</figure>"
        )
    return '<div class="quotes">' + "".join(blocks) + "</div>"


def _ask(card: ReportCard) -> str:
    if not card.ask:
        return ""
    return f"""
        <div class="ask">
          <p class="ask__label">Send this to your client</p>
          <p class="ask__text" data-copy-text>{_e(card.ask)}</p>
          <button type="button" class="copy no-print" data-copy>Copy</button>
        </div>"""


def _terms(card: ReportCard) -> str:
    if not (card.fallback or card.walk_away):
        return ""
    parts = []
    if card.fallback:
        parts.append(
            f"<div><h5>If they push back</h5><p>{_e(card.fallback)}</p></div>"
        )
    if card.walk_away:
        parts.append(
            f"<div><h5>Walk away if</h5><p>{_e(card.walk_away)}</p></div>"
        )
    return '<div class="terms">' + "".join(parts) + "</div>"


def _card(card: ReportCard) -> str:
    notes = "".join(f'<p class="card__note">{_e(n)}</p>' for n in card.notes)
    return f"""
    <article class="card card--{card.band}" id="card-{card.number}">
      <span class="card__ord">{card.number:02d}</span>
      <span class="badge badge--{card.band}">{_e(card.badge)}</span>
      <h3>{_e(card.rule_name)}</h3>
      <p class="card__where">{_e(card.section_label)} <span>&middot;</span> {_e(card.rule_id)}</p>
      {_quotes(card)}
      <div class="blocks">
        <div class="block"><h4>Why it matters</h4><p>{_e(card.why)}</p></div>
        <div class="block"><h4>What to change</h4><p>{_e(card.fix)}</p></div>
      </div>
      {_ask(card)}
      {_terms(card)}
      {notes}
    </article>"""


def _limits(report: Report) -> str:
    return f"""
    <section class="limits">
      <h2>What this report cannot tell you</h2>
      <ul>
        <li><strong>It only sees what is written down.</strong> We check
          {report.rule_count} specific clause types for problems that are
          present in the text. We cannot see a protection that is
          <em>missing</em> &mdash; a contract that says nothing about late
          payment is often worse than one that says the wrong thing.</li>
        <li><strong>One clause, one card.</strong> Where two neighbouring
          clauses raise the same problem, we fold them into a single card and
          list both sentences. If you change one, change both.</li>
        <li><strong>Your deal may justify a clause.</strong> A rush job, a
          six-figure fee, or a client you have worked with for years can make a
          clause reasonable that would be a trap for someone else. The severity
          is about the clause, not about your situation.</li>
        <li><strong>Negotiation is not legal advice.</strong> The wording below
          is a starting position, not a contract amendment. Anything you sign
          changes your rights.</li>
      </ul>
    </section>"""


def _disclaimer() -> str:
    return f"""
    <section class="disclaimer">
      <h2>Important &mdash; please read</h2>
      <p>{_e(DISCLAIMER)}</p>
    </section>"""


_BANDS = (
    ("critical", "deal-breaker", "deal-breakers"),
    ("serious", "serious", "serious"),
    ("moderate", "costly", "costly"),
    ("minor", "to watch", "to watch"),
)


def _paywall(report: Report, payment_url: str) -> str:
    """The block that replaces the cards nobody has paid for.

    It may only state numbers that are already true in `report.summary`, and it
    may not name a single locked clause: naming them would hand over most of the
    finding for free. Counts create the reason to pay; the quote, the why and
    the fix are what the $5 actually buys.
    """
    total = report.summary.cards
    shown = len(report.cards)
    hidden = total - shown
    if hidden <= 0:
        return ""

    counts = report.summary.counts
    shown_band = report.cards[-1].band if report.cards else ""
    chips = []
    for band, singular, plural in _BANDS:
        remaining = counts.get(band, 0) - (1 if band == shown_band else 0)
        if remaining > 0:
            word = singular if remaining == 1 else plural
            chips.append(f"<li><strong>{remaining}</strong> more {word}</li>")

    headline = (
        f"You are seeing 1 of the {total} problems we found."
        if shown == 1
        else f"You are seeing {shown} of the {total} problems we found."
    )

    return f"""
    <section class="paywall" id="unlock">
      <p class="paywall__kicker">Preview &middot; {shown} of {total} clauses</p>
      <h2 class="paywall__title">{_e(headline)}</h2>
      <p class="paywall__body">The other {hidden} are already analysed. Each one comes with the
        sentence quoted from your contract, a plain-English explanation of what it
        costs you, and the exact wording to send back to your client.</p>
      <ul class="paywall__counts">{"".join(chips)}</ul>
      <a class="paywall__cta" href="{_e(payment_url)}" target="_blank"
         rel="noopener noreferrer">Unlock the full report &mdash; {PRICE}</a>
      <p class="paywall__fine">One-time payment &middot; card handled by Stripe, we never see it
        &middot; refundable for 7 days &middot; no account needed<br>
        Already paid and still seeing this? Email us and we will unlock it by hand.</p>
    </section>"""


def _footer(report: Report) -> str:
    return f"""
    <footer class="footer">
      <span>Contract Redline &middot; {_e(report.date_label)}</span>
      <span>{_e(report.source_name)} &middot; {report.rule_count} rules &middot; {report.sentence_count} sentences</span>
    </footer>"""


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def render(report: Report, *, preview: bool = False, payment_url: str = "") -> str:
    """Return the complete HTML document as a string.

    `preview=True` adds the unlock block, but only when the report in hand
    actually has fewer cards than its own summary says. Passing `preview=True`
    with a full report changes nothing, so the flag can never half-lock a page.
    """
    title = f"Contract risk report — {report.source_name}"
    cards = "\n".join(_card(card) for card in report.cards)
    paywall = _paywall(report, payment_url or SITE.payment_url) if preview else ""

    body = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(title)}</title>
<meta name="description" content="Plain-English red-flag report for {_e(report.source_name)}. {_e(report.summary.verdict)}">
<meta name="robots" content="noindex, nofollow">
<style>{CSS}</style>
</head>
<body>
<div class="page">
  {_masthead(report)}
  <main>
    {_hero(report)}
    {_top_three(report)}
    {_index_table(report)}
    <section class="section">
      <h2>The clauses, one by one</h2>
      {cards}
    </section>
    {paywall}
  </main>
  {_limits(report)}
  {_disclaimer()}
  {_footer(report)}
</div>
<script>{JS}</script>
</body>
</html>
"""
    return body
