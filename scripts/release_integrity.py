#!/usr/bin/env python3
"""DEEPSIFT v1 research release — scientific-artifact integrity manifest.

    uv run python scripts/release_integrity.py --write     # record SHA-256 of every scientific artifact (once, at release freeze)
    uv run python scripts/release_integrity.py --verify    # recompute and compare; exit 1 on any difference

Covers every Phase 3 run artifact, frozen config, split, dataset manifest, review/Jev record and phase report. Presentation
files (web app, figures, paper, README) are deliberately NOT covered: they may change; the science may not.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "release" / "science-artifacts.json"
GLOBS = ["artifacts/phase3/**/*", "artifacts/phase3_1/**/*", "artifacts/phase3_2/**/*", "artifacts/phase3_3/**/*", "artifacts/phase3_4/**/*",
         "artifacts/phase3_final/**/*", "config/phase3_*.json", "config/phase2.yaml", "data/splits/*.json", "data/manifests/navcam_*.json",
         "data/manifests/synthetic_controls_*.json", "data/review/*.json", "docs/phase3*-report.md", "docs/phase3-final-test-report.md",
         "docs/jev-evaluation.md", "docs/jev-model-selection.md"]


def collect() -> dict[str, str]:
    files = sorted({p for g in GLOBS for p in ROOT.glob(g) if p.is_file()})
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def aggregate(h: dict[str, str]) -> str:
    return hashlib.sha256("\n".join(f"{k} {v}" for k, v in sorted(h.items())).encode()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    now = collect()
    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({"release": "deepsift-v1-research", "files": len(now), "aggregate_sha256": aggregate(now), "sha256": now}, indent=1))
        print(f"recorded {len(now)} scientific artifacts · aggregate {aggregate(now)}")
        return 0
    rec = json.loads(OUT.read_text())["sha256"]
    changed = [k for k in rec if now.get(k) != rec[k]]
    added = [k for k in now if k not in rec]
    print(json.dumps({"files_recorded": len(rec), "unchanged": len(rec) - len(changed), "changed_or_missing": changed, "new_files": added,
                      "aggregate_sha256": aggregate(now), "verdict": "INTACT" if not changed and not added else "CHANGED"}, indent=1))
    return 0 if not changed and not added else 1


if __name__ == "__main__":
    sys.exit(main())
