r"""Stress test: realistic CLEAN boilerplate that must stay quiet (steps 5a-5c).

These are sentences pulled from the shape of ordinary, freelancer-friendly US
service contracts. Every one of them is harmless. If any rule fires on them,
the product cries wolf on a good contract - worse than missing a flag, because
the user stops trusting the report and never comes back.

The 5b block is the one that matters most: it holds the IP clauses that are
NORMAL. Assigning the deliverable, granting a perpetual non-exclusive licence,
letting the client adapt the work for its own business - all standard. A rule
that flags these is not "cautious", it is broken.

The 5c block holds the liability and termination clauses that are NORMAL: a cap
that exists, a mutual termination right, a fault-scoped indemnity. These are the
sentences every real contract contains, so a false positive here would hit
100% of uploads rather than 1%.

Run:  .\\.venv\\Scripts\\python.exe tools\stress_clean.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.engine.matcher import scan  # noqa: E402
from app.engine.textnorm import prepare  # noqa: E402
from app.rules.redlines_us import RULES  # noqa: E402

SENTENCES = [
    # --- "including but not limited to" in places that are NOT scope creep ---
    "Confidential Information includes but is not limited to business plans, pricing, and customer lists.",
    "Client grants Contractor a licence to use its trademarks, including but not limited to the Northwind logo.",
    "The Deliverables include but are not limited to the files listed in Exhibit A, which is a closed list.",
    "Either party may disclose Confidential Information to its advisors, including but not limited to lawyers and accountants.",
    # --- set-off vocabulary used in the freelancer's favour ---
    "Contractor may set off any unpaid invoice against amounts held by Contractor.",
    "The invoice amount shall be paid in full; Client may not deduct any sums without Contractor's written consent.",
    "Client shall pay all invoices without set-off, counterclaim, or deduction.",
    # --- pass-through vocabulary that is actually fine ---
    "Client shall pay each invoice within thirty (30) days of receipt, regardless of whether Client has been paid.",
    "Contractor will be introduced to Client's end client during onboarding.",
    "Client's end client has approved the concept direction.",
    # --- "no charge" in the freelancer's favour ---
    "Client shall provide brand assets at no additional cost to Contractor.",
    "Client shall bear all third-party licence fees at Client's sole expense.",
    "Contractor will invoice travel at cost, reimbursable within fifteen (15) days.",
    # --- ordinary closed-scope drafting ---
    "The Services consist solely of the items described in Exhibit A.",
    "Any work outside Exhibit A requires a written change order signed by both parties.",
    "The fee includes two rounds of revisions; further rounds are billed at $120 per hour.",
    "Contractor will deliver the final files within ten (10) business days of approval.",
    # --- ordinary acceptance, termination, IP ---
    "Deliverables are deemed accepted if Client does not object in writing within five (5) business days.",
    "Either party may terminate this Agreement for convenience on thirty (30) days' written notice.",
    "Contractor retains ownership of all preliminary concepts and unused directions.",
    "Contractor may display the Deliverables in its portfolio after publication.",
    "Contractor's total liability shall not exceed the fees paid under this Agreement.",
    # --- 5b: ordinary IP clauses, the ones that appear in nearly every contract ---
    "Contractor hereby assigns all right, title and interest in the Deliverables to Client.",
    "Contractor assigns all right, title and interest in the final Deliverables to Client upon receipt of full payment.",
    "Upon full payment, all right, title and interest in the Deliverables passes to Client.",
    "Contractor grants Client a perpetual, worldwide, non-exclusive licence to use the Deliverables.",
    "Contractor grants Client a non-exclusive, non-transferable licence for the term of this Agreement.",
    "Contractor retains all right, title and interest in its pre-existing tools, libraries, and templates.",
    "Contractor reserves the right to reuse general knowledge, techniques, and know-how.",
    "Nothing in this Agreement transfers ownership of Contractor's pre-existing materials.",
    "Client may modify and adapt the Deliverables for its own internal business use.",
    "Client may create derivative works from the Deliverables for its own internal use.",
    "Client shall not use Contractor's name or logo without prior written consent.",
    "Contractor may include the Deliverables in its portfolio and case studies.",
    "Contractor shall be credited as the designer of the Deliverables.",
    "Contractor shall not be required to waive any moral rights.",
    # --- the client protecting its own data ---
    "Contractor shall not use Client Data to train any machine learning model.",
    "Contractor shall not disclose Confidential Information to any third party.",
    "Client may not resell, sublicense, or distribute the Deliverables as a standalone product.",
    # --- 5c: ordinary liability limits and mutual termination ---
    "In no event shall either party's aggregate liability exceed the total fees paid under this Agreement.",
    "Each party's aggregate liability under this Agreement shall not exceed the fees paid.",
    "Contractor's liability is limited to the total amount of fees actually received.",
    "Neither party shall be liable for indirect, incidental, or consequential damages.",
    "Either party may terminate this Agreement at any time upon thirty (30) days' written notice.",
    "Client may terminate this Agreement for cause upon Contractor's uncured material breach.",
    "Contractor may terminate this Agreement at any time if Client fails to pay an undisputed invoice.",
    "Client may terminate this Agreement at any time for convenience, provided that Client pays a kill fee equal to fifty percent (50%) of the remaining fees.",
    "This Agreement continues until terminated in accordance with this Section 7.",
    "Sections 4, 5, and 9 survive any termination or expiration of this Agreement.",
    # Fault-scoped and mutual indemnities: the negotiated shape, not a trap.
    "Contractor shall indemnify Client against third-party claims that the Deliverables infringe a third party's intellectual property rights.",
    "Each Party shall indemnify the other against third-party claims arising from its own breach of this Agreement.",
    "Contractor shall indemnify Client for third-party claims to the extent caused by Contractor's gross negligence or willful misconduct.",
    "The prevailing party in any arbitration shall be entitled to recover its reasonable attorneys' fees and costs.",
    # --- 5d: the restrictive covenants that are NORMAL ---
    # A freelancer must be able to keep trading. Every sentence here is what a
    # negotiated, fair contract looks like - flagging any of them would tell the
    # user their good contract is bad.
    "Contractor may provide services to other clients during the term of this Agreement.",
    "Contractor is free to accept any other engagement, including work for Client's competitors after the Term.",
    "Nothing in this Agreement restricts Contractor from working with other clients.",
    "Contractor shall not be required to work exclusively for Client.",
    "Contractor shall not disclose Client's confidential information to any competitor.",
    "Contractor shall not solicit any employee of Client.",
    "Contractor may solicit additional work from Client at any time.",
    # --- 5d: amendment clauses that protect the freelancer ---
    "This Agreement may be amended only by a written instrument signed by both parties.",
    "No amendment shall be effective unless in writing and signed by both parties.",
    "Any change to the scope must be agreed in a written change order signed by both parties.",
    # --- 5d: standard dispute resolution ---
    "This Agreement shall be governed by the laws of the State of New York, without regard to its conflict of laws principles.",
    "Each party waives any right to a trial by jury.",
    "Any dispute shall be resolved by arbitration in accordance with the rules of the American Arbitration Association, except that either party may bring a claim in small claims court.",
    # --- 5d: the freelancer's own late-payment protection ---
    "Client shall pay interest at one percent (1%) per month on invoices more than thirty (30) days overdue.",
    "A late fee of $50 per day applies to invoices unpaid after thirty (30) days.",
    "Time is of the essence with respect to Client's payment obligations.",
    # --- 5d: finite confidentiality, bounded warranties ---
    "Confidentiality obligations survive for three (3) years after termination of this Agreement.",
    "Contractor warrants that the Deliverables will be free from material defects for ninety (90) days.",
    "Contractor disclaims all warranties, including any warranty of merchantability or fitness for a particular purpose.",
    "Contractor shall perform the Services in a professional and workmanlike manner.",
    "Each party shall comply with all applicable laws and regulations.",
]

findings = []
for s in SENTENCES:
    for f in scan(prepare(s), RULES):
        if f.is_reportable:
            findings.append((s, f.rule_id, f.matched_text))

print(f"Scanned {len(SENTENCES)} harmless sentences.\n")
for s, rule_id, match in findings:
    print(f"  FALSE POSITIVE  {rule_id}  \"{match}\"\n      in: {s}")

if findings:
    print(f"\nRESULT: {len(findings)} false positive(s) on clean boilerplate")
    raise SystemExit(1)

print(f"RESULT: zero false positives on {len(SENTENCES)} clean sentences")
