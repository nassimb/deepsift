"""Split / segment handling for Phase-2 evaluation.

A segment = contiguous sols. The warm-up block is loaded (so trailing baselines exist at the first
scored sol) but nothing in it is ever scored: no units, no labels, no bytes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import polars as pl

from deepsift.adapters.base import LoadedMission
from deepsift.adapters.curiosity import CuriosityAdapter
from deepsift.core.config import DATA_DIR
from deepsift.evaluation.labels import Label
from deepsift.core.models import LabelSource

SPLITS_PATH = DATA_DIR / "splits" / "splits.json"
GROUND_TRUTH = DATA_DIR / "ground_truth" / "documented_events.json"
CACHE = DATA_DIR / "processed" / "cache"


@dataclass(frozen=True)
class Segment:
    id: str
    split: str
    warmup: tuple[int, int] | None
    eval: tuple[int, int]

    @property
    def load_sols(self) -> list[int]:
        lo = self.warmup[0] if self.warmup else self.eval[0]
        return list(range(lo, self.eval[1] + 1))


def load_splits() -> dict:
    return json.loads(SPLITS_PATH.read_text())


def segments(split: str) -> list[Segment]:
    spec = load_splits()["splits"][split]
    return [Segment(s["id"], split, tuple(s["warmup"]) if s.get("warmup") else None, tuple(s["eval"])) for s in spec["segments"]]


def pds_gaps() -> dict[str, list[int]]:
    g = load_splits().get("pds_gaps", {})
    return {"REMS": g.get("REMS", []), "RAD": g.get("RAD", [])}


@dataclass
class SegmentData:
    segment: Segment
    adapter: CuriosityAdapter
    mission: LoadedMission
    eval_t0: datetime
    eval_t1: datetime
    labels: list[Label] = field(default_factory=list)
    label_meta: dict[str, dict] = field(default_factory=dict)


def _sol_bounds_utc(samples: pl.DataFrame, s0: int, s1: int) -> tuple[datetime, datetime]:
    """UTC bounds of sols [s0, s1] from the data's own sol/UTC relation (REMS clock)."""
    r = samples.filter((pl.col("instrument") == "REMS") & (pl.col("channel") == "pressure"))
    import numpy as np

    x = r["t"].dt.epoch("ms").to_numpy() / 1000.0
    y = r["sol"].to_numpy() + r["lmst_s"].to_numpy() / 86400.0
    slope, icpt = np.polyfit(y - y.mean(), x, 1)
    to_t = lambda sol: datetime.fromtimestamp(float(icpt + slope * (sol - y.mean())), tz=timezone.utc)  # noqa: E731
    return to_t(s0), to_t(s1 + 1)


@lru_cache(maxsize=8)
def load_segment(seg: Segment, window_s: int = 300, decimation: int = 8, zlib_level: int = 6) -> SegmentData:
    a = CuriosityAdapter(window_s=window_s, decimation=decimation, zlib_level=zlib_level)
    a.load(seg.load_sols)
    m = a.normalize()
    t0, t1 = _sol_bounds_utc(m.samples, seg.eval[0], seg.eval[1])
    sd = SegmentData(seg, a, m, t0, t1)
    sd.labels, sd.label_meta = documented_labels_for(t0, t1, seg)
    return sd


def documented_labels_for(t0: datetime, t1: datetime, seg: Segment) -> tuple[list[Label], dict[str, dict]]:
    doc = json.loads(GROUND_TRUTH.read_text())
    gaps = pds_gaps()
    labels, meta = [], {}
    for e in doc["events"]:
        s = datetime.fromisoformat(e["start_time"].replace("Z", "+00:00"))
        en = datetime.fromisoformat(e["end_time"].replace("Z", "+00:00"))
        if en < t0 or s > t1:
            continue
        # sol-242 development event is only ever used inside the calibration split
        if e["event_id"] == "SEP-2013-04-SOL242" and seg.split != "calibration":
            continue
        inst = e["affected_instruments"][0]
        tu = e.get("time_uncertainty") or {}
        labels.append(Label(
            id=e["event_id"], source=LabelSource.DOCUMENTED_EVENT, instrument=inst, t_start=s, t_end=en,
            expected_type=e["event_type"], severity=e["severity"], description=e.get("notes", ""),
            reference=e.get("citation"), status=e["confidence_in_time_bounds"],
        ))
        meta[e["event_id"]] = {
            "subtype": e.get("event_subtype"), "tolerance_before_s": tu.get("start_days", 0) * 86400,
            "tolerance_after_s": tu.get("end_days", 0) * 86400, "confidence": e["confidence_in_time_bounds"],
            "gap_sols": gaps.get(inst, []), "magnitude": e.get("magnitude", {}), "source": e["source"],
            "partially_outside_segment": s < t0 or en > t1,
        }
    return labels, meta


def eval_filter_events(events, sd: SegmentData):
    return [e for e in events if sd.segment.eval[0] <= e.sol <= sd.segment.eval[1]]


def eval_windows(iw: pl.DataFrame, sd: SegmentData) -> pl.DataFrame:
    return iw.filter((pl.col("sol") >= sd.segment.eval[0]) & (pl.col("sol") <= sd.segment.eval[1]))


def utc(t: datetime | str) -> datetime:
    if isinstance(t, str):
        return datetime.fromisoformat(t.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def pad(t: datetime, s: float) -> datetime:
    return t + timedelta(seconds=s)
