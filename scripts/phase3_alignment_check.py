#!/usr/bin/env python3
"""Phase 3 assessment — can Navcam image times be aligned with our local REMS / RAD telemetry?  READ-ONLY.

Uses (a) product names from artifacts/phase3_assessment/listing_survey.json (the SCLK is in every Navcam file name),
(b) a handful of PDS label files (text, ~24 KB each) to fit SCLK → UTC, and (c) telemetry ALREADY on disk.
No image product is downloaded. Output: artifacts/phase3_assessment/alignment.json.
"""

from __future__ import annotations

import bisect
import json
import re
import sys
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "pipeline"))
from deepsift.adapters.curiosity import CuriosityAdapter  # noqa: E402

BASE = "https://planetarydata.jpl.nasa.gov/img/data/msl/MSLNAV_0XXX/DATA"
SURVEY = ROOT / "artifacts" / "phase3_assessment" / "listing_survey.json"
OUT = ROOT / "artifacts" / "phase3_assessment" / "alignment.json"
SEGMENTS = {"validation_sep": (412, 430), "validation_fd": (779, 820)}


def label_time(sol: int, name: str) -> tuple[float, datetime]:
    t = urllib.request.urlopen(f"{BASE}/SOL{sol:05d}/{name.replace('.IMG', '.LBL')}", timeout=60).read().decode("latin-1")
    sclk = float(re.search(r'SPACECRAFT_CLOCK_START_COUNT\s*=\s*"?([\d.]+)', t).group(1))
    utc = datetime.fromisoformat(re.search(r"^\s*START_TIME\s*=\s*([\dT:.\-]+)", t, re.M).group(1)).replace(tzinfo=timezone.utc)
    return sclk, utc


def main() -> int:
    survey = json.loads(SURVEY.read_text())
    recs = [r for r in survey["records"] if r["instrument"] == "navcam" and any(lo <= r["sol"] <= hi for lo, hi in SEGMENTS.values())]
    prods = [(r["sol"], p) for r in recs for p in r["products"] if p.get("sclk")]
    # SCLK → UTC: linear fit on labels spread over both segments; checked on held-back labels
    picks = [prods[i] for i in np.linspace(0, len(prods) - 1, 8).astype(int)]
    pts = [label_time(s, p["name"]) for s, p in picks]
    fit_pts, chk_pts = pts[::2], pts[1::2]
    x = np.array([p[0] for p in fit_pts])
    y = np.array([(p[1] - datetime(2000, 1, 1, tzinfo=timezone.utc)).total_seconds() for p in fit_pts])
    a, b = np.polyfit(x, y, 1)
    to_utc = lambda s: datetime(2000, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=a * s + b)  # noqa: E731
    fit_err = [abs((to_utc(s) - u).total_seconds()) for s, u in chk_pts]

    ad = CuriosityAdapter()
    sols = sorted({s for lo, hi in SEGMENTS.values() for s in range(lo, hi + 1)})
    ad.load(sols)
    m = ad.normalize()
    smp = m.samples
    rems_t = sorted(smp.filter((smp["instrument"] == "REMS") & (smp["channel"] == "pressure"))["t"].to_list())
    rad_t = sorted(set(smp.filter(smp["instrument"] == "RAD")["t"].to_list()))
    rems_s = [t.timestamp() for t in rems_t]
    rad_s = [t.timestamp() for t in rad_t]
    rad_gaps = np.diff(rad_s) if len(rad_s) > 1 else np.array([])

    def nearest(arr, v):
        i = bisect.bisect_left(arr, v)
        c = [abs(arr[j] - v) for j in (i - 1, i) if 0 <= j < len(arr)]
        return min(c) if c else None

    rows = []
    for sol, p in prods:
        u = to_utc(p["sclk"]).timestamp()
        rows.append({"sol": sol, "ptype": p["ptype"], "seq": p.get("seq"), "dt_rems_s": nearest(rems_s, u), "dt_rad_s": nearest(rad_s, u)})

    def stats(xs):
        xs = np.array([v for v in xs if v is not None])
        return {"n": int(xs.size), "median_s": float(np.median(xs)), "p90_s": float(np.percentile(xs, 90)),
                "within_150s": float((xs <= 150).mean()), "within_15min": float((xs <= 900).mean()), "within_60min": float((xs <= 3600).mean())} if xs.size else {"n": 0}
    img = [r for r in rows if r["ptype"] in ("F", "D", "S", "M")]
    out = {
        "sclk_to_utc": {"slope": a, "intercept_s_since_2000": b, "fit_labels": len(fit_pts), "check_abs_error_s": fit_err},
        "rems_pressure_samples": len(rems_s), "rad_observations": len(rad_s),
        "rad_observation_spacing_s": {"median": float(np.median(rad_gaps)), "p90": float(np.percentile(rad_gaps, 90))} if rad_gaps.size else None,
        "navcam_products_by_type": dict(Counter(r["ptype"] for r in rows)),
        "images_FDSM_nearest_rems": stats([r["dt_rems_s"] for r in img]),
        "images_FDSM_nearest_rad": stats([r["dt_rad_s"] for r in img]),
        "sequences": dict(Counter(r["seq"] for r in img).most_common(12)),
        "n_sequences": len({(r["sol"], r["seq"]) for r in img}),
    }
    OUT.write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
