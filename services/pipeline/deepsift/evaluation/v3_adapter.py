"""JEV_SCHEMA_V3 ranking adapter — VALIDATION-only, experimental, versioned. The frozen global policy is untouched.

Declared and frozen on 2026-09-25 BEFORE any V3 answer existed (see docs/jev-model-selection.md § JEV_SCHEMA_V3):

  * Jev supplies only bounded scientific signals: scientific_interest (+ mission_relevance for WITH_OBJECTIVE).
    phenomenon_class is recorded but NOT used for priority (kept only if it shows measurable value).
  * Categorical → numeric: equally spaced ordinal scale (none 0, low .25, medium .5, high .75, top 1.0). Chosen as
    the least-assumption mapping for a 5-level ordinal answer; not tuned.
  * The CHOSEN category is used, never the probabilities or the confidence (the q1 pilot showed confidence did not
    separate correct from incorrect answers). No confidence penalty.
  * Jev's judgments assume valid measurements, so they are multiplied by the deterministic data-quality factor
    CLEAN 1.0 / SUSPECT 0.5 / BAD 0.0 (from decision/state.py data_quality_state; frozen flags only).
  * No instrument-failure floor, no engine action upgrade: V3 provides neither signal.

Strategies built here:
  JEV_V3_*            utility = frozen objective weights · {science: QC·interest, mission_relevance: QC·relevance (WITH)
                      or the frozen deterministic relevance (NO), anomaly_strength, novelty}; action = frozen thresholds
  V3_ADAPTER_NO_JEV   control: identical adapter with every Jev value replaced by 0.5 (isolates adapter/QC effects)
  RULES+JEV_V3_*      the RULES strategy unchanged (utility and action), plus a bounded Jev adjustment
                      RULES_PLUS_JEV_WEIGHT · (jev_signal − 0.5), jev_signal = QC·interest (NO) or the mean of
                      QC·interest and QC·relevance (WITH): Jev can reorder within ±0.05 utility but never sets an action.
"""

from __future__ import annotations

from deepsift.core.models import EngineDecision
from deepsift.decision.state import data_quality_state
from deepsift.evaluation.benchmark import event_units
from deepsift.priority.engine import anomaly_strength, effective_weights, rules_type, threshold_action

INTEREST_VALUE = {"none": 0.0, "low": 0.25, "medium": 0.5, "high": 0.75, "exceptional": 1.0}
RELEVANCE_VALUE = {"none": 0.0, "low": 0.25, "medium": 0.5, "high": 0.75, "very_high": 1.0}
QC_FACTOR = {"CLEAN": 1.0, "SUSPECT": 0.5, "BAD": 0.0}
RULES_PLUS_JEV_WEIGHT = 0.10


def _choice(d: EngineDecision | None, q: str) -> str | None:
    if d is None or d.error or q not in d.answers:
        return None
    return d.answers[q].choice


def jev_signals(e, sci: EngineDecision | None, rel: EngineDecision | None) -> dict:
    qc = QC_FACTOR[data_quality_state(e)[0]]
    i, r = _choice(sci, "scientific_interest"), _choice(rel, "mission_relevance")
    return {"qc": qc, "interest": qc * INTEREST_VALUE[i] if i else None, "relevance": qc * RELEVANCE_VALUE[r] if r else None}


def v3_strategy(name: str, events, sci_decs, rel_decs, objective, cfg, constant: float | None = None):
    """JEV_V3_* (or the NO_JEV control when `constant` is given). Returns (units, per-event decisions)."""
    from deepsift.evaluation.strategies import StrategyOutput

    w = effective_weights(cfg, objective)
    out, dec = [], {}
    for k, e in enumerate(events):
        s = jev_signals(e, sci_decs[k] if sci_decs else None, rel_decs[k] if rel_decs else None)
        interest = s["qc"] * constant if constant is not None else (s["interest"] if s["interest"] is not None else 0.0)
        if rel_decs is not None and constant is None:
            relevance = s["relevance"] if s["relevance"] is not None else 0.0
        else:
            relevance = objective.relevance({rules_type(e): 1.0}, e.sensors)[0]
        terms = {"science_value": interest, "mission_relevance": relevance,
                 "anomaly_strength": anomaly_strength(e.features.deviation_score, cfg.priority.anomaly_scale),
                 "novelty": e.features.novelty}
        u = sum(w[t] * terms[t] for t in w)
        ev = e.model_copy(deep=True)
        ev.proposed_action = threshold_action(u, cfg)
        unit = event_units([ev])[0]
        unit.utility = u
        out.append(unit)
        dec[e.id] = {"utility": u, "action": ev.proposed_action.value, **s}
    return StrategyOutput(name, out, decisions=dec)


def rules_plus_v3(name: str, rules_out, events, sci_decs, rel_decs):
    """RULES unchanged, plus a bounded Jev reordering term; actions are the RULES actions."""
    from dataclasses import replace

    from deepsift.evaluation.strategies import StrategyOutput

    by_id = {e.id: k for k, e in enumerate(events)}
    units = []
    for u in rules_out.units:
        k = by_id[u.id]
        s = jev_signals(events[k], sci_decs[k], rel_decs[k] if rel_decs else None)
        parts = [x for x in (s["interest"], s["relevance"] if rel_decs else None) if x is not None]
        sig = sum(parts) / len(parts) if parts else 0.5
        units.append(replace(u, utility=u.utility + RULES_PLUS_JEV_WEIGHT * (sig - 0.5)))
    return StrategyOutput(name, units, decisions=rules_out.decisions)
