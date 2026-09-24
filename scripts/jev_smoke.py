#!/usr/bin/env python3
"""Smoke-test the real Jev API with ONE event before any benchmark. Exit 0 only if the answer shapes are valid."""

from __future__ import annotations

import sys
from pathlib import Path

from deepsift.core.env import load_dotenv
from deepsift.decision.jev import JevDecisionEngine, jev_available, missing_key_instructions, sdk_version
from deepsift.decision.questions import QUESTIONS

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    load_dotenv()
    if not jev_available():
        print(missing_key_instructions())
        return 2
    from deepsift.adapters.curiosity import CuriosityAdapter
    from deepsift.core.config import load_config
    from deepsift.features.detect import detect_events

    cfg = load_config(ROOT / "config" / "phase2.yaml")
    a = CuriosityAdapter()
    a.load(list(range(232, 252)))  # calibration split only
    det = detect_events(a.normalize(), a, cfg)
    ev = max(det.events, key=lambda e: e.features.deviation_score)
    log = ROOT / "artifacts" / "jev_smoke_calls.jsonl"
    eng = JevDecisionEngine(model=cfg.decision_engine.jev_model, call_log=log, run_id="smoke")
    [d] = eng.decide([ev], "MSL / CURIOSITY", "Gale Crater, Mars")
    print(f"typesafe-sdk {sdk_version()} · event {ev.id} · latency {d.latency_ms:.0f} ms · model {d.model}")
    if d.error:
        print("ERROR:", d.error)
        return 1
    ok = set(d.answers) == set(QUESTIONS)
    for name, q in QUESTIONS.items():
        a_ = d.answers.get(name)
        if a_ is None:
            continue
        if q.kind == "choice":
            ok &= a_.choice in q.criteria and abs(sum(a_.probabilities.values()) - 1) < 0.05
            print(f"  {name:22s} {a_.choice:>18s}  conf {a_.confidence:.3f}")
        else:
            ok &= a_.noul is not None and 0 <= a_.noul <= 1
            print(f"  {name:22s} P(yes)={a_.noul:.3f}")
    print(f"tokens in {d.input_tokens} · cost ${d.cost_usd:.6f} (configured price) · call log {log.relative_to(ROOT)}")
    print("SMOKE TEST PASSED" if ok else "SMOKE TEST FAILED: unexpected answer shape")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
