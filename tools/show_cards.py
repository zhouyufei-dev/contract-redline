"""Print the cached card for each finding matching a rule id (quick QA read)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

wanted = set(sys.argv[1:] or ["R11", "R18"])
for path in sorted(Path("data/cache/llm").glob("*.json")):
    data = json.loads(path.read_text(encoding="utf-8"))
    if data["rule_id"] not in wanted:
        continue
    print(f"### {data['rule_id']}  attempts={data['attempts']}")
    print(f"clause : {data['clause'][:110]}")
    print(f"why    : {data['why']}")
    print(f"fix    : {data['fix']}")
    print(f"ask    : {data['ask']}")
    print(f"fallbk : {data['fallback']}")
    print(f"walk   : {data['walk_away']}\n")
