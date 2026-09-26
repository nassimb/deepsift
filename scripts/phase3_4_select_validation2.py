#!/usr/bin/env python3
"""Select PHASE3_VALIDATION2 by the rule pre-registered in config/phase3_4_validation_config.json — PDS LISTINGS ONLY.

    uv run python scripts/phase3_4_select_validation2.py

Reuses the listing checks of scripts/phase3_select_test.py unchanged (Navcam directory listings, REMS/RAD listings,
conjunction moratoria). No image, label or telemetry product is downloaded and no image content is read. The scan starts
at sol 1100, so the held-out test interval 950–979 is never listed. Writes data/splits/phase3_validation2.json
(phase3_splits.json is not modified).
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import phase3_select_test as S  # noqa: E402

CFG = json.loads((ROOT / "config" / "phase3_4_validation_config.json").read_text())
RULE = CFG["validation2_selection_rule"]
OUT = ROOT / "data" / "splits" / "phase3_validation2.json"
EXCLUDED = [(412, 430), (779, 820), (950, 979)]


def main() -> int:
    p2 = S.phase2_sols()
    idx_code = S.client.head(f"{S.NAV}/INDEX/INDEX.TAB").status_code
    conj = []
    for c in S.CONJUNCTIONS:
        d0, d1 = date.fromisoformat(c["start"]), date.fromisoformat(c["end"])
        guess = 230 if d0.year == 2013 else 1010
        conj.append({**c, "sols": [S.sol_of_date(d0, guess), S.sol_of_date(d1, guess)]})
    log, chosen = [], None
    for s in range(RULE["start"], RULE["stop_before"]):
        w = list(range(s, s + RULE["length"]))
        checks = {"R1_outside_phase2_and_phase3": not (set(w) & p2) and not any(w[0] <= b and w[-1] >= a for a, b in EXCLUDED)}
        checks["R6_no_conjunction"] = not any(c["sols"][0] is not None and w[0] <= c["sols"][1] and w[-1] >= c["sols"][0] for c in conj)
        if not (checks["R1_outside_phase2_and_phase3"] and checks["R6_no_conjunction"]):
            log.append({"start": s, **checks})
            continue
        nav = [S.navcam(x) for x in w]
        checks["R2_active_sols"] = sum(1 for n in nav if n["acquisitions"] > 0)
        checks["R3_acquisitions"] = sum(n["acquisitions"] for n in nav)
        ok23 = checks["R2_active_sols"] >= S.MIN_ACTIVE and checks["R3_acquisitions"] >= S.MIN_ACQ
        passed = False
        if ok23:
            checks["R4_rems_sols"] = sum(S.rems(x) for x in w)
            checks["R5_rad_sols"] = sum(S.rad(x) for x in w)
            checks["R7_reproducible"] = (idx_code == 200 and all(n["http"] in (200, 404) for n in nav)
                                         and not any(n["img_without_lbl"] or n["zero_size"] for n in nav))
            passed = checks["R4_rems_sols"] >= S.TELEMETRY_MIN_SOLS and checks["R5_rad_sols"] >= S.TELEMETRY_MIN_SOLS and checks["R7_reproducible"]
        log.append({"start": s, **checks, "passed": passed})
        print(s, checks, "PASS" if passed else "", flush=True)
        if passed:
            chosen = w
            break
    if chosen is None:
        print("STOP: no window satisfies the pre-registered rule before sol", RULE["stop_before"])
        return 1
    per_sol = {x: {**S.navcam(x), "rems": S.rems(x), "rad": S.rad(x)} for x in chosen}
    OUT.write_text(json.dumps({
        "name": RULE["name"], "sols": [chosen[0], chosen[-1]], "selected_at": datetime.now(timezone.utc).isoformat(),
        "git_commit_at_selection": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip(),
        "phase3_4_config_hash": CFG["config_hash"], "rule": RULE, "conjunctions": conj, "navcam_index_head_status": idx_code,
        "phase2_sols_excluded": [min(p2), max(p2), len(p2)], "excluded_phase3": EXCLUDED,
        "evidence": {"windows_evaluated": log, "per_sol": per_sol,
                     "totals": {"active_sols": sum(1 for v in per_sol.values() if v["acquisitions"]),
                                "acquisitions_listed": sum(v["acquisitions"] for v in per_sol.values()),
                                "products_listed": sum(v["products"] for v in per_sol.values()),
                                "rems_sols": sum(v["rems"] for v in per_sol.values()), "rad_sols": sum(v["rad"] for v in per_sol.values())}},
        "pds_listing_sha256": S.HASHES, "note": "listings only; no image content read; final test 950–979 unchanged and untouched"}, indent=1))
    print(f"PHASE3_VALIDATION2 = sols {chosen[0]}–{chosen[-1]} → {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
