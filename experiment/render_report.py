"""Render <run_dir>/report/report.md to report.pdf (and report.html).

Run from the repo root:
    uv run --with markdown --with weasyprint python3 -I experiment/render_report.py <run_dir>

Image paths in the markdown are relative to report/, so the HTML is written next to it.
"""

import sys
from pathlib import Path

import markdown
from weasyprint import HTML

CSS = """
@page { size: A4; margin: 18mm 16mm; @bottom-right { content: counter(page); font-size: 8pt; color: #52514e; } }
body { font-family: "DejaVu Sans", sans-serif; font-size: 9.5pt; line-height: 1.45; color: #0b0b0b; }
h1 { font-size: 17pt; margin: 0 0 8pt; }
h2 { font-size: 12.5pt; margin: 16pt 0 6pt; border-bottom: 1px solid #e1e0d9; padding-bottom: 2pt; }
table { border-collapse: collapse; margin: 6pt 0 10pt; font-size: 8.5pt; }
th, td { border-bottom: 1px solid #e1e0d9; padding: 2.5pt 7pt; text-align: left; }
th { color: #52514e; font-weight: 600; }
img { width: 100%; margin: 4pt 0; }
code { font-size: 8.5pt; background: #f3f2ee; padding: 0 2pt; }
a { color: #2a78d6; }
"""


def main(run):
    src = run / "report" / "report.md"
    body = markdown.markdown(src.read_text(), extensions=["tables"])
    html = f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{body}</body></html>"
    out_html = src.with_suffix(".html")
    out_html.write_text(html)
    HTML(filename=str(out_html)).write_pdf(src.with_suffix(".pdf"))
    print(src.with_suffix(".pdf"))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
