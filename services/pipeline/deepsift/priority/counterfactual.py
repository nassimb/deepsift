"""Counterfactual explorer — computed by re-running the deterministic scorer, never generated.

For each input of the utility we solve (the utility is linear in each term) for the value at
which the action would change, then *verify* by re-running `decide_action` with that value.
Floors and engine-upgrade rules are therefore respected automatically.
"""

from __future__ import annotations

from deepsift.core.models import ACTION_RANK, DownlinkAction, EngineDecision, GateStatus, ScientificEvent
from deepsift.objectives.objective import MissionObjective
from deepsift.priority.engine import TERMS, decide_action, effective_weights, terms_for, utility_from

EPS = 1e-4


def _action_with(terms, conf, weights, d, gate_status, cfg):
    u, _, _ = utility_from(terms, conf, weights, cfg.priority.confidence_penalty)
    return decide_action(u, d, gate_status, cfg)[0], u


def counterfactuals(e: ScientificEvent, d: EngineDecision, gate_status: GateStatus, objective: MissionObjective,
                    cfg, objectives: dict[str, MissionObjective] | None = None) -> dict:
    weights = effective_weights(cfg, objective)
    terms, conf, _ = terms_for(e, d, objective, cfg)
    if gate_status in (GateStatus.FALLBACK, GateStatus.ENGINE_ERROR):
        conf = 1.0
    lam = cfg.priority.confidence_penalty
    current, u0 = _action_with(terms, conf, weights, d, gate_status, cfg)
    th = cfg.priority.thresholds
    boundaries = {DownlinkAction.FULL_DATA: th.full_data, DownlinkAction.COMPRESS: th.compress, DownlinkAction.SUMMARY_ONLY: th.summary_only}
    penalty = 1 - lam * (1 - conf)
    out: list[dict] = []

    # 1) per-term changes
    for k in TERMS:
        if weights[k] <= 0:
            continue
        rest = sum(weights[j] * terms[j] for j in TERMS if j != k)
        for target_action, T in boundaries.items():
            for side in (-EPS, +EPS):  # just below / just above the boundary
                x = (T / penalty - rest) / weights[k] + side
                if not 0.0 <= x <= 1.0:
                    continue
                mod = dict(terms, **{k: x})
                act, u = _action_with(mod, conf, weights, d, gate_status, cfg)
                if act != current:
                    out.append({
                        "input": k, "from": round(terms[k], 4), "to": round(x, 4),
                        "delta": round(x - terms[k], 4), "action": act.value, "utility": round(u, 4), "verified": True,
                    })
    # 2) confidence
    for T in boundaries.values():
        base = sum(weights[j] * terms[j] for j in TERMS)
        if base <= 0 or lam <= 0:
            continue
        for side in (-EPS, +EPS):
            p = T / base + side
            c = 1 - (1 - p) / lam
            if 0.0 <= c <= 1.0:
                act, u = _action_with(terms, c, weights, d, gate_status, cfg)
                if act != current:
                    out.append({"input": "confidence", "from": round(conf, 4), "to": round(c, 4), "delta": round(c - conf, 4),
                                "action": act.value, "utility": round(u, 4), "verified": True})

    # keep the smallest change per (input, resulting action)
    best: dict[tuple[str, str], dict] = {}
    for r in out:
        key = (r["input"], r["action"])
        if key not in best or abs(r["delta"]) < abs(best[key]["delta"]):
            best[key] = r
    changes = sorted(best.values(), key=lambda r: (abs(r["delta"]), r["input"]))

    # 3) objective swaps (re-scored with each preset's weights and relevance)
    by_objective = []
    for oid, obj in (objectives or {}).items():
        w2 = effective_weights(cfg, obj)
        t2, c2, _ = terms_for(e, d, obj, cfg)
        if gate_status in (GateStatus.FALLBACK, GateStatus.ENGINE_ERROR):
            c2 = 1.0
        act, u = _action_with(t2, c2, w2, d, gate_status, cfg)
        by_objective.append({"objective": oid, "name": obj.name, "action": act.value, "utility": round(u, 4),
                             "mission_relevance": round(t2["mission_relevance"], 4)})

    # 4) detection threshold: would this event exist at a stricter z threshold?
    max_level_z = max((abs(c.robust_z) for n, c in e.features.channels.items() if n in e.sensors), default=0.0)
    detection = {
        "max_flagged_abs_z": round(max_level_z, 3),
        "note": (f"with z_threshold above {max_level_z:.2f}σ the level trigger would not fire"
                 + ("; other triggers (dip / quality flags) may still keep the event" if len(e.features.trigger_reasons) > len(e.sensors) or any("drop" in r or "missing" in r or "noise" in r or "identical" in r for r in e.features.trigger_reasons) else "")),
    }
    return {
        "current_action": current.value, "utility": round(u0, 4), "terms": {k: round(v, 4) for k, v in terms.items()},
        "confidence": round(conf, 4), "weights": weights, "changes": changes, "by_objective": by_objective,
        "detection": detection,
        "method": "linear solve per input, then verified by re-running the deterministic action policy",
    }


def rank_change(a: DownlinkAction, b: DownlinkAction) -> int:
    return ACTION_RANK[b] - ACTION_RANK[a]
