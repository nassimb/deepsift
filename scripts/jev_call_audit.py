#!/usr/bin/env python3
"""Where would the Jev calls go? Counts only — no API call, no metric, no label is computed.

For a split it reproduces exactly the candidate events the study would send to the engine (same frozen
config, same synthetic seeds), builds the exact Jev request payload per variant, and counts:
  - raw requests (what the Phase-2 runner would have sent without a cache)
  - unique payloads (what a request-level cache needs)
  - repeats caused by synthetic batches re-detecting the same natural events

    uv run python scripts/jev_call_audit.py --split validation [--batches 25]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "pipeline"))

from deepsift.core.config import load_config  # noqa: E402
from deepsift.decision.jev import VARIANTS, questions_payload  # noqa: E402
from deepsift.decision.questions import QUESTIONS, SINGLE_DECISION_QUESTIONS  # noqa: E402
from deepsift.decision.state import build_state_variant  # noqa: E402
from deepsift.evaluation.segments import eval_filter_events, eval_windows, load_segment, segments  # noqa: E402
from deepsift.evaluation.sweeps import plan_sweep_batch  # noqa: E402
from deepsift.features.detect import detect_events  # noqa: E402
from deepsift.features.novelty import assign_novelty  # noqa: E402
from deepsift.objectives.objective import load_objectives  # noqa: E402


def payload_hash(state, qset, model) -> str:
    q = questions_payload(SINGLE_DECISION_QUESTIONS if qset == "single" else QUESTIONS)
    return hashlib.sha256(json.dumps({"state": state, "questions": q, "model": model}, sort_keys=True).encode()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="validation")
    ap.add_argument("--batches", type=int, default=25)
    args = ap.parse_args()
    cfg = load_config(ROOT / "config" / "phase2.yaml")
    obj = load_objectives()[cfg.objective].model_dump(mode="json")
    model = cfg.decision_engine.jev_model
    funnel = []
    raw_requests = Counter()
    unique = {v: set() for v in VARIANTS}
    real_hashes = {v: set() for v in VARIANTS}
    per_dataset = Counter()
    import hashlib as _h

    for seg in segments(args.split):
        sd = load_segment(seg, cfg.detection.rems_window_s, cfg.compression.decimation_factor, cfg.compression.zlib_level)
        det0 = detect_events(sd.mission, sd.adapter, cfg)
        assign_novelty(det0.events)
        ev0 = eval_filter_events(det0.events, sd)
        iw0 = eval_windows(det0.instrument_windows, sd)
        samples_eval = sd.mission.samples.filter((sd.mission.samples["sol"] >= seg.eval[0]) & (sd.mission.samples["sol"] <= seg.eval[1])).height
        funnel.append({"segment": seg.id, "raw_samples_scored_sols": samples_eval, "instrument_windows": iw0.height,
                       "candidate_windows": int(iw0["flagged"].sum()), "candidate_events": len(ev0)})
        sets = [("real", ev0)]
        seed0 = int(_h.sha256(f"{args.split}:{seg.id}".encode()).hexdigest()[:8], 16) % 1_000_000
        n = max(10, int(0.8 * (seg.eval[1] - seg.eval[0] + 1)))
        for b in range(args.batches):
            inj = plan_sweep_batch(sd.mission.samples, det0.windows, seg.eval, n, seed0 + b, cfg.detection.min_sigma or {}, f"{seg.id}-B{b:02d}")
            det = detect_events(sd.mission, sd.adapter, cfg, injections=inj)
            assign_novelty(det.events)
            sets.append((f"synthetic", eval_filter_events(det.events, sd)))
        for name, evs in sets:
            per_dataset[name] += len(evs)
            for v, (sv, qset) in VARIANTS.items():
                for e in evs:
                    h = payload_hash(build_state_variant(e, "MSL / CURIOSITY", "Gale Crater, Mars (4.59°S, 137.44°E landing site)", sv, obj), qset, model)
                    raw_requests[v] += 1
                    unique[v].add(h)
                    if name == "real":
                        real_hashes[v].add(h)
        print(f"  {seg.id}: {len(ev0)} real candidates, {sum(len(e) for n_, e in sets[1:])} synthetic-batch candidates", flush=True)

    out = {
        "split": args.split, "batches_per_segment": args.batches, "model_requested": model,
        "funnel": funnel,
        "candidate_events": dict(per_dataset),
        "requests_per_event": 1, "decisions_per_request": {v: (1 if VARIANTS[v][1] == "single" else len(QUESTIONS)) for v in VARIANTS},
        "per_variant": {v: {"raw_requests_without_cache": raw_requests[v], "unique_payloads": len(unique[v]),
                            "real_unique": len(real_hashes[v]),
                            "synthetic_payloads_identical_to_a_real_payload": None} for v in VARIANTS},
        "total_raw_requests_without_cache": sum(raw_requests.values()),
        "total_unique_payloads": sum(len(u) for u in unique.values()),
    }
    dest = ROOT / "artifacts" / "jev_preflight" / f"call_audit_{args.split}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "funnel"}, indent=1))
    print(json.dumps(out["funnel"], indent=1))


if __name__ == "__main__":
    main()
