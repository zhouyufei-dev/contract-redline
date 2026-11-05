"""Prove what happens to an uploaded file, rather than trusting the docstring.

Records every temp folder the web path creates, runs a real scan from bytes the
way the page does, then checks the folders are gone. Also fails loudly if any
contract text lands on disk outside that folder.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.web import uploads  # noqa: E402

DOCX = ROOT / "data" / "samples" / "fake_contract_01.docx"
CACHE = ROOT / "data" / "cache" / "llm"

created: list[Path] = []
_real_mkdtemp = tempfile.mkdtemp


def spy(*args, **kwargs):
    folder = _real_mkdtemp(*args, **kwargs)
    created.append(Path(folder))
    return folder


def snapshot(folder: Path) -> set[str]:
    return {str(p) for p in folder.rglob("*")} if folder.exists() else set()


before_cache = snapshot(CACHE)
before_tmp = {p.name for p in Path(tempfile.gettempdir()).glob("contract-redline-*")}

tempfile.mkdtemp = spy
try:
    data = DOCX.read_bytes()
    analysis = uploads.analyze_upload("fake_contract_01.docx", data, use_llm=False)
finally:
    tempfile.mkdtemp = _real_mkdtemp

print(f"cards produced        : {len(analysis.report.cards)}")
print(f"temp folders created  : {len(created)}")
for folder in created:
    print(f"   {folder.name}  still exists = {folder.exists()}")

after_cache = snapshot(CACHE)
after_tmp = {p.name for p in Path(tempfile.gettempdir()).glob("contract-redline-*")}

print(f"leftover temp folders : {sorted(after_tmp - before_tmp)}")
print(f"llm cache grew        : {sorted(after_cache - before_cache) or 'no'}")
print()
ok = all(not f.exists() for f in created) and not (after_tmp - before_tmp) and not (
    after_cache - before_cache)
print("VERDICT:", "file removed from disk after the scan" if ok else "SOMETHING PERSISTS")
sys.exit(0 if ok else 1)
