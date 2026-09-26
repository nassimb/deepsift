#!/usr/bin/env python3
"""Download Navcam raw EDR (.IMG + .LBL, all tiers) for PHASE3_VALIDATION2 only (data/splits/phase3_validation2.json).

    uv run python scripts/fetch_navcam_validation2.py --workers 2

Same product handling and manifest fields as scripts/fetch_navcam.py (kept unchanged: it is hash-frozen by the Phase 3.3
config). Refuses any sol outside the frozen validation2 interval and any sol in the held-out test interval 950–979.
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

SPLIT = ROOT / "data" / "splits" / "phase3_validation2.json"
TEST = (950, 979)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=2)
    args = ap.parse_args()
    lo, hi = json.loads(SPLIT.read_text())["sols"]
    sols = list(range(lo, hi + 1))
    if any(TEST[0] <= s <= TEST[1] for s in sols):
        raise SystemExit("STOP: the held-out TEST interval 950–979 is never downloaded in Phase 3.4")
    ad = CuriosityNavcamAdapter()
    refs = ad.discover_products(sols)
    print(f"validation2: sols {lo}-{hi} · {len(refs)} products listed", flush=True)

    def one(ref):
        img, lbl = ad.fetch_product(ref)
        rec = ad.normalize_metadata(ref, lbl.read_text(encoding="latin-1"))
        rec.update({"path_img": str(img.relative_to(ROOT)), "path_lbl": str(lbl.relative_to(ROOT)),
                    "archive_bytes_img": img.stat().st_size, "archive_bytes_lbl": lbl.stat().st_size,
                    "sha256_img": sha256_file(img), "sha256_lbl": sha256_file(lbl)})
        return rec

    with ThreadPoolExecutor(args.workers) as ex:
        recs = list(ex.map(one, refs))
    assert all(lo <= r["sol"] <= hi for r in recs)
    recs.sort(key=lambda r: (r["sol"], r["sclk_name"], r["eye"], r["tier"]))
    out = ROOT / "data" / "manifests" / "navcam_validation2.json"
    out.write_text(json.dumps({"split": "validation2", "sols": [lo, hi], "source": "PDS Imaging Node MSLNAV_0XXX (raw EDR)",
                               "fetched_at": datetime.now(timezone.utc).isoformat(), "n_products": len(recs), "n_listed": len(refs),
                               "archive_bytes": sum(r["archive_bytes_img"] + r["archive_bytes_lbl"] for r in recs), "products": recs}, indent=1))
    print(f"→ {out.relative_to(ROOT)} · {len(recs)} products", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
