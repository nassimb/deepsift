"""JEV_SCHEMA_V3 invariants (SYNTHETIC TEST DATA only)."""

import json

from .conftest import make_event

from deepsift.core.models import AnswerDist, EngineDecision
from deepsift.decision.jev import ALL_VARIANTS, VARIANTS, question_specs_for
from deepsift.decision.state import V3_BANNED_WORDS, build_state_v3, data_quality_state

THR = {"REMS": 9.344, "RAD": 8.603, "dip_pa": 0.43}


def test_v3_removes_system_questions_and_instrument_class():
    sci, rel = question_specs_for("v3_science"), question_specs_for("v3_relevance")
    assert set(sci) == {"scientific_interest", "phenomenon_class"} and set(rel) == {"mission_relevance"}
    assert "instrument_anomaly" not in sci["phenomenon_class"].criteria
    assert not {"instrument_failure", "downlink_action", "needs_deep_analysis"} & (set(sci) | set(rel))
    assert "v3_science" not in VARIANTS and "v3_science" in ALL_VARIANTS      # pre-registered five unchanged


def test_v3_state_neutral_and_objective_only_in_relevance_state():
    e = make_event(z=40.0, missing=0.9)
    obj = {"name": "Engineering Health", "description": "Sensor health first"}
    s_sci = build_state_v3(e, "MSL", "Gale", THR)
    s_rel = build_state_v3(e, "MSL", "Gale", THR, obj)
    assert "mission_objective" not in s_sci and s_rel["mission_objective"]["name"] == "Engineering Health"
    txt = json.dumps(s_sci).lower()
    assert not any(w in txt for w in V3_BANNED_WORDS)
    assert s_sci["deviating_sensors"]["atmospheric pressure"]["magnitude"] == "extreme relative to the local baseline"


def test_data_quality_state_uses_frozen_flags_only():
    assert data_quality_state(make_event(z=12.0))[0] == "CLEAN"
    assert data_quality_state(make_event(z=12.0, missing=0.9))[0] == "BAD"          # level + dropout on the only channel
    assert data_quality_state(make_event(z=1.0, noise=6.0))[0] == "BAD"             # noise only


def test_v3_adapter_ignores_confidence():
    from deepsift.core.config import load_config
    from deepsift.core.config import ROOT
    from deepsift.evaluation.v3_adapter import v3_strategy
    from deepsift.objectives.objective import load_objectives

    cfg = load_config(ROOT / "config" / "phase2.yaml")
    obj = load_objectives()[cfg.objective]
    e = make_event(z=12.0)

    def dec(conf):
        p = {k: 0.0 for k in ("none", "low", "medium", "high", "exceptional")} | {"high": 1.0}
        return EngineDecision(engine="t", answers={"scientific_interest": AnswerDist(kind="choice", choice="high", confidence=conf, probabilities=p)})
    a = v3_strategy("A", [e], [dec(0.99)], None, obj, cfg).units[0].utility
    b = v3_strategy("B", [e], [dec(0.2)], None, obj, cfg).units[0].utility
    assert a == b
