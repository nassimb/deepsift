"""Confidence gating — model output is evidence, never truth."""

from __future__ import annotations

from deepsift.core.models import EngineDecision, GateStatus
from deepsift.decision.questions import GATING_QUESTIONS


def decision_confidence(d: EngineDecision) -> float:
    confs = [d.answers[q].confidence for q in GATING_QUESTIONS if q in d.answers and d.answers[q].confidence is not None]
    return min(confs) if confs else 0.0


def gate(d: EngineDecision, cfg, deep_available: bool) -> tuple[GateStatus, float, str]:
    """Return (status, confidence, reason). Thresholds come from config.gating."""
    g = cfg.gating
    if d.error or not d.answers:
        return GateStatus.ENGINE_ERROR, 0.0, f"engine error → deterministic rules ({d.error})"
    conf = decision_confidence(d)
    wants_deep = d.answers.get("needs_deep_analysis")
    p_deep = wants_deep.noul if wants_deep and wants_deep.noul is not None else 0.0
    if deep_available and p_deep >= g.deep_request_threshold:
        return GateStatus.ESCALATED, conf, f"engine requested deep analysis (P={p_deep:.2f} ≥ {g.deep_request_threshold})"
    if conf >= g.auto_threshold:
        return GateStatus.AUTO, conf, f"confidence {conf:.2f} ≥ {g.auto_threshold} → automatic routing"
    if conf >= g.uncertain_threshold:
        return GateStatus.UNCERTAIN, conf, f"confidence {conf:.2f} in [{g.uncertain_threshold}, {g.auto_threshold}) → kept, flagged uncertain"
    if deep_available:
        return GateStatus.ESCALATED, conf, f"confidence {conf:.2f} < {g.uncertain_threshold} → deep analysis"
    return GateStatus.FALLBACK, conf, f"confidence {conf:.2f} < {g.uncertain_threshold}, no deep provider → deterministic rules"
