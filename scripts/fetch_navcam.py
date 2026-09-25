#!/usr/bin/env python3
"""Download Navcam raw EDR products (.IMG + .LBL, all tiers) for ONE Phase 3 split and write a manifest.

    uv run python scripts/fetch_navcam.py --split development

Guards: validation needs --allow-validation; test needs --allow-test (neither is to be used until instructed).
Files keep the PDS archive structure under data/raw/navcam/MSLNAV_0XXX/DATA/SOLnnnnn/ (git-ignored); the manifest
data/manifests/navcam_<split>.json (committed) records URL, product ID, sol, UTC, SCLK, eye, site/drive/pose,
sequence, tier, compression method/rate/ratio, archive bytes, estimated downlink bytes and SHA-256 of IMG and LBL.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "pipeline"))

from deepsift.imaging.navcam import CuriosityNavcamAdapter, sha256_file  # noqa: E402

SPLITS = ROOT / "data" / "splits" / "phase3_splits.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", required=True, choices=["development", "validation", "test"])
    ap.add_argument("--allow-validation", action="store_true")
    ap.add_argument("--allow-test", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    if args.split == "validation" and not args.allow_validation:
        raise SystemExit("validation imagery is not to be downloaded yet (pass --allow-validation when instructed)")
    if args.split == "test" and not args.allow_test:
        raise SystemExit("the Phase 3 TEST interval is held out (pass --allow-test only for the final evaluation)")
    spec = json.loads(SPLITS.read_text())
    lo, hi = spec[args.split]["sols"]
    ad = CuriosityNavcamAdapter()
    refs = ad.discover_products(list(range(lo, hi + 1)))
    print(f"{args.split}: sols {lo}-{hi} · {len(refs)} products listed")

    def one(ref):
        img, lbl = ad.fetch_product(ref)
        rec = ad.normalize_metadata(ref, lbl.read_text(encoding="latin-1"))
        rec.update({"path_img": str(img.relative_to(ROOT)), "path_lbl": str(lbl.relative_to(ROOT)),
                    "archive_bytes_img": img.stat().st_size, "archive_bytes_lbl": lbl.stat().st_size,
                    "sha256_img": sha256_file(img), "sha256_lbl": sha256_file(lbl)})
        return rec

    with ThreadPoolExecutor(args.workers) as ex:
        recs = list(ex.map(one, refs))
    recs.sort(key=lambda r: (r["sol"], r["sclk_name"], r["eye"], r["tier"]))
    out = ROOT / "data" / "manifests" / f"navcam_{args.split}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"split": args.split, "sols": [lo, hi], "source": "PDS Imaging Node MSLNAV_0XXX (raw EDR)",
                               "fetched_at": datetime.now(timezone.utc).isoformat(), "n_products": len(recs),
                               "archive_bytes": sum(r["archive_bytes_img"] + r["archive_bytes_lbl"] for r in recs),
                               "products": recs}, indent=1, default=str))
    print(f"→ {out.relative_to(ROOT)} · {sum(r['archive_bytes_img'] + r['archive_bytes_lbl'] for r in recs) / 1e9:.3f} GB on disk")
    return 0


if __name__ == "__main__":
    sys.exit(main())
