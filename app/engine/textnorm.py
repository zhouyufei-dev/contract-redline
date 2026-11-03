"""Text normalisation and sentence segmentation.

Why this exists
---------------
A regex that looks perfect against a .txt file silently fails against a real
PDF, because PDF extraction wraps every ~90 characters. The clause

    ... within sixty (60)
    days of the invoice date ...

contains the same words, but `r"sixty \\(60\\) days"` no longer matches. Measured
in tools/check_pdf_quality.py: the raw PDF text loses 2 of 19 red flags; after
whitespace collapsing it loses 0.

Design constraint
-----------------
`normalize()` must be length-preserving (1 character in, 1 character out).
Character offsets are the only thing linking a match back to the original page,
so a normalisation step that changes the length would silently corrupt every
piece of evidence we quote to the user.

Two layers:
  1. normalize()          - 1:1 character substitution (smart quotes, dashes)
  2. split_sentences()    - segments the text, then collapses whitespace
                            *inside each segment*
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --------------------------------------------------------------------------
# 1:1 character normalisation
# --------------------------------------------------------------------------

# Every entry maps exactly one character to exactly one character, so the
# string length never changes. Do NOT add multi-character mappings here.
_CHAR_MAP = {
    "\u2018": "'",   # left single quote
    "\u2019": "'",   # right single quote / apostrophe  <- the big one in PDFs
    "\u201a": "'",
    "\u201b": "'",
    "\u201c": '"',   # left double quote
    "\u201d": '"',   # right double quote
    "\u201e": '"',
    "\u2013": "-",   # en dash   ("Net–60")
    "\u2014": "-",   # em dash
    "\u2212": "-",   # minus sign
    "\u00a0": " ",   # non-breaking space
    "\u2007": " ",
    "\u202f": " ",
    "\u200b": " ",   # zero-width space -> space (NOT deletion: length must hold)
    "\ufeff": " ",   # BOM
    "\u2032": "'",
    "\u00b4": "'",
}


def normalize(text: str) -> str:
    """Replace typographic characters with their ASCII equivalents.

    Length-preserving. Call this exactly once, before anything else touches
    the extracted text.
    """
    return text.translate(str.maketrans(_CHAR_MAP))


def collapse_whitespace(text: str) -> str:
    """Collapse all runs of whitespace into a single space and strip."""
    return re.sub(r"\s+", " ", text).strip()


# --------------------------------------------------------------------------
# Sentence segmentation
# --------------------------------------------------------------------------

# Words whose trailing period does not end a sentence. Without this list,
# "Northwind Retail Group, Inc., a Delaware corporation" becomes two sentences
# and the evidence quote gets cut in half.
_ABBREVIATIONS = {
    "inc", "llc", "ltd", "co", "corp", "plc", "lp", "llp",
    "u.s", "us", "no", "nos", "vs", "v",
    "mr", "mrs", "ms", "dr", "prof", "st", "jr", "sr",
    "e.g", "i.e", "etc", "approx", "dept", "est", "al", "fig",
}

# "2.2 Payment Terms." left us with a trailing "2.2" fragment if we split
# inside the number. A period that sits between two digits is part of a
# section number, never a full stop.
_SECTION_NUMBER_HEAD = re.compile(r"^\s*(\d+(?:\.\d+){0,2})\.?\s+\S")

_SENT_BOUNDARY_CHAR = re.compile(r"[.!?]")
_PARA_BREAK = re.compile(r"\n[ \t]*\n")
_HEADING_LINE = re.compile(r"\n(?=\s*\d+(?:\.\d+){0,2}\.?\s+[A-Z])")
_WORD_TAIL = re.compile(r"([A-Za-z][A-Za-z.]*)$")


@dataclass
class Sentence:
    """One segment of the contract, with everything the engine needs.

    Attributes:
        text:   whitespace-collapsed text; this is what regexes run against.
        start:  offset into the normalised document (start of raw segment).
        end:    offset into the normalised document (end of raw segment).
        clause: nearest preceding section number ("2.3"), or "" if none.
        index:  position of this segment in document order.
    """

    text: str
    start: int
    end: int
    clause: str = ""
    index: int = 0

    def __str__(self) -> str:  # pragma: no cover - debugging aid
        prefix = f"[{self.clause}] " if self.clause else ""
        return f"{prefix}{self.text}"


def _is_sentence_period(text: str, pos: int) -> bool:
    """Decide whether the '.' at `pos` actually terminates a sentence."""
    # Part of a section number ("2.2")?
    if 0 < pos < len(text) - 1:
        prev_char = text[pos - 1]
        next_char = text[pos + 1]
        if prev_char.isdigit() and next_char.isdigit():
            return False

    # Known abbreviation ("Inc.", "e.g.")?
    match = _WORD_TAIL.search(text[:pos])
    if match:
        word = match.group(1).lower().rstrip(".")
        if word in _ABBREVIATIONS:
            return False
        # "U.S." / "e.g." style: the tail itself contains inner dots
        if word and all(p in _ABBREVIATIONS for p in word.split(".") if p):
            if "." in word:
                return False

    # Next non-space character must look like the start of a new sentence.
    rest = text[pos + 1:]
    stripped = rest.lstrip(" \t")
    if not stripped:
        return True
    # A newline right after the period is a strong signal.
    if rest[: len(rest) - len(stripped)].find("\n") >= 0:
        return True
    first = stripped[0]
    if first.islower():
        return False
    return True


def _boundaries(text: str) -> list[int]:
    """Offsets at which a new segment starts."""
    cuts: set[int] = set()

    for m in _SENT_BOUNDARY_CHAR.finditer(text):
        pos = m.start()
        if _is_sentence_period(text, pos):
            cuts.add(m.end())

    for m in _PARA_BREAK.finditer(text):
        cuts.add(m.end())

    for m in _HEADING_LINE.finditer(text):
        cuts.add(m.start() + 1)

    return sorted(cuts)


def split_sentences(text: str) -> list[Sentence]:
    """Segment normalised text into sentences, tracking section numbers.

    `text` must already have been passed through normalize().
    """
    if not text.strip():
        return []

    cuts = _boundaries(text)
    spans: list[tuple[int, int]] = []
    cursor = 0
    for cut in cuts:
        if cut > cursor:
            spans.append((cursor, cut))
            cursor = cut
    if cursor < len(text):
        spans.append((cursor, len(text)))

    sentences: list[Sentence] = []
    current_clause = ""

    for start, end in spans:
        raw = text[start:end]
        collapsed = collapse_whitespace(raw)
        if not collapsed:
            continue

        head = _SECTION_NUMBER_HEAD.match(collapsed)
        if head:
            current_clause = head.group(1)

        sentences.append(
            Sentence(
                text=collapsed,
                start=start,
                end=end,
                clause=current_clause,
                index=len(sentences),
            )
        )

    return sentences


def prepare(text: str) -> list[Sentence]:
    """normalize + split, the only entry point callers should use."""
    return split_sentences(normalize(text))
