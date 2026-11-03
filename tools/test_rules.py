"""Cumulative regression suite for the rule engine.

Run from the project root:
    .\\.venv\\Scripts\\python.exe tools\\test_rules.py

Grows with every batch. Sections:
  A.  Fake contract vs the answer key (docs/03)
  B.  Synthetic negations          - must NOT fire
  C.  Synthetic positives          - MUST fire
  D.  Numeric thresholds
  E.  Cross-rule isolation
  F.  Reinforcing negation         - must still fire
  F2. Idioms that only look like negations
  G.  Evidence integrity
  H.  Clean contract               - must find nothing
  I.  R03 pay-when-paid            (5a)
  J.  R04 set-off                  (5a)
  K.  R06 open scope               (5a)
  L.  R07 free extra work          (5a)
  M.  No clause is reported twice  (5a)

Exit code is non-zero if anything fails.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.engine.matcher import (  # noqa: E402
    STATUS_CONFIRMED,
    STATUS_SUPPRESSED,
    Pattern,
    Rule,
    scan,
)
from app.engine.textnorm import prepare  # noqa: E402
from app.parsers.extractor import extract_text  # noqa: E402
from app.rules.redlines_us import (  # noqa: E402
    R01, R02, R03, R04, R05, R06, R07, R08, R09, R10, R11, R12, R13,
    R14, R15, R16, R17, R18, R19, R20, RULES,
)

BY_ID = {r.id: r for r in RULES}

failures: list[str] = []
total_checks = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global total_checks
    total_checks += 1
    print(f"  [{'PASS' if condition else 'FAIL'}] {label}" + (f"  <- {detail}" if detail else ""))
    if not condition:
        failures.append(label)


def fired(text: str, rule=None) -> set[str]:
    """Rule ids that produced a reportable finding for this text."""
    rules = [rule] if rule else RULES
    found = scan(prepare(text), rules)
    return {f.rule_id for f in found if f.is_reportable and f.status != STATUS_SUPPRESSED}


def suppressed(text: str, rule) -> list:
    return [f for f in scan(prepare(text), [rule]) if f.status == STATUS_SUPPRESSED]


# ==========================================================================
# A. The fake contract, against docs/03-测试合同标准答案.md
# ==========================================================================

print("\n=== A. Fake contract (answer key) ===")

contract = extract_text("data/samples/fake_contract_01.docx")
findings = scan(prepare(contract), RULES)
reportable = [f for f in findings if f.is_reportable]

# Step 5d answer key: one rule per planted clause, twenty-four reports. R08 and
# R09 each own two clauses - two separate sentences the user has to strike, so
# two separate cards is the correct output, not a duplicate. R17 and R18 and
# R19 each own two clauses for the same reason: 10.1 (time of the essence) is a
# different sentence to fix than 10.2 (the $500/day), 9.1 than 9.2.
#
# Deliberately ABSENT from the key, and listed as traps below:
#   11.1  governing law only  - universal boilerplate, no decision for the user
#   11.3  mutual prevailing-party fees - standard; fired on clean boilerplate
#   11.4  mutual jury waiver  - standard, and moot inside arbitration
#   5.2   "uninterrupted ... on schedule" - the shape docs/01 lists, downgraded
#   12.2  one-way assignment  - a real gap, but not one of the twenty (MVP)
EXPECTED = {
    ("R06", "1.1"),
    ("R07", "1.2"),
    ("R01", "2.2"),
    ("R02", "2.3"),
    ("R03", "2.4"),
    ("R04", "2.5"),
    ("R05", "3.1"),
    ("R08", "4.1"),
    ("R08", "4.2"),
    ("R09", "4.3"),
    ("R09", "4.4"),
    ("R10", "4.5"),
    ("R11", "6.1"),
    ("R12", "6.2"),
    ("R13", "7.2"),
    ("R14", "8.1"),
    ("R15", "8.2"),
    ("R19", "9.1"),
    ("R19", "9.2"),
    ("R18", "10.1"),
    ("R18", "10.2"),
    ("R17", "11.2"),
    ("R16", "12.1"),
    ("R20", "5.1"),
}
got_pairs = {(f.rule_id, f.clause) for f in reportable}

check("exactly 24 red flags reported", len(reportable) == 24, f"got {len(reportable)}")
check("every expected (rule, clause) pair is present",
      got_pairs == EXPECTED,
      f"missing={sorted(EXPECTED - got_pairs)} extra={sorted(got_pairs - EXPECTED)}")

by_pair = {(f.rule_id, f.clause): f for f in reportable}

check("R01 extracted 60 days from 2.2",
      ("R01", "2.2") in by_pair and by_pair[("R01", "2.2")].value == 60)
check("R03 quotes the pass-through wording in 2.4",
      ("R03", "2.4") in by_pair and "receipt of payment from the end client" in by_pair[("R03", "2.4")].sentence)
check("R04 quotes the set-off wording in 2.5",
      ("R04", "2.5") in by_pair and "set off" in by_pair[("R04", "2.5")].matched_text)
check("R06 quotes the open-scope wording in 1.1",
      ("R06", "1.1") in by_pair and "including but not limited to" in by_pair[("R06", "1.1")].matched_text)
check("R07 quotes the free-work wording in 1.2",
      ("R07", "1.2") in by_pair and "at no additional cost" in by_pair[("R07", "1.2")].matched_text)
check("R08 quotes the expensive part in 4.1 (unused directions, not the vague sweep)",
      ("R08", "4.1") in by_pair and by_pair[("R08", "4.1")].matched_text.lower() == "unused directions")
check("R08 quotes the actual 4.2 body, not the bare heading",
      ("R08", "4.2") in by_pair and len(by_pair[("R08", "4.2")].sentence) > 80)
check("R09 quotes the portfolio ban in 4.4",
      ("R09", "4.4") in by_pair and "portfolio" in by_pair[("R09", "4.4")].matched_text)
check("R10 quotes the AI-training clause in 4.5",
      ("R10", "4.5") in by_pair and "machine learning" in by_pair[("R10", "4.5")].matched_text)

check("R20 quotes 'error-free' in 5.1",
      ("R20", "5.1") in by_pair and "error-free" in by_pair[("R20", "5.1")].matched_text)
check("R14 quotes the ban, starting at 'shall not'",
      ("R14", "8.1") in by_pair
      and by_pair[("R14", "8.1")].matched_text.lower().startswith("shall not")
      and "competitor" in by_pair[("R14", "8.1")].matched_text)
check("R15 quotes the solicitation ban, not the bare heading",
      ("R15", "8.2") in by_pair and "solicit" in by_pair[("R15", "8.2")].matched_text)
check("R19 quotes the perpetuity wording in 9.2",
      ("R19", "9.2") in by_pair and "in perpetuity" in by_pair[("R19", "9.2")].matched_text)
check("R19 quotes 'whether or not marked' in 9.1",
      ("R19", "9.1") in by_pair and "whether or not" in by_pair[("R19", "9.1")].matched_text)
check("R18 quotes the per-day damages in 10.2",
      ("R18", "10.2") in by_pair and "per day" in by_pair[("R18", "10.2")].matched_text)
check("R17 quotes the arbitration seat in 11.2",
      ("R17", "11.2") in by_pair and "arbitration" in by_pair[("R17", "11.2")].matched_text)
check("11.3 (mutual fee-shifting) is not reported",
      ("R17", "11.3") not in by_pair)
check("R16 quotes the unilateral amendment in 12.1",
      ("R16", "12.1") in by_pair and "may modify" in by_pair[("R16", "12.1")].matched_text.lower())

# 2.4 is a fatal clause - but for R03, NOT because 15 days is a long term.
check("2.4 is reported by R03 only (15 days is not a long payment term)",
      ("R01", "2.4") not in by_pair and ("R03", "2.4") in by_pair)

# Clauses that LOOK like traps but must stay silent for every rule shipped so far.
# 4.4 (portfolio consent) used to be on this list: it is a false positive for the
# payment rules (R02 reads "consent ... sole discretion" as acceptance wording).
# As of 5b it is a genuine R09 trap, so it moved to the EXPECTED answer key.
clauses_hit = {f.clause for f in reportable}
for clause, why in [
    ("3.2", "shall not request unlimited revisions"),
    ("2.6", "no interest / late fee waiver"),
    ("2.7", "suspend work after 30 days"),
    ("6.3", "shall not be liable for client materials"),
    ("1.3", "change order clause (looks open, is closed)"),
    ("5.2", "uninterrupted + on schedule - downgraded, see R20 notes"),
    ("11.1", "governing law only - universal boilerplate"),
    ("11.3", "mutual prevailing-party fees - standard boilerplate"),
    ("11.4", "mutual jury waiver - standard, moot in arbitration"),
    ("12.2", "one-way assignment - real gap, outside the twenty"),
    ("12.5", "force majeure - mutual relief, not a liability cap"),
]:
    check(f"trap {clause} ({why}) NOT reported", clause not in clauses_hit)

check("4.4 is only reported by R09 - consent wording is not an acceptance trap",
      [f.rule_id for f in reportable if f.clause == "4.4"] == ["R09"],
      str([f.rule_id for f in reportable if f.clause == "4.4"]))

gate = [f for f in findings if f.status == STATUS_SUPPRESSED]
check("negation gate suppressed exactly 1 hit", len(gate) == 1, f"got {len(gate)}")
check("suppressed hit is R05 in 3.2", bool(gate) and gate[0].rule_id == "R05" and gate[0].clause == "3.2")

# Same answers from the PDF - proves the normaliser survives line wrapping.
pdf_reportable = [f for f in scan(prepare(extract_text("data/samples/fake_contract_01.pdf")), RULES)
                  if f.is_reportable]
check("PDF produces the same 24 red flags", len(pdf_reportable) == 24, f"got {len(pdf_reportable)}")
check("PDF finds the same (rule, clause) pairs",
      {(f.rule_id, f.clause) for f in pdf_reportable} == EXPECTED)

# Plain text round-trip.
txt_reportable = [f for f in scan(prepare(extract_text("data/samples/fake_contract_01.txt")), RULES)
                  if f.is_reportable]
check("TXT produces the same 24 red flags", len(txt_reportable) == 24, f"got {len(txt_reportable)}")


# ==========================================================================
# B. Synthetic traps
# ==========================================================================

print("\n=== B. Synthetic negations (must NOT fire) ===")

NEG_CASES = [
    ("R05", "Client shall not request unlimited revisions to approved work."),
    ("R05", "Contractor is not obligated to provide unlimited revisions."),
    ("R05", "Neither party shall require unlimited revisions under this SOW."),
    ("R05", "Client may never demand unlimited revisions after sign-off."),
    ("R02", "Client shall not withhold payment on any undisputed invoice."),
    ("R02", "No acceptance by Client shall be unreasonably withheld, and payment is due regardless."),
    ("R01", "Client shall pay interest on late payment after thirty (30) days."),
    ("R01", "Payment is due within thirty (30) days of the invoice date."),
]
for rule_id, sentence in NEG_CASES:
    got = fired(sentence, BY_ID[rule_id])
    check(f"{rule_id} skips: {sentence[:52]}...", rule_id not in got, f"fired {got}")

print("\n=== C. Synthetic positives (MUST fire) ===")

POS_CASES = [
    ("R01", "Client shall pay each invoice within ninety (90) days of receipt."),
    ("R01", "Payment terms are Net 60 from the invoice date."),
    ("R01", "Client will pay Net sixty (60) days after invoice."),
    ("R01", "All invoices are payable within 45 days from receipt of invoice."),
    ("R02", "Final payment is subject to Client's acceptance of the Deliverables."),
    ("R02", "Client may withhold payment until Client is satisfied with the work."),
    ("R02", "Contractor shall not be paid until Client issues written acceptance."),
    ("R05", "Contractor shall provide unlimited rounds of revisions."),
    ("R05", "Contractor will revise the Deliverables until Client is satisfied."),
    ("R05", "Contractor shall make revisions as many times as necessary."),
]
for rule_id, sentence in POS_CASES:
    got = fired(sentence, BY_ID[rule_id])
    check(f"{rule_id} fires: {sentence[:52]}...", rule_id in got, f"got {got or 'nothing'}")

print("\n=== D. Numeric threshold ===")

check("Net 30 is not a red flag", "R01" not in fired("Payment is Net 30.", R01))
check("Net 45 is a red flag", "R01" in fired("Payment is Net 45.", R01))
check("15 days is not a red flag", "R01" not in fired("Pay within fifteen (15) days.", R01))
check("cure period of 45 days is not a payment term",
      "R01" not in fired("Contractor may suspend work if payment is more than forty-five (45) days after written notice.", R01))

print("\n=== E. Cross-rule isolation ===")

check("R02 does not fire on a revisions clause",
      "R02" not in fired("Contractor shall provide revisions until Client is satisfied.", R02))
check("R05 does not fire on an acceptance clause",
      "R05" not in fired("Payment is due until Client is satisfied with the deliverables.", R05))
check("R02 does not fire on a portfolio consent clause",
      "R02" not in fired("Contractor shall not display work without Client's prior written consent, "
                         "which Client may withhold in its sole discretion.", R02))

print("\n=== F. Reinforcing negation (must still fire) ===")

check("'shall not be deemed accepted until' IS the risk",
      "R02" in fired("Deliverables shall not be deemed accepted until Client issues written acceptance.", R02))
check("'no obligation to pay until acceptance' IS the risk",
      "R02" in fired("Client has no obligation to pay until acceptance of the Deliverables.", R02))

print("\n=== F2. Idioms that only look like negations ===")

R11_PROBE = Rule(
    id="RX1", name="probe", severity=10, why="", fix="",
    patterns=(Pattern(regex=re.compile(r"without\s+limitation", re.I), label="probe"),),
)
probe = scan(prepare("Contractor shall indemnify Client without limitation as to amount."), [R11_PROBE])
check("'without limitation' is not treated as a negation",
      bool(probe) and probe[0].status == STATUS_CONFIRMED,
      probe[0].status if probe else "no hit")

check("'no later than 60 days' still counts as a long payment term",
      "R01" in fired("Client shall pay no later than sixty (60) days after invoice.", R01))
check("'whether or not' does not cancel a revision clause",
      "R05" in fired("Contractor shall provide unlimited revisions, whether or not Client pays.", R05))

print("\n=== G. Evidence integrity ===")

sample = "2.5 Terms. Client shall pay within ninety (90) days of invoice."
f = [x for x in scan(prepare(sample), [R01]) if x.is_reportable]
check("clause number attached", bool(f) and f[0].clause == "2.5", f[0].clause if f else "none")
check("quoted sentence is verbatim from input", bool(f) and f[0].sentence in sample.replace("  ", " "))
check("Offset points inside the document", bool(f) and 0 <= f[0].offset < len(sample))

print("\n=== H. Clean contract (must find nothing) ===")

CLEAN = """
MASTER SERVICES AGREEMENT

1. FEES. Client shall pay each invoice within fifteen (15) days of receipt.
2. REVISIONS. The fee includes two (2) rounds of revisions. Additional rounds
   are billed at the hourly rate in Exhibit A.
3. ACCEPTANCE. Deliverables are accepted when Contractor delivers them and
   Client does not object in writing within five (5) business days.
4. TERM. Either party may terminate on thirty (30) days' written notice.
5. LIABILITY. Contractor's aggregate liability shall not exceed the fees paid.
6. SCOPE. Contractor shall deliver exactly the items listed in Exhibit A.
7. EXPENSES. Client reimburses pre-approved travel at cost.
8. PAYMENT SOURCE. Client is solely responsible for payment; Contractor's fees
   are not subject to Client's receipt of payment from any third party.
"""

clean_findings = [x for x in scan(prepare(CLEAN), RULES) if x.is_reportable]
check("clean contract produces zero findings", len(clean_findings) == 0,
      ", ".join(f"{x.rule_id}@{x.clause}" for x in clean_findings) or "none")


# ==========================================================================
# I. R03 - pay-when-paid (step 5a)
# ==========================================================================

print("\n=== I. R03 pay-when-paid ===")

R03_MUST_FIRE = [
    "Client shall pay Contractor within fifteen (15) days after Client's receipt of payment from the end client.",
    "This Agreement is a pay-when-paid contract.",
    "Payment to Contractor is conditioned upon receipt of payment from the Owner.",
    "Contractor acknowledges that Client's obligations hereunder are funded by Client's end client.",
    "Client shall remit payment to Contractor upon receipt of payment from the prime contractor.",
]
for s in R03_MUST_FIRE:
    check(f"R03 fires: {s[:55]}...", "R03" in fired(s, R03), f"got {fired(s, R03) or 'nothing'}")

R03_MUST_NOT_FIRE = [
    # Killed by the generic negation gate.
    "Nothing in this Agreement shall be construed as a pay-when-paid arrangement.",
    "Client's obligation to pay is not subject to receipt of payment from the end client.",
    # Killed by context_none: this is the CURE, not the trap.
    "Client shall pay within thirty (30) days of invoice regardless of whether the end client has paid.",
    # Killed by context_any: no money in the sentence.
    "The Deliverables were designed for Client's end client, Northwind Retail.",
    # A different clause entirely: receipt of the deliverable, not of money.
    "Client shall confirm receipt of the Deliverables within five (5) business days.",
]
for s in R03_MUST_NOT_FIRE:
    check(f"R03 skips: {s[:55]}...", "R03" not in fired(s, R03), f"fired {fired(s, R03)}")

check("R03 does not steal R01's long-payment clause",
      "R03" not in fired("Client shall pay each invoice within sixty (60) days of the invoice date.", R03))


# ==========================================================================
# J. R04 - unilateral set-off (step 5a)
# ==========================================================================

print("\n=== J. R04 set-off ===")

R04_MUST_FIRE = [
    "Client may deduct from any invoice any amounts it believes are owed.",
    "Client shall have the right to deduct chargebacks from amounts due to Contractor.",
    "Client may withhold any amount owed to Contractor pending resolution of a dispute.",
    "Client may offset any losses against fees payable to Contractor.",
    "Client may set off any amount it believes in good faith it is owed.",
]
for s in R04_MUST_FIRE:
    check(f"R04 fires: {s[:55]}...", "R04" in fired(s, R04), f"got {fired(s, R04) or 'nothing'}")

# THE collision test for this batch. This sentence belongs to R02, and only R02.
ACCEPTANCE_CLAUSE = "Client may withhold payment until Client is satisfied, in Client's sole discretion."
check("R04 does NOT fire on 'withhold payment until satisfied' (that is R02's)",
      "R04" not in fired(ACCEPTANCE_CLAUSE, R04), f"fired {fired(ACCEPTANCE_CLAUSE, R04)}")
check("the same sentence still fires R02",
      "R02" in fired(ACCEPTANCE_CLAUSE, R02))
check("in the fake contract, 2.3 is R02 only", ("R04", "2.3") not in by_pair)

R04_MUST_NOT_FIRE = [
    "Client may not set off any amounts against Contractor's invoices.",
    # Direction: this right protects the freelancer.
    "Contractor may set off unpaid invoices against amounts owed to Client.",
    "The parties shall make any adjustments by mutual written agreement.",
]
for s in R04_MUST_NOT_FIRE:
    check(f"R04 skips: {s[:55]}...", "R04" not in fired(s, R04), f"fired {fired(s, R04)}")


# ==========================================================================
# K. R06 - open-ended scope (step 5a)
# ==========================================================================

print("\n=== K. R06 open scope ===")

R06_MUST_FIRE = [
    "Contractor shall perform the services, including but not limited to design, copywriting, and motion graphics.",
    "Contractor shall perform such other services as Client may request.",
    "Contractor shall perform any other duties as assigned by Client from time to time.",
    "The scope of work includes any other work Client asks for.",
    "Contractor shall provide the Deliverables, including without limitation all source files.",
]
for s in R06_MUST_FIRE:
    check(f"R06 fires: {s[:55]}...", "R06" in fired(s, R06), f"got {fired(s, R06) or 'nothing'}")

# THE false-positive risk for this batch: "including but not limited to" inside
# an indemnity clause widens liability, it does not widen scope. That is R11's job.
INDEMNITY = ("Contractor shall indemnify, defend and hold harmless Client from any and all "
             "claims, including but not limited to reasonable attorneys' fees.")
check("R06 does NOT fire on 'including but not limited to' inside an indemnity clause",
      "R06" not in fired(INDEMNITY, R06), f"fired {fired(INDEMNITY, R06)}")

R06_MUST_NOT_FIRE = [
    "This Agreement does not include any other services except by written change order.",
    "Section 9 survives termination, including without limitation its confidentiality obligations.",
    "Any change to the scope requires a written change order signed by both Parties.",
    "The Deliverables are exactly the items listed in Exhibit A.",
]
for s in R06_MUST_NOT_FIRE:
    check(f"R06 skips: {s[:55]}...", "R06" not in fired(s, R06), f"fired {fired(s, R06)}")

check("R06 does not fire on the fake contract's change-order clause 1.3", ("R06", "1.3") not in by_pair)


# ==========================================================================
# L. R07 - free extra work (step 5a)
# ==========================================================================

print("\n=== L. R07 free extra work ===")

R07_MUST_FIRE = [
    "Contractor shall perform additional work at no additional cost.",
    "Any work requested by Client shall be performed at no additional charge.",
    "Contractor shall correct all defects at its own expense.",
    "Contractor shall provide bug fixes for twelve months following acceptance at no charge.",
    "Contractor shall provide the Services free of charge during the pilot.",
    "Contractor shall provide ongoing support for twelve months without additional compensation.",
]
for s in R07_MUST_FIRE:
    check(f"R07 fires: {s[:55]}...", "R07" in fired(s, R07), f"got {fired(s, R07) or 'nothing'}")

R07_MUST_NOT_FIRE = [
    # DIRECTION: the client paying nothing is not the freelancer's problem.
    "Client shall provide all brand assets and licensed fonts at no additional cost to Contractor.",
    "Client shall deliver the source materials at Client's sole expense.",
    "Contractor shall not be required to perform additional work at no cost.",
    "Contractor invoices the client at the agreed hourly rate for extra rounds.",
]
for s in R07_MUST_NOT_FIRE:
    check(f"R07 skips: {s[:55]}...", "R07" not in fired(s, R07), f"fired {fired(s, R07)}")


# ==========================================================================
# M. One clause, one finding (step 5a)
# ==========================================================================

print("\n=== M. No clause is reported twice ===")

per_clause: dict[str, list[str]] = {}
for x in reportable:
    per_clause.setdefault(x.clause, []).append(x.rule_id)
dupes = {c: ids for c, ids in per_clause.items() if len(ids) > 1}
check("no clause carries two different rules", not dupes, str(dupes))

# Same rule twice in different clauses is correct when the contract really does
# two different bad things (4.1 sweep + 4.2 work-for-hire). The engine keeps
# both; grouping them in the final report is step 7's job.
check("R08 appears twice, for two different clauses (4.1 and 4.2)",
      sorted(f.clause for f in reportable if f.rule_id == "R08") == ["4.1", "4.2"])
check("R09 appears twice, for two different clauses (4.3 and 4.4)",
      sorted(f.clause for f in reportable if f.rule_id == "R09") == ["4.3", "4.4"])


# ==========================================================================
# N. R08 - IP assignment sweep (step 5b)
# ==========================================================================

print("\n=== N. R08 full IP assignment ===")

R08_MUST_FIRE = [
    "Contractor assigns all concepts, drafts, sketches, and unused directions to Client.",
    "All materials created in connection with the Services shall be owned by Client.",
    "All Deliverables shall be deemed work made for hire under the Copyright Act.",
    "Contractor hereby assigns, including all unused concepts and rejected designs, to Client.",
]
for s in R08_MUST_FIRE:
    check(f"R08 fires: {s[:55]}...", "R08" in fired(s, R08), f"got {fired(s, R08) or 'nothing'}")

# THE line this rule must not cross. Every sentence below is a NORMAL IP clause,
# several of them are the exact fix R08 recommends. None may be reported.
R08_MUST_NOT_FIRE = [
    # Plain assignment of the final deliverable - the single most common clause
    # in real contracts. Reporting this would put a FATAL card on everything.
    "Contractor hereby assigns all right, title and interest in the Deliverables to Client, in perpetuity, throughout the world.",
    "Contractor assigns all right, title and interest in the final Deliverables to Client upon receipt of full payment.",
    # The cure: freelancer keeps the unused material.
    "Contractor retains ownership of all preliminary concepts and unused directions.",
    "Contractor reserves all rights in its pre-existing tools and templates.",
    # A licence is not an assignment.
    "Contractor grants Client a perpetual, worldwide, non-exclusive licence to use the Deliverables.",
    "Nothing in this Section transfers ownership of Contractor's pre-existing tools or templates.",
    "Client shall return all drafts and unused materials to Contractor at the end of the engagement.",
    # "unused" used for something else entirely.
    "Any unused budget shall be refunded to Client within ten (10) days.",
    "The Parties acknowledge that no Deliverable is a work made for hire.",
]
for s in R08_MUST_NOT_FIRE:
    check(f"R08 skips: {s[:55]}...", "R08" not in fired(s, R08), f"fired {fired(s, R08)}")


# ==========================================================================
# O. R09 - moral rights / portfolio (step 5b)
# ==========================================================================

print("\n=== O. R09 moral rights + portfolio ===")

R09_MUST_FIRE = [
    "Contractor waives, and agrees not to assert, any moral rights in the Deliverables.",
    "Contractor waives all moral rights and rights of attribution.",
    "Contractor shall not display the Deliverables in any portfolio.",
    "Contractor may not include the Deliverables in a case study without Client's prior written consent.",
    "Contractor shall not use the Deliverables in its portfolio or on social media.",
]
for s in R09_MUST_FIRE:
    check(f"R09 fires: {s[:55]}...", "R09" in fired(s, R09), f"got {fired(s, R09) or 'nothing'}")

R09_MUST_NOT_FIRE = [
    # The GOOD clause: the freelancer keeps the right to show the work.
    "Contractor may display the Deliverables in its portfolio after publication.",
    "Contractor retains a non-exclusive right to showcase the Deliverables on its website.",
    "Contractor retains all moral rights in the Deliverables.",
    "Nothing in this Section waives any moral rights of Contractor.",
    # Contains the consent phrase but is an assignment restriction (R16 territory).
    "Contractor may not assign this Agreement without Client's prior written consent.",
    "Client may not use Contractor's name without prior written consent.",
]
for s in R09_MUST_NOT_FIRE:
    check(f"R09 skips: {s[:55]}...", "R09" not in fired(s, R09), f"fired {fired(s, R09)}")


# ==========================================================================
# P. R10 - resale / sublicence / AI training (step 5b)
# ==========================================================================

print("\n=== P. R10 resale + AI training ===")

R10_MUST_FIRE = [
    "Client may sublicense the Deliverables to third parties.",
    "Client may resell the Deliverables as a template product.",
    "Client may use the Deliverables to train machine learning models.",
    "Client may fine-tune AI models using the Deliverables.",
    "Client may create derivative works from the Deliverables and distribute them as a product.",
]
for s in R10_MUST_FIRE:
    check(f"R10 fires: {s[:55]}...", "R10" in fired(s, R10), f"got {fired(s, R10) or 'nothing'}")

R10_MUST_NOT_FIRE = [
    # Direction: the freelancer's own reuse of their tools.
    "Contractor may sublicense its pre-existing tools to other clients.",
    # A restriction on the contractor protects the client; it takes nothing away.
    "Contractor shall not use Client Data to train AI models.",
    "Client may not resell the Deliverables.",
    # Adapting what you bought, for your own use, is normal.
    "Client may create derivative works from the Deliverables for its own internal use.",
    "Client may modify and adapt the Deliverables for its own business.",
]
for s in R10_MUST_NOT_FIRE:
    check(f"R10 skips: {s[:55]}...", "R10" not in fired(s, R10), f"fired {fired(s, R10)}")


# ==========================================================================
# Q. Cross-rule isolation for the IP cluster (step 5b)
# ==========================================================================

print("\n=== Q. IP cluster isolation ===")

# 4.1 sweeps ownership; it must not be re-labelled as resale/AI.
check("4.1 is R08 only (no R10 on the same clause)",
      [f.rule_id for f in reportable if f.clause == "4.1"] == ["R08"],
      str([f.rule_id for f in reportable if f.clause == "4.1"]))
check("4.5 is R10 only (no R08 on the same clause)",
      [f.rule_id for f in reportable if f.clause == "4.5"] == ["R10"])
check("4.4 portfolio ban is not reported as R02 (acceptance)",
      "R02" not in {f.rule_id for f in reportable if f.clause == "4.4"})

# Documents with no IP clause at all must stay silent across the IP cluster.
NO_IP = (
    "1. SERVICES. Contractor shall design a logo. The scope is limited to Exhibit A.\n"
    "2. FEES. Client shall pay within fifteen (15) days of receipt.\n"
    "3. TERM. Either party may terminate on thirty (30) days' written notice.\n"
)
no_ip = [f for f in scan(prepare(NO_IP), RULES) if f.is_reportable]
check("a contract with no IP clause triggers no IP rule",
      not [f for f in no_ip if f.rule_id in ("R08", "R09", "R10")],
      ", ".join(f"{f.rule_id}@{f.clause}" for f in no_ip) or "none")

# ==========================================================================
# R. R11 - uncapped one-way indemnity (step 5c)
# ==========================================================================

print("\n=== R. R11 uncapped indemnity ===")

R11_MUST_FIRE = [
    "Contractor shall indemnify, defend and hold harmless Client from and against any and all claims, losses and damages, including reasonable attorneys' fees, arising out of or relating to the Services.",
    "Contractor shall indemnify Client against any and all claims arising out of or relating to the Services.",
    "Contractor agrees to defend and hold harmless Client from and against all claims, costs and expenses.",
    "Contractor shall indemnify Client against all third-party claims, including reasonable attorneys' fees and costs.",
]
for s in R11_MUST_FIRE:
    check(f"R11 fires: {s[:55]}...", "R11" in fired(s, R11), f"got {fired(s, R11) or 'nothing'}")

R11_MUST_NOT_FIRE = [
    # 6.3 - an exemption that protects the freelancer. The contract's own trap.
    "Contractor shall not be liable for any loss arising solely from materials or information supplied by Client.",
    # A one-risk IP indemnity limited to infringement is standard, not fatal.
    "Contractor shall indemnify Client against third-party claims that the Deliverables infringe a third party's intellectual property rights.",
    # Mutual indemnity: the negotiated, balanced shape.
    "Each Party shall indemnify the other against third-party claims arising from its own breach of this Agreement.",
    # Fault-scoped: you only pay for your own gross negligence.
    "Contractor shall indemnify Client for third-party claims to the extent caused by Contractor's gross negligence or willful misconduct.",
    "Contractor shall indemnify Client for claims caused solely by Contractor's willful misconduct.",
    # Already capped.
    "Contractor shall indemnify Client against all claims, provided that such liability shall not exceed the total fees paid.",
    # Arbitration and fee-shifting mention the same vocabulary but promise no indemnity.
    "Any dispute arising out of or relating to this Agreement shall be resolved by binding arbitration.",
    "The prevailing party in any arbitration or proceeding shall be entitled to recover its reasonable attorneys' fees and costs.",
    # A pure disclaimer, not a promise.
    "Nothing in this Agreement shall be construed as an agreement to indemnify Client for Client's own negligence.",
]
for s in R11_MUST_NOT_FIRE:
    check(f"R11 skips: {s[:55]}...", "R11" not in fired(s, R11), f"fired {fired(s, R11)}")


# ==========================================================================
# S. R12 - liability stated to be uncapped (step 5c)
# ==========================================================================

print("\n=== S. R12 uncapped liability ===")

R12_MUST_FIRE = [
    "The obligations set forth in Section 6.1 apply without limitation as to amount, duration, or number of claims.",
    "The indemnity applies without limitation as to the amount of any claim.",
    "There is no cap on Contractor's liability under this Agreement.",
    "Contractor shall have unlimited liability for any breach of this Agreement.",
    "Contractor's obligations are not subject to any limitation of liability.",
    "Contractor shall have no limitation of liability for claims arising under Section 6.",
]
for s in R12_MUST_FIRE:
    check(f"R12 fires: {s[:55]}...", "R12" in fired(s, R12), f"got {fired(s, R12) or 'nothing'}")

R12_MUST_NOT_FIRE = [
    # The single most protective sentence a freelancer can get. "In no event
    # shall" is the OPENING of a cap, which is why it is not a pattern.
    "In no event shall either party's aggregate liability exceed the total fees paid under this Agreement.",
    "Each party's aggregate liability under this Agreement shall not exceed the fees paid.",
    "Contractor's liability is limited to the total amount of fees actually received.",
    "Neither party shall be liable for indirect, incidental, or consequential damages.",
    "Contractor's total liability shall not exceed the fees paid under this Agreement.",
]
for s in R12_MUST_NOT_FIRE:
    check(f"R12 skips: {s[:55]}...", "R12" not in fired(s, R12), f"fired {fired(s, R12)}")


# ==========================================================================
# T. R13 - client may terminate at any time (step 5c)
# ==========================================================================

print("\n=== T. R13 terminate for convenience ===")

R13_MUST_FIRE = [
    "Client may terminate this Agreement or any SOW at any time, for any reason or for no reason, without further obligation or payment of any kind.",
    "Client may terminate this Agreement at any time for convenience.",
    "Client may terminate this Agreement at any time without cause.",
    "Client has sole discretion to terminate the engagement.",
    "Client may terminate the Agreement at any time, for any reason or for no reason.",
]
for s in R13_MUST_FIRE:
    check(f"R13 fires: {s[:55]}...", "R13" in fired(s, R13), f"got {fired(s, R13) or 'nothing'}")

R13_MUST_NOT_FIRE = [
    # Mutual rights with notice are balanced: the freelancer can leave too.
    "Either party may terminate this Agreement for convenience on thirty (30) days' written notice.",
    "Either party may terminate this Agreement at any time upon thirty (30) days' written notice.",
    # The freelancer's own exit right is not a risk to the freelancer.
    "Contractor may terminate this Agreement at any time if Client fails to pay an undisputed invoice.",
    # Cause-based termination is the normal shape.
    "Client may terminate this Agreement for cause upon Contractor's uncured material breach.",
    "Client may terminate this Agreement only in the event of Contractor's material breach after thirty (30) days' written notice.",
    # A kill fee makes the same right fair.
    "Client may terminate this Agreement at any time for convenience, provided that Client pays a kill fee equal to fifty percent (50%) of the remaining fees.",
    # Ordinary term and survival clauses.
    "This Agreement commences on the Effective Date and continues until terminated in accordance with this Section 7.",
    "Sections 4, 5, and 9 survive any termination or expiration of this Agreement.",
]
for s in R13_MUST_NOT_FIRE:
    check(f"R13 skips: {s[:55]}...", "R13" not in fired(s, R13), f"fired {fired(s, R13)}")


# ==========================================================================
# U. Cross-rule isolation for the liability / termination cluster (step 5c)
# ==========================================================================

print("\n=== U. Liability + termination isolation ===")

# 6.1 is the indemnity; 6.2 is the missing cap. Two clauses, two different
# problems - but neither may spill onto the other.
check("6.1 is R11 only (no R12 on the same clause)",
      [f.rule_id for f in reportable if f.clause == "6.1"] == ["R11"],
      str([f.rule_id for f in reportable if f.clause == "6.1"]))
check("6.2 is R12 only (no R11 on the same clause)",
      [f.rule_id for f in reportable if f.clause == "6.2"] == ["R12"],
      str([f.rule_id for f in reportable if f.clause == "6.2"]))
check("7.2 is R13 only",
      [f.rule_id for f in reportable if f.clause == "7.2"] == ["R13"],
      str([f.rule_id for f in reportable if f.clause == "7.2"]))

# The free-passage words: no liability rule may touch the client's exemption,
# the term clause, the survival clause, or the freelancer's own exit right.
for clause in ("6.3", "7.1", "7.3", "7.4"):
    check(f"{clause} carries no flag",
          not [f for f in reportable if f.clause == clause],
          ", ".join(f"{f.rule_id}" for f in reportable if f.clause == clause))

# Section 11 is R17's territory (batch 5d). `arising out of or relating to`
# and `attorneys' fees` appear there; R11 must not answer for them.
check("section 11 raises no R11/R12/R13",
      not [f for f in reportable if (f.clause or "").startswith("11.")
           and f.rule_id in ("R11", "R12", "R13")],
      ", ".join(f"{f.rule_id}@{f.clause}" for f in reportable
                if (f.clause or "").startswith("11.")))

# THE collision test for 5c, the mirror of the 5a R04/R02 case:
# "including but not limited to" lives inside an indemnity. R11 owns the
# sentence; R06 must stay out of it.
BOTH_WAYS = ("Contractor shall indemnify Client against all claims, "
             "including but not limited to attorneys' fees.")
check("an indemnity with 'including but not limited to' is R11, not R06",
      fired(BOTH_WAYS) == {"R11"}, f"got {fired(BOTH_WAYS)}")

# A document with no liability or termination clause at all must stay silent.
NO_LIAB = (
    "1. SERVICES. Contractor shall design a logo. The scope is limited to Exhibit A.\n"
    "2. FEES. Client shall pay within fifteen (15) days of receipt.\n"
    "3. IP. Contractor assigns the final Deliverables to Client upon full payment.\n"
)
no_liab = [f for f in scan(prepare(NO_LIAB), RULES) if f.is_reportable]
check("a contract with no liability/termination clause triggers no 5c rule",
      not [f for f in no_liab if f.rule_id in ("R11", "R12", "R13")],
      ", ".join(f"{f.rule_id}@{f.clause}" for f in no_liab) or "none")

# ==========================================================================
# V. R14 / R15 - non-compete and non-solicitation (step 5d)
# ==========================================================================

print("\n=== V. R14 non-compete / R15 non-solicitation ===")

R14_MUST_FIRE = [
    "Contractor shall not directly or indirectly provide services similar to the Services to any competitor of Client, or to any person or entity engaged in a similar line of business.",
    "During the Term and for twelve (12) months thereafter, Contractor shall not provide services to any competitor of Client.",
    "Contractor agrees not to provide services to any competing business during the engagement.",
    "Contractor shall not work for any competitor of Client during the Term.",
    "8.1 Non-Competition. Contractor shall not engage with any competing business.",
]
for s in R14_MUST_FIRE:
    check(f"R14 fires: {s[:55]}...", "R14" in fired(s, R14), f"got {fired(s, R14) or 'nothing'}")

R14_MUST_NOT_FIRE = [
    # Permission to keep trading - the whole point of a fair contract.
    "Contractor may provide services to other clients during the term of this Agreement.",
    "Contractor is free to accept other engagements and to work for other clients.",
    # The 5a bug in a new costume: "Nothing" sits 9 words from the verb.
    "Nothing in this Agreement shall prevent Contractor from providing services to any competitor after the Term.",
    "Nothing herein restricts Contractor from working for competitors of Client.",
    # Direction reversed: the client is the one restricted.
    "Client shall not provide services similar to the Services to any competitor of Contractor.",
    # A confidentiality bar is not a non-compete.
    "Contractor shall not disclose Client's confidential information to any competitor.",
    # No real restriction - just an absence of exclusivity.
    "Contractor shall not be required to work exclusively for Client.",
]
for s in R14_MUST_NOT_FIRE:
    check(f"R14 skips: {s[:55]}...", "R14" not in fired(s, R14), f"fired {fired(s, R14)}")

R15_MUST_FIRE = [
    "Contractor shall not, directly or indirectly, solicit, engage, or accept work from any client, customer, vendor, employee, or contact of Client that Contractor became aware of during the engagement.",
    "Contractor shall not, during the Term and for one (1) year after, solicit or accept work from any customer of Client.",
    "Contractor shall not solicit any client of the Client for a period of twelve months.",
    "The Contractor agrees not to accept work from any of Client's customers.",
]
for s in R15_MUST_FIRE:
    check(f"R15 fires: {s[:55]}...", "R15" in fired(s, R15), f"got {fired(s, R15) or 'nothing'}")

R15_MUST_NOT_FIRE = [
    # Employee-only non-solicits: normal, and no lost income.
    "Contractor shall not solicit Client's employees for employment.",
    "Contractor shall not solicit or hire any employee of Client during the Term.",
    "Client shall not solicit any employee of Contractor.",
    "Non-Solicitation of Employees. Contractor shall not hire any personnel of Client.",
    # Selling more to the same client is the freelancer's upside, not a trap.
    "Contractor may solicit additional work from Client at any time.",
    "Nothing in this Agreement shall prevent Contractor from soliciting additional work from Client.",
    # Direction reversed / permission granted.
    "Client shall not solicit any client of Contractor.",
    "Contractor may accept work from any client, including competitors of Client.",
]
for s in R15_MUST_NOT_FIRE:
    check(f"R15 skips: {s[:55]}...", "R15" not in fired(s, R15), f"fired {fired(s, R15)}")


# ==========================================================================
# W. R16 - unilateral amendment (step 5d)
# ==========================================================================

print("\n=== W. R16 unilateral amendment ===")

R16_MUST_FIRE = [
    "Client may modify these terms at any time by posting an updated version on its supplier portal, and Contractor's continued performance constitutes acceptance of the revised terms.",
    "Client reserves the right to modify these terms at any time.",
    "Client may amend the Agreement in its sole discretion.",
    "Contractor's continued use of the platform constitutes acceptance of the revised terms.",
    "Company may update the policies from time to time without notice to Contractor.",
]
for s in R16_MUST_FIRE:
    check(f"R16 fires: {s[:55]}...", "R16" in fired(s, R16), f"got {fired(s, R16) or 'nothing'}")

R16_MUST_NOT_FIRE = [
    # These are the fix R16 recommends. Reporting them would be absurd.
    "This Agreement may be amended only by a written instrument signed by both parties.",
    "No amendment shall be effective unless in writing and signed by both parties.",
    "The Parties may amend this Agreement by mutual written agreement.",
    "This Agreement may not be modified except by a written instrument executed by each party.",
    # Amendable, but not the contract itself.
    "Client may modify the Deliverables at any time before final delivery.",
    # A change order is scope control, and it protects the freelancer.
    "Any change to the scope must be agreed in a written change order signed by both parties.",
]
for s in R16_MUST_NOT_FIRE:
    check(f"R16 skips: {s[:55]}...", "R16" not in fired(s, R16), f"fired {fired(s, R16)}")


# ==========================================================================
# X. R17 - forum, arbitration, fees (step 5d)
# ==========================================================================

print("\n=== X. R17 forum / arbitration / fees ===")

R17_MUST_FIRE = [
    "Any dispute arising out of or relating to this Agreement shall be resolved by binding arbitration administered in Wilmington, Delaware, under the Commercial Arbitration Rules of the American Arbitration Association.",
    "Any dispute shall be resolved by binding arbitration in New York, New York.",
    "The parties submit to the exclusive jurisdiction of the courts of the State of Delaware.",
    "Venue shall be exclusively in Dallas County, Texas.",
    "Client shall be entitled to recover its reasonable attorneys' fees and costs.",
    "Contractor shall reimburse Client for all legal fees incurred in collecting any amount.",
    "Contractor waives any right to a trial by jury.",
    "This Agreement shall be governed by the laws of England and Wales.",
]
for s in R17_MUST_FIRE:
    check(f"R17 fires: {s[:55]}...", "R17" in fired(s, R17), f"got {fired(s, R17) or 'nothing'}")

R17_MUST_NOT_FIRE = [
    # Governing law alone appears in every contract and decides nothing for the
    # user - it must never be a card (this is the 11.1 decision).
    "This Agreement shall be governed by the laws of the State of California, without regard to its conflict of laws principles.",
    # Mutual prevailing-party fees: standard, and it fired on clean boilerplate
    # the moment it was a pattern.
    "The prevailing party in any arbitration shall be entitled to recover its reasonable attorneys' fees and costs.",
    # Mutual jury waiver.
    "Each Party waives any right to a trial by jury.",
    "Both parties waive any right to a trial by jury.",
    # Small-claims carve-out is the fix, not the trap.
    "Any dispute shall be resolved by binding arbitration, except that either party may bring a claim in small claims court.",
    # Negated arbitration.
    "The parties agree that binding arbitration shall not be required for claims under $10,000.",
    # The freelancer's own right to sue for fees is not a risk to the freelancer.
    "Contractor may recover its reasonable attorneys' fees if Client fails to pay.",
]
for s in R17_MUST_NOT_FIRE:
    check(f"R17 skips: {s[:55]}...", "R17" not in fired(s, R17), f"fired {fired(s, R17)}")


# ==========================================================================
# Y. R18 - liquidated damages per day (step 5d)
# ==========================================================================

print("\n=== Y. R18 per-day penalties ===")

R18_MUST_FIRE = [
    "For each day of delay in delivery of any Deliverable, Contractor shall pay to Client liquidated damages of five hundred dollars ($500.00) per day.",
    "Time is of the essence with respect to all delivery dates set forth in any SOW.",
    "Contractor shall pay liquidated damages of $1,000 per day for each day of delay.",
    "A penalty of $250 per day applies to late delivery.",
    "Contractor shall pay a late fee of $100 per day for every day the work is late.",
]
for s in R18_MUST_FIRE:
    check(f"R18 fires: {s[:55]}...", "R18" in fired(s, R18), f"got {fired(s, R18) or 'nothing'}")

R18_MUST_NOT_FIRE = [
    # The freelancer's own late-payment protection - the mirror-image trap.
    "Client shall pay interest at one and one-half percent (1.5%) per month on overdue invoices.",
    "A late fee of $50 per day applies to invoices unpaid after thirty (30) days.",
    "Client shall pay a late fee of 1.5% per month on any invoice not paid within thirty (30) days.",
    # Time pressure aimed at the client's payment, not the freelancer's delivery.
    "Time is of the essence with respect to Client's payment obligations.",
    # Ordinary delivery language.
    "The Deliverables shall be delivered no later than the dates set out in Exhibit A.",
    "Contractor shall use commercially reasonable efforts to meet the delivery schedule.",
]
for s in R18_MUST_NOT_FIRE:
    check(f"R18 skips: {s[:55]}...", "R18" not in fired(s, R18), f"fired {fired(s, R18)}")


# ==========================================================================
# Z. R19 / R20 - perpetual confidentiality, absolute warranty (step 5d)
# ==========================================================================

print("\n=== Z. R19 perpetual confidentiality / R20 absolute warranty ===")

R19_MUST_FIRE = [
    "Contractor shall keep all information disclosed by Client confidential, whether or not marked as confidential.",
    "The confidentiality obligations shall survive termination and continue in perpetuity.",
    "Contractor's confidentiality obligations are perpetual.",
    "The obligations of confidentiality shall continue indefinitely after termination of this Agreement.",
]
for s in R19_MUST_FIRE:
    check(f"R19 fires: {s[:55]}...", "R19" in fired(s, R19), f"got {fired(s, R19) or 'nothing'}")

R19_MUST_NOT_FIRE = [
    # 7.4: survival of a section is not a perpetual obligation.
    "Sections 4, 5, 6, 8, 9, and 11 survive any termination or expiration of this Agreement.",
    # 4.1: "in perpetuity" in an ASSIGNMENT belongs to R08, not R19.
    "Contractor assigns to Client all right, title and interest in the Deliverables in perpetuity.",
    # A finite term is the fix.
    "Contractor shall keep Client's Confidential Information confidential for three (3) years after termination.",
    "Confidentiality obligations survive for five (5) years after termination of this Agreement.",
    # Standard carve-outs.
    "Confidential Information does not include information that is publicly available or that Contractor already knew.",
]
for s in R19_MUST_NOT_FIRE:
    check(f"R19 skips: {s[:55]}...", "R19" not in fired(s, R19), f"fired {fired(s, R19)}")

R20_MUST_FIRE = [
    "Contractor warrants that the Deliverables will be error-free, free from defects, fit for Client's particular purpose, and compliant with all applicable laws and regulations.",
    "Contractor warrants that the Deliverables will be error-free.",
    "Contractor warrants the Deliverables are fit for Client's particular purpose.",
    "Contractor represents and warrants that the Services will be free from defects.",
    "Contractor warrants that the Deliverables are merchantable.",
    "Contractor warrants that the Services will be uninterrupted and error-free.",
]
for s in R20_MUST_FIRE:
    check(f"R20 fires: {s[:55]}...", "R20" in fired(s, R20), f"got {fired(s, R20) or 'nothing'}")

R20_MUST_NOT_FIRE = [
    # "material defects" is a bounded, reasonable standard.
    "Contractor warrants that the Deliverables will be free from material defects for ninety (90) days.",
    # A disclaimer is the freelancer's protection, and "fitness for a particular
    # purpose" is how they write it - it must never be a warranty finding.
    "Contractor disclaims all warranties, including any warranty of merchantability or fitness for a particular purpose.",
    "EXCEPT AS SET FORTH HEREIN, CONTRACTOR DISCLAIMS ALL OTHER WARRANTIES.",
    # Ordinary professionalism is not an absolute standard.
    "Contractor shall perform the Services in a professional and workmanlike manner.",
    # Not a promise about the work product at all.
    "Each party shall comply with all applicable laws and regulations.",
    "Client shall have no obligation to accept Deliverables that are not fit for their intended purpose.",
]
for s in R20_MUST_NOT_FIRE:
    check(f"R20 skips: {s[:55]}...", "R20" not in fired(s, R20), f"fired {fired(s, R20)}")


# ==========================================================================
# AA. Cross-rule isolation for the 5d cluster
# ==========================================================================

print("\n=== AA. Non-compete / forum / warranty isolation ===")

for clause, only in (("8.1", "R14"), ("8.2", "R15"), ("9.1", "R19"),
                     ("9.2", "R19"), ("10.1", "R18"), ("10.2", "R18"),
                     ("11.2", "R17"), ("12.1", "R16"), ("5.1", "R20")):
    got = [f.rule_id for f in reportable if f.clause == clause]
    check(f"{clause} is {only} only", got == [only], str(got))

# 4.1's "in perpetuity" must not drag R19 onto the IP clause.
check("4.1 raises R08 only - no R19 on the assignment",
      sorted({f.rule_id for f in reportable if f.clause == "4.1"}) == ["R08"],
      str(sorted({f.rule_id for f in reportable if f.clause == "4.1"})))

# An IP assignment "in perpetuity" that also mentions information is the exact
# collision the R19 regex was shaped to prevent.
IP_PERPETUAL = (
    "Contractor hereby irrevocably assigns to Client all right, title and "
    "interest in the Deliverables, including all information, materials and "
    "unused concepts, in perpetuity."
)
check("perpetual IP assignment with 'information' is R08, never R19",
      fired(IP_PERPETUAL) == {"R08"}, f"got {fired(IP_PERPETUAL)}")

# A document with no restrictive covenants must stay silent.
NO_COVENANT = (
    "1. SERVICES. Contractor shall design a logo per Exhibit A.\n"
    "2. FEES. Client shall pay within fifteen (15) days of receipt.\n"
    "3. IP. Contractor assigns the Deliverables to Client upon full payment.\n"
    "4. TERM. Either party may terminate on thirty (30) days' written notice.\n"
)
no_cov = [f for f in scan(prepare(NO_COVENANT), RULES) if f.is_reportable]
check("a contract with no covenants triggers no 5d rule",
      not [f for f in no_cov if f.rule_id in ("R14", "R15", "R16", "R17", "R18", "R19", "R20")],
      ", ".join(f"{f.rule_id}@{f.clause}" for f in no_cov) or "none")


print()
if failures:
    print(f"RESULT: {len(failures)} of {total_checks} check(s) FAILED")
    for item in failures:
        print(f"  - {item}")
    raise SystemExit(1)

print(f"RESULT: all {total_checks} checks passed")
