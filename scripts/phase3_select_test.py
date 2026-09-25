#!/usr/bin/env python3
"""Freeze the Phase 3 held-out TEST interval by a deterministic rule — PDS directory LISTINGS ONLY.

    uv run python scripts/phase3_select_test.py

No image, no label and no telemetry product is downloaded; no image content or benchmark output is looked at.
Writes data/splits/phase3_splits.json (development / validation / test + the evidence behind the choice).

Rule (fixed by the user, 2026-09-25) and the operational definitions declared here BEFORE the scan runs:
  Scan windows [s, s+29] for s = 950, 951, … and take the FIRST that satisfies ALL of:
  R1 outside every Phase 2 interval — the calibration / validation / test EVALUATION sols and their warm-up sols
  R2 ≥ 10 sols with ≥ 1 Navcam acquisition
  R3 ≥ 500 Navcam acquisitions in total. ACQUISITION = one capture instant (unique spacecraft clock in the EDR file
     name) with at least one non-thumbnail EDR product; a stereo left/right pair is ONE acquisition (as in Phase 3 M3)
  R4 REMS available: a REMS MODRDR (RMD) product listed for ≥ 27 of the 30 sols (90 %)
  R5 RAD available:  a RAD RDR product listed for ≥ 27 of the 30 sols (90 %)
  R6 not inside a known solar-conjunction operational gap: the window must not overlap the command-moratorium dates
     below (UTC dates converted to sols with the sol↔UTC pairs in the RAD RDR product names)
  R7 reproducibly usable: every sol's Navcam directory listing is retrievable (HTTP 200, or 404 = no products);
     every Navcam .IMG listed has a matching .LBL; no listed .IMG has size 0; the archive index
     MSLNAV_0XXX/INDEX/INDEX.TAB answers (HEAD 200)
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "splits" / "phase3_splits.json"
NAV = "https://planetarydata.jpl.nasa.gov/img/data/msl/MSLNAV_0XXX"
REMS_BASE = "https://atmos.nmsu.edu/PDS/data/mslrem_1001"
RAD_BASE = "https://pds-ppi.igpp.ucla.edu/data/MSL-M-RAD-3-RDR-V1.0"
START, LENGTH, MIN_ACTIVE, MIN_ACQ, TELEMETRY_MIN_SOLS = 950, 30, 10, 500, 27
CONJUNCTIONS = [  # command moratoria (UTC dates) with sources
    {"start": "2013-04-04", "end": "2013-05-01", "source": "https://www.jpl.nasa.gov/news/for-moratorium-on-sending-commands-to-mars-blame-the-sun/"},
    {"start": "2015-06-07", "end": "2015-06-21", "source": "https://www.jpl.nasa.gov/news/mars-missions-to-pause-commanding-in-june-due-to-sun/"},
]
DEVELOPMENT, VALIDATION = [412, 430], [779, 820]
ROW = re.compile(r'indexcolname"><a href="([^"]+)">[^<]+</a></td><td class="indexcollastmod">[^<]*</td><td class="indexcolsize">\s*([^<]+)<')
HASHES: dict[str, str] = {}
client = httpx.Client(timeout=90, follow_redirects=True)


def get(url: str) -> tuple[int, str]:
    for attempt in range(4):
        try:
            r = client.get(url)
            if r.status_code in (200, 404):
                if r.status_code == 200:
                    HASHES[url] = hashlib.sha256(r.content).hexdigest()
                return r.status_code, r.text
        except httpx.HTTPError:
            pass
        time.sleep(2 * (attempt + 1))
    return -1, ""


def phase2_sols() -> set[int]:
    spec = json.loads((ROOT / "data" / "splits" / "splits.json").read_text())["splits"]
    out = set()
    for sp in spec.values():
        for seg in sp["segments"]:
            for k in ("warmup", "eval"):
                if seg.get(k):
                    out.update(range(seg[k][0], seg[k][1] + 1))
    return out


_nav: dict[int, dict] = {}


def navcam(sol: int) -> dict:
    if sol not in _nav:
        code, html = get(f"{NAV}/DATA/SOL{sol:05d}/")
        rows = ROW.findall(html) if code == 200 else []
        imgs = [(n, s.strip()) for n, s in rows if n.endswith(".IMG")]
        lbls = {n for n, _ in rows if n.endswith(".LBL")}
        acq = {m.group(1) for n, _ in imgs if (m := re.match(r"N[LR][AB]_(\d{9})EDR_([A-Z])", n)) and m.group(2) != "T"}
        _nav[sol] = {"http": code, "products": len(imgs), "acquisitions": len(acq),
                     "img_without_lbl": sum(1 for n, _ in imgs if n.replace(".IMG", ".LBL") not in lbls),
                     "zero_size": sum(1 for _, s in imgs if s in ("0", "0K"))}
    return _nav[sol]


_buckets: dict[str, list] = {}


def buckets(base: str):
    if base not in _buckets:
        _, html = get(f"{base}/DATA/")
        _buckets[base] = sorted({(int(a), int(b), f"SOL_{a}_{b}") for a, b in re.findall(r"SOL_(\d{5})_(\d{5})/", html)})
    return _buckets[base]


def bucket(base: str, sol: int) -> str | None:
    return next((n for lo, hi, n in buckets(base) if lo <= sol <= hi), None)


_rems: dict[int, bool] = {}
_rad_names: dict[str, list[str]] = {}


def rems(sol: int) -> bool:
    if sol not in _rems:
        b = bucket(REMS_BASE, sol)
        code, html = get(f"{REMS_BASE}/DATA/{b}/SOL{sol:05d}/") if b else (404, "")
        _rems[sol] = code == 200 and "RMD" in html
    return _rems[sol]


def rad_listing(sol: int) -> list[str]:
    b = bucket(RAD_BASE, sol)
    if not b:
        return []
    if b not in _rad_names:
        _, html = get(f"{RAD_BASE}/DATA/{b}/")
        _rad_names[b] = re.findall(r"RAD_RDR_\d{4}_\d{3}_\d\d_\d\d_\d{4}_V\d\d\.TXT", html)
    return _rad_names[b]


def rad(sol: int) -> bool:
    return any(n.endswith(f"_{sol:04d}_V{n[-6:-4]}.TXT") or f"_{sol:04d}_V" in n for n in rad_listing(sol))


def sol_of_date(d: date, near_sol: int) -> int | None:
    """Sol whose RAD product (named by UTC year/day-of-year) falls on date d, from the RAD listings."""
    pairs = []
    for s in range(near_sol - 80, near_sol + 80, 10):
        for n in rad_listing(s):
            m = re.match(r"RAD_RDR_(\d{4})_(\d{3})_\d\d_\d\d_(\d{4})", n)
            pairs.append((date(int(m.group(1)), 1, 1).toordinal() + int(m.group(2)) - 1, int(m.group(3))))
    if not pairs:
        return None
    o = d.toordinal()
    best = min(pairs, key=lambda p: abs(p[0] - o))
    return best[1] + round((o - best[0]) * 86400 / 88775.244)


def main() -> int:
    p2 = phase2_sols()
    idx_code = client.head(f"{NAV}/INDEX/INDEX.TAB").status_code
    conj = []
    for c in CONJUNCTIONS:
        d0, d1 = date.fromisoformat(c["start"]), date.fromisoformat(c["end"])
        guess = 230 if d0.year == 2013 else 1010
        conj.append({**c, "sols": [sol_of_date(d0, guess), sol_of_date(d1, guess)]})
    log = []
    chosen = None
    for s in range(START, 2400):
        w = list(range(s, s + LENGTH))
        checks = {"R1_outside_phase2": not (set(w) & p2)}
        checks["R6_no_conjunction"] = not any(c["sols"][0] is not None and w[0] <= c["sols"][1] and w[-1] >= c["sols"][0] for c in conj)
        if not (checks["R1_outside_phase2"] and checks["R6_no_conjunction"]):
            log.append({"start": s, **checks})
            continue
        nav = [navcam(x) for x in w]
        checks["R2_active_sols"] = sum(1 for n in nav if n["acquisitions"] > 0)
        checks["R3_acquisitions"] = sum(n["acquisitions"] for n in nav)
        ok23 = checks["R2_active_sols"] >= MIN_ACTIVE and checks["R3_acquisitions"] >= MIN_ACQ
        if ok23:
            checks["R4_rems_sols"] = sum(rems(x) for x in w)
            checks["R5_rad_sols"] = sum(rad(x) for x in w)
            checks["R7_reproducible"] = (idx_code == 200 and all(n["http"] in (200, 404) for n in nav)
                                         and not any(n["img_without_lbl"] or n["zero_size"] for n in nav))
        passed = ok23 and checks["R4_rems_sols"] >= TELEMETRY_MIN_SOLS and checks["R5_rad_sols"] >= TELEMETRY_MIN_SOLS and checks["R7_reproducible"]
        log.append({"start": s, **checks, "passed": passed})
        print(s, checks, "PASS" if passed else "")
        if passed:
            chosen = w
            break
    if chosen is None:
        print("no window satisfies the rule")
        return 1
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    per_sol = {x: {**navcam(x), "rems": rems(x), "rad": rad(x)} for x in chosen}
    out = {
        "version": "phase3-v1", "camera": "MSL Navcam (MSLNAV_0XXX raw EDR)",
        "selected_at": datetime.now(timezone.utc).isoformat(), "git_commit_at_selection": commit,
        "development": {"sols": DEVELOPMENT, "note": "Phase 2 validation SEP segment; approved 2026-09-25"},
        "validation": {"sols": VALIDATION, "note": "Phase 2 validation FD segment; approved 2026-09-25"},
        "test": {"sols": [chosen[0], chosen[-1]], "note": "held out; selected by the rule below from listings only; immutable"},
        "selection_rule": {
            "text": __doc__.split("Rule (", 1)[1],
            "parameters": {"start": START, "length": LENGTH, "min_active_sols": MIN_ACTIVE, "min_acquisitions": MIN_ACQ,
                           "telemetry_min_sols": TELEMETRY_MIN_SOLS},
            "conjunctions": conj, "phase2_sols_excluded": [min(p2), max(p2), len(p2)],
            "navcam_index_head_status": idx_code},
        "evidence": {"windows_evaluated": log, "test_per_sol": per_sol,
                     "test_totals": {"active_sols": sum(1 for v in per_sol.values() if v["acquisitions"]),
                                     "acquisitions": sum(v["acquisitions"] for v in per_sol.values()),
                                     "products_listed": sum(v["products"] for v in per_sol.values()),
                                     "rems_sols": sum(v["rems"] for v in per_sol.values()),
                                     "rad_sols": sum(v["rad"] for v in per_sol.values())}},
        "pds_listing_sha256": HASHES,
        "survivorship_note": ("The PDS archive holds only observations that were actually downlinked. Phase 3 tests "
                              "retrospective bandwidth-constrained prioritization of archived rover observations, not "
                              "reconstruction of the complete onboard image stream."),
    }
    OUT.write_text(json.dumps(out, indent=1))
    print(f"TEST = sols {chosen[0]}–{chosen[-1]} → {OUT.relative_to(ROOT)}  ({len(HASHES)} listing hashes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
