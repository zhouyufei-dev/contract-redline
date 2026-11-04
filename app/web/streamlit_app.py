r"""Entry point. Registers the pages and hands control to Streamlit.

    streamlit run app/web/streamlit_app.py        (or `.\web.ps1`)

This file used to be the scanner page. It is now only a router, because the
service has to publish a Terms of Service, a Privacy Policy and a Refund Policy
at stable URLs - a payment processor will not approve an account whose legal
pages are behind a query string.

The pages live in `pages.py`; the stylesheet and footer live in `ui.py`. Nothing
in this file, or in those two, decides whether a clause is a risk: that is still
`app/rules/` + `app/engine/`, reached through `app/pipeline.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make `import app...` work no matter which directory the server was started
# from. Locally the repo root happens to be the working directory, so this line
# changes nothing; on a host that starts the app from somewhere else (Streamlit
# Community Cloud runs the main file by path) the import would otherwise fail
# with "No module named 'app'" before the page renders.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from app.site import SITE
from app.web import pages, ui

st.set_page_config(
    page_title=f"{SITE.product} — scan your client contract",
    page_icon="◆",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# Applied once, before the router runs, so every page shares it. The stylesheet
# also hides Streamlit's own chrome (header, footer, "..." menu, status widget) -
# kept there, not here, so there is one place to edit and no second rule that can
# drift out of sync or fight it.
st.markdown(ui.CSS, unsafe_allow_html=True)

nav = st.navigation(
    [
        st.Page(func, title=title, url_path=path, default=(index == 0))
        for index, (title, path, func) in enumerate(pages.ROUTES)
    ],
    # Hidden: navigation lives in the footer, so the scanning page stays a page
    # with one action on it rather than one with a menu.
    position="hidden",
)

nav.run()

# Runs after whichever page ran above: one footer, defined once.
ui.footer()
