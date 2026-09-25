#!/usr/bin/env python3
"""Project-level Jev (Phase 2) summary for the research UI, read from STORED artifacts only.

    uv run python scripts/build_jev_phase2_summary.py

Reads artifacts/runs/<jev runs>/ (analysis.json, jev_calls.jsonl, …) — never calls an API, never writes to a run
folder. Output: apps/web/data/jev-phase2.json. The UI uses it so the project-level Jev result does not depend on any
API key being present now.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "artifacts" / "runs"
OUT = ROOT / "apps" / "web" / "data" / "jev-phase2.json"
V3 = "20260925T094903-jev-v3-pilot-84af"
HISTORY = [
    ("20260925T090044-jev-probe-6ded", "probe", "single authenticated request (OpenRouter)"),
    ("20260925T090119-jev-smoke-b935", "smoke", "30 validation events, operational checks"),
    ("20260925T091126-jev-pilot-7351", "pilot q1", "300 validation events × 5 variants — degenerate answers"),
    ("20260925T092458-jev-wording-q2-d559", "wording q2", "150 events — mixed effect, not adopted"),
    (V3, "V3 pilot", "598 events, science-only schema — healthy outputs, no ordering gain"),
]
CONCLUSION = ("Jev 1.13 was evaluated via OpenRouter during Phase 2. On validation, it did not provide a measurable "
              "improvement in candidate-event ranking over deterministic baselines or the local edge model. Under the "
              "pre-registered stop rule, Jev was discontinued for the ranking role.")
SCOPE = ("This result applies to this experiment and this ranking role only, not to Jev in general. All Jev runs, "
         "call logs and the cache are preserved for reproducibility.")


def calls(run: str) -> dict:
    log = RUNS / run / "jev_calls.jsonl"
    rows = [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []
    live = [r for r in rows if not r.get("cache_hit")]
    return {"live_calls": len(live), "cost_usd": round(sum(r.get("cost_usd") or 0 for r in live), 6),
            "models_returned": sorted({r.get("model_returned") for r in live if r.get("model_returned")})}


def main() -> int:
    a = json.loads((RUNS / V3 / "analysis.json").read_text())
    au = a["auroc"]
    hist = [{"run_id": r, "stage": s, "what": w, **calls(r)} for r, s, w in HISTORY]
    out = {
        "status": "EVALUATED · NOT RETAINED IN DEFAULT RANKING PATH",
        "model": "typesafe/jev-1.13", "transport": "OpenRouter", "split": "validation", "tag": "phase2-complete",
        "conclusion": CONCLUSION, "scope": SCOPE,
        "evidence": {
            "run_id": V3, "file": f"artifacts/runs/{V3}/analysis.json", "events": a["preflight"]["events"],
            "high_severity_labels": a["ranking"]["synthetic|high|ORDER:RULES|0.005"]["labels"],
            "auroc": {k: au[f"synthetic|{k}"]["auroc"] for k in ("RULES", "LOCAL_EDGE", "JEV_V3_NO_OBJECTIVE", "JEV_V3_WITH_OBJECTIVE")},
            "auroc_diff_vs_rules": {k: {"diff": au[f"synthetic|JEV_V3_{k.upper()}-minus-RULES"]["diff"],
                                        "ci95": au[f"synthetic|JEV_V3_{k.upper()}-minus-RULES"]["ci95_cluster_bootstrap"]}
                                    for k in ("no_objective", "with_objective")},
            "auroc_diff_vs_local_edge": {k: {"diff": au[f"synthetic|JEV_V3_{k.upper()}-minus-LOCAL_EDGE"]["diff"],
                                             "ci95": au[f"synthetic|JEV_V3_{k.upper()}-minus-LOCAL_EDGE"]["ci95_cluster_bootstrap"]}
                                         for k in ("no_objective", "with_objective")},
        },
        "history": hist,
        "totals": {"live_calls": sum(h["live_calls"] for h in hist), "cost_usd": round(sum(h["cost_usd"] for h in hist), 6)},
        "docs": ["docs/jev-model-selection.md", "docs/jev-evaluation.md"],
    }
    OUT.write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ("status", "evidence", "totals")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
