"""Glue between a browser upload and the pipeline.

Streamlit hands us a filename and a blob of bytes. Everything else in the
project works on a path, so the job here is: check the upload, put it in a
throwaway temp folder, run `app.pipeline.analyze`, delete the folder.

Keeping this out of `streamlit_app.py` has one practical benefit - the upload
rules can be tested without a browser or a Streamlit runtime.

Nothing is written outside the temp folder, and nothing is kept after the
analysis: the report is a string by then, and the contract is not ours to store.
"""

from __future__ import annotations

import contextlib
import re
import shutil
import tempfile
from pathlib import Path
from typing import Iterator

from app.pipeline import Analysis, analyze

ALLOWED_SUFFIXES = (".pdf", ".docx")
MAX_BYTES = 20 * 1024 * 1024  # 20 MB - a long contract is ~1 MB
#: The same limit in MB, for anything that has to *say* the number (the uploader
#: help text, the page footer, .streamlit/config.toml - see test_web.py, which
#: fails if those three ever disagree).
MAX_MB = MAX_BYTES // (1024 * 1024)

# Anything outside this set is replaced. Parentheses and dashes appear in real
# file names ("Acme - Design Contract (v2).docx") and are harmless; slashes,
# colons, quotes and control characters are not.
_UNSAFE = re.compile(r"[^A-Za-z0-9._ ()\-]+")


class UploadError(Exception):
    """Bad upload. The message is user-facing, plain English, no jargon."""


def safe_name(name: str | None) -> str:
    """Strip directories and anything that is not a boring filename character.

    A browser may send `..\\..\\etc\\passwd` or a 4,000-character name; both are
    reduced to a plain file name before anything touches the disk.
    """
    base = Path((name or "").replace("\\", "/")).name
    base = _UNSAFE.sub("_", base).strip(" ._") or "contract"
    stem, dot, suffix = base.rpartition(".")
    if dot and suffix.lower() in ("pdf", "docx"):
        base = f"{stem[:80] or 'contract'}.{suffix.lower()}"
    else:
        base = f"{base[:80]}.pdf" if not dot else f"{stem[:80]}.{suffix[:8]}"
    return base


def validate(name: str | None, data: bytes | None) -> str:
    """Return the lower-case suffix, or raise UploadError with a reason."""
    if not data:
        raise UploadError("That file looks empty. Try uploading it again.")
    if len(data) > MAX_BYTES:
        size = len(data) / (1024 * 1024)
        raise UploadError(
            f"That file is {size:.0f} MB. The limit is "
            f"{MAX_MB} MB - a contract is normally under 2 MB."
        )
    suffix = Path((name or "").replace("\\", "/")).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        shown = suffix or "(no extension)"
        raise UploadError(
            f"We cannot read '{shown}' files. Please upload a PDF or a DOCX."
        )
    if suffix == ".pdf" and not data.lstrip()[:5] == b"%PDF-":
        raise UploadError(
            "That file is named .pdf but is not a PDF. "
            "If it came from a Mac or a scanner app, export it again as PDF."
        )
    if suffix == ".docx" and not data.lstrip()[:2] == b"PK":
        raise UploadError(
            "That file is named .docx but is not a Word document. "
            "An old .doc renamed to .docx will not open - save it as .docx in Word."
        )
    return suffix


@contextlib.contextmanager
def saved_upload(name: str | None, data: bytes) -> Iterator[Path]:
    """Write the upload to a temp folder and always clean up afterwards."""
    folder = Path(tempfile.mkdtemp(prefix="contract-redline-"))
    try:
        target = folder / safe_name(name)
        target.write_bytes(data)
        yield target
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def analyze_upload(
    name: str | None,
    data: bytes,
    *,
    use_llm: bool = True,
    use_cache: bool = False,
    on_step=None,
) -> Analysis:
    """Full pipeline on an uploaded file. Raises UploadError or ExtractionError.

    `source_name` is the name the user sees in the report, so it stays the
    general name from the browser (kept readable) rather than the sanitised
    temp filename.

    `use_cache` defaults to False, unlike the command-line path: the cache writes
    every clause it explains to data/cache/llm, and once this page is on a public
    URL that folder fills up with other people's contract text. The page promises
    the file is deleted the moment the scan finishes, and a disk cache of clause
    quotes makes that promise untrue. The command line keeps the cache - it is a
    development convenience there, and there is only one user.
    """
    validate(name, data)
    display = Path((name or "contract").replace("\\", "/")).name
    with saved_upload(name, data) as path:
        return analyze(
            path,
            use_llm=use_llm,
            use_cache=use_cache,
            source_name=display[:120] or path.name,
            on_step=on_step,
        )


def download_name(source_name: str) -> str:
    """`freelance-agreement.docx` -> `freelance-agreement.report.html`."""
    stem = Path(source_name).stem or "contract"
    return f"{stem}.report.html"
