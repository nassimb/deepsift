#!/usr/bin/env python3
"""Pick ONE local vision model for Phase 3 — on the DEVELOPMENT split only, before any validation or test imagery.

    uv run python scripts/phase3_select_vision_model.py

Selection rule (declared before running):
  1. eligible: deterministic (two runs, max |Δ| < 1e-5) AND p95 CPU latency ≤ 250 ms per image (4 threads)
  2. among eligible: highest STEREO RETRIEVAL@1 — for every stereo acquisition, is the left image's nearest neighbour
     among all right images its own right image? (label-free sanity check of similarity behaviour)
  3. tie (within 0.01): smaller model file
Peak memory is measured in a fresh subprocess per model. Output: config/phase3_vision_model.json (frozen).
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "pipeline"))

from deepsift.imaging.acquisitions import group_acquisitions  # noqa: E402
from deepsift.imaging.embeddings import MODELS, Embedder  # noqa: E402
from deepsift.imaging.features import to_work  # noqa: E402
from deepsift.imaging.pds3 import parse_label, read_image  # noqa: E402

OUT = ROOT / "config" / "phase3_vision_model.json"
MEM_SNIPPET = """
import sys, resource, numpy as np
sys.path.insert(0, 'services/pipeline')
from deepsift.imaging.embeddings import Embedder
e = Embedder(sys.argv[1]); x = np.random.default_rng(0).random((256, 256)).astype('float32')
for _ in range(20): e.embed(x)
r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
print(r / 1e6 if r > 1e7 else r / 1024)
"""


def load(p: dict) -> np.ndarray:
    return to_work(read_image(ROOT / p["path_img"], parse_label((ROOT / p["path_lbl"]).read_text(encoding="latin-1"))))


def main() -> int:
    man = json.loads((ROOT / "data" / "manifests" / "navcam_development.json").read_text())
    acqs = group_acquisitions(man["products"])
    pairs = []
    for a in acqs:
        if a["stereo"]:
            L = [p for p in a["primaries"] if p["eye"] == "L" and p["tier"] == a["primary_tier"]]
            R = [p for p in a["primaries"] if p["eye"] == "R" and p["tier"] == a["primary_tier"]]
            if L and R:
                pairs.append((load(L[0]), load(R[0])))
    print(f"stereo pairs (same tier): {len(pairs)}")
    report = {}
    for name in MODELS:
        emb = Embedder(name)
        emb.embed(pairs[0][0])                                           # warm-up (excluded)
        lat, EL, ER = [], [], []
        for left, right in pairs:
            v, ms = emb.embed(left)
            lat.append(ms)
            EL.append(v)
            v, ms = emb.embed(right)
            lat.append(ms)
            ER.append(v)
        EL, ER = np.stack(EL), np.stack(ER)
        r1 = float(np.mean(np.argmax(EL @ ER.T, axis=1) == np.arange(len(EL))))
        again = np.stack([emb.embed(left)[0] for left, _ in pairs[:20]])
        det = float(np.max(np.abs(again - EL[:20])))
        mem = float(subprocess.run([sys.executable, "-c", MEM_SNIPPET, name], cwd=ROOT, capture_output=True, text=True).stdout.strip() or "nan")
        report[name] = {"file_bytes": emb.size_bytes, "embedding_dim": int(EL.shape[1]), "p50_ms": float(np.percentile(lat, 50)),
                        "p95_ms": float(np.percentile(lat, 95)), "n_inferences": len(lat), "stereo_retrieval_at_1": r1,
                        "determinism_max_abs_diff": det, "peak_rss_mb_isolated": mem,
                        "onnxruntime_provider": "CPUExecutionProvider", "threads": 4}
        print(name, report[name])
    elig = {k: v for k, v in report.items() if v["determinism_max_abs_diff"] < 1e-5 and v["p95_ms"] <= 250}
    if not elig:
        raise SystemExit("no eligible model")
    best = max(elig.values(), key=lambda v: v["stereo_retrieval_at_1"])["stereo_retrieval_at_1"]
    tied = [k for k, v in elig.items() if best - v["stereo_retrieval_at_1"] <= 0.01]
    chosen = min(tied, key=lambda k: report[k]["file_bytes"])
    models = json.loads((ROOT / "data" / "manifests" / "vision_models.json").read_text())["models"]
    OUT.write_text(json.dumps({"chosen": chosen, "chosen_sha256": models[chosen]["sha256"], "chosen_url": models[chosen]["url"],
                               "rule": __doc__.split("Selection rule", 1)[1].split("Output:")[0].strip(),
                               "split_used": "development (sols 412–430) only", "selected_at": datetime.now(timezone.utc).isoformat(),
                               "stereo_pairs": len(pairs), "candidates": report, "label": "LOCAL VISION BASELINE — not a deployability claim"},
                              indent=1))
    print(f"CHOSEN: {chosen} → {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
