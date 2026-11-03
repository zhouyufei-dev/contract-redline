"""One-call smoke test: is the key good, is the model name right, how slow is it?

Prints the settings line (no key material), one real finding's card, the token
usage and the wall time. Run this before spending 24 calls on a whole contract.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import require_settings  # noqa: E402
from app.engine.matcher import scan  # noqa: E402
from app.engine.textnorm import prepare  # noqa: E402
from app.llm import deepseek_client as ds  # noqa: E402
from app.parsers.extractor import extract_text  # noqa: E402
from app.rules.redlines_us import RULES  # noqa: E402

settings = require_settings()
print(settings.describe())
print()

text = extract_text("data/samples/fake_contract_01.docx")
findings = [f for f in scan(prepare(text), RULES) if f.is_reportable]
target = next(f for f in findings if f.clause == "2.2")
print(f"Probing {target.rule_id} at {target.clause}: {target.sentence[:90]}...\n")

started = time.perf_counter()
card = ds.explain_one(target, use_cache=False)
elapsed = time.perf_counter() - started

print(f"source    : {card.source}  (attempts={card.attempts})")
print(f"elapsed   : {elapsed:.2f}s")
print(f"tokens    : prompt={card.prompt_tokens} completion={card.completion_tokens}")
if card.problems:
    print(f"problems  : {card.problems}")
print()
for field in ds.CARD_FIELDS:
    print(f"[{field}]\n{getattr(card, field)}\n")
