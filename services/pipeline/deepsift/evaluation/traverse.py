"""Traverse frame selection (Phase 3 primary path) and traverse metrics.

The selection methods are the frozen Phase 3.2 / 3.3 definitions (config/phase3_3_validation_config.json → "traverse"),
moved here unchanged from scripts/run_phase3_2.py / run_phase3_3.py so that later phases import one implementation:

    EVERY_NTH_FRAME, UNIFORM_DISTANCE, METADATA_POSITION (= POSITION), EMBEDDING_CHANGE, POSITION_PLUS_EMBEDDING_CHANGE

Inputs are per-sequence arrays only (positions in metres, L2-normalised embeddings). No pHash, quality, telemetry or Jev
signal enters any selection. `metrics` adds the Phase 3.4 scale-aware metrics (p95 gap, gap / length, gap / native
spacing, distance from every archived frame position to its nearest kept frame) next to the Phase 3.3 ones.
"""

from __future__ import annotations

import math

import numpy as np

METHODS = ["EVERY_NTH_FRAME", "UNIFORM_DISTANCE", "METADATA_POSITION", "EMBEDDING_CHANGE", "POSITION_PLUS_EMBEDDING_CHANGE"]


def fps(D: np.ndarray, k: int) -> list[int]:
    """Farthest-point sampling on a distance matrix, starting from frame 0 (frozen definition)."""
    sel = [0]
    dmin = D[0].copy()
    while len(sel) < k:
        j = int(np.argmax(dmin))
        if dmin[j] <= 0:
            rest = [x for x in range(len(D)) if x not in sel]
            if not rest:
                break
            j = rest[0]
        sel.append(j)
        dmin = np.minimum(dmin, D[j])
    return sorted(set(sel))


def uniform_distance(cum: np.ndarray, targets: np.ndarray) -> list[int]:
    used: list[int] = []
    for d in targets:
        for j in np.argsort(np.abs(cum - d), kind="stable"):
            if int(j) not in used:
                used.append(int(j))
                break
    return sorted(used)


def select(method: str, xy: np.ndarray, emb: np.ndarray, frac: float) -> list[int]:
    """Indices (into the sequence) kept at FULL for retention fraction `frac` (< 1)."""
    m = len(xy)
    k = max(1, math.ceil(frac * m))
    Dp = np.linalg.norm(xy[:, None] - xy[None], axis=2)
    De = 1.0 - emb @ emb.T
    cum = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))])
    if method == "EVERY_NTH_FRAME":
        step = max(1, round(1 / frac))
        return sorted(list(range(0, m, step))[:k] or [0])
    if method == "UNIFORM_DISTANCE":
        return uniform_distance(cum, np.linspace(0, cum[-1], k))
    if method == "METADATA_POSITION":
        return fps(Dp, k)
    if method == "EMBEDDING_CHANGE":
        return fps(De, k)
    if method == "POSITION_PLUS_EMBEDDING_CHANGE":
        return fps(0.5 * Dp / (Dp.max() or 1.0) + 0.5 * De / (De.max() or 1.0), k)
    raise ValueError(method)


def gaps(xy: np.ndarray, sel: list[int]) -> list[float]:
    s = sorted(sel)
    return [float(np.linalg.norm(xy[a] - xy[b])) for a, b in zip(s, s[1:])]


def metrics(xy: np.ndarray, emb: np.ndarray, sel: list[int], radius_m: float = 5.0) -> dict:
    """Per-sequence metrics for one selection (SEND_ALL = all indices)."""
    s = sorted(sel)
    Dp = np.linalg.norm(xy[:, None] - xy[None], axis=2)
    native = gaps(xy, list(range(len(xy))))
    g = gaps(xy, s)
    length = float(sum(native)) or 1.0
    med_native = float(np.median(native)) if native else 0.0
    return {"frames": len(xy), "frames_retained": len(s), "gaps_m": g,
            "position_coverage": float(np.mean(np.min(Dp[:, s], axis=1) <= radius_m)),
            "max_distance_to_kept_m": float(np.max(np.min(Dp[:, s], axis=1))),
            "p95_distance_to_kept_m": float(np.percentile(np.min(Dp[:, s], axis=1), 95)),
            "mean_gap_m": float(np.mean(g)) if g else 0.0, "max_gap_m": max(g) if g else 0.0,
            "p95_gap_m": float(np.percentile(g, 95)) if g else 0.0,
            "max_gap_over_length": (max(g) if g else 0.0) / length,
            "max_gap_over_native_median_spacing": ((max(g) if g else 0.0) / med_native) if med_native > 0 else None,
            "traverse_length_m": length, "native_median_spacing_m": med_native,
            "traverse_distance_represented": float(sum(g)) / length if len(s) > 1 else 0.0,
            "visual_change_coverage": float(np.mean(np.max(emb @ emb[s].T, axis=1)))}
