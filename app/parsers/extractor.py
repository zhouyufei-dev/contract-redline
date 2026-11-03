"""Turn a local PDF / DOCX file into plain text.

This is the only place in the project that knows about file formats.
Everything downstream (rules, engine, LLM, report) works on plain strings,
so swapping the extractor out later does not touch the rest of the app.

Contract:
    extract_text(path) -> str

Supported: .pdf (text layer), .docx, .txt
Not supported (MVP): scanned / image-only PDFs — we detect them and say so
clearly instead of silently returning an empty string.
"""

from __future__ import annotations

from pathlib import Path

# 少于这么多字符，基本可以断定 PDF 是扫描件（没有文字层）。
# 一页正常合同的文字通常在 1500 字符以上。
MIN_PDF_CHARS = 50


class ExtractionError(Exception):
    """Raised when a file cannot be turned into text.

    The message is meant to be shown to the end user, so it is written in
    plain English with no stack-trace jargon.
    """


def extract_text(path: str | Path) -> str:
    """Read a contract file and return its plain text.

    Args:
        path: path to a .pdf, .docx or .txt file.

    Returns:
        The document text, with one blank line between paragraphs / pages.

    Raises:
        ExtractionError: file missing, unsupported type, or no text layer.
    """
    file = Path(path)

    if not file.exists():
        raise ExtractionError(f"File not found: {file}")
    if not file.is_file():
        raise ExtractionError(f"Not a file: {file}")

    suffix = file.suffix.lower()

    if suffix == ".pdf":
        text = _extract_pdf(file)
    elif suffix == ".docx":
        text = _extract_docx(file)
    elif suffix == ".txt":
        text = _extract_txt(file)
    elif suffix == ".doc":
        # 老版 .doc 是二进制格式，python-docx 读不了。
        raise ExtractionError(
            "Legacy .doc files are not supported. "
            "Open it in Word and save as .docx, then try again."
        )
    else:
        raise ExtractionError(
            f"Unsupported file type '{suffix or '(none)'}'. "
            "Please upload a .pdf or .docx file."
        )

    text = text.strip()
    if not text:
        raise ExtractionError(
            "No readable text was found in this file. "
            "If it is a scanned document (photos or images of paper), "
            "it needs OCR first, which this version does not support."
        )
    return text


# --------------------------------------------------------------------------
# .pdf
# --------------------------------------------------------------------------

def _extract_pdf(file: Path) -> str:
    """pdfplumber, page by page.

    Tables are extracted separately because contract fee schedules and
    revision limits often live in tables, and page.extract_text() can
    flatten them into unusable columns.
    """
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover - install problem, not code
        raise ExtractionError(
            "PDF support is not installed. Run: pip install pdfplumber"
        ) from exc

    chunks: list[str] = []

    try:
        with pdfplumber.open(str(file)) as pdf:
            for page_no, page in enumerate(pdf.pages, start=1):
                page_text = page.extract_text() or ""
                if page_text.strip():
                    chunks.append(f"--- Page {page_no} ---\n{page_text.strip()}")

                for table in page.extract_tables() or []:
                    rows = []
                    for row in table:
                        cells = [(c or "").strip() for c in row]
                        if any(cells):
                            rows.append(" | ".join(cells))
                    if rows:
                        chunks.append(
                            f"--- Page {page_no} table ---\n" + "\n".join(rows)
                        )
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError(
            f"Could not read this PDF. The file may be corrupted or "
            f"password-protected ({type(exc).__name__})."
        ) from exc

    text = "\n\n".join(chunks)

    if len(text.strip()) < MIN_PDF_CHARS:
        raise ExtractionError(
            "This PDF appears to be a scanned document (images of pages "
            "rather than text). This version only supports PDFs with a "
            "text layer. Try exporting the original document to PDF again, "
            "or paste the text into a .txt file."
        )
    return text


# --------------------------------------------------------------------------
# .docx
# --------------------------------------------------------------------------

def _extract_docx(file: Path) -> str:
    """python-docx, paragraphs in document order, plus table contents.

    Heading styles are prefixed with '#' so that the contract's section
    structure survives into the plain text. The rules do not need it, but
    the report does: quoting "Section 3.1" is far more useful than quoting
    a bare sentence.
    """
    try:
        import docx
    except ImportError as exc:  # pragma: no cover - install problem, not code
        raise ExtractionError(
            "DOCX support is not installed. Run: pip install python-docx"
        ) from exc

    try:
        document = docx.Document(str(file))
    except Exception as exc:
        raise ExtractionError(
            f"Could not read this DOCX. It may be corrupted, or it may be a "
            f"legacy .doc renamed to .docx ({type(exc).__name__})."
        ) from exc

    blocks: list[str] = []

    for para in document.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style = (para.style.name or "").lower()
        if style.startswith("heading") or style == "title":
            blocks.append(f"# {text}")
        else:
            blocks.append(text)

    for index, table in enumerate(document.tables, start=1):
        rows = []
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if any(cells):
                rows.append(" | ".join(cells))
        if rows:
            blocks.append(f"--- Table {index} ---\n" + "\n".join(rows))

    return "\n\n".join(blocks)


# --------------------------------------------------------------------------
# .txt  (not a product feature — it is here so we can test the pipeline fast)
# --------------------------------------------------------------------------

def _extract_txt(file: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return file.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise ExtractionError("Could not decode this text file.")
