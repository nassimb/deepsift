"""End-to-end orchestration with stage instrumentation.

RAW → normalize → window → features → candidate filter → decision engine → gating
    → (deep analysis) → priority → storage/downlink scheduler

Stages are separable so that (a) changing the mission objective re-runs only `score` + `simulate`,
and (b) the benchmark can swap the decision stage for other strategies on identical inputs.
"""

from __future__ import annotations

import json
import statistics
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import polars as pl

from deepsift.adapters.base import MissionAdapter
from deepsift.adapters.curiosity import CuriosityAdapter
from deepsift.audit.log import AuditLog
from deepsift.core.config import DATA_DIR, PIPELINE_VERSION, Config
from deepsift.core.models import DownlinkAction, EngineDecision, GateStatus, ScientificEvent
from deepsift.decision.base import DecisionEngine
from deepsift.decision.deep import DeepAnalysisProvider, NoDeepAnalysis, make_provider
from deepsift.decision.gating import gate
from deepsift.decision.jev import JevDecisionEngine, jev_available
from deepsift.decision.mock import MockDecisionEngine
from deepsift.decision.state import build_state
from deepsift.features.detect import DetectionResult
from deepsift.features.novelty import assign_novelty
from deepsift.objectives.objective import MissionObjective, load_objectives
from deepsift.priority.engine import blend_deep, bytes_for, explain, rules_decision, score_event
from deepsift.simulation.scheduler import BACKGROUND_UTILITY, Blackout, Item, simulate

RUNS_DIR = DATA_DIR / "processed" / "runs"


def make_engine(cfg: Config) -> DecisionEngine:
    de = cfg.decision_engine
    if de.kind == "jev" or (de.kind == "auto" and jev_available()):
        if not jev_available():
            raise RuntimeError("decision_engine.kind=jev but TYPESAFE_API_KEY is not set")
        return JevDecisionEngine(model=de.jev_model, timeout_s=de.timeout_s, max_concurrency=de.max_concurrency,
                                 price_per_mtok_input_usd=de.price_per_mtok_input_usd)
    return MockDecisionEngine()


def effective_decision(e: ScientificEvent, cfg: Config) -> EngineDecision:
    """The decision actually used for scoring, derived deterministically from stored state."""
    if e.gate in (GateStatus.FALLBACK, GateStatus.ENGINE_ERROR) or e.decision is None:
        return rules_decision(e, cfg)
    if e.gate == GateStatus.ESCALATED:
        if e.deep is None or e.deep.error:
            return rules_decision(e, cfg)
        return blend_deep(e.decision, e.deep)
    return e.decision


@dataclass
class RunResult:
    run_id: str
    config: Config
    objective: MissionObjective
    events: list[ScientificEvent]
    detection: DetectionResult
    simulation: dict
    metadata: dict
    timings_ms: dict[str, float]
    performance: dict
    engine: dict
    deep_provider: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Pipeline:
    def __init__(self, cfg: Config, adapter: MissionAdapter | None = None, engine: DecisionEngine | None = None,
                 deep: DeepAnalysisProvider | None = None, audit: AuditLog | None = None):
        self.cfg = cfg
        self.adapter = adapter or CuriosityAdapter(window_s=cfg.detection.rems_window_s,
                                                   decimation=cfg.compression.decimation_factor,
                                                   zlib_level=cfg.compression.zlib_level)
        self.engine = engine or make_engine(cfg)
        self.deep = deep or make_provider(cfg.deep_analysis.provider, cfg.deep_analysis.model)
        self.audit = audit
        self.objectives = load_objectives()

    # ------------------------------------------------------------------ stages
    def detect(self, sols=None, injections=None) -> DetectionResult:
        t0 = time.perf_counter()
        self.adapter.load(sols)
        mission = self.adapter.normalize()
        t_norm = (time.perf_counter() - t0) * 1000
        from deepsift.features.detect import detect_events

        det = detect_events(mission, self.adapter, self.cfg, injections=injections)
        t1 = time.perf_counter()
        assign_novelty(det.events)
        det.timings_ms = {"normalize": t_norm, **det.timings_ms, "novelty": (time.perf_counter() - t1) * 1000}
        det.mission = mission  # type: ignore[attr-defined]
        return det

    def decide(self, events: list[ScientificEvent], metadata, objective: MissionObjective, windows: pl.DataFrame | None = None) -> dict:
        t0 = time.perf_counter()
        decisions = self.engine.decide(events, metadata.short_name, metadata.location,
                                       objective=objective.model_dump(mode="json")) if events else []
        t_engine = (time.perf_counter() - t0) * 1000
        deep_ms = []
        t1 = time.perf_counter()
        for e, d in zip(events, decisions):
            e.decision = d
            g0 = time.perf_counter()
            status, conf, reason = gate(d, self.cfg, self.deep.available)
            e.gate, e.gate_reason = status, reason
            gate_ms = (time.perf_counter() - g0) * 1000
            e.trace = [x for x in e.trace if x["stage"] not in ("decision_engine", "gating", "deep_analysis")]
            e.trace.append({"stage": "decision_engine", "ms": round(d.latency_ms, 4), "measured": True, "detail": d.engine})
            e.trace.append({"stage": "gating", "ms": round(gate_ms, 4), "measured": True, "detail": status.value})
            if status == GateStatus.ESCALATED:
                history = self._history(e, windows)
                e.deep = self.deep.analyze(build_state(e, metadata.short_name, metadata.location),
                                           {"mission": metadata.short_name, "location": metadata.location},
                                           objective.model_dump(mode="json"), history)
                deep_ms.append(e.deep.latency_ms)
                e.trace.append({"stage": "deep_analysis", "ms": round(e.deep.latency_ms, 3), "measured": True,
                                "detail": e.deep.provider + (f" error: {e.deep.error}" if e.deep.error else "")})
        return {"engine_ms": t_engine, "gating_and_deep_ms": (time.perf_counter() - t1) * 1000, "deep_ms": deep_ms,
                "decision_latencies": [d.latency_ms for d in decisions]}

    def score(self, events: list[ScientificEvent], objective: MissionObjective) -> float:
        t0 = time.perf_counter()
        for e in events:
            s0 = time.perf_counter()
            d = effective_decision(e, self.cfg)
            pb, action, notes = score_event(e, d, e.gate or GateStatus.FALLBACK, objective, self.cfg)
            e.priority, e.proposed_action = pb, action
            e.explanation = explain(e, pb, action, e.gate_reason or "", notes)
            e.trace = [x for x in e.trace if x["stage"] != "priority_engine"]
            e.trace.append({"stage": "priority_engine", "ms": round((time.perf_counter() - s0) * 1000, 4), "measured": True,
                            "detail": f"utility {pb.utility:.3f} → {action.value}"})
        return (time.perf_counter() - t0) * 1000

    def simulate(self, events: list[ScientificEvent], det: DetectionResult, blackout: Blackout | None = None) -> dict:
        t0 = time.perf_counter()
        iw = det.instrument_windows
        items = [
            Item(id=e.id, kind="event", arrival=e.sol_end, utility=e.priority.utility, action=e.proposed_action,
                 sizes={a.value: bytes_for(e, a) for a in DownlinkAction}, raw=e.bytes.raw,
                 cost_exponent=self.cfg.priority.cost_exponent)
            for e in events if e.priority and e.proposed_action
        ]
        if self.cfg.downlink.background_summary:
            bg = det.windows.filter(~pl.col("flagged")).group_by("instrument", "sol", "channel").agg(
                pl.col("mean").mean().round(3).alias("mean"), pl.col("min").min().round(3).alias("min"),
                pl.col("max").max().round(3).alias("max"), pl.col("n").sum().alias("n"))
            for (inst, sol), part in bg.group_by("instrument", "sol"):
                blob = json.dumps(part.drop("instrument", "sol").to_dicts(), separators=(",", ":"))
                raw = int(iw.filter((pl.col("instrument") == inst) & (pl.col("sol") == sol) & ~pl.col("flagged"))["raw"].sum() or 0)
                items.append(Item(id=f"BG-{inst}-{int(sol):04d}", kind="background", arrival=int(sol) + 0.999,
                                  utility=BACKGROUND_UTILITY, action=DownlinkAction.SUMMARY_ONLY,
                                  sizes={"full_data": len(blob), "compress": len(blob), "summary_only": len(blob), "discard": 0},
                                  raw=raw, cost_exponent=self.cfg.priority.cost_exponent))
        raw_timeline = [
            (int(r["sol"]) + (r["lmst_s"] or 0) / 86400, int(r["raw"] or 0)) for r in iw.select("sol", "lmst_s", "raw").iter_rows(named=True)
        ]
        sols = sorted(det.windows["sol"].unique().to_list())
        sim = simulate(items, raw_timeline, self.cfg, blackout=blackout, sol_range=(sols[0], sols[-1]))
        by_id = {i["id"]: i for i in sim["items"]}
        ms = (time.perf_counter() - t0) * 1000
        for e in events:
            it = by_id.get(e.id)
            if it:
                e.final_action = DownlinkAction(it["final"])
                e.downlink_bytes = it["sent"]
                e.status = it["state"]
                e.trace = [x for x in e.trace if x["stage"] != "scheduler"]
                e.trace.append({"stage": "scheduler", "ms": round(ms / max(len(items), 1), 4), "measured": False,
                                "detail": f"{it['proposed']} → {it['final']} ({it['state']})"})
        sim["wall_ms"] = ms
        return sim

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _history(e: ScientificEvent, windows: pl.DataFrame | None) -> list[dict]:
        if windows is None:
            return []
        h = windows.filter(pl.col("channel").is_in(e.sensors) & (pl.col("sol") >= e.sol - 3) & (pl.col("sol") <= e.sol))
        return h.select("channel", "sol", pl.col("lmst_mid").truediv(3600).round(2).alias("lmst_h"), pl.col("mean").round(3),
                        pl.col("baseline").round(3), pl.col("robust_z").round(2)).tail(40).to_dicts()

    def _amortize(self, events: list[ScientificEvent], det: DetectionResult) -> None:
        # batch stages are timed once; each event gets a share proportional to its raw bytes
        total_raw = max(int(det.instrument_windows["raw"].sum() or 0), 1)
        tm = det.timings_ms
        for e in events:
            share = e.bytes.raw / total_raw
            n_rows = sum(c.n for c in e.features.channels.values())
            e.trace = [
                {"stage": "raw_data", "ms": None, "measured": True,
                 "detail": f"{n_rows} channel samples, {e.bytes.raw:,} raw bytes from {', '.join(e.source.products)}"},
                {"stage": "normalize", "ms": round(tm.get("normalize", 0) * share, 4), "measured": False, "detail": "amortized by raw-byte share"},
                {"stage": "windowing", "ms": round(tm.get("windowing", 0) * share, 4), "measured": False, "detail": "amortized by raw-byte share"},
                {"stage": "feature_extraction", "ms": round(tm.get("feature_extraction", 0) * share, 4), "measured": False, "detail": "amortized by raw-byte share"},
                {"stage": "candidate_filter", "ms": round(tm.get("candidate_detection", 0) * share, 4), "measured": False,
                 "detail": "; ".join(e.features.trigger_reasons[:2])},
            ]

    # ------------------------------------------------------------------ full run
    def run(self, sols=None, injections=None, objective_id: str | None = None, blackout: Blackout | None = None,
            persist: bool = True, note: str = "") -> RunResult:
        objective = self.objectives[objective_id or self.cfg.objective]
        det = self.detect(sols, injections)
        md = det.mission.metadata  # type: ignore[attr-defined]
        self._amortize(det.events, det)
        dstats = self.decide(det.events, md, objective, det.windows)
        score_ms = self.score(det.events, objective)
        sim = self.simulate(det.events, det, blackout)

        timings = {**det.timings_ms, "decision_engine": dstats["engine_ms"], "gating_and_deep": dstats["gating_and_deep_ms"],
                   "priority": score_ms, "scheduler": sim["wall_ms"]}
        preprocessing = sum(det.timings_ms.get(k, 0) for k in ("normalize", "injection", "windowing", "feature_extraction", "candidate_detection", "novelty"))
        lat = dstats["decision_latencies"]
        perf = {
            "samples": det.counts["samples"],
            "rows_per_sec": det.counts["samples"] / (preprocessing / 1000) if preprocessing else None,
            "events": len(det.events),
            "events_per_sec": len(det.events) / ((dstats["engine_ms"] + dstats["gating_and_deep_ms"] + score_ms) / 1000) if det.events else None,
            "preprocessing_ms": preprocessing,
            "decision_latency_ms_mean": statistics.fmean(lat) if lat else None,
            "decision_latency_ms_p95": sorted(lat)[int(0.95 * (len(lat) - 1))] if lat else None,
            "deep_calls": len(dstats["deep_ms"]),
            "deep_latency_ms_mean": statistics.fmean(dstats["deep_ms"]) if dstats["deep_ms"] else None,
            "engine_cost_usd": sum(e.decision.cost_usd or 0 for e in det.events if e.decision) if self.engine.is_real_model else None,
            "measured_on": datetime.now(timezone.utc).isoformat(),
            "note": "wall-clock on this machine; the mock engine's latency is Python function time, not model inference",
        }
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]
        metadata = {
            "mission": md.id, "name": md.name, "short_name": md.short_name, "target": md.target, "location": md.location,
            "instruments": md.instruments, "channels": [c.__dict__ for c in md.channels], "citations": md.data_citations,
            "data_source": md.data_source.value, "sols": md.sols, "products": md.products,
            "counts": det.counts, "synthetic_injections": [i.to_dict() for i in (injections or [])],
            "pipeline_version": PIPELINE_VERSION, "config_version": self.cfg.version(),
        }
        result = RunResult(run_id=run_id, config=self.cfg, objective=objective, events=det.events, detection=det,
                           simulation=sim, metadata=metadata, timings_ms=timings, performance=perf,
                           engine=self.engine.describe(), deep_provider=self.deep.name)
        if persist:
            if self.audit:
                self.audit.record_config(self.cfg)
                self.audit.record_run(run_id, self.cfg, self.engine.name, self.deep.name, objective.id,
                                      md.data_source.value, md.sols, len(det.events), timings, note)
                self.audit.record_decisions(run_id, det.events, objective, self.cfg)
            save_run(result)
        return result


def save_run(r: RunResult) -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": r.run_id, "created_at": r.created_at, "config": r.config.model_dump(mode="json"),
        "objective": r.objective.model_dump(mode="json"), "metadata": r.metadata, "timings_ms": r.timings_ms,
        "performance": r.performance, "engine": r.engine, "deep_provider": r.deep_provider,
        "events": [e.model_dump(mode="json") for e in r.events],
        "simulation": {k: v for k, v in r.simulation.items()},
    }
    (RUNS_DIR / f"{r.run_id}.json").write_text(json.dumps(payload))
    (RUNS_DIR / "latest.txt").write_text(r.run_id)


def no_deep() -> DeepAnalysisProvider:
    return NoDeepAnalysis()
