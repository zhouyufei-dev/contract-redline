"""Show exactly where the DOCX text and the TXT source differ."""

from __future__ import annotations

import difflib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.parsers.extractor import extract_text  # noqa: E402

docx_text = extract_text("data/samples/fake_contract_01.docx")
txt_text = extract_text("data/samples/fake_contract_01.txt")

print(f"docx: {len(docx_text)} chars, {len(docx_text.splitlines())} lines")
print(f"txt : {len(txt_text)} chars, {len(txt_text.splitlines())} lines")

if docx_text == txt_text:
    print("identical")
    raise SystemExit(0)

diff = list(
    difflib.unified_diff(
        txt_text.splitlines(keepends=False),
        docx_text.splitlines(keepends=False),
        fromfile="txt",
        tofile="docx",
        lineterm="",
        n=1,
    )
)
print("\n".join(diff[:60]))
print(f"\ndiff lines: {len(diff)}")

# 逐字符找第一个不同点
for i, (a, b) in enumerate(zip(txt_text, docx_text)):
    if a != b:
        print(f"\nfirst difference at index {i}")
        print(f"  txt  ...{txt_text[max(0, i - 60):i + 40]!r}")
        print(f"  docx ...{docx_text[max(0, i - 60):i + 40]!r}")
        break
else:
    print(f"\nprefix identical; longer one has {abs(len(txt_text) - len(docx_text))} extra chars")
    longer = txt_text if len(txt_text) > len(docx_text) else docx_text
    print(repr(longer[min(len(txt_text), len(docx_text)) - 80:]))
