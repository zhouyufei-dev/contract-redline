"""Build a text-layer PDF test sample from the plain-text contract.

Why: the MVP must handle PDF *and* DOCX. This gives us a PDF that is
guaranteed to contain every red flag, with the same 131 paragraphs, so the
rule engine can be tested against both formats and produce identical results.

Deliberately NOT doing anything fancy: no columns, no headers/footers, no
tables. That keeps this file honest as a "clean text layer" baseline. A
second, messier PDF (headers, hyphenated line breaks) is worth adding later
when we tune app/engine/textnorm.py.

Run from the project root:
    .\\.venv\\Scripts\\python.exe tools\\build_pdf.py
"""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "data" / "samples" / "fake_contract_01.txt"
TARGET = ROOT / "data" / "samples" / "fake_contract_01.pdf"

# US Letter in millimetres
PAGE_W, PAGE_H = 215.9, 279.4
MARGIN = 25.4


class ContractPDF(FPDF):
    def header(self) -> None:
        # A running header is realistic for contracts, and it is also the kind
        # of repeated line that textnorm.drop_repeated_lines() must remove later.
        self.set_font("Times", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 6, "Northwind Retail Group / Rivera Studio - Confidential",
                  align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.ln(4)

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("Times", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 6, f"Page {self.page_no()} of {{nb}}",
                  align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)


def main() -> None:
    lines = SOURCE.read_text(encoding="utf-8").splitlines()

    pdf = ContractPDF(format="letter", unit="mm")
    pdf.set_margins(MARGIN, 30, MARGIN)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_font("Times", size=11)

    for line in lines:
        text = line.strip()
        if not text:
            pdf.ln(4)
            continue

        is_heading = (
            text.isupper()
            or text[:2].rstrip(".").isdigit()
            and "." not in text[:4]
        )
        pdf.set_font("Times", "B" if is_heading else "", 11)
        # multi_cell wraps long paragraphs; that is what creates the
        # mid-sentence line breaks the normaliser has to stitch back together.
        pdf.multi_cell(0, 5.2, text, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1.6)

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(TARGET))
    print(f"WROTE: {TARGET}  ({TARGET.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
