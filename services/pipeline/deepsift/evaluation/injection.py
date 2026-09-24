"""Controlled synthetic anomaly injection.

Injected anomalies modify *values* of real samples in a copy of the dataset. They are always
tagged: every modified sample carries the injection id, every overlapping event lists it in
`synthetic_injection_ids`, and each injection becomes a SYNTHETIC_ANOMALY evaluation label.
Byte costs remain those of the original records (injection does not change the archive).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

import numpy as np
import polars as pl

from deepsift.core.models import EventType

KINDS = {
    # kind: (channels, expected event type, severity, default duration s)
    "short_radiation_spike": (["dose_b", "dose_e"], EventType.RADIATION, "high", 1),
    "long_radiation_event": (["dose_b", "dose_e"], EventType.RADIATION, "high", 6 * 3600),
    "pressure_drop": (["pressure"], EventType.ATMOSPHERIC, "high", 25),
    "temperature_discontinuity": (["air_temp"], EventType.INSTRUMENT_ANOMALY, "medium", 900),
    "sensor_stuck": (["ground_temp"], EventType.INSTRUMENT_ANOMALY, "medium", 600),
    "sensor_dropout": (["rel_humidity"], EventType.INSTRUMENT_ANOMALY, "low", 600),
    "noisy_sensor": (["pressure"], EventType.INSTRUMENT_ANOMALY, "low", 600),
    "slow_drift": (["air_temp"], EventType.INSTRUMENT_ANOMALY, "medium", 3 * 3600),
    "multi_sensor_correlated": (["pressure", "ground_temp", "uv_abc"], EventType.ATMOSPHERIC, "high", 300),
}


@dataclass
class Injection:
    id: str
    kind: str
    channels: list[str]
    t_start: datetime
    duration_s: float
    magnitude: float
    expected_type: str
    severity: str

    @property
    def t_end(self) -> datetime:
        return self.t_start + timedelta(seconds=max(self.duration_s, 1))

    def to_dict(self) -> dict:
        d = asdict(self)
        d["t_start"] = self.t_start.isoformat()
        d["t_end"] = self.t_end.isoformat()
        d["label_source"] = "SYNTHETIC_ANOMALY"
        return d


def apply_injections(samples: pl.DataFrame, injections: list[Injection], seed: int = 0) -> pl.DataFrame:
    """Return a copy of `samples` with injections applied and an `injection_id` column."""
    rng = np.random.default_rng(seed)
    s = samples.with_columns(pl.lit(None, dtype=pl.Utf8).alias("injection_id"))
    for inj in injections:
        # RAD observations are ~15–30 min integrations: a spike hits the observation(s) whose
        # start falls within ±20 min of the injection window.
        pad = timedelta(minutes=20) if set(inj.channels) <= {"dose_b", "dose_e"} else timedelta(0)
        in_win = pl.col("channel").is_in(inj.channels) & pl.col("t").is_between(inj.t_start - pad, inj.t_end + pad)
        idx = s.with_row_index("_i").filter(in_win)["_i"].to_numpy()
        if len(idx) == 0:
            continue
        vals = s["value"].to_numpy().copy()
        ts = s["t"].dt.epoch("ms").to_numpy()[idx] / 1000.0
        chans = s["channel"].to_numpy()[idx]
        t0 = inj.t_start.timestamp()
        frac = np.clip((ts - t0) / max(inj.duration_s, 1), 0, 1)
        keep = np.ones(len(s), dtype=bool)
        m = inj.magnitude
        k = inj.kind
        if k in ("short_radiation_spike", "long_radiation_event"):
            vals[idx] = vals[idx] * (1 + m)
        elif k == "pressure_drop":
            centre = t0 + inj.duration_s / 2
            vals[idx] -= m * np.exp(-0.5 * ((ts - centre) / (inj.duration_s / 4)) ** 2)
        elif k == "temperature_discontinuity":
            vals[idx] += m
        elif k == "sensor_stuck":
            vals[idx] = vals[idx[0]]
        elif k == "sensor_dropout":
            keep[idx] = False
        elif k == "noisy_sensor":
            vals[idx] += rng.normal(0, m, len(idx))
        elif k == "slow_drift":
            vals[idx] += m * frac
        elif k == "multi_sensor_correlated":
            shape = np.sin(np.pi * frac)
            sign = np.where(chans == "pressure", -1.0, np.where(chans == "uv_abc", -0.05, 1.0))
            vals[idx] += sign * m * shape
        ids = s["injection_id"].to_list()
        for j in idx:
            ids[int(j)] = inj.id
        s = s.with_columns(pl.Series("value", vals), pl.Series("injection_id", ids, dtype=pl.Utf8)).filter(pl.Series(keep))
    return s


DEFAULT_MAGNITUDE = {
    "short_radiation_spike": 0.25,       # +25 % dose rate
    "long_radiation_event": 0.15,
    "pressure_drop": 2.5,                # Pa
    "temperature_discontinuity": 6.0,    # K step
    "sensor_stuck": 0.0,
    "sensor_dropout": 0.0,
    "noisy_sensor": 1.5,                 # Pa σ
    "slow_drift": 8.0,                   # K over the duration
    "multi_sensor_correlated": 3.0,      # Pa / K
}


def plan_injections(samples: pl.DataFrame, per_sol: float, seed: int, kinds: list[str] | None = None) -> list[Injection]:
    """Place injections at random times *where the target channels actually have data*."""
    rng = np.random.default_rng(seed)
    kinds = kinds or list(KINDS)
    sols = sorted(samples["sol"].unique().to_list())
    n = max(1, int(round(per_sol * len(sols))))
    out: list[Injection] = []
    for i in range(n):
        kind = kinds[i % len(kinds)]
        chans, etype, severity, dur = KINDS[kind]
        pool = samples.filter(pl.col("channel") == chans[0])
        if pool.is_empty():
            continue
        # sample a real timestamp of the primary channel, skip the first sol (baseline warm-up)
        pool = pool.filter(pl.col("sol") > sols[0]) if len(sols) > 1 else pool
        row = pool.row(int(rng.integers(0, len(pool))), named=True)
        out.append(Injection(
            id=f"INJ-{i:03d}-{kind}", kind=kind, channels=chans, t_start=row["t"], duration_s=dur,
            magnitude=DEFAULT_MAGNITUDE[kind], expected_type=etype.value, severity=severity,
        ))
    return out
