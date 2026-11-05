"""Shared look and feel: the stylesheet, the hero, the footer.

Kept apart from `pages.py` so that a page is about content and this file is
about pixels. `streamlit_app.py` injects the CSS once, before the router runs,
and every page ends with `footer()`.

The footer carries the operator's legal identity on purpose: a reviewer (or a
customer) should be able to find out who they are dealing with without digging.
"""

from __future__ import annotations

import streamlit as st

from app.site import SITE


CSS = """
<style>
:root {
  --ink: #14161b;
  --body: #3b424c;
  --muted: #6b7280;
  --line: #e4e4e0;
  --critical: #b42318;
}

/* Streamlit chrome: this is a product page, not a notebook.
   Header, footer, the "..." menu and the running-status widget all belong to
   the dev tool, not to the product. `visibility` instead of `display` keeps the
   layout metrics Streamlit's own JS reads while the app boots; height:0 stops
   the hidden header from reserving its 3.75rem strip at the top. */
#MainMenu, footer, header[data-testid="stHeader"],
div[data-testid="stStatusWidget"] { visibility: hidden !important; height: 0 !important; }
[data-testid="stSidebarNav"] { display: none; }
[data-testid="stSidebar"] { display: none; }
.block-container {
  max-width: 780px;
  padding-top: 3.2rem;
  padding-bottom: 1.5rem;
}
.stApp { background: #ffffff; }

html, body, [class*="css"], .stMarkdown, p, li, label, input, button {
  font-family: ui-sans-serif, -apple-system, "Segoe UI", Roboto,
               "Helvetica Neue", Arial, sans-serif;
  color: var(--body);
}

.cr-kicker {
  margin: 0 0 14px;
  font-size: 11.5px;
  font-weight: 650;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--critical);
}
.cr-kicker span {
  display: inline-block;
  width: 8px; height: 8px;
  border-radius: 2px;
  background: var(--critical);
  margin-right: 8px;
  vertical-align: 1px;
}

.cr-h1 {
  margin: 0 0 16px;
  font-size: 40px;
  line-height: 1.12;
  letter-spacing: -0.025em;
  font-weight: 620;
  color: var(--ink);
}

.cr-sub {
  margin: 0 0 14px;
  font-size: 17px;
  line-height: 1.55;
  color: var(--ink);
  max-width: 60ch;
}

.cr-sub strong { color: var(--ink); font-weight: 600; }

/* The paragraph under the subtitle: what the tool actually does. Quieter than
   the sub, larger than the small print, so the three lines read as one
   descending scale rather than three competing blocks. */
.cr-lede {
  margin: 0 0 30px;
  font-size: 15px;
  line-height: 1.68;
  color: var(--body);
  max-width: 66ch;
}

/* The free-check / price line, directly above the upload box. */
.cr-offer {
  margin: 0 0 10px;
  font-size: 13.5px;
  line-height: 1.55;
  color: var(--body);
}
.cr-offer strong { color: var(--ink); font-weight: 650; }

/* The privacy promise under the button. One shade louder than the fine print
   below it: it is the reason a stranger trusts the upload box with a contract. */
.cr-trust {
  margin: 14px 0 6px;
  font-size: 13px;
  line-height: 1.55;
  color: var(--ink);
}

/* Phones: the 40px headline and the 17px sub both wrap hard below ~640px, and
   the headline ran to four lines. Scaled down rather than reflowed - same
   proportions, just smaller, so desktop is untouched. */
@media (max-width: 640px) {
  .cr-h1 { font-size: 29px; line-height: 1.18; }
  .cr-sub { font-size: 15.5px; }
  .cr-lede { font-size: 14.5px; }
  .block-container { padding-top: 1.6rem; }
}

/* The upload box: the biggest thing on the page, on purpose. */
[data-testid="stFileUploaderDropzone"] {
  border: 2px dashed #d6d6d0;
  border-radius: 14px;
  background: #fbfbf9;
  padding: 34px 24px;
  transition: border-color .15s ease, background .15s ease;
}
[data-testid="stFileUploaderDropzone"]:hover {
  border-color: var(--critical);
  background: #fef9f8;
}
[data-testid="stFileUploaderDropzone"] button {
  border-radius: 8px !important;
  border: 1px solid var(--line) !important;
  background: #ffffff !important;
  color: var(--ink) !important;
  font-weight: 550 !important;
  box-shadow: none !important;
}
[data-testid="stFileUploaderDropzoneInstructions"] > div > span {
  font-size: 15px;
  color: var(--ink);
  font-weight: 550;
}
[data-testid="stFileUploaderDropzoneInstructions"] > div > small {
  font-size: 12.5px;
  color: var(--muted);
}

/* The main action. */
.stButton > button[kind="primary"] {
  width: 100%;
  border-radius: 10px;
  border: none;
  background: var(--ink);
  color: #ffffff;
  font-size: 16px;
  font-weight: 600;
  padding: 0.15rem 1rem;
  min-height: 50px;
  box-shadow: none;
  transition: background .15s ease, transform .05s ease;
}
.stButton > button[kind="primary"]:hover {
  background: #000000;
  color: #ffffff;
}
.stButton > button[kind="primary"]:active { transform: translateY(1px); }
.stButton > button[kind="primary"]:disabled {
  background: #c9c9c4; color: #ffffff;
}

.stButton > button:not([kind="primary"]) {
  border-radius: 10px;
  border: 1px solid var(--line);
  background: #ffffff;
  color: var(--ink);
  font-weight: 550;
  box-shadow: none;
}

/* Small print under the button. */
.cr-fine {
  margin: 14px 0 0;
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--muted);
  text-align: center;
}
.cr-fine strong { color: var(--body); font-weight: 550; }

/* The separator before the result. */
.cr-rule {
  height: 1px;
  background: var(--line);
  margin: 34px 0 26px;
  border: 0;
}

.cr-result-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  margin: 0 0 4px;
}
.cr-result-title {
  margin: 0;
  font-size: 15px;
  font-weight: 650;
  color: var(--ink);
  letter-spacing: -0.01em;
}
.cr-result-meta {
  margin: 0;
  font-size: 12.5px;
  color: var(--muted);
  text-align: right;
}
.cr-result-sub {
  margin: 6px 0 18px;
  font-size: 13.5px;
  color: var(--muted);
}

/* The report frame: a sheet of paper, not an embedded app. */
.cr-frame-label {
  margin: 0 0 8px;
  font-size: 11.5px;
  font-weight: 650;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--muted);
}

div[data-testid="stIFrame"] {
  border: 1px solid var(--line);
  border-radius: 12px;
  overflow: hidden;
  background: #f6f5f2;
  box-shadow: 0 1px 2px rgba(20, 22, 27, .04);
}

.stDownloadButton > button {
  width: 100%;
  border-radius: 10px;
  min-height: 44px;
  font-weight: 550;
}

/* ---- paywall ------------------------------------------------------------ */

.cr-paywall {
  margin: 20px 0 8px;
  padding: 26px 26px 22px;
  background: var(--ink);
  color: #e9e6dd;
  border-radius: 12px;
  border: 1px solid #000;
}

.cr-paywall p { margin: 0; }

.cr-paywall-kicker {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: .14em;
  text-transform: uppercase;
  color: #b9b4a6;
  margin-bottom: 10px !important;
}

.cr-paywall-title {
  font-size: 26px;
  line-height: 1.22;
  letter-spacing: -.01em;
  color: #ffffff;
  margin-bottom: 10px !important;
}

.cr-paywall-body {
  max-width: 58ch;
  font-size: 15px;
  line-height: 1.55;
  color: #d3d0c6;
  margin-bottom: 16px !important;
}

.cr-paywall-counts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0 0 20px;
  padding: 0;
  list-style: none;
}

.cr-paywall-counts li {
  padding: 5px 12px;
  border: 1px solid #3b3e46;
  border-radius: 999px;
  font-size: 12.5px;
  color: #e9e6dd;
}

.cr-paywall-counts strong { color: #ffffff; font-weight: 650; }

a.cr-paywall-cta {
  display: inline-block;
  padding: 13px 24px;
  background: #ffffff;
  color: var(--ink) !important;
  border-radius: 8px;
  font-size: 15px;
  font-weight: 650;
  text-decoration: none !important;
}

a.cr-paywall-cta:hover { background: #efece3; color: var(--ink) !important; }

.cr-paywall-fine {
  margin-top: 14px !important;
  font-size: 12px;
  line-height: 1.5;
  color: #9c988d;
}

/* Streamlit's toggle label. */
[data-testid="stWidgetLabel"] p { font-size: 13.5px; color: var(--body); }

/* The status widget is hidden with the rest of the chrome, up in the header
   rule - one place for all of it, so a later edit cannot leave half of it on. */

/* ---- legal pages ------------------------------------------------------- */

.cr-nav {
  margin: 0 0 26px;
  font-size: 13px;
  color: var(--muted);
}
.cr-nav a {
  color: var(--muted);
  text-decoration: none;
  border-bottom: 1px solid transparent;
}
.cr-nav a:hover { color: var(--ink); border-bottom-color: var(--ink); }

.stMarkdown h1 {
  font-size: 34px;
  line-height: 1.15;
  letter-spacing: -0.02em;
  font-weight: 620;
  color: var(--ink);
  margin: 0 0 18px;
}
.stMarkdown h2 {
  font-size: 19px;
  font-weight: 640;
  color: var(--ink);
  margin: 34px 0 10px;
  letter-spacing: -0.01em;
}
.stMarkdown h3 {
  font-size: 15.5px;
  font-weight: 640;
  color: var(--ink);
  margin: 24px 0 8px;
}
.stMarkdown p, .stMarkdown li {
  font-size: 14.8px;
  line-height: 1.72;
  color: var(--body);
}
.stMarkdown ul, .stMarkdown ol { padding-left: 22px; margin: 10px 0 14px; }
.stMarkdown li { margin: 5px 0; }
.stMarkdown strong { color: var(--ink); font-weight: 620; }
.stMarkdown a { color: var(--ink); text-decoration: underline; text-underline-offset: 2px; }
.stMarkdown hr { border: 0; border-top: 1px solid var(--line); margin: 28px 0; }

/* The footer, on every page. */
.cr-footer {
  margin-top: 56px;
  padding-top: 20px;
  border-top: 1px solid var(--line);
  font-size: 12.5px;
  line-height: 1.65;
  color: var(--muted);
}
.cr-footer a { color: var(--body); text-decoration: none; border-bottom: 1px solid var(--line); }
.cr-footer a:hover { color: var(--ink); border-bottom-color: var(--ink); }
.cr-footer-links { margin: 0 0 10px; }
.cr-footer p { margin: 0 0 4px; }
.cr-footer .cr-fine { text-align: left; margin-top: 10px; font-size: 12px; }
</style>
"""


def hero() -> None:
    st.markdown(
        """
        <p class="cr-kicker"><span></span>Contract Redline</p>
        <h1 class="cr-h1">Protect Your Work Before You Sign.</h1>
        <p class="cr-sub">
          Spot hidden contract risks before they cost you money, time, or
          ownership of your work.
        </p>
        <p class="cr-lede">
          Upload your freelance contract. Our rule-based checker scans 20 common
          contract risk types and shows you the clauses that deserve a closer
          look — with plain-English explanations and practical negotiation
          suggestions.
        </p>
        """,
        unsafe_allow_html=True,
    )


def crumb(label: str = "Back to the scanner") -> None:
    st.markdown(f'<p class="cr-nav"><a href="./">← {label}</a></p>', unsafe_allow_html=True)


def footer() -> None:
    st.markdown(
        f"""
        <div class="cr-footer">
          <p class="cr-footer-links">
            <a href="pricing">Pricing</a> &nbsp;·&nbsp;
            <a href="terms">Terms of Service</a> &nbsp;·&nbsp;
            <a href="privacy">Privacy Policy</a> &nbsp;·&nbsp;
            <a href="refund">Refund Policy</a>
          </p>
          <p>© {SITE.copyright_year} {SITE.operator} · {SITE.address}</p>
          <p><a href="mailto:{SITE.email}">{SITE.email}</a></p>
          <p class="cr-fine">
            {SITE.product} is software, not a law firm. It does not provide legal
            advice, and using it does not create an attorney–client relationship.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
