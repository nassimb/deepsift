#!/usr/bin/env python3
"""Train the LOCAL EDGE BASELINE on the CALIBRATION split only → artifacts/models/local_edge.json.

Training labels come exclusively from synthetic injections (seeds 10000+, disjoint from the
validation/test sweep seeds). No documented event and no validation/test data is read.
"""

from __future__ import annotations

import json
from pathlib import Path

from deepsift.core.config import load_config
from deepsift.evaluation.local_edge import train
from deepsift.evaluation.segments import load_segment, segments
from deepsift.evaluation.sweeps import plan_sweep_batch
from deepsift.features.detect import detect_events
from deepsift.features.novelty import assign_novelty

ROOT = Path(__file__).resolve().parents[1]
N_BATCHES = 25
SEED_BASE = 10_000


def main() -> None:
    cfg = load_config(ROOT / "config" / "phase2.yaml")
    events = []
    for seg in segments("calibration"):
        sd = load_segment(seg)
        det0 = detect_events(sd.mission, sd.adapter, cfg)
        n = max(10, int(0.8 * (seg.eval[1] - seg.eval[0] + 1)))
        for b in range(N_BATCHES):
            inj = plan_sweep_batch(sd.mission.samples, det0.windows, seg.eval, n, SEED_BASE + b,
                                   cfg.detection.min_sigma or {}, f"CAL{b:02d}")
            det = detect_events(sd.mission, sd.adapter, cfg, injections=inj)
            assign_novelty(det.events)
            events += [e for e in det.events if seg.eval[0] <= e.sol <= seg.eval[1]]
    model = train(events)
    model.meta.update({"split": "calibration", "batches": N_BATCHES, "seed_base": SEED_BASE, "config_version": cfg.version()})
    out = ROOT / "artifacts" / "models" / "local_edge.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(model.to_json())
    print(json.dumps(model.meta, indent=1))
    print(json.dumps(model.footprint(events[:500]), indent=1))


if __name__ == "__main__":
    main()
