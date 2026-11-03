"""Throwaway probe: does a Stripe redirect land safely on the page?

Runs the real scanner page with ?session_id=... in the URL and no key in .env,
then with ?paid=true, and checks what a customer would see. Not part of the
suite; tools/test_paywall.py covers the logic.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ["STRIPE_SECRET_KEY"] = ""

from streamlit.testing.v1 import AppTest  # noqa: E402

HARNESS = """
import sys
sys.path.insert(0, {root!r})
import streamlit as st
from app.web import pages, ui
st.markdown(ui.CSS, unsafe_allow_html=True)
pages.scanner()
"""

tmp = Path(tempfile.mkdtemp())
script = tmp / "scanner.py"
script.write_text(HARNESS.format(root=str(ROOT)), encoding="utf-8")


def run(params: dict[str, str]) -> AppTest:
    at = AppTest.from_file(str(script), default_timeout=90)
    for key, value in params.items():
        at.query_params[key] = value
    at.run()
    return at


print("1. ?session_id=cs_test_... with no key configured")
at = run({"session_id": "cs_test_" + "z" * 30})
errors = [e.value for e in at.error]
print("   exception:", at.exception)
print("   errors   :", errors)
print("   unlocked :", at.session_state.get("paid_for"))
print("   credit   :", at.session_state.get("payment_credit"))
assert not at.exception, at.exception
assert errors, "expected a visible error explaining the missing key"
assert not at.session_state.get("paid_for"), "must not unlock"

print("2. ?paid=true, the string anyone can type")
at = run({"paid": "true"})
print("   exception:", at.exception)
print("   unlocked :", at.session_state.get("paid_for"))
print("   credit   :", at.session_state.get("payment_credit"))
assert not at.exception, at.exception
assert not at.session_state.get("paid_for"), "?paid=true must never unlock"
assert not at.session_state.get("payment_credit"), "?paid=true must not create credit"

print("3. no query string")
at = run({})
print("   exception:", at.exception)
assert not at.exception, at.exception

print("\nprobe passed")
