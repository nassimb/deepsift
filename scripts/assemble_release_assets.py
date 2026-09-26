#!/usr/bin/env python3
"""Assemble the publication assets for the GitHub release `deepsift-v1-research` into release/deepsift-v1-research/
(git-ignored) plus a zip, with SHA256SUMS. Copies small, already-committed presentation files only — no datasets.

    uv run python scripts/assemble_release_assets.py
"""

from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "release" / "deepsift-v1-research"
FILES = {
    "deepsift-v1-paper.pdf": "artifacts/public/deepsift-v1-paper.pdf",
    "deepsift-one-pager.pdf": "artifacts/public/deepsift-one-pager.pdf",
    "RELEASE_NOTES.md": "docs/release/github-release-notes-v1.md",
    "public-claims-checklist.md": "docs/public-claims-checklist.md",
    "science-artifacts.json": "docs/release/science-artifacts.json",
}
DIRS = {"figures": ("docs/figures", "*"), "media": ("artifacts/public/media", "*.png")}


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    for dst, src in FILES.items():
        shutil.copy(ROOT / src, OUT / dst)
    for dst, (src, pat) in DIRS.items():
        (OUT / dst).mkdir()
        for f in sorted((ROOT / src).glob(pat)):
            shutil.copy(f, OUT / dst / f.name)
    files = sorted(p for p in OUT.rglob("*") if p.is_file())
    (OUT / "SHA256SUMS").write_text("".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(OUT)}\n" for p in files))
    z = shutil.make_archive(str(OUT), "zip", OUT.parent, OUT.name)
    total = sum(p.stat().st_size for p in files)
    print(f"{len(files)} files · {total / 1e6:.1f} MB → {OUT.relative_to(ROOT)} and {Path(z).relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
