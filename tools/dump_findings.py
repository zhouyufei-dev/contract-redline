"""Dump reportable findings grouped by rule, to design the merge rules."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.engine.matcher import scan  # noqa: E402
from app.engine.textnorm import prepare  # noqa: E402
from app.parsers.extractor import extract_text  # noqa: E402
from app.rules.redlines_us import RULES  # noqa: E402

text = extract_text("data/samples/fake_contract_01.docx")
findings = [f for f in scan(prepare(text), RULES) if f.is_reportable]

print(f"{len(findings)} reportable findings\n")
for f in findings:
    print(f"{f.rule_id:4} {f.clause:6} sev={f.severity:2} {f.status:9} {f.sentence[:80]}")
