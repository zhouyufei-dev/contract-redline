"""Read the rendered page the way a test does, and print what a visitor would see.

Checks the two things that were wrong on screen: the footer placeholders and the
contradictory file-size labels. Prints only the lines that matter.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

at = AppTest.from_file(str(ROOT / "app" / "web" / "streamlit_app.py"), default_timeout=90)
at.run()
if at.exception:
    print("exception:", at.exception)
    sys.exit(1)

blobs = [m.value for m in at.markdown]
text = "\n".join(blobs)

print("markdown blocks:", len(blobs))
print()

print("--- identity in the rendered output ---")
for needle in ("Contract Redline", "Kowloon", "support@contractredline.io", "contractredline.io"):
    print(f"  {needle:32} {'present' if needle in text else 'MISSING'}")
print(f"  {'any [placeholder]':32} {'FOUND: ' + str(text[text.find('[') - 40:text.find('[') + 40]) if '[' in text.replace('[data-testid', '') else 'none'}")
print()

print("--- file size wording ---")
for line in text.splitlines():
    if "MB" in line:
        print("  ", line.strip()[:170])
print()

print("--- footer block ---")
for blob in blobs:
    if "support@" in blob or "All rights reserved" in blob or "Terms" in blob and "Privacy" in blob:
        print(blob[:700])
        print("  ...")
        break
