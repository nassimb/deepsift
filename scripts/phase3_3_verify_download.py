#!/usr/bin/env python3
"""Phase 3.3: verify the validation Navcam download (completeness, SHA-256, metadata preservation, no test sols on disk).

    uv run python scripts/phase3_3_verify_download.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "pipeline"))

from deepsift.imaging.acquisitions import group_acquisitions, grouping_stats  # noqa: E402
from deepsift.imaging.navcam import sha256_file  # noqa: E402

REQUIRED = ["product_id", "url_img", "sol", "utc", "sclk_name", "eye", "tier", "site", "drive", "pose", "sequence_id",
            "compression", "compression_rate_bpp", "sha256_img", "sha256_lbl", "path_img", "path_lbl"]


def main() -> int:
    man = json.loads((ROOT / "data" / "manifests" / "navcam_validation.json").read_text())
    prods = man["products"]
    log = (ROOT / "data" / "fetch_navcam_validation.log").read_text()
    m = re.search(r"(\d+) products listed", log)
    listed = int(m.group(1)) if m else None
    problems = Counter()
    for p in prods:
        for k in REQUIRED:
            if p.get(k) is None and not (k == "compression_rate_bpp" and p.get("compression_ratio") is not None):
                problems[f"missing_field:{k}"] += 1
        img, lbl = ROOT / p["path_img"], ROOT / p["path_lbl"]
        if not img.exists() or not lbl.exists():
            problems["missing_file"] += 1
            continue
        if img.stat().st_size == 0:
            problems["empty_img"] += 1
        if sha256_file(img) != p["sha256_img"]:
            problems["sha256_img_mismatch"] += 1
        if sha256_file(lbl) != p["sha256_lbl"]:
            problems["sha256_lbl_mismatch"] += 1
        if not (779 <= p["sol"] <= 820):
            problems["sol_outside_validation"] += 1
    data = ROOT / "data" / "raw" / "navcam" / "MSLNAV_0XXX" / "DATA"
    sols_on_disk = sorted(int(d.name[3:]) for d in data.iterdir() if d.name.startswith("SOL"))
    test_on_disk = [s for s in sols_on_disk if 950 <= s <= 979]
    acqs = group_acquisitions(prods)
    rep = {"manifest_products": len(prods), "listed_by_fetch": listed, "complete": listed == len(prods),
           "problems": dict(problems), "sha256_verified": len(prods) - problems["sha256_img_mismatch"] - problems["missing_file"],
           "sols_on_disk": sols_on_disk, "test_sols_on_disk": test_on_disk, "grouping": grouping_stats(prods, acqs),
           "stereo_acquisitions": sum(a["stereo"] for a in acqs), "tiers": dict(Counter(p["tier"] for p in prods)),
           "compression": dict(Counter(p["compression"] for p in prods))}
    rep["verdict"] = "PASS" if rep["complete"] and not problems and not test_on_disk else "FAIL"
    out = ROOT / "data" / "manifests" / "navcam_validation_verification.json"
    out.write_text(json.dumps(rep, indent=1, default=str))
    print(json.dumps(rep, indent=1, default=str))
    return 0 if rep["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
