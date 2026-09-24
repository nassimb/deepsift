"""Systematic synthetic stress test: parameter sweeps with fixed seeds.

Magnitudes are expressed in multiples of the *background* σ the detector itself uses at the injection
point (1.4826·MAD of the nearest-LMST values over the trailing baseline sols, floored by the calibrated
sensor noise). Difficulty buckets — declared before any Phase-2 result was computed:

    NEAR_NOISE_FLOOR  < 2 σ      WEAK  2–4 σ      MODERATE  4–8 σ      OBVIOUS  ≥ 8 σ

The grid deliberately extends past the calibrated level threshold (~9 σ REMS, ~8.6 σ RAD) so that the
sweep crosses it from both sides. Synthetic results are NEVER pooled with documented-event results.

Severity convention for synthetic labels (a priori): multi-sensor or RAD offsets → high; single-channel
REMS offsets → medium; quality faults (stuck, dropout, noise) → low.
"""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import polars as pl

from deepsift.evaluation.injection import Injection

REMS_CHANNELS = ["pressure", "air_temp", "ground_temp", "uv_abc", "rel_humidity"]
RAD_CHANNELS = ["dose_b", "dose_e"]
MAGNITUDE_SIGMA = [1, 2, 3, 4, 5, 8, 12, 16]
REMS_DURATIONS_S = [30, 120, 300, 900, 3600]
RAD_DURATIONS_S = [1800, 3600, 10800, 43200]
SHAPES = ["step", "pulse", "ramp"]
SENSOR_COUNTS = [1, 2, 3]
QUALITY_KINDS = ["sensor_stuck", "sensor_dropout", "noisy_sensor"]
MIN_SPACING_S = 3 * 3600


def bucket(m: float) -> str:
    if m < 2:
        return "NEAR_NOISE_FLOOR"
    if m < 4:
        return "WEAK"
    if m < 8:
        return "MODERATE"
    return "OBVIOUS"


def _sigma_lookup(windows: pl.DataFrame):
    """(channel, t) → background σ of the window containing t (uninjected detection)."""
    idx = {}
    for (ch,), part in windows.filter(pl.col("n") > 0).sort("t_start").group_by("channel"):
        idx[ch] = (part["t_start"].to_list(), part["t_end"].to_list(), part["sigma"].to_list())

    def get(ch: str, t):
        if ch not in idx:
            return None
        ts, te, sg = idx[ch]
        import bisect

        i = bisect.bisect_right(ts, t) - 1
        if i >= 0 and ts[i] <= t <= te[i] + timedelta(minutes=5):
            return sg[i]
        return None

    return get


def plan_sweep_batch(samples: pl.DataFrame, windows: pl.DataFrame, eval_sols: tuple[int, int], n: int, seed: int,
                     floors: dict[str, float], batch_id: str) -> list[Injection]:
    rng = np.random.default_rng(seed)
    sig = _sigma_lookup(windows)
    pools = {}
    for ch in REMS_CHANNELS + RAD_CHANNELS:
        pools[ch] = samples.filter((pl.col("channel") == ch) & (pl.col("sol") >= eval_sols[0]) & (pl.col("sol") <= eval_sols[1]))["t"]
    placed: list = []
    out: list[Injection] = []
    tries = 0
    while len(out) < n and tries < n * 50:
        tries += 1
        family = rng.choice(["rems_offset", "rad_offset", "quality"], p=[0.55, 0.2, 0.25])
        if family == "rad_offset":
            chans = list(RAD_CHANNELS)
            dur = float(rng.choice(RAD_DURATIONS_S))
            kind = f"offset_{rng.choice(SHAPES)}"
        elif family == "rems_offset":
            k = int(rng.choice(SENSOR_COUNTS))
            chans = list(rng.choice(REMS_CHANNELS, size=k, replace=False))
            dur = float(rng.choice(REMS_DURATIONS_S))
            kind = f"offset_{rng.choice(SHAPES)}"
        else:
            kind = str(rng.choice(QUALITY_KINDS))
            chans = [str(rng.choice(REMS_CHANNELS))]
            dur = float(rng.choice([120, 300, 900, 3600]))
        pool = pools[chans[0]]
        if pool.is_empty():
            continue
        t0 = pool[int(rng.integers(0, len(pool)))]
        if any(abs((t0 - p).total_seconds()) < MIN_SPACING_S + dur for p in placed):
            continue
        m = float(rng.choice(MAGNITUDE_SIGMA))
        sigmas = {c: sig(c, t0) for c in chans}
        if any(v is None or not np.isfinite(v) for v in sigmas.values()):
            continue
        meta = {"batch": batch_id, "family": family, "shape": kind.split("_", 1)[1] if kind.startswith("offset_") else None,
                "magnitude_sigma": m, "sigma_bg": sigmas, "sensor_count": len(chans), "sign": float(rng.choice([-1.0, 1.0]))}
        if kind.startswith("offset_"):
            meta["abs_magnitude"] = {c: m * sigmas[c] for c in chans}
            meta["bucket"] = bucket(m)
            severity = "high" if (len(chans) > 1 or family == "rad_offset") else "medium"
            etype = "radiation" if family == "rad_offset" else "atmospheric" if set(chans) & {"pressure", "uv_abc", "rel_humidity"} else "thermal"
            mag = m
        elif kind == "noisy_sensor":
            mag = m * floors.get(chans[0], 0.1)          # noise σ in multiples of the sensor noise floor
            meta["bucket"] = bucket(m)
            severity, etype = "low", "instrument_anomaly"
        else:
            mag = 0.0
            meta["bucket"] = "QUALITY_FAULT"
            severity, etype = "low", "instrument_anomaly"
        placed.append(t0)
        out.append(Injection(id=f"SYN-{batch_id}-{len(out):03d}", kind=kind, channels=[str(c) for c in chans], t_start=t0,
                             duration_s=dur, magnitude=mag, expected_type=etype, severity=severity, meta=meta))
    return out
