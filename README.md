# Contract Redline Scanner — MVP

Plain-English red-flag reports for freelance service contracts.

**Target user:** US-based freelancers (designers, developers) who sign client
contracts without a lawyer.
**MVP scope:** text-based PDF + DOCX only · 20 fixed red-flag rules · US market only.

## Architecture (this is the whole point)

```
contract file
     |
     v
[1] app/parsers/    extract plain text            (PDF / DOCX)      <-- DONE
     |
     v
[2] app/rules/      deterministic regex rules     <-- decides IF a risk exists,
     |                                                and quotes the evidence
     v
[3] app/engine/     negation check, scoring, ranking
     |
     v
[4] app/llm/        DeepSeek explains WHY it is a trap   <-- DONE, never decides IF
     |              and HOW to negotiate it                  (guards.py rejects
     |                                                       invented quotes/money)
     v
[5] app/report/     English report + hardcoded disclaimer
```

The split matters: the rule engine is the single source of truth for *what the
contract says*. The LLM only writes prose. That is what keeps the output free of
hallucination — the quoted clause is always real text from the user's file.

## Environment

Installed and verified on this machine:

| Item | Value |
|---|---|
| Python | 3.12.10 (`%LOCALAPPDATA%\Programs\Python\Python312\python.exe`) |
| Virtual env | `.venv/` in the project root |
| Packages | pdfplumber 0.11.10 · python-docx 1.2.0 · fpdf2 2.9.0 (dev only) |

### Where the keys come from

`app/config.py` is still the only module that reads configuration, and it now
reads three sources, lowest priority first:

| Source | Used by | Notes |
|---|---|---|
| `.env` | local development | git-ignored; never leaves this machine |
| Streamlit secrets | the deployed app | Settings → Secrets on Streamlit Cloud |
| process environment | one-off runs | `$env:DEEPSEEK_API_KEY=...` |

The deployed site has no `.env`, so without the middle row it would start with no
DeepSeek key and no Stripe key: the page would load, but explanations would fall
back to rule text and no payment could ever be verified. `.streamlit/secrets.toml.example`
shows the exact shape; the real `secrets.toml` is git-ignored.

Deployment steps, including the switch from Stripe test mode to live: **`docs/11-第11步-部署上线手册.md`**.

## How to run

```powershell
.\run.ps1 data/samples/fake_contract_01.docx
.\run.ps1 data/samples/fake_contract_01.pdf -Save
.\run.ps1 data/samples/fake_contract_01.docx -Scan            # run the rules
.\run.ps1 data/samples/fake_contract_01.docx -Scan -ShowSuppressed
.\run.ps1 data/samples/fake_contract_01.docx -Scan -Explain  # + DeepSeek explanations
.\run.ps1 data/samples/fake_contract_01.docx -Scan -Explain -SaveReport
.\run.ps1 data/samples/fake_contract_01.docx -Scan -Html   # client-facing HTML report
.\run.ps1 data/samples/fake_contract_01.docx -Scan -Html -Open
```

### Web UI

```powershell
.\web.ps1                 # http://localhost:8501
.\web.ps1 -Port 8600      # if 8501 is taken
```

Upload a PDF or DOCX in the browser, press **Scan My Contract**, and the HTML
report renders in the page with a download button. The first run installs
Streamlit once (`requirements-web.txt`, ~50 MB); after that the server starts in
a few seconds. `Ctrl+C` in that window stops it.

The first card is free; the other nineteen sit behind a $5 one-off payment
(`app/web/paywall.py`). To test the paid flow, see `docs/10-第10步-付费墙说明.md`.
Without `STRIPE_SECRET_KEY` in `.env` the site still runs and still scans, but a
returning payment is refused rather than guessed at - it never unlocks for free.

Same pipeline, same rules, same report as the CLI - `app/pipeline.py` holds the
four steps and both entry points call it, so the page cannot drift from the
terminal. `app/web/` contains no analysis logic at all.

The report lands in `data/outputs/<name>.report.html`: one self-contained file
(CSS inlined, no fonts or images to fetch), so it opens by double-click and
survives being emailed as an attachment. `Ctrl+P` in the browser gives a clean
Letter-size PDF - the print stylesheet keeps cards from breaking across pages.

`run.ps1` calls the venv's Python for you — no activation needed.
Without it: `.\.venv\Scripts\python.exe -m app.main <file>`.

## Tests

```powershell
.\.venv\Scripts\python.exe tools\check_step3.py        # extractor acceptance
.\.venv\Scripts\python.exe tools\check_pdf_quality.py  # tx/docx/pdf damage report
.\.venv\Scripts\python.exe tools\test_rules.py         # cumulative rule suite (297 checks)
.\.venv\Scripts\python.exe tools\stress_clean.py       # false-positive storm on clean boilerplate
.\.venv\Scripts\python.exe tools\test_llm.py           # LLM layer, offline (45 checks, no key)
.\.venv\Scripts\python.exe tools\test_report.py        # report layer (56 checks, no key)
.\.venv\Scripts\python.exe tools\test_config.py        # key sources and precedence (16 checks, no key)
.\.venv\Scripts\python.exe tools\test_web.py           # upload gate + page render (44 checks, no key)
.\.venv\Scripts\python.exe tools\test_site.py          # legal pages + site structure (106 checks, no key)
.\.venv\Scripts\python.exe tools\test_site.py --strict # same, and fails on leftover placeholders
.\.venv\Scripts\python.exe tools\test_paywall.py       # teaser, Stripe proof, gate (64 checks, no key)
powershell -File tools\run_all.ps1                     # every suite above, in one go
.\.venv\Scripts\python.exe tools\llm_smoke.py          # one real API call, for a key check
```

## Status

**Step 9 (partial): the site publishes Terms, Privacy, Refund and Pricing.**

Each is a real route (`/terms`, `/privacy`, `/refund`, `/pricing`), reached from a
footer on every page, and each carries the operator's name, address and email —
the things a payment-processor review looks for. Payment is paused until the
Stripe Hong Kong account exists; nothing is charged today.

**Step 8 done: a one-page web front end (`.\web.ps1`).**

Title, one paragraph, one upload box, one button. Nothing else on the page is
clickable. While the scan runs the page shows a live status list ("Reading the
document and checking 20 red-flag clauses", "Writing plain-English
explanations", "Laying out your report") rather than a spinner that says nothing.
The result is the same self-contained HTML file the CLI writes, embedded in a
frame, with a download button - what the user sees is byte-for-byte what they
download.

Two behaviours worth knowing: a file that is not really a PDF/DOCX (an old
`.doc` renamed, a phone photo renamed `.pdf`) is rejected before parsing with a
sentence explaining what to do, and the upload is written to a temp folder that
is deleted in a `finally` block, so no contract text is left on disk after a
scan. The AI-explanation toggle is exposed because turning it off is a real use
case (no key configured, or the user wants the rule wording only) - the set of
red flags is identical either way.

**Step 7 done: the findings now render as a client-facing HTML report.**

Structure is fixed: a risk overview at the top (verdict, four severity counts, a
"start with these" shortlist, a full index table), one card per red flag in the
middle (the verbatim clause with the offending words highlighted, *why it
matters*, *what to change*, a copy-paste ask, push-back and walk-away lines),
and the hardcoded disclaimer at the end. `app/report/renderer.py` builds a
`Report` model and `html_report.py` only renders it, so a PDF renderer or a web
frontend can consume the same object later.

Two opinionated calls (D-019): consecutive sibling clauses that trip the same
rule are **merged into one card** - 24 findings become 20 cards, and the model is
asked to explain only the longest sentence in each group, which is why the run
above costs 20 calls instead of 24. And there is **no 0-100 risk score**: a
single uncapped indemnity makes a contract unsignable, and averaging it with nine
minor issues would let the number talk the user out of that.

**Step 6 (unchanged): the rule brain is still the judge; DeepSeek is only the translator.**

Every finding now gets a plain-English card (`why` / `fix` / `ask` / `fallback` /
`walk_away`) written by `deepseek-chat`. The model never sees the whole contract
and never decides whether a risk exists - it sees one matched sentence plus that
rule's hand-written anchors. Its answer is checked by `app/llm/guards.py`: quotes
must exist in the sentence, dollar figures must exist in the sentence, no Chinese,
no statutes, no other rule ids. A rejected card is retried once, then replaced by
the rule's own text, so the report always renders.

Measured on the fake contract: 24 findings, 24 cards, 28 API calls (4 rewritten
after the money guard fired), 26,943 tokens, **12.7s** with 4 workers; a second
run of the same file is served entirely from cache (0 calls, 0.0s). Roughly one
US cent of tokens per contract. Full write-up: `docs/06-...md`.

**Step 5d (unchanged): all twenty rules (R01-R20) run end-to-end. The rule brain is frozen.**

On the fake contract the scanner reports 24 red flags across 24 clauses - one card
per sentence the user would actually have to strike (1.1 R06, 1.2 R07, 2.2 R01,
2.3 R02, 2.4 R03, 2.5 R04, 3.1 R05, 4.1 R08, 4.2 R08, 4.3 R09, 4.4 R09, 4.5 R10,
5.1 R20, 6.1 R11, 6.2 R12, 7.2 R13, 8.1 R14, 8.2 R15, 9.1 R19, 9.2 R19, 10.1 R18,
10.2 R18, 11.2 R17, 12.1 R16) - and suppresses exactly 1 (3.2). All 20 rules fire
somewhere. Same answer from PDF, DOCX and TXT, and no clause is ever reported by
two different rules.

297 automated checks in `tools/test_rules.py` cover the answer key, negation traps,
direction traps, cross-rule isolation and a clean contract. `tools/stress_clean.py`
hammers the rules with 74 harmless sentences - the IP clauses that are normal
commercial practice (plain assignment of the deliverable, perpetual non-exclusive
licence, client adapting the work for its own use), the liability clauses that are
normal practice (a cap that exists, a mutual termination right, a fault-scoped
indemnity), and the restrictive covenants that are normal practice (a freelancer
free to serve other clients, an amendment clause that needs both signatures, a
mutual jury waiver, a late fee in the freelancer's favour) - and expects zero hits.

Deliberately **not** reported, and why: see D-014 in `docs/00-决策记录.md`. In
short - a governing-law clause, a *mutual* attorneys'-fees clause, a *mutual*
jury waiver and "compliant with all applicable laws" appear in essentially every
commercial contract; a card the user cannot act on is worse than no card.

- Locked product decisions: `docs/00-决策记录.md`
- The 20 rules: `docs/01-合同红线清单.md`
- What every folder is for: `docs/02-目录说明.md`
- Test contract + expected answers: `docs/03-测试合同标准答案.md`
- How the matcher works: `docs/04-第4步-匹配引擎说明.md`
- Rule expansion batches 5a-5d: `docs/05-第5步-规则扩充说明.md`
- DeepSeek integration, guards and cost: `docs/06-第6步-DeepSeek接入说明.md`
- Report layout, card design and print-to-PDF: `docs/07-第7步-报告排版说明.md`
- Web front end, upload gate and how to run it: `docs/08-第8步-前端页面说明.md`

## Roadmap

1. [x] Red-flag list v1.0 — 20 rules confirmed
2. [x] Project skeleton
3. [x] Read a PDF/DOCX and print its text
4. [x] Implement 3 rules first (R01, R02, R05) and print raw hits
5. [x] Implement all 20 rules in 4 batches (5a: R03/R04/R06/R07; 5b: R08/R09/R10; 5c: R11/R12/R13; 5d: R14-R20)
6. [x] Connect DeepSeek for explanations
7. [x] Report rendering + disclaimer
8. [x] Streamlit web UI (upload -> report)
9. [x] Legal pages (Terms / Privacy / Refund) + pricing, at stable URLs
10. [ ] Payment (Stripe HK) - paused
