"""Deterministic priority engine — application code owns every final action.

    utility = confidence_penalty × Σ_k w_k · term_k          (terms and weights in [0, 1])
      terms:  science_value      E[value] under the engine's science_value distribution
              mission_relevance  objective.relevance(P(event_type), flagged channels)
              anomaly_strength   1 − exp(−deviation_score / anomaly_scale)
              novelty            1 − max cosine similarity to earlier events
      confidence_penalty = 1 − λ·(1 − confidence)
    action  = threshold(utility) → then rule floors (uncertain gate, instrument-failure floor)
              → optional one-level upgrade when the engine confidently recommends more
    density = utility / (bytes of the proposed product in KB)^β   (used by the scheduler)

Everything here is a pure function of (event features, decision, objective, config), so any
past decision can be recomputed exactly from the audit log.
"""

from __future__ import annotations

import math

from deepsift.core.models import (
    ACTION_RANK,
    RANK_ACTION,
    SCIENCE_VALUE_NUMERIC,
    AnswerDist,
    DownlinkAction,
    EngineDecision,
    EventType,
    GateStatus,
    PriorityBreakdown,
    ScienceValue,
    ScientificEvent,
)
from deepsift.objectives.objective import MissionObjective

TERMS = ("science_value", "mission_relevance", "anomaly_strength", "novelty")
QUALITY_KEYS = ("flat_fraction", "missing_fraction", "noise_ratio")


def anomaly_strength(deviation: float, scale: float) -> float:
    return 1 - math.exp(-max(deviation, 0.0) / scale)


def rules_type(e: ScientificEvent) -> str:
    """Deterministic event-type guess used by the rules baseline and by fallback gating."""
    ch = {k: c for k, c in e.features.channels.items() if k in e.sensors}  # only channels that triggered
    if any(c.flat_fraction >= 0.95 or c.missing_fraction >= 0.5 or c.noise_ratio >= 4 for c in ch.values()):
        return EventType.INSTRUMENT_ANOMALY.value
    if e.instrument == "RAD":
        return EventType.RADIATION.value
    atm = {"pressure", "uv_abc", "rel_humidity"} & set(e.sensors)
    th = {"air_temp", "ground_temp"} & set(e.sensors)
    if atm and len(atm) >= len(th):
        return EventType.ATMOSPHERIC.value
    if th:
        return EventType.THERMAL.value
    return EventType.UNKNOWN.value


def rules_decision(e: ScientificEvent, cfg) -> EngineDecision:
    """One-hot 'decision' from deterministic rules (used for FALLBACK / ENGINE_ERROR and the rules strategy)."""
    s = anomaly_strength(e.features.deviation_score, cfg.priority.anomaly_scale)
    level = ScienceValue.CRITICAL if s > 0.9 else ScienceValue.HIGH if s > 0.7 else ScienceValue.MEDIUM if s > 0.45 else ScienceValue.LOW
    t = rules_type(e)
    one = lambda keys, k: {x: (1.0 if x == k else 0.0) for x in keys}  # noqa: E731
    return EngineDecision(
        engine="deterministic-rules-v1",
        answers={
            "science_value": AnswerDist(kind="choice", choice=level.value, confidence=1.0,
                                        probabilities=one([v.value for v in ScienceValue], level.value)),
            "event_type": AnswerDist(kind="choice", choice=t, confidence=1.0,
                                     probabilities=one([v.value for v in EventType], t)),
            "instrument_failure": AnswerDist(kind="choice", choice="yes" if t == "instrument_anomaly" else "no", confidence=1.0,
                                             probabilities=one(["yes", "no", "uncertain"], "yes" if t == "instrument_anomaly" else "no")),
        },
    )


def blend_deep(d: EngineDecision, deep, weight: float = 0.5) -> EngineDecision:
    """Mix a deep-analysis verdict into the engine distributions (weight = deep share)."""
    if deep is None or deep.error:
        return d
    answers = dict(d.answers)
    for q, val in (("science_value", deep.science_value), ("event_type", deep.event_type), ("instrument_failure", deep.instrument_failure)):
        if val is None or q not in answers:
            continue
        a = answers[q]
        probs = {k: (1 - weight) * p + (weight if k == val.value else 0.0) for k, p in a.probabilities.items()}
        top = max(probs, key=probs.get)
        answers[q] = AnswerDist(kind="choice", choice=top, confidence=probs[top], probabilities=probs)
    return d.model_copy(update={"answers": answers})


def effective_weights(cfg, objective: MissionObjective) -> dict[str, float]:
    w = dict(objective.priority_weights or cfg.priority.weights)
    total = sum(w.get(k, 0.0) for k in TERMS) or 1.0
    return {k: w.get(k, 0.0) / total for k in TERMS}


def terms_for(e: ScientificEvent, d: EngineDecision, objective: MissionObjective, cfg) -> tuple[dict[str, float], float, str]:
    sv = d.answers.get("science_value")
    science = sum(SCIENCE_VALUE_NUMERIC[ScienceValue(k)] * p for k, p in (sv.probabilities if sv else {}).items() if k in ScienceValue._value2member_map_)
    et = d.answers.get("event_type")
    rel, rel_rule = objective.relevance(et.probabilities if et else {}, e.sensors)
    terms = {
        "science_value": science,
        "mission_relevance": rel,
        "anomaly_strength": anomaly_strength(e.features.deviation_score, cfg.priority.anomaly_scale),
        "novelty": e.features.novelty,
    }
    confs = [a.confidence for k, a in d.answers.items() if k in ("science_value", "event_type") and a.confidence is not None]
    return terms, (min(confs) if confs else 1.0), rel_rule


def utility_from(terms: dict[str, float], confidence: float, weights: dict[str, float], lam: float) -> tuple[float, float, dict[str, float]]:
    contributions = {k: weights[k] * terms[k] for k in TERMS}
    penalty = 1 - lam * (1 - confidence)
    return penalty * sum(contributions.values()), penalty, contributions


def threshold_action(u: float, cfg) -> DownlinkAction:
    t = cfg.priority.thresholds
    if u >= t.full_data:
        return DownlinkAction.FULL_DATA
    if u >= t.compress:
        return DownlinkAction.COMPRESS
    if u >= t.summary_only:
        return DownlinkAction.SUMMARY_ONLY
    return DownlinkAction.DISCARD


def bytes_for(e: ScientificEvent, action: DownlinkAction) -> int:
    return {
        DownlinkAction.FULL_DATA: e.bytes.full,
        DownlinkAction.COMPRESS: e.bytes.compressed,
        DownlinkAction.SUMMARY_ONLY: e.bytes.summary,
        DownlinkAction.DISCARD: 0,
    }[action]


def decide_action(u: float, d: EngineDecision, gate_status: GateStatus, cfg) -> tuple[DownlinkAction, list[str]]:
    """Threshold → floors → engine upgrade. Returns (action, deterministic reasons)."""
    t = cfg.priority.thresholds
    action = threshold_action(u, cfg)
    notes = [f"utility {u:.3f} → {action.value.upper()} (thresholds full {t.full_data}, compress {t.compress}, summary {t.summary_only})"]
    if gate_status == GateStatus.UNCERTAIN and ACTION_RANK[action] < ACTION_RANK[DownlinkAction.SUMMARY_ONLY]:
        action = DownlinkAction.SUMMARY_ONLY
        notes.append("uncertain gate: floor raised to SUMMARY_ONLY (uncertain events are never silently discarded)")
    fail = d.answers.get("instrument_failure")
    p_fail = fail.probabilities.get("yes", 0.0) if fail else 0.0
    if p_fail >= cfg.priority.instrument_failure_floor and ACTION_RANK[action] < ACTION_RANK[DownlinkAction.SUMMARY_ONLY]:
        action = DownlinkAction.SUMMARY_ONLY
        notes.append(f"engineering safety: P(instrument failure)={p_fail:.2f} ≥ {cfg.priority.instrument_failure_floor} → at least SUMMARY_ONLY")
    rec = d.answers.get("downlink_action")
    if (
        cfg.priority.engine_action_policy == "upgrade_only" and rec and rec.choice in ACTION_RANK
        and gate_status == GateStatus.AUTO and (rec.confidence or 0) >= cfg.gating.auto_threshold
        and ACTION_RANK[DownlinkAction(rec.choice)] > ACTION_RANK[action]
    ):
        new = RANK_ACTION[ACTION_RANK[action] + 1]
        notes.append(f"engine recommended {rec.choice.upper()} at confidence {rec.confidence:.2f}; policy upgrade_only raised {action.value.upper()} → {new.value.upper()}")
        action = new
    return action, notes


def score_event(e: ScientificEvent, d: EngineDecision, gate_status: GateStatus, objective: MissionObjective, cfg):
    """Return (PriorityBreakdown, proposed action, explanation lines)."""
    weights = effective_weights(cfg, objective)
    terms, conf, rel_rule = terms_for(e, d, objective, cfg)
    if gate_status in (GateStatus.FALLBACK, GateStatus.ENGINE_ERROR):
        conf = 1.0  # rules are deterministic; no model confidence to penalise
    u, penalty, contributions = utility_from(terms, conf, weights, cfg.priority.confidence_penalty)
    action, notes = decide_action(u, d, gate_status, cfg)
    kb = max(bytes_for(e, action), 1) / 1024
    density = u / (kb ** cfg.priority.cost_exponent)
    pb = PriorityBreakdown(
        science_value=terms["science_value"], mission_relevance=terms["mission_relevance"],
        anomaly_strength=terms["anomaly_strength"], novelty=terms["novelty"], confidence=conf,
        weights=weights, contributions=contributions, utility=u, confidence_penalty=penalty, density=density,
    )
    notes.insert(0, f"mission relevance {terms['mission_relevance']:.2f} via {rel_rule} (objective: {objective.name})")
    return pb, action, notes


def explain(e: ScientificEvent, pb: PriorityBreakdown, action: DownlinkAction, gate_reason: str, notes: list[str]) -> list[str]:
    """'Why was this selected?' — assembled only from features, config and decision metadata."""
    lines = list(e.features.trigger_reasons[:4])
    f = e.features
    if f.correlated_channels >= 2:
        lines.append(f"{f.correlated_channels} channels flagged simultaneously")
    if f.cross_instrument_coincidence:
        lines.append("another instrument flagged a candidate within the coincidence window")
    if f.duration_s >= 3600:
        lines.append(f"event lasted {f.duration_s / 3600:.1f} h")
    lines.append(f"novelty {f.novelty:.2f}" + (f" (most similar: {f.most_similar_event})" if f.most_similar_event else " (no similar earlier event)"))
    top = max(pb.contributions, key=pb.contributions.get)
    lines.append(f"largest utility contribution: {top.replace('_', ' ')} ({pb.contributions[top]:.3f})")
    lines.append(gate_reason)
    lines.extend(notes)
    return lines
