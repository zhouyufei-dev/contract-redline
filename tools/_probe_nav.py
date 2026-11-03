import sys, tempfile
from pathlib import Path
from streamlit.testing.v1 import AppTest

tmp = Path(tempfile.mkdtemp())
(tmp / "app.py").write_text(
    '''
import streamlit as st

def scan():
    st.markdown("<h1>SCANNER</h1>", unsafe_allow_html=True)
    st.button("Scan My Contract")

def terms():
    st.markdown("TERMS BODY")

pg = st.navigation([
    st.Page(scan, title="Scan", url_path="scan", default=True),
    st.Page(terms, title="Terms", url_path="terms"),
])
pg.run()
''',
    encoding="utf-8",
)

at = AppTest.from_file(str(tmp / "app.py"), default_timeout=60)
at.run()
print("exception:", at.exception)
print("markdown:", [m.value[:40] for m in at.markdown])
print("buttons:", [b.label for b in at.button])
try:
    at.switch_page("terms")
    print("after switch, markdown:", [m.value[:40] for m in at.markdown])
except Exception as exc:
    print("switch_page failed:", type(exc).__name__, exc)
