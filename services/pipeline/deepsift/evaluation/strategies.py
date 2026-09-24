"""Phase-2 triage strategies. Each returns Units for the common byte allocator.

STRATEGIES (display names are neutral — no "winner"):
  RANDOM                  instrument windows, random order, FULL products (seeded; run over many seeds)
  STATISTICAL             instrument windows ranked by RMS robust z (+ dip term), FULL products
  RULES                   candidate events, deterministic rule decision → priority engine
  RULES_PLUS_STATISTICAL  RULES first; leftover budget to STATISTICAL windows outside candidate events
  LOCAL_EDGE              candidate events scored by a small local logistic model (no network)
  ENGINE_ONLY             engine answers used for every event (no confidence fallback)
  RULES_PLUS_ENGINE       engine answers gated by confidence; low confidence → rules (the v0.1 pipeline)
  ENGINE_SINGLE_DECISION  utility = P(retain) from one yes/no question (Jev ablation)
  ENGINE_PLUS_DEEP        RULES_PLUS_ENGINE with deep escalation — UNAVAILABLE unless a provider is enabled
  ORACLE                  knows the labels; value-per-byte optimal window selection — NOT DEPLOYABLE
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import polars as pl

from deepsift.core.models import DownlinkAction, EngineDecision, GateStatus, ScientificEvent
from deepsift.decision.gating import gate
from deepsift.evaluation.benchmark import Unit, event_units, window_units
from deepsift.evaluation.labels import SEVERITY_WEIGHT, Label
from deepsift.priority.engine import bytes_for, rules_decision, score_event, threshold_action

ORACLE_LABEL = "ORACLE — NOT DEPLOYABLE"


@dataclass
class StrategyOutput:
    name: str
    units: list[Unit]
    available: bool = True
    reason: str | None = None
    per_unit_latency_ms: list[float] = field(default_factory=list)
    engine_calls: int = 0
    deep_calls: int = 0
    cost_usd: float | None = None
    decisions: dict[str, dict] = field(default_factory=dict)   # event_id -> small decision summary (failure analysis)


def unavailable(name: str, reason: str) -> StrategyOutput:
    return StrategyOutput(name=name, units=[], available=False, reason=reason)


def random_strategy(iw: pl.DataFrame, seed: int) -> StrategyOutput:
    rng = random.Random(seed)
    units = window_units(iw)
    for u in units:
        u.utility = rng.random()
    return StrategyOutput("RANDOM", units)


def statistical_scores(windows: pl.DataFrame) -> dict[str, float]:
    w = windows.with_columns((pl.col("robust_z") ** 2).alias("z2"))
    score = w.group_by("instrument", "window").agg((pl.col("z2").mean().sqrt() + pl.col("dip_sigma").fill_null(0).max() * 0.25).alias("s"))
    return {f"{a}:{b}": s for a, b, s in score.iter_rows()}


def statistical_strategy(iw: pl.DataFrame, windows: pl.DataFrame, scale: float) -> StrategyOutput:
    t0 = time.perf_counter()
    smap = statistical_scores(windows)
    units = window_units(iw)
    for u in units:
        u.utility = 1 - math.exp(-smap.get(u.id, 0.0) / scale)
    lat = (time.perf_counter() - t0) * 1000 / max(len(units), 1)
    return StrategyOutput("STATISTICAL", units, per_unit_latency_ms=[lat] * len(units))


def rules_strategy(events: list[ScientificEvent], objective, cfg) -> StrategyOutput:
    out = []
    lat = []
    decisions = {}
    for e in events:
        t0 = time.perf_counter()
        ev = e.model_copy(deep=True)
        d = rules_decision(ev, cfg)
        pb, act, _ = score_event(ev, d, GateStatus.FALLBACK, objective, cfg)
        ev.priority, ev.proposed_action = pb, act
        lat.append((time.perf_counter() - t0) * 1000)
        out.append(ev)
        decisions[e.id] = {"type": d.answers["event_type"].choice, "science": d.answers["science_value"].choice,
                           "utility": pb.utility, "action": act.value}
    return StrategyOutput("RULES", event_units(out), per_unit_latency_ms=lat, decisions=decisions)


def rules_plus_statistical(events, iw, windows, objective, cfg) -> StrategyOutput:
    r = rules_strategy(events, objective, cfg)
    s = statistical_strategy(iw, windows, cfg.priority.anomaly_scale)
    spans = [(u.instrument, u.t0, u.t1) for u in r.units]
    for u in r.units:
        u.utility += 1.0                                  # rules' selections are allocated first
    extra = [u for u in s.units if not any(i == u.instrument and a <= u.t1 and b >= u.t0 for i, a, b in spans)]
    return StrategyOutput("RULES_PLUS_STATISTICAL", r.units + extra,
                          per_unit_latency_ms=r.per_unit_latency_ms + s.per_unit_latency_ms[: len(extra)],
                          decisions=r.decisions)


def local_edge_strategy(events, model, cfg) -> StrategyOutput:
    out, lat, decisions = [], [], {}
    for e in events:
        t0 = time.perf_counter()
        p = model.predict_proba_event(e)
        act = threshold_action(p, cfg)
        lat.append((time.perf_counter() - t0) * 1000)
        ev = e.model_copy(deep=True)
        ev.proposed_action = act
        u = event_units([ev])[0]
        u.utility = p
        out.append(u)
        decisions[e.id] = {"p_important": p, "action": act.value}
    return StrategyOutput("LOCAL_EDGE", out, per_unit_latency_ms=lat, decisions=decisions)


def engine_strategies(events, decisions: list[EngineDecision], objective, cfg, engine_name: str,
                      single_decision: bool = False) -> list[StrategyOutput]:
    """Derive ENGINE_ONLY and RULES_PLUS_ENGINE from ONE set of engine answers (no duplicate calls)."""
    lat = [d.latency_ms for d in decisions]
    calls = len(decisions)
    cost = sum(d.cost_usd or 0 for d in decisions) if any(d.cost_usd for d in decisions) else None
    if single_decision:
        units, dec = [], {}
        for e, d in zip(events, decisions):
            p = d.answers["retain"].noul if (not d.error and "retain" in d.answers) else None
            ev = e.model_copy(deep=True)
            if p is None:                                 # engine error → rules
                rd = rules_decision(ev, cfg)
                pb, act, _ = score_event(ev, rd, GateStatus.ENGINE_ERROR, objective, cfg)
                p, ev.proposed_action = pb.utility, act
            else:
                ev.proposed_action = threshold_action(p, cfg)
            u = event_units([ev])[0]
            u.utility = p
            units.append(u)
            dec[e.id] = {"p_retain": p, "action": ev.proposed_action.value, "error": d.error}
        return [StrategyOutput("ENGINE_SINGLE_DECISION", units, per_unit_latency_ms=lat, engine_calls=calls, cost_usd=cost, decisions=dec)]

    only, gated = [], []
    dec_only, dec_gated = {}, {}
    for e, d in zip(events, decisions):
        eo = e.model_copy(deep=True)
        if d.error or not d.answers:
            dd, gs = rules_decision(eo, cfg), GateStatus.ENGINE_ERROR
        else:
            dd, gs = d, GateStatus.AUTO
        pb, act, _ = score_event(eo, dd, gs, objective, cfg)
        eo.priority, eo.proposed_action = pb, act
        only.append(eo)
        et = d.answers.get("event_type") if d.answers else None
        sv = d.answers.get("science_value") if d.answers else None
        dec_only[e.id] = {"type": et.choice if et else None, "type_conf": et.confidence if et else None,
                          "science": sv.choice if sv else None, "science_conf": sv.confidence if sv else None,
                          "utility": pb.utility, "action": act.value, "error": d.error}

        eg = e.model_copy(deep=True)
        status, conf, _ = gate(d, cfg, deep_available=False)
        eff = rules_decision(eg, cfg) if status in (GateStatus.FALLBACK, GateStatus.ENGINE_ERROR) else d
        pb2, act2, _ = score_event(eg, eff, status, objective, cfg)
        eg.priority, eg.proposed_action, eg.gate = pb2, act2, status
        gated.append(eg)
        dec_gated[e.id] = {**dec_only[e.id], "gate": status.value, "confidence": conf, "utility": pb2.utility, "action": act2.value}
    return [
        StrategyOutput("ENGINE_ONLY", event_units(only), per_unit_latency_ms=lat, engine_calls=calls, cost_usd=cost, decisions=dec_only),
        StrategyOutput("RULES_PLUS_ENGINE", event_units(gated), per_unit_latency_ms=lat, engine_calls=calls, cost_usd=cost, decisions=dec_gated),
    ]


def oracle_strategy(iw: pl.DataFrame, labels: list[Label], tolerance: dict[str, tuple[float, float]]) -> StrategyOutput:
    """Upper bound with label knowledge. Tier 1: the cheapest window touching each label (maximises the
    number of labels recovered). Tier 2: remaining label windows by severity-value per byte (coverage)."""
    units = window_units(iw)
    touching: dict[str, list] = {}
    for u in units:
        v = 0.0
        for lab in labels:
            if lab.instrument and lab.instrument != u.instrument:
                continue
            b, a = tolerance.get(lab.id, (0.0, 0.0))
            if u.t0 <= lab.t_end + timedelta(seconds=a) and u.t1 >= lab.t_start - timedelta(seconds=b):
                v = max(v, SEVERITY_WEIGHT.get(lab.severity, 1.0))
                touching.setdefault(lab.id, []).append(u)
        u.utility = v / max(u.sizes["full_data"], 1) * 1e6 if v else 0.0
        if not v:
            u.action = DownlinkAction.DISCARD
    for lab in labels:                                   # tier 1 (high severity first)
        cand = touching.get(lab.id)
        if cand:
            cheapest = min(cand, key=lambda u: u.sizes["full_data"])
            cheapest.utility = max(cheapest.utility, 1e12 + SEVERITY_WEIGHT.get(lab.severity, 1.0) * 1e9 - cheapest.sizes["full_data"])
    return StrategyOutput(ORACLE_LABEL, units)


def event_time(e: ScientificEvent) -> tuple[datetime, datetime]:
    return (datetime.fromisoformat(e.timestamp_start.replace("Z", "+00:00")),
            datetime.fromisoformat(e.timestamp_end.replace("Z", "+00:00")))


__all__ = [
    "StrategyOutput", "unavailable", "random_strategy", "statistical_strategy", "rules_strategy", "rules_plus_statistical",
    "local_edge_strategy", "engine_strategies", "oracle_strategy", "ORACLE_LABEL", "bytes_for",
]
