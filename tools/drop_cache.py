"""Delete the cached card for one clause, so the next run re-asks the API for it."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.engine.matcher import scan  # noqa: E402
from app.engine.textnorm import prepare  # noqa: E402
from app.llm.deepseek_client import CACHE_DIR, _cache_key  # noqa: E402
from app.parsers.extractor import extract_text  # noqa: E402
from app.rules.redlines_us import RULES  # noqa: E402

clause = sys.argv[1] if len(sys.argv) > 1 else "7.2"
settings = get_settings()
findings = [f for f in scan(prepare(extract_text("data/samples/fake_contract_01.docx")), RULES)
            if f.is_reportable]

for finding in findings:
    if finding.clause == clause:
        path = CACHE_DIR / f"{_cache_key(settings.model, finding)}.json"
        if path.exists():
            path.unlink()
            print(f"removed cache for {finding.rule_id} @ {clause}")
        else:
            print(f"no cache for {finding.rule_id} @ {clause}")
