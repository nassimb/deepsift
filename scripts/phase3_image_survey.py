#!/usr/bin/env python3
"""Phase 3 dataset assessment — READ-ONLY survey of PDS Imaging Node directory LISTINGS (no image downloads).

    uv run python scripts/phase3_image_survey.py

For Navcam (MSLNAV_0XXX EDR), Mastcam (MSLMST_* EDR/RDR) and MAHLI (MSLMHL_* EDR/RDR) it reads the HTML
directory listings of each sol directory in the calibration and validation segments (never the Phase-2 test
segments) and records product names and listed sizes (Apache rounds sizes to K/M; totals are ±5 %).
Output: artifacts/phase3_assessment/listing_survey.json.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://planetarydata.jpl.nasa.gov/img/data/msl"
OUT = ROOT / "artifacts" / "phase3_assessment" / "listing_survey.json"
ROW = re.compile(r'indexcolname"><a href="([^"]+)">[^<]+</a></td><td class="indexcollastmod">[^<]*</td><td class="indexcolsize">\s*([^<]+)<')
SEGMENTS = {"calibration": (232, 251), "validation_sep": (412, 430), "validation_fd": (779, 820)}
UNIT = {"K": 1024, "M": 1024 ** 2, "G": 1024 ** 3}


def get(url: str) -> str:
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001
            if "404" in str(exc):
                return ""
            time.sleep(2 * (attempt + 1))
    return ""


def listing(url: str) -> list[tuple[str, int | None]]:
    out = []
    for name, size in ROW.findall(get(url)):
        size = size.strip()
        if name.endswith("/") or size == "-":
            out.append((name, None))
            continue
        m = re.match(r"([\d.]+)([KMG]?)", size)
        out.append((name, int(float(m.group(1)) * UNIT.get(m.group(2), 1)) if m else None))
    return out


def sol_volume_map(prefix: str, n: int) -> dict[int, str]:
    """sol → volume for MSSS instruments (one listing per volume)."""
    def one(v):
        vol = f"{prefix}_{v:04d}"
        return vol, [int(d.rstrip("/")) for d, _ in listing(f"{BASE}/{vol}/DATA/EDR/SURFACE/") if d.rstrip("/").isdigit()]
    m = {}
    with ThreadPoolExecutor(4) as ex:
        for vol, sols in ex.map(one, range(1, n + 1)):
            for s in sols:
                m.setdefault(s, vol)
    return m


def navcam_product(name: str) -> dict:
    # e.g. NLB_434069809EDR_F0170826TRAV00108M1.IMG : N=Navcam, L/R eye, A/B string, sclk, EDR, product-type letter
    m = re.match(r"N([LR])([AB])_(\d{9})EDR_([A-Z])\d{7}([A-Z]{4})\d{5}", name)
    return {"eye": m.group(1), "string": m.group(2), "sclk": int(m.group(3)), "ptype": m.group(4), "seq": m.group(5)} if m else {}


def msss_product(name: str) -> dict:
    # e.g. 0113MR0006960000200584C00_XXXX.DAT : sol, camera (ML/MR/MH), sequence, ..., product-type letter + version
    m = re.match(r"(\d{4})(M[LRHD])(\d{6})(\d{3})(\d{7})([A-Z])(\d{2})_([A-Z]{4})", name)
    return {"sol": int(m.group(1)), "cam": m.group(2), "seq": m.group(3), "ptype": m.group(6), "suffix": m.group(8)} if m else {}


def survey_sol(inst: str, sol: int, vol_map: dict[int, str] | None) -> dict:
    rec = {"instrument": inst, "sol": sol, "products": []}
    if inst == "navcam":
        url = f"{BASE}/MSLNAV_0XXX/DATA/SOL{sol:05d}/"
        for name, size in listing(url):
            if name.endswith(".IMG"):
                rec["products"].append({"name": name, "bytes": size, "level": "EDR", **navcam_product(name)})
        rec["url"] = url
        return rec
    vol = (vol_map or {}).get(sol)
    rec["volume"] = vol
    if not vol:
        return rec
    for level in ("EDR", "RDR"):
        url = f"{BASE}/{vol}/DATA/{level}/SURFACE/{sol:04d}/"
        for name, size in listing(url):
            if name.endswith((".DAT", ".IMG")):
                rec["products"].append({"name": name, "bytes": size, "level": level, **msss_product(name)})
    return rec


def main() -> int:
    maps = {"mastcam": sol_volume_map("MSLMST", 32), "mahli": sol_volume_map("MSLMHL", 32)}
    jobs = [(inst, s) for inst in ("navcam", "mastcam", "mahli") for lo, hi in SEGMENTS.values() for s in range(lo, hi + 1)]
    with ThreadPoolExecutor(6) as ex:
        recs = list(ex.map(lambda j: survey_sol(j[0], j[1], maps.get(j[0])), jobs))
    summary = defaultdict(dict)
    for seg, (lo, hi) in SEGMENTS.items():
        for inst in ("navcam", "mastcam", "mahli"):
            rs = [r for r in recs if r["instrument"] == inst and lo <= r["sol"] <= hi]
            prods = [p for r in rs for p in r["products"]]
            summary[seg][inst] = {
                "sols": hi - lo + 1, "sols_with_products": sum(1 for r in rs if r["products"]),
                "products": len(prods), "bytes": sum(p["bytes"] or 0 for p in prods),
                "by_level_type": {f"{k[0]}:{k[1]}": {"n": n, "bytes": sum(p["bytes"] or 0 for p in prods if (p["level"], p.get("ptype") or p.get("suffix")) == k)}
                                  for k, n in Counter((p["level"], p.get("ptype") or p.get("suffix")) for p in prods).most_common()},
                "per_sol_counts": {r["sol"]: len(r["products"]) for r in rs},
            }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "base": BASE, "segments": SEGMENTS,
                               "sol_volume_maps": {k: {str(s): v for s, v in m.items() if any(lo <= s <= hi for lo, hi in SEGMENTS.values())} for k, m in maps.items()},
                               "summary": summary, "records": recs}, indent=1))
    print(json.dumps(summary, indent=1, default=str)[:6000])
    print(f"→ {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
