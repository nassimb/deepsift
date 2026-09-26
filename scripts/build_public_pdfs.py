#!/usr/bin/env python3
"""Render the paper and the one-pager to PDF: Markdown → styled HTML → Chrome headless --print-to-pdf.

    uvx --with markdown python scripts/build_public_pdfs.py

Outputs artifacts/public/deepsift-v1-paper.pdf and artifacts/public/deepsift-one-pager.pdf (presentation files, outside the
scientific integrity manifest). Content is taken verbatim from docs/*.md; figures from docs/figures/*.png.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "public"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CSS = """
@page { size: Letter; margin: 16mm 16mm 16mm 16mm; }
body { font-family: "Charter", "Georgia", serif; font-size: 10.2pt; line-height: 1.42; color: #111; max-width: 100%; }
h1 { font-size: 16pt; line-height: 1.2; margin: 0 0 6pt; }
h2 { font-size: 12pt; margin: 14pt 0 4pt; border-bottom: 0.5pt solid #999; padding-bottom: 2pt; page-break-after: avoid; }
h3 { font-size: 10.5pt; margin: 10pt 0 3pt; }
p, li { margin: 3pt 0; }
table { border-collapse: collapse; margin: 4pt 0 8pt; font-size: 8.8pt; page-break-inside: avoid; }
th, td { border: 0.5pt solid #bbb; padding: 2pt 5pt; text-align: left; vertical-align: top; }
th { background: #f0f0f0; }
code { font-family: "Menlo", monospace; font-size: 8.4pt; }
img { max-width: 100%; display: block; margin: 6pt auto 2pt; page-break-inside: avoid; }
em { color: #333; }
blockquote { margin: 4pt 0 4pt 10pt; padding-left: 8pt; border-left: 2pt solid #999; color: #222; }
.onepager body, body.onepager { font-size: 9.1pt; line-height: 1.3; }
body.onepager h1 { font-size: 15pt; margin-bottom: 2pt; }
body.onepager p { margin: 3pt 0; }
body.onepager table { font-size: 8.2pt; margin: 2pt 0 4pt; }
body.onepager ul { margin: 1pt 0; padding-left: 14pt; }
body.onepager li { margin: 0.5pt 0; }
body.onepager th, body.onepager td { padding: 1pt 4pt; }
body.onepager { font-size: 8.8pt; line-height: 1.26; }
"""


LIST = re.compile(r"^\s*([-*]|\d+\.)\s")


def blank_before_lists(text: str) -> str:
    """Python-Markdown needs a blank line before a list that follows a paragraph (GitHub does not); add it for printing."""
    out: list[str] = []
    for line in text.splitlines():
        if LIST.match(line) and out and out[-1].strip() and not LIST.match(out[-1]) and not out[-1].startswith((" ", "\t")):
            out.append("")
        out.append(line)
    return "\n".join(out)


def render(md_path: Path, pdf_path: Path, cls: str = "") -> None:
    html_body = markdown.markdown(blank_before_lists(md_path.read_text()), extensions=["tables", "sane_lists"])
    html = f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body class='{cls}'>{html_body}</body></html>"
    tmp = md_path.parent / f".{md_path.stem}.print.html"      # alongside the .md so relative figure paths resolve
    tmp.write_text(html)
    try:
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={pdf_path}", tmp.as_uri()],
                       check=True, capture_output=True, timeout=120)
    finally:
        tmp.unlink(missing_ok=True)


def main() -> int:
    if not Path(CHROME).exists() and not shutil.which("chromium"):
        print("Chrome not found; Markdown sources remain the canonical versions")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    render(ROOT / "docs" / "deepsift-paper.md", OUT / "deepsift-v1-paper.pdf")
    render(ROOT / "docs" / "deepsift-one-pager.md", OUT / "deepsift-one-pager.pdf", "onepager")
    for f in sorted(OUT.glob("*.pdf")):
        print(f"→ {f.relative_to(ROOT)} · {f.stat().st_size / 1e3:.0f} kB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
