"""Benchmark harness: identical data, identical byte budget, different triage strategies.

Strategies
  random       instrument windows in random order, FULL products, until the budget is spent
  rules        candidate events scored by the deterministic rules path (no decision engine)
  statistical  all instrument windows ranked by multivariate robust deviation, FULL products
  engine       candidate events → decision engine → gating → priority (no deep analysis)
  engine_deep  as `engine` with a DeepAnalysisProvider; reported UNAVAILABLE when none is configured

All strategies pass through the same greedy byte allocator: descending utility, degrading a
product one level at a time when it does not fit. Labels are never visible to any strategy.
"""

from __future__ import annotations

import math
import random
import statistics
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import polars as pl

from deepsift.core.config import DATA_DIR, PIPELINE_VERSION, Config
from deepsift.core.models import ACTION_RANK, RANK_ACTION, DownlinkAction, GateStatus
from deepsift.decision.deep import NoDeepAnalysis
from deepsift.evaluation.injection import plan_injections
from deepsift.evaluation.labels import SEVERITY_WEIGHT, Label, documented_labels, synthetic_labels
from deepsift.priority.engine import bytes_for, rules_decision, score_event

EXPERIMENTS_DIR = DATA_DIR / "processed" / "experiments"


@dataclass
class Unit:
    id: str
    instrument: str
    t0: datetime
    t1: datetime
    utility: float
    action: DownlinkAction
    sizes: dict[str, int]
    raw: int


def allocate(units: list[Unit], budget: int) -> list[tuple[Unit, DownlinkAction, int]]:
    """Greedy by utility; degrade until it fits; stop at DISCARD."""
    out, left = [], budget
    for u in sorted(units, key=lambda u: -u.utility):
        a = u.action
        while a != DownlinkAction.DISCARD and u.sizes[a.value] > left:
            a = RANK_ACTION[ACTION_RANK[a] - 1]
        size = u.sizes[a.value] if a != DownlinkAction.DISCARD else 0
        left -= size
        out.append((u, a, size))
    return out


def window_units(iw: pl.DataFrame, summary_bytes: int = 600) -> list[Unit]:
    return [
        Unit(id=f"{r['instrument']}:{r['window']}", instrument=r["instrument"], t0=r["t_start"], t1=r["t_end"], utility=0.0,
             action=DownlinkAction.FULL_DATA, raw=int(r["raw"] or 0),
             sizes={"full_data": int(r["full"] or 0), "compress": int(r["compressed"] or 0), "summary_only": summary_bytes, "discard": 0})
        for r in iw.iter_rows(named=True)
    ]


def event_units(events) -> list[Unit]:
    out = []
    for e in events:
        out.append(Unit(
            id=e.id, instrument=e.instrument, t0=datetime.fromisoformat(e.timestamp_start.replace("Z", "+00:00")),
            t1=datetime.fromisoformat(e.timestamp_end.replace("Z", "+00:00")), utility=e.priority.utility if e.priority else 0.0,
            action=e.proposed_action or DownlinkAction.DISCARD, raw=e.bytes.raw,
            sizes={a.value: bytes_for(e, a) for a in DownlinkAction},
        ))
    return out


def evaluate(selection, labels: list[Label], raw_total: int, fidelity: dict[str, float]) -> dict:
    kept = [(u, a, s) for u, a, s in selection if a != DownlinkAction.DISCARD]
    downlinked = sum(s for _, _, s in kept)
    rec: dict[str, dict] = {}
    covered_units = set()
    for lab in labels:
        best = 0.0
        best_action = None
        for u, a, _ in kept:
            if lab.instrument and u.instrument != lab.instrument:
                continue
            if u.t0 <= lab.t_end and u.t1 >= lab.t_start:
                covered_units.add(u.id)
                f = fidelity[a.value]
                if f > best:
                    best, best_action = f, a.value
        rec[lab.id] = {"source": lab.source.value, "severity": lab.severity, "recovered": best > 0,
                       "fidelity": best, "action": best_action, "expected_type": lab.expected_type}

    def recall(pred) -> float | None:
        xs = [r for r in rec.values() if pred(r)]
        return sum(r["recovered"] for r in xs) / len(xs) if xs else None

    value = sum(SEVERITY_WEIGHT.get(r["severity"], 1.0) * r["fidelity"] for r in rec.values())
    return {
        "labels": len(labels),
        "recall": recall(lambda r: True),
        "recall_high": recall(lambda r: r["severity"] == "high"),
        "recall_by_source": {src: recall(lambda r, s=src: r["source"] == s) for src in sorted({r["source"] for r in rec.values()})},
        "retained_units": len(kept),
        "retained_unlabeled_rate": (sum(1 for u, _, _ in kept if u.id not in covered_units) / len(kept)) if kept else None,
        "downlink_bytes": downlinked,
        "raw_bytes": raw_total,
        "data_reduction": 1 - downlinked / raw_total if raw_total else None,
        "labeled_value_recovered": value,
        "science_value_per_mb_proxy": value / (downlinked / 1e6) if downlinked else None,
        "actions": {a.value: sum(1 for _, x, _ in selection if x == a) for a in DownlinkAction},
        "per_label": rec,
    }


def run_benchmark(pipeline, cfg: Config, trials: int = 3, sols=None, strategies=None, human=None, save: bool = True) -> dict:
    """Run every strategy on `trials` injection seeds. Returns a JSON-serialisable result."""
    strategies = strategies or ["random", "rules", "statistical", "engine", "engine_deep"]
    started = datetime.now(timezone.utc)
    pipeline.adapter.load(sols)
    base_samples = pipeline.adapter.normalize().samples
    n_sols = base_samples["sol"].n_unique()
    budget = cfg.downlink.passes_per_sol * cfg.downlink.pass_bytes * n_sols
    fidelity = cfg.compression.fidelity
    objective = pipeline.objectives[cfg.objective]
    per_trial: list[dict] = []

    for k in range(trials):
        seed = cfg.benchmark.injection_seed + k
        injections = plan_injections(base_samples, cfg.benchmark.injections_per_sol, seed)
        labels = documented_labels() + synthetic_labels(injections) + (human or [])
        det = pipeline.detect(sols, injections)
        md = det.mission.metadata  # type: ignore[attr-defined]
        iw = det.instrument_windows
        raw_total = int(iw["raw"].sum() or 0)
        trial = {"seed": seed, "injections": [i.to_dict() for i in injections], "strategies": {}}

        for name in strategies:
            t0 = time.perf_counter()
            extra: dict = {"engine_calls": 0, "deep_calls": 0, "cost_usd": None}
            if name == "random":
                rng = random.Random(cfg.benchmark.random_seed + k)
                units = window_units(iw)
                for u in units:
                    u.utility = rng.random()
            elif name == "statistical":
                w = det.windows.with_columns((pl.col("robust_z") ** 2).alias("z2"))
                score = w.group_by("instrument", "window").agg(
                    (pl.col("z2").mean().sqrt() + pl.col("dip_sigma").fill_null(0).max() * 0.25).alias("s"))
                smap = {f"{a}:{b}": s for a, b, s in score.iter_rows()}
                units = window_units(iw)
                for u in units:
                    u.utility = 1 - math.exp(-smap.get(u.id, 0.0) / cfg.priority.anomaly_scale)
            elif name == "rules":
                events = [e.model_copy(deep=True) for e in det.events]
                for e in events:
                    e.gate = GateStatus.FALLBACK
                    pb, act, _ = score_event(e, rules_decision(e, cfg), GateStatus.FALLBACK, objective, cfg)
                    e.priority, e.proposed_action = pb, act
                units = event_units(events)
            elif name in ("engine", "engine_deep"):
                if name == "engine_deep" and not pipeline.deep.available:
                    trial["strategies"][name] = {"available": False,
                                                 "reason": "no DeepAnalysisProvider configured (set deep_analysis.provider=claude and ANTHROPIC_API_KEY)"}
                    continue
                events = [e.model_copy(deep=True) for e in det.events]
                saved = pipeline.deep
                if name == "engine":
                    pipeline.deep = NoDeepAnalysis()
                try:
                    stats = pipeline.decide(events, md, objective, det.windows)
                finally:
                    pipeline.deep = saved
                pipeline.score(events, objective)
                units = event_units(events)
                extra = {
                    "engine_calls": len(events),
                    "deep_calls": len(stats["deep_ms"]),
                    "cost_usd": sum(e.decision.cost_usd or 0 for e in events if e.decision) if pipeline.engine.is_real_model else None,
                    "engine_latency_ms_mean": statistics.fmean(stats["decision_latencies"]) if stats["decision_latencies"] else None,
                    "gates": {g.value: sum(1 for e in events if e.gate == g) for g in GateStatus},
                }
            else:
                continue
            selection = allocate(units, budget)
            wall = (time.perf_counter() - t0) * 1000
            m = evaluate(selection, labels, raw_total, fidelity)
            m.update(extra)
            m["available"] = True
            m["units_considered"] = len(units)
            m["strategy_wall_ms"] = wall
            m["expensive_fraction"] = (extra["deep_calls"] / len(units)) if units else 0.0
            trial["strategies"][name] = m
        trial["labels"] = [lab.model_dump(mode="json") for lab in labels]
        per_trial.append(trial)

    summary = {}
    for name in strategies:
        rows = [t["strategies"].get(name) for t in per_trial]
        rows = [r for r in rows if r and r.get("available")]
        if not rows:
            summary[name] = {"available": False, "reason": per_trial[0]["strategies"].get(name, {}).get("reason", "not run")}
            continue
        agg = {"available": True}
        for key in ("recall", "recall_high", "retained_unlabeled_rate", "downlink_bytes", "data_reduction",
                    "science_value_per_mb_proxy", "strategy_wall_ms", "deep_calls", "engine_calls", "expensive_fraction", "units_considered"):
            vals = [r[key] for r in rows if r.get(key) is not None]
            agg[key] = {"mean": statistics.fmean(vals), "std": statistics.pstdev(vals) if len(vals) > 1 else 0.0, "n": len(vals)} if vals else None
        sources = sorted({s for r in rows for s in r["recall_by_source"]})
        agg["recall_by_source"] = {
            s: statistics.fmean([r["recall_by_source"][s] for r in rows if r["recall_by_source"].get(s) is not None])
            for s in sources if any(r["recall_by_source"].get(s) is not None for r in rows)
        }
        costs = [r["cost_usd"] for r in rows if r.get("cost_usd") is not None]
        agg["cost_usd"] = statistics.fmean(costs) if costs else None
        summary[name] = agg

    result = {
        "id": started.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6],
        "created_at": started.isoformat(),
        "pipeline_version": PIPELINE_VERSION,
        "config_version": cfg.version(),
        "config": cfg.model_dump(mode="json"),
        "objective": objective.id,
        "engine": pipeline.engine.describe(),
        "deep_provider": pipeline.deep.name,
        "data_source": pipeline.adapter.metadata().data_source.value,
        "sols": pipeline.adapter.metadata().sols,
        "trials": trials,
        "budget_bytes": budget,
        "summary": summary,
        "per_trial": per_trial,
        "caveats": [
            "Recall is measured against synthetic injections plus one documented event; unlabeled real phenomena exist, "
            "so 'retained_unlabeled_rate' is an upper bound on the false-positive rate, not the rate itself.",
            "science_value_per_mb_proxy = Σ(severity weight × assumed product fidelity) / downlinked MB. It is a proxy; "
            "it does not measure true scientific value.",
            "When the engine is 'mock-heuristic-v1' the 'engine' rows describe a hand-written heuristic, not Jev. "
            "The heuristic and the injection generator were written by the same authors.",
            "Byte costs are zlib sizes of PDS ASCII records; flight encodings would differ.",
        ],
    }
    if save:
        import json

        EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
        (EXPERIMENTS_DIR / f"{result['id']}.json").write_text(json.dumps(result, default=str))
    return result
