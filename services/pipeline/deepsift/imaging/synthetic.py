"""Phase 3.1 — SYNTHETIC VISUAL CONTROLS (versioned; generator SYNTH_V1).

Every control is a perturbed COPY of a development NASA PDS observation. Original products are never modified; outputs
live under data/synthetic/ (git-ignored), described by data/manifests/synthetic_controls_v1.json. They are controlled
image perturbations — never "Mars anomalies" or scientific events — and are labelled SYNTHETIC CONTROL everywhere.

Families (declared before any result) and objective difficulty levels (derived from parameters only):
  ENGINEERING QUALITY CONTROLS
    BLUR            Gaussian σ in working-scale pixels (256 px wide):  OBVIOUS 4 · MODERATE 2 · SUBTLE 1 · NEAR_NOISE_FLOOR 0.5
    EXPOSURE        gain (direction by seed, over ↑ / under ↓):       3.0|0.2 · 1.8|0.45 · 1.3|0.75 · 1.05|0.95
    MISSING_REGION  zeroed rectangle, area fraction:                   0.30 · 0.10 · 0.03 · 0.005
    STRIPING        stuck columns (0 or 4095), fraction of columns:    0.20 · 0.05 · 0.01 · 0.002
    FRAME_DROPOUT   lost trailing rows (zeros), fraction of rows:      0.50 · 0.20 · 0.05 · 0.01
  VISUAL NOVELTY CONTROLS
    LOCALIZED_STRUCTURE  filled disk, (area fraction, contrast in image σ): (0.01,4) · (0.005,2) · (0.0025,1) · (0.001,0.3)
    TEXTURE_CHANGE       checker patch, (area fraction, amplitude in σ):    (0.04,3) · (0.02,1.5) · (0.01,0.7) · (0.005,0.25)
  REDUNDANCY CONTROL (pHash / grouping evaluation only)
    NEAR_DUPLICATE  Gaussian noise σ = 5 DN + 1-pixel shift — a true duplicate of its source by construction
"""

from __future__ import annotations

import hashlib

import numpy as np
from scipy.ndimage import gaussian_filter

GENERATOR = "SYNTH_V1"
DN_MAX = 4095.0
LEVELS = ["OBVIOUS", "MODERATE", "SUBTLE", "NEAR_NOISE_FLOOR"]
FAMILIES = {
    "BLUR": ("ENGINEERING_QUALITY", {"OBVIOUS": {"sigma_work_px": 4.0}, "MODERATE": {"sigma_work_px": 2.0},
                                     "SUBTLE": {"sigma_work_px": 1.0}, "NEAR_NOISE_FLOOR": {"sigma_work_px": 0.5}}),
    "EXPOSURE": ("ENGINEERING_QUALITY", {"OBVIOUS": {"gain_over": 3.0, "gain_under": 0.2}, "MODERATE": {"gain_over": 1.8, "gain_under": 0.45},
                                         "SUBTLE": {"gain_over": 1.3, "gain_under": 0.75}, "NEAR_NOISE_FLOOR": {"gain_over": 1.05, "gain_under": 0.95}}),
    "MISSING_REGION": ("ENGINEERING_QUALITY", {"OBVIOUS": {"area": 0.30}, "MODERATE": {"area": 0.10}, "SUBTLE": {"area": 0.03},
                                               "NEAR_NOISE_FLOOR": {"area": 0.005}}),
    "STRIPING": ("ENGINEERING_QUALITY", {"OBVIOUS": {"column_fraction": 0.20}, "MODERATE": {"column_fraction": 0.05},
                                         "SUBTLE": {"column_fraction": 0.01}, "NEAR_NOISE_FLOOR": {"column_fraction": 0.002}}),
    "FRAME_DROPOUT": ("ENGINEERING_QUALITY", {"OBVIOUS": {"row_fraction": 0.50}, "MODERATE": {"row_fraction": 0.20},
                                              "SUBTLE": {"row_fraction": 0.05}, "NEAR_NOISE_FLOOR": {"row_fraction": 0.01}}),
    "LOCALIZED_STRUCTURE": ("VISUAL_NOVELTY", {"OBVIOUS": {"area": 0.01, "contrast_sigma": 4.0}, "MODERATE": {"area": 0.005, "contrast_sigma": 2.0},
                                               "SUBTLE": {"area": 0.0025, "contrast_sigma": 1.0}, "NEAR_NOISE_FLOOR": {"area": 0.001, "contrast_sigma": 0.3}}),
    "TEXTURE_CHANGE": ("VISUAL_NOVELTY", {"OBVIOUS": {"area": 0.04, "amplitude_sigma": 3.0}, "MODERATE": {"area": 0.02, "amplitude_sigma": 1.5},
                                          "SUBTLE": {"area": 0.01, "amplitude_sigma": 0.7}, "NEAR_NOISE_FLOOR": {"area": 0.005, "amplitude_sigma": 0.25}}),
}
DUPLICATE = ("REDUNDANCY", {"noise_dn": 5.0, "shift_px": 1})


def seed_for(*parts) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)


def _rect(rng, h, w, area):
    a = area * h * w
    aspect = rng.uniform(0.5, 2.0)
    rh = int(max(1, min(h, round(np.sqrt(a * aspect)))))
    rw = int(max(1, min(w, round(a / max(rh, 1)))))
    y0 = int(rng.integers(0, h - rh + 1))
    x0 = int(rng.integers(0, w - rw + 1))
    return y0, x0, y0 + rh, x0 + rw


def perturb(img: np.ndarray, family: str, level: str, seed: int) -> tuple[np.ndarray, dict, list[int] | None]:
    """Return (perturbed copy, parameters actually applied, bounding region [y0, x0, y1, x1] or None)."""
    rng = np.random.default_rng(seed)
    x = img.astype(np.float32).copy()
    h, w = x.shape
    p = dict(FAMILIES[family][1][level])
    box = None
    sd = float(x.std()) or 1.0
    if family == "BLUR":
        p["sigma_native_px"] = p["sigma_work_px"] * w / 256.0
        x = gaussian_filter(x, p["sigma_native_px"])
    elif family == "EXPOSURE":
        up = bool(rng.random() < 0.5)
        p["direction"] = "over" if up else "under"
        p["gain"] = p["gain_over"] if up else p["gain_under"]
        x = x * p["gain"]
    elif family == "MISSING_REGION":
        box = list(_rect(rng, h, w, p["area"]))
        x[box[0]:box[2], box[1]:box[3]] = 0.0
    elif family == "STRIPING":
        k = max(1, round(p["column_fraction"] * w))
        cols = np.sort(rng.choice(w, size=k, replace=False))
        p["value"] = float(rng.choice([0.0, DN_MAX]))
        p["columns"] = int(k)
        x[:, cols] = p["value"]
    elif family == "FRAME_DROPOUT":
        k = max(1, round(p["row_fraction"] * h))
        x[h - k:, :] = 0.0
        box = [h - k, 0, h, w]
    elif family == "LOCALIZED_STRUCTURE":
        r = max(1.0, float(np.sqrt(p["area"] * h * w / np.pi)))
        cy = float(rng.uniform(r, h - r))
        cx = float(rng.uniform(r, w - r))
        yy, xx = np.ogrid[:h, :w]
        mask = (yy - cy) ** 2 + (xx - cx) ** 2 <= r * r
        sign = float(rng.choice([-1.0, 1.0]))
        x[mask] += sign * p["contrast_sigma"] * sd
        p.update(radius_px=r, sign=sign, image_sigma_dn=sd)
        box = [int(cy - r), int(cx - r), int(cy + r) + 1, int(cx + r) + 1]
    elif family == "TEXTURE_CHANGE":
        box = list(_rect(rng, h, w, p["area"]))
        period = max(2, w // 64)
        yy, xx = np.mgrid[box[0]:box[2], box[1]:box[3]]
        checker = np.where(((yy // period) + (xx // period)) % 2 == 0, 1.0, -1.0)
        x[box[0]:box[2], box[1]:box[3]] += p["amplitude_sigma"] * sd * checker
        p.update(period_px=period, image_sigma_dn=sd)
    else:
        raise ValueError(family)
    return np.clip(x, 0, DN_MAX), p, box


def near_duplicate(img: np.ndarray, seed: int) -> tuple[np.ndarray, dict]:
    rng = np.random.default_rng(seed)
    p = dict(DUPLICATE[1])
    x = img.astype(np.float32) + rng.normal(0, p["noise_dn"], img.shape).astype(np.float32)
    x = np.roll(x, p["shift_px"], axis=1)
    return np.clip(x, 0, DN_MAX), p


def save_png16(path, arr: np.ndarray) -> None:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.clip(np.rint(arr), 0, DN_MAX).astype(np.uint16)).save(path, format="PNG")


def load_png16(path) -> np.ndarray:
    from PIL import Image

    return np.asarray(Image.open(path), dtype=np.float32)
