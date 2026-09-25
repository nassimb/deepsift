"""QUALITY_V2 — development-tuned engineering-quality detector (QUALITY_V1 in features.py stays frozen).

Adds detectors for defects V1 cannot see by construction, and derives thresholds from the UNTOUCHED real development
images (percentiles) plus the TUNE half of the synthetic controls (only to choose the sharpness percentile).
Recall is then measured on the disjoint EVAL half; the real-image false-alarm rate is IN-SAMPLE (development) and
must be re-measured on validation.

Extra features (all local, deterministic):
  stuck_column_fraction  columns with zero variance (stuck / striping)
  zero_pixel_fraction    pixels exactly 0 DN (masked / missing regions — real Navcam frames have DN ≥ ~30)
  missing_any            any complete zero row or column (partial frames)
  sharpness_norm         Laplacian variance / image variance at working scale (blur; per primary tier)
Still ENGINEERING ONLY — never a science-value signal.
"""

from __future__ import annotations

import numpy as np

from deepsift.imaging.features import quality as quality_v1
from deepsift.imaging.features import to_work

SHARP_PERCENTILE_CHOICES = (1, 2, 5)


def extra_features(img: np.ndarray) -> dict:
    w = to_work(img)
    lap = w[:-2, 1:-1] + w[2:, 1:-1] + w[1:-1, :-2] + w[1:-1, 2:] - 4 * w[1:-1, 1:-1]
    return {"stuck_column_fraction": float(np.mean(img.std(axis=0) == 0)),
            "zero_pixel_fraction": float(np.mean(img <= 0)),
            "missing_any": bool(np.any(np.all(img <= 0, axis=1)) or np.any(np.all(img <= 0, axis=0))),
            "sharpness_norm": float(lap.var() / (w.var() + 1e-9))}


def features(img: np.ndarray, error_pixels=None) -> dict:
    return {**quality_v1(img, error_pixels), **extra_features(img)}


def fit(real: list[tuple[str, dict]], sharp_percentile: int) -> dict:
    """real: [(primary_tier, features)] of UNTOUCHED development images → thresholds."""
    b = np.array([f["brightness"] for _, f in real])
    th = {"brightness_lo": float(np.percentile(b, 1)), "brightness_hi": float(np.percentile(b, 99)),
          "saturated_hi": max(0.005, float(np.percentile([f["saturated_fraction"] for _, f in real], 99)) * 2),
          "zero_pixel_hi": max(0.0005, float(np.percentile([f["zero_pixel_fraction"] for _, f in real], 99)) * 2),
          "sharp_percentile": sharp_percentile, "sharpness_norm_lo": {}}
    for tier in sorted({t for t, _ in real}):
        xs = [f["sharpness_norm"] for t, f in real if t == tier]
        th["sharpness_norm_lo"][tier] = float(np.percentile(xs, sharp_percentile))
    return th


def classify(f: dict, tier: str, th: dict) -> tuple[str, list[str]]:
    reasons = []
    if f["quality_state"] == "BAD":
        return "BAD", ["v1_bad"]
    if f["quality_state"] == "SUSPECT":
        reasons.append("v1_suspect")
    if f["stuck_column_fraction"] > 0:
        reasons.append("stuck_columns")
    if f["zero_pixel_fraction"] >= th["zero_pixel_hi"]:
        reasons.append("zero_pixels")
    if f["missing_any"]:
        reasons.append("missing_rows_or_columns")
    if f["saturated_fraction"] >= th["saturated_hi"]:
        reasons.append("saturation")
    if not th["brightness_lo"] <= f["brightness"] <= th["brightness_hi"]:
        reasons.append("brightness_out_of_range")
    lo = th["sharpness_norm_lo"].get(tier)
    if lo is not None and f["sharpness_norm"] < lo:
        reasons.append("low_sharpness")
    return ("SUSPECT" if reasons else "CLEAN"), reasons
