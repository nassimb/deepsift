"""LOCAL EDGE BASELINE — a small, interpretable, network-free decision model.

L2-regularised logistic regression on 14 event features. Trained ONLY on the calibration split with
synthetic injections from seeds disjoint from validation/test (target = the candidate event overlaps an
injection). Inference is pure numpy on a JSON of coefficients — no scikit-learn at runtime.

This makes no claim of spacecraft flight compatibility; it measures what a tiny local model achieves.
"""

from __future__ import annotations

import json
import math
import time
import tracemalloc
from pathlib import Path

import numpy as np

from deepsift.core.models import ScientificEvent
from deepsift.features.detect import QUALITY_FLAGS

FEATURES = [
    "log_deviation", "rarity", "log_duration", "n_flagged", "cross_instrument", "novelty", "is_rad",
    "flag_level", "flag_dip", "flag_quality", "max_abs_z_flagged", "lmst_sin", "lmst_cos", "log_raw_kb",
]


def featurize(e: ScientificEvent) -> list[float]:
    f = e.features
    flagged = [c for n, c in f.channels.items() if n in e.sensors]
    flags = {x for c in flagged for x in c.flags}
    return [
        math.log1p(f.deviation_score), f.rarity_score, math.log1p(f.duration_s), float(len(e.sensors)),
        float(f.cross_instrument_coincidence), f.novelty, float(e.instrument == "RAD"),
        float("level" in flags), float("dip" in flags), float(bool(flags & QUALITY_FLAGS)),
        max((abs(c.robust_z) for c in flagged), default=0.0) / 10.0,
        math.sin(2 * math.pi * f.lmst_hour / 24), math.cos(2 * math.pi * f.lmst_hour / 24),
        math.log1p(e.bytes.raw / 1024),
    ]


class LocalEdgeModel:
    def __init__(self, mean, scale, coef, intercept, meta=None):
        self.mean = np.asarray(mean)
        self.scale = np.asarray(scale)
        self.coef = np.asarray(coef)
        self.intercept = float(intercept)
        self.meta = meta or {}

    def predict_proba_event(self, e: ScientificEvent) -> float:
        x = (np.asarray(featurize(e)) - self.mean) / self.scale
        return float(1 / (1 + math.exp(-(x @ self.coef + self.intercept))))

    def to_json(self) -> str:
        return json.dumps({"features": FEATURES, "mean": self.mean.tolist(), "scale": self.scale.tolist(),
                           "coef": self.coef.tolist(), "intercept": self.intercept, "meta": self.meta})

    @classmethod
    def load(cls, path: Path) -> "LocalEdgeModel":
        d = json.loads(path.read_text())
        return cls(d["mean"], d["scale"], d["coef"], d["intercept"], d.get("meta"))

    def footprint(self, sample: list[ScientificEvent]) -> dict:
        """Measured on this machine: serialized size, per-event CPU latency, peak Python memory during inference."""
        blob = self.to_json().encode()
        lat = []
        tracemalloc.start()
        for e in sample:
            t0 = time.perf_counter()
            self.predict_proba_event(e)
            lat.append((time.perf_counter() - t0) * 1000)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return {"model_json_bytes": len(blob), "parameters": int(self.coef.size + 1), "features": len(FEATURES),
                "latency_ms_p50": float(np.percentile(lat, 50)) if lat else None,
                "latency_ms_p99": float(np.percentile(lat, 99)) if lat else None,
                "inference_peak_python_bytes": int(peak), "note": "CPU wall-clock on the development laptop; not a flight-hardware figure"}


def train(events: list[ScientificEvent], C: float = 1.0) -> LocalEdgeModel:
    from sklearn.linear_model import LogisticRegression

    X = np.array([featurize(e) for e in events])
    y = np.array([1 if e.synthetic_injection_ids else 0 for e in events])
    mean, scale = X.mean(0), X.std(0)
    scale[scale == 0] = 1.0
    clf = LogisticRegression(C=C, max_iter=2000, class_weight="balanced").fit((X - mean) / scale, y)
    return LocalEdgeModel(mean, scale, clf.coef_[0], clf.intercept_[0],
                          {"n_train": int(len(y)), "positives": int(y.sum()), "C": C,
                           "coefficients": dict(zip(FEATURES, [round(float(c), 4) for c in clf.coef_[0]]))})
