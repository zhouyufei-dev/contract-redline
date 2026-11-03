"""How much does PDF extraction damage the text for rule matching?

Compares three views of the same contract:
  1. .txt source (ground truth)
  2. .docx extracted
  3. .pdf extracted  ->  raw  vs  whitespace-collapsed

The gap between raw and collapsed is the measured cost of NOT normalising
whitespace before running regexes. That number is the argument for
app/engine/textnorm.py existing.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.parsers.extractor import extract_text  # noqa: E402

NEEDLES = {
    "R01": "sixty (60) days",
    "R02": "upon Client's final acceptance",
    "R03": "receipt of payment from the end client",
    "R04": "Client may set off",
    "R05": "unlimited revisions",
    "R06": "including but not limited to",
    "R07": "at no additional cost",
    "R08": "all right, title and interest",
    "R09": "shall not display the Deliverables",
    "R10": "generative artificial intelligence",
    "R11": "indemnify, defend and hold harmless",
    "R13": "for any reason or for no reason",
    "R14": "Non-Competition",
    "R15": "Non-Solicitation",
    "R16": "continued performance constitutes acceptance",
    "R17": "binding arbitration",
    "R18": "liquidated damages",
    "R19": "in perpetuity",
    "R20": "error-free",
}


def collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def score(text: str) -> tuple[int, list[str]]:
    misses = [rid for rid, needle in NEEDLES.items() if needle not in text]
    return len(NEEDLES) - len(misses), misses


print(f"{'source':<28}{'raw hits':>10}{'normalised':>13}   missing after normalise")
print("-" * 78)

for label, path in [
    ("txt  (ground truth)", "data/samples/fake_contract_01.txt"),
    ("docx", "data/samples/fake_contract_01.docx"),
    ("pdf", "data/samples/fake_contract_01.pdf"),
]:
    text = extract_text(path)
    raw_hits, _ = score(text)
    norm_hits, misses = score(collapse(text))
    print(f"{label:<28}{raw_hits:>7}/{len(NEEDLES)}{norm_hits:>10}/{len(NEEDLES)}"
          f"   {', '.join(misses) if misses else '-'}")

pdf_text = extract_text("data/samples/fake_contract_01.pdf")
lines = pdf_text.splitlines()
repeated = [ln for ln in set(lines) if ln.strip() and lines.count(ln) > 3]
print("\nRepeated lines in the PDF (headers/footers to strip later):")
for ln in repeated:
    print(f"  x{lines.count(ln):<3} {ln[:70]}")
