#!/usr/bin/env python3
"""Phase 3.4 step 7: study scale-aware spatial metrics on DEVELOPMENT data only (sols 412–430).

    uv run python scripts/phase3_4_metric_study.py

Reads only the frozen development baseline (observations + embeddings). No validation1 (779–820) or test data is read.
First asserts that deepsift.evaluation.traverse reproduces the frozen Phase 3.3 development traverse numbers, then
computes candidate metrics A–E for every method and fraction. Output: artifacts/phase3_4/metric_study_development.json.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "pipeline"))

from deepsift.evaluation import traverse as T  # noqa: E402

DEV = ROOT / "artifacts" / "phase3_3" / "20260926T134654-phase3.3-dev-32ec"
FRACTIONS = [0.5, 0.25, 0.125]


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "")).replace(tzinfo=timezone.utc).timestamp()


def sequences(obs):
    seqs = defaultdict(list)
    for i in sorted(range(len(obs)), key=lambda i: ts(obs[i]["utc"])):
        seqs[(obs[i]["sol"], obs[i]["sequence_id"])].append(i)
    return {k: v for k, v in seqs.items() if k[1].startswith("trav") and len(v) >= 10}


def main() -> int:
    obs = [json.loads(x) for x in (DEV / "observations.jsonl").read_text().splitlines()]
    assert all(412 <= o["sol"] <= 430 for o in obs), "development only"
    E = np.load(DEV / "embeddings.npy")
    frozen = json.loads((DEV / "results.json").read_text())["traverse"]["summary"]
    rows = defaultdict(list)
    for key, fr in sequences(obs).items():
        xy = np.array([[obs[i]["location_context"]["landing_x"], obs[i]["location_context"]["landing_y"]] for i in fr])
        em = E[fr]
        rows[(1.0, "SEND_ALL")].append(T.metrics(xy, em, list(range(len(fr)))))
        for f in FRACTIONS:
            for m in T.METHODS:
                rows[(f, m)].append(T.metrics(xy, em, T.select(m, xy, em, f)))
    # reproduction check against the frozen Phase 3.3 development run
    for (f, m), rs in rows.items():
        fz = frozen[f"{f}|{m}"]
        assert abs(np.mean([r["position_coverage"] for r in rs]) - fz["position_coverage_5m"]) < 1e-9, (f, m)
        assert abs(np.mean([r["visual_change_coverage"] for r in rs]) - fz["visual_change_coverage"]) < 1e-6, (f, m)
        assert abs(max(r["max_gap_m"] for r in rs) - fz["max_spatial_gap_m_worst"]) < 1e-9, (f, m)
    out = {}
    for (f, m), rs in sorted(rows.items(), key=lambda kv: (-kv[0][0], kv[0][1])):
        pooled = [g for r in rs for g in r["gaps_m"]]
        out[f"{f}|{m}"] = {
            "A_absolute_max_gap_m_worst": max(r["max_gap_m"] for r in rs),
            "B_max_gap_over_length_worst": max(r["max_gap_over_length"] for r in rs),
            "C_max_gap_over_native_median_spacing_worst": max(r["max_gap_over_native_median_spacing"] or 0 for r in rs),
            "D_p95_gap_m_pooled": float(np.percentile(pooled, 95)) if pooled else 0.0,
            "D_p95_gap_m_worst_sequence": max(r["p95_gap_m"] for r in rs),
            "E_coverage_5m": float(np.mean([r["position_coverage"] for r in rs])),
            "F_max_distance_to_kept_m_worst": max(r["max_distance_to_kept_m"] for r in rs),
            "F_p95_distance_to_kept_m_worst": max(r["p95_distance_to_kept_m"] for r in rs),
            "visual_change_coverage": float(np.mean([r["visual_change_coverage"] for r in rs])),
            "mean_gap_m": float(np.mean(pooled)) if pooled else 0.0}
    native = [g for r in rows[(1.0, "SEND_ALL")] for g in r["gaps_m"]]
    res = {"split": "development", "sols": [412, 430], "sequences": len(rows[(1.0, "SEND_ALL")]),
           "reproduces_frozen_phase3_3_dev": True,
           "native_spacing_m": {"median": float(np.median(native)), "p95": float(np.percentile(native, 95)), "max": max(native)},
           "per_sequence_native": [{"length_m": r["traverse_length_m"], "median_spacing_m": r["native_median_spacing_m"],
                                    "max_gap_m": r["max_gap_m"]} for r in rows[(1.0, "SEND_ALL")]],
           "candidates": out}
    p = ROOT / "artifacts" / "phase3_4" / "metric_study_development.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k != "candidates"}, indent=1))
    for k, v in out.items():
        print(k.ljust(38), " ".join(f"{a.split('_')[0]}={b:.3g}" for a, b in v.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
