"""M6/M7 — cheap local image features: decoding, engineering QUALITY state, perceptual hash. No cloud, no ML.

Quality is an ENGINEERING signal only (exposure, clipping, missing data, corruption); it is never used as, or mixed
into, a science-value estimate.

Declared quality thresholds (a priori, not tuned on results; 12-bit data, DN 0–4095):
  BAD      missing ≥ 25 %  or  saturated ≥ 50 %  or  contrast (std/4095) < 0.002 (flat)  or  label error pixels ≥ 5 %
  SUSPECT  missing ≥ 1 %   or  saturated ≥ 5 %   or  black ≥ 5 %  or  brightness < 0.02 or > 0.95  or  flat rows ≥ 2 %
  CLEAN    otherwise
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from deepsift.core.config import ROOT
from deepsift.imaging.pds3 import parse_label, read_image

DN_MAX = 4095.0
WORK = 256                       # working resolution for features / hashes / embeddings


def load_primary(acq: dict) -> np.ndarray:
    p = acq["primary"]
    lbl = (ROOT / p["path_lbl"]).read_text(encoding="latin-1")
    return read_image(ROOT / p["path_img"], parse_label(lbl))


def to_work(img: np.ndarray, size: int = WORK) -> np.ndarray:
    """Resize to size×size (area/bicubic via PIL) and scale to 0–1 with the fixed 12-bit range (no per-image stretch)."""
    im = Image.fromarray(np.clip(img, 0, DN_MAX).astype(np.float32))
    return np.asarray(im.resize((size, size), Image.BOX if min(img.shape) >= size else Image.BICUBIC), dtype=np.float32) / DN_MAX


def quality(img: np.ndarray, error_pixels: int | None) -> dict:
    n = img.size
    zero_rows = np.all(img <= 0, axis=1)
    zero_cols = np.all(img <= 0, axis=0)
    missing = (zero_rows.sum() * img.shape[1] + zero_cols.sum() * img.shape[0] - zero_rows.sum() * zero_cols.sum()) / n
    flat_rows = float(np.mean(img.std(axis=1) == 0))
    w = to_work(img)
    lap = w[:-2, 1:-1] + w[2:, 1:-1] + w[1:-1, :-2] + w[1:-1, 2:] - 4 * w[1:-1, 1:-1]
    hist = np.histogram(np.clip(img, 0, DN_MAX), bins=256, range=(0, DN_MAX))[0].astype(float)
    pr = hist[hist > 0] / n
    f = {
        "brightness": float(img.mean() / DN_MAX), "contrast": float(img.std() / DN_MAX),
        "entropy_bits": float(-(pr * np.log2(pr)).sum()), "sharpness": float(lap.var()),
        "saturated_fraction": float(np.mean(img >= DN_MAX)), "black_fraction": float(np.mean(img <= 0)),
        "missing_fraction": float(missing), "flat_row_fraction": flat_rows,
        "error_pixel_fraction": (error_pixels / n) if isinstance(error_pixels, (int, float)) else None,
        "dn_max": float(img.max()), "dn_min": float(img.min()),
    }
    epf = f["error_pixel_fraction"] or 0.0
    if f["missing_fraction"] >= 0.25 or f["saturated_fraction"] >= 0.5 or f["contrast"] < 0.002 or epf >= 0.05:
        state = "BAD"
    elif (f["missing_fraction"] >= 0.01 or f["saturated_fraction"] >= 0.05 or f["black_fraction"] >= 0.05
          or f["brightness"] < 0.02 or f["brightness"] > 0.95 or flat_rows >= 0.02):
        state = "SUSPECT"
    else:
        state = "CLEAN"
    f["quality_state"] = state
    return f


def phash(img: np.ndarray) -> int:
    """64-bit perceptual hash: 32×32 → 2-D DCT → top-left 8×8 (DC dropped from the median) → sign vs median."""
    w = to_work(img, 32).astype(np.float64)
    n = 32
    k = np.arange(n)
    dct = np.cos(np.pi * (2 * k[None, :] + 1) * k[:, None] / (2 * n))
    c = dct @ w @ dct.T
    block = c[:8, :8].flatten()
    med = np.median(block[1:])
    bits = block > med
    return int("".join("1" if b else "0" for b in bits), 2)


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def jpeg_bytes(img: np.ndarray, quality_q: int = 50) -> int:
    """Measured size of a DEEPSIFT ground re-encoding (8-bit JPEG at native resolution) — NOT an onboard product."""
    import io

    b = io.BytesIO()
    Image.fromarray((np.clip(img, 0, DN_MAX) / DN_MAX * 255).astype(np.uint8)).save(b, format="JPEG", quality=quality_q)
    return b.getbuffer().nbytes


__all__ = ["load_primary", "to_work", "quality", "phash", "hamming", "jpeg_bytes", "Path"]
