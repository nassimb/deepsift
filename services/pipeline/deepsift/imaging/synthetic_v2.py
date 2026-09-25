"""SYNTHETIC_GENERATOR_V2 + perturbation CONTRACTS (Phase 3.2). SYNTH_V1 (synthetic.py) stays frozen.

Why V2: in Phase 3.1, V1 visual-novelty perturbations were clipped to [0, 4095]; dark disks / checker troughs hit DN 0
and accidentally triggered engineering-quality detection (cross-talk). V2 never clips a visual-novelty perturbation:
its amplitude is attenuated just enough to stay inside [DN_LO, DN_HI] = [1, 4094] and the applied scale is recorded
(`amplitude_scale`); difficulty levels stay defined by the NOMINAL parameters. Engineering families are unchanged from
V1 (they are meant to violate engineering constraints) but must respect their own contracts. All outputs are
SYNTHETIC CONTROLS — modified copies of NASA PDS observations, never Mars anomalies.
"""

from __future__ import annotations

import numpy as np

from deepsift.imaging import synthetic as v1

GENERATOR = "SYNTH_V2"
DN_LO, DN_HI = 1.0, 4094.0
LEVELS = v1.LEVELS
FAMILIES = v1.FAMILIES

# ---------------------------------------------------------------- contracts (allowed changes / forbidden side effects)
VISUAL_FORBIDDEN = ["dimension_change", "new_zero_pixels", "new_saturation", "changes_outside_region", "new_missing_rows_or_columns",
                    "new_stuck_columns", "global_exposure_shift", "global_histogram_collapse"]
CONTRACTS = {
    "LOCALIZED_STRUCTURE": {"kind": "VISUAL_NOVELTY", "allowed": ["bounded inserted structure inside the declared region"],
                            "forbidden": VISUAL_FORBIDDEN},
    "TEXTURE_CHANGE": {"kind": "VISUAL_NOVELTY", "allowed": ["local texture / spatial-frequency change inside the declared region"],
                       "forbidden": VISUAL_FORBIDDEN},
    "BLUR": {"kind": "ENGINEERING_QUALITY", "allowed": ["global smoothing"], "forbidden": ["dimension_change", "new_zero_pixels"]},
    "EXPOSURE": {"kind": "ENGINEERING_QUALITY", "allowed": ["global gain change", "clipping at 0 / 4095 (intended)"], "forbidden": ["dimension_change"]},
    "MISSING_REGION": {"kind": "ENGINEERING_QUALITY", "allowed": ["zeroed pixels inside the declared region"],
                       "forbidden": ["dimension_change", "changes_outside_region"]},
    "STRIPING": {"kind": "ENGINEERING_QUALITY", "allowed": ["stuck columns at 0 or 4095"], "forbidden": ["dimension_change", "changes_outside_columns"]},
    "FRAME_DROPOUT": {"kind": "ENGINEERING_QUALITY", "allowed": ["zeroed trailing rows"], "forbidden": ["dimension_change", "changes_outside_region"]},
    "NEAR_DUPLICATE": {"kind": "REDUNDANCY", "allowed": ["small noise + 1-px shift"],
                       "forbidden": ["dimension_change", "new_zero_pixels", "new_saturation", "global_exposure_shift"]},
}


def _mask(shape, box):
    m = np.zeros(shape, dtype=bool)
    if box is not None:
        m[box[0]:box[2], box[1]:box[3]] = True
    return m


def check_contract(family: str, src: np.ndarray, out: np.ndarray, params: dict, box: list[int] | None) -> list[str]:
    """Names of forbidden side effects present in `out` (empty list = contract satisfied)."""
    bad = []
    forb = set(CONTRACTS[family]["forbidden"])
    if out.shape != src.shape:
        return ["dimension_change"]
    if "new_zero_pixels" in forb and int(np.sum(out <= 0)) > int(np.sum(src <= 0)):
        bad.append("new_zero_pixels")
    if "new_saturation" in forb and int(np.sum(out >= 4095)) > int(np.sum(src >= 4095)):
        bad.append("new_saturation")
    if "changes_outside_region" in forb:
        outside = ~_mask(src.shape, box)
        if box is None or np.any(out[outside] != src[outside]):
            bad.append("changes_outside_region")
    if "changes_outside_columns" in forb:
        cols = np.ones(src.shape[1], dtype=bool)
        cols[params.get("column_indices", [])] = False
        if np.any(out[:, cols] != src[:, cols]):
            bad.append("changes_outside_columns")
    if "new_missing_rows_or_columns" in forb:
        z = lambda a: int(np.sum(np.all(a <= 0, axis=1)) + np.sum(np.all(a <= 0, axis=0)))  # noqa: E731
        if z(out) > z(src):
            bad.append("new_missing_rows_or_columns")
    if "new_stuck_columns" in forb and int(np.sum(out.std(axis=0) == 0)) > int(np.sum(src.std(axis=0) == 0)):
        bad.append("new_stuck_columns")
    sd = float(src.std()) or 1.0
    if "global_exposure_shift" in forb and abs(float(out.mean()) - float(src.mean())) > 0.1 * sd:
        bad.append("global_exposure_shift")
    if "global_histogram_collapse" in forb and float(out.std()) < 0.9 * sd:
        bad.append("global_histogram_collapse")
    return bad


def _bounded_add(x: np.ndarray, delta: np.ndarray, region: tuple[slice, slice]) -> tuple[np.ndarray, float]:
    """Add delta inside `region` scaled by the largest s ≤ 1 keeping every pixel in [DN_LO, DN_HI] — no clipping."""
    xs = x[region]
    with np.errstate(divide="ignore", invalid="ignore"):
        up = np.where(delta > 0, (DN_HI - xs) / delta, np.inf)
        dn = np.where(delta < 0, (xs - DN_LO) / (-delta), np.inf)
    s = float(min(1.0, np.min(up), np.min(dn)))
    s = max(0.0, s)
    out = x.copy()
    out[region] = xs + s * delta
    return out, s


def perturb(img: np.ndarray, family: str, level: str, seed: int) -> tuple[np.ndarray, dict, list[int] | None]:
    if family not in ("LOCALIZED_STRUCTURE", "TEXTURE_CHANGE"):
        y, p, box = v1.perturb(img, family, level, seed)          # engineering families: identical to V1
        if family == "STRIPING":                                    # record the stuck columns for the contract check
            rng = np.random.default_rng(seed)
            k = max(1, round(p["column_fraction"] * img.shape[1]))
            p["column_indices"] = sorted(int(c) for c in rng.choice(img.shape[1], size=k, replace=False))
        return y, p, box
    rng = np.random.default_rng(seed)
    x = img.astype(np.float32).copy()
    h, w = x.shape
    p = dict(FAMILIES[family][1][level])
    sd = float(x.std()) or 1.0
    if family == "LOCALIZED_STRUCTURE":
        r = max(1.0, float(np.sqrt(p["area"] * h * w / np.pi)))
        cy = float(rng.uniform(r, h - r))
        cx = float(rng.uniform(r, w - r))
        box = [int(cy - r), int(cx - r), int(cy + r) + 1, int(cx + r) + 1]
        box = [max(0, box[0]), max(0, box[1]), min(h, box[2]), min(w, box[3])]
        yy, xx = np.ogrid[box[0]:box[2], box[1]:box[3]]
        disk = ((yy - cy) ** 2 + (xx - cx) ** 2 <= r * r).astype(np.float32)
        sign = float(rng.choice([-1.0, 1.0]))
        delta = sign * p["contrast_sigma"] * sd * disk
        p.update(radius_px=r, sign=sign, image_sigma_dn=sd)
    else:
        box = list(v1._rect(rng, h, w, p["area"]))
        period = max(2, w // 64)
        yy, xx = np.mgrid[box[0]:box[2], box[1]:box[3]]
        checker = np.where(((yy // period) + (xx // period)) % 2 == 0, 1.0, -1.0).astype(np.float32)
        delta = p["amplitude_sigma"] * sd * checker
        p.update(period_px=period, image_sigma_dn=sd)
    out, s = _bounded_add(x, delta, (slice(box[0], box[2]), slice(box[1], box[3])))
    p["amplitude_scale"] = s
    p["effective_fraction_of_nominal"] = s
    return out, p, box


def near_duplicate(img: np.ndarray, seed: int) -> tuple[np.ndarray, dict]:
    rng = np.random.default_rng(seed)
    p = dict(v1.DUPLICATE[1])
    x = img.astype(np.float32) + rng.normal(0, p["noise_dn"], img.shape).astype(np.float32)
    x = np.roll(x, p["shift_px"], axis=1)
    lo, hi = max(DN_LO, float(img.min())), min(DN_HI, float(img.max()))
    return np.clip(x, lo, hi), p                                   # stays inside the SOURCE range: no new 0 / 4095
