"""Step 3 acceptance check: does the extractor return the same text we wrote?

Run from the project root:
    .\\.venv\\Scripts\\python.exe tools\\check_step3.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.parsers.extractor import ExtractionError, extract_text  # noqa: E402

SAMPLES = Path("data/samples")
DOCX = SAMPLES / "fake_contract_01.docx"
TXT = SAMPLES / "fake_contract_01.txt"

failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f"  ({detail})" if detail else ""))
    if not condition:
        failures.append(label)


print("\n1. DOCX vs TXT source")
docx_text = extract_text(DOCX)
txt_text = extract_text(TXT)


def words(text: str) -> list[str]:
    """Whitespace-insensitive comparison key.

    DOCX stores each visual line of the signature block as its own paragraph,
    so the extracted text legitimately contains more blank lines than the
    .txt source. What must NOT change is the sequence of words.
    """
    return text.split()


check("DOCX word sequence equals TXT source", words(docx_text) == words(txt_text),
      f"{len(docx_text):,} vs {len(txt_text):,} chars")

print("\n2. Every embedded red flag survives extraction")
must_contain = [
    ("R01 net 60", "sixty (60) days"),
    ("R02 acceptance", "upon Client's final acceptance"),
    ("R03 pay-when-paid", "receipt of payment from the end client"),
    ("R04 set-off", "Client may set off"),
    ("R05 unlimited revisions", "unlimited revisions"),
    ("R06 open scope", "including but not limited to"),
    ("R07 free extra work", "at no additional cost"),
    ("R08 assignment", "all right, title and interest"),
    ("R09 portfolio ban", "shall not display the Deliverables"),
    ("R10 AI training", "generative artificial intelligence"),
    ("R11 indemnity", "indemnify, defend and hold harmless"),
    ("R13 terminate for convenience", "for any reason or for no reason"),
    ("R14 non-compete", "Non-Competition"),
    ("R15 non-solicit", "Non-Solicitation"),
    ("R16 unilateral amendment", "continued performance constitutes acceptance"),
    ("R17 arbitration", "binding arbitration"),
    ("R18 liquidated damages", "liquidated damages"),
    ("R19 perpetual", "in perpetuity"),
    ("R20 warranty", "error-free"),
]
for label, needle in must_contain:
    check(label, needle in docx_text)

print("\n3. Negation traps are present verbatim (step 4 must not fire on them)")
for label, needle in [
    ("3.2 not request unlimited", "shall not request unlimited revisions"),
    ("6.3 not be liable", "shall not be liable"),
    ("2.7 may suspend work", "Contractor may suspend work"),
]:
    check(label, needle in docx_text)

print("\n4. Structure survived (paragraphs are separated)")
check("no double spaces at line ends", "  \n" not in docx_text)
check("has section numbering", "2.3 Acceptance." in docx_text)

print("\n5. Error handling")
for label, bad in [("missing file", "nope.pdf"), ("unsupported type", "README.md")]:
    try:
        extract_text(bad)
        check(label, False, "no exception raised")
    except ExtractionError as exc:
        check(label, True, str(exc)[:60])

print()
if failures:
    print(f"RESULT: {len(failures)} check(s) FAILED")
    for item in failures:
        print(f"  - {item}")
    raise SystemExit(1)

print("RESULT: all checks passed")
