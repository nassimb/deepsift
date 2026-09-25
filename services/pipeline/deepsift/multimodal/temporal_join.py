"""M5 — TELEMETRY CONTEXT for each image acquisition (never called co-measurement: alignment is minutes-level).

Uses the frozen Phase 2 pipeline unchanged (config/phase2.yaml detector + rules scoring) on the segment containing the
acquisitions, and the telemetry already on disk. Declared: context window ±TELEMETRY_CONTEXT_S around the image time.
  rems_gap_s / rad_gap_s   time to the nearest REMS pressure sample / RAD observation start
  context_events           Phase 2 candidate events whose [start − window, end + window] contains the image time
  telemetry_score          max frozen RULES utility among context events (0 if none) — used by TELEMETRY PRIORITY
"""

from __future__ import annotations

import bisect
from datetime import datetime, timedelta, timezone

from deepsift.core.config import ROOT, load_config
from deepsift.evaluation.segments import eval_filter_events, load_segment, segments
from deepsift.evaluation.strategies import rules_strategy
from deepsift.features.detect import detect_events
from deepsift.features.novelty import assign_novelty
from deepsift.objectives.objective import load_objectives

TELEMETRY_CONTEXT_S = 1800


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


class TelemetryContext:
    def __init__(self, sol_range: tuple[int, int], split: str = "validation"):
        cfg = load_config(ROOT / "config" / "phase2.yaml")
        seg = next(s for s in segments(split) if s.eval[0] <= sol_range[0] and s.eval[1] >= sol_range[1])
        sd = load_segment(seg, cfg.detection.rems_window_s, cfg.compression.decimation_factor, cfg.compression.zlib_level)
        det = detect_events(sd.mission, sd.adapter, cfg)
        assign_novelty(det.events)
        self.events = eval_filter_events(det.events, sd)
        obj = load_objectives()[cfg.objective]
        self.utility = {k: v["utility"] for k, v in rules_strategy(self.events, obj, cfg).decisions.items()}
        smp = sd.mission.samples
        self.rems = sorted(t.timestamp() for t in smp.filter((smp["instrument"] == "REMS") & (smp["channel"] == "pressure"))["t"].to_list())
        self.rad = sorted({t.timestamp() for t in smp.filter(smp["instrument"] == "RAD")["t"].to_list()})
        self.segment_id = seg.id
        self.config_version = cfg.version()

    @staticmethod
    def _nearest(arr, v):
        i = bisect.bisect_left(arr, v)
        c = [abs(arr[j] - v) for j in (i - 1, i) if 0 <= j < len(arr)]
        return min(c) if c else None

    def context(self, utc: str) -> dict:
        t = datetime.fromisoformat(utc.replace("Z", "")).replace(tzinfo=timezone.utc)
        w = timedelta(seconds=TELEMETRY_CONTEXT_S)
        ctx = [e for e in self.events if _ts(e.timestamp_start) - w <= t <= _ts(e.timestamp_end) + w]
        gaps = [0.0 if _ts(e.timestamp_start) <= t <= _ts(e.timestamp_end)
                else min(abs((t - _ts(e.timestamp_start)).total_seconds()), abs((t - _ts(e.timestamp_end)).total_seconds()))
                for e in ctx]
        best = max(ctx, key=lambda e: self.utility.get(e.id, 0.0)) if ctx else None
        return {"rems_gap_s": self._nearest(self.rems, t.timestamp()), "rad_gap_s": self._nearest(self.rad, t.timestamp()),
                "context_events": [e.id for e in ctx], "context_event_gap_s": min(gaps) if gaps else None,
                "context_instruments": sorted({e.instrument for e in ctx}),
                "telemetry_score": self.utility.get(best.id, 0.0) if best else 0.0, "top_context_event": best.id if best else None,
                "label": "TELEMETRY CONTEXT (minutes-level alignment; not co-measurement)"}
