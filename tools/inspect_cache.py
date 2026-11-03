"""Which cached cards needed a repair, and what the guardrail complained about?"""
from __future__ import annotations

import json
import pathlib

root = pathlib.Path("data/cache/llm")
files = sorted(root.glob("*.json"))
print(f"{len(files)} cached cards\n")

for path in files:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("attempts", 1) > 1 or data.get("problems"):
        print(f"{data['rule_id']}  attempts={data['attempts']}  source={data['source']}")
        print(f"  clause: {data['clause'][:100]}")
        print(f"  problems: {data.get('problems')}")
        print()
