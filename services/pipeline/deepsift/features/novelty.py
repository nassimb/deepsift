"""Historical novelty: similarity of each event to earlier events (causal, in time order)."""

from __future__ import annotations

import math

import numpy as np

from deepsift.core.models import ScientificEvent

CHANNEL_ORDER = ["pressure", "air_temp", "ground_temp", "uv_abc", "rel_humidity", "dose_b", "dose_e"]


def signature(e: ScientificEvent) -> np.ndarray:
    ch = e.features.channels
    v = []
    for name in CHANNEL_ORDER:
        c = ch.get(name)
        v.append(float(np.clip(c.robust_z / 8, -2, 2)) if c else 0.0)
    for name in CHANNEL_ORDER:
        c = ch.get(name)
        v.append(1.0 if c and name in e.sensors else 0.0)
    q = [c for c in ch.values()]
    v += [
        max((c.dip for c in q), default=0.0) / 2,
        1.0 if any("stuck" in c.flags for c in q) else 0.0,
        1.0 if any("dropout" in c.flags for c in q) else 0.0,
        1.0 if any("noise" in c.flags for c in q) else 0.0,
        0.5 * math.sin(2 * math.pi * e.features.lmst_hour / 24),
        0.5 * math.cos(2 * math.pi * e.features.lmst_hour / 24),
        min(math.log10(e.features.duration_s + 1) / 5, 1.0),
    ]
    return np.array(v)


def assign_novelty(events: list[ScientificEvent]) -> None:
    """Set features.novelty = 1 − max cosine similarity to any earlier event."""
    ordered = sorted(events, key=lambda e: e.timestamp_start)
    sigs: list[tuple[str, np.ndarray]] = []
    for e in ordered:
        s = signature(e)
        best, best_id = 0.0, None
        for pid, ps in sigs:
            denom = np.linalg.norm(s) * np.linalg.norm(ps)
            sim = float(s @ ps / denom) if denom > 0 else 0.0
            if sim > best:
                best, best_id = sim, pid
        e.features.novelty = round(1 - best, 4)
        e.features.most_similar_event = best_id
        sigs.append((e.id, s))
