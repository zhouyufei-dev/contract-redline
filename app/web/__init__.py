"""Web front end package.

`streamlit_app.py` is the page; `uploads.py` is the upload -> pipeline glue.
Both are thin: every decision about what counts as a risk happens in
`app/rules/` and `app/engine/`, and neither file in here may second-guess it.
"""
