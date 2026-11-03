"""List every rule's id, name, severity and short why (for report design)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.rules.redlines_us import RULES  # noqa: E402

for rule in RULES:
    print(f"{rule.id}  sev={rule.severity:2}  {rule.name}")
    print(f"     why: {rule.why[:100]}")
