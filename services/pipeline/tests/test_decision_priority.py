import json

import httpx2
import pytest

from deepsift.core.models import DownlinkAction, GateStatus
from deepsift.decision.gating import gate
from deepsift.decision.jev import JevDecisionEngine
from deepsift.decision.mock import MockDecisionEngine
from deepsift.decision.questions import QUESTIONS
from deepsift.decision.state import build_state
from deepsift.objectives.objective import MissionObjective, load_objectives
from deepsift.priority.counterfactual import counterfactuals
from deepsift.priority.engine import decide_action, effective_weights, score_event, threshold_action

from .conftest import make_decision, make_event


# ------------------------------------------------------------------ mock engine
def test_mock_engine_returns_bounded_answers():
    e = make_event(z=9, sensors=("pressure",), dip=1.2)
    [d] = MockDecisionEngine().decide([e], "MSL", "Gale")
    assert set(d.answers) == set(QUESTIONS)
    for name, q in QUESTIONS.items():
        a = d.answers[name]
        if q.kind == "choice":
            assert a.choice in q.criteria
            assert set(a.probabilities) == set(q.criteria)
            assert abs(sum(a.probabilities.values()) - 1) < 1e-3
            assert 0 <= a.confidence <= 1
        else:
            assert 0 <= a.noul <= 1
    assert d.state_sent["channels"]["pressure"]["deviation"].startswith("+9.0 sigma")
    assert not MockDecisionEngine.is_real_model


def test_mock_engine_is_deterministic():
    e = make_event(z=5)
    a, b = MockDecisionEngine().decide([e, e], "MSL", "Gale")
    assert a.answers["science_value"].probabilities == b.answers["science_value"].probabilities


def test_state_has_qualitative_descriptors_and_no_raw_rows():
    s = build_state(make_event(z=-12, flat=0.99), "MSL", "Gale")
    txt = json.dumps(s)
    assert "extremely far below normal" in txt and "values stuck" in txt
    assert "rows" not in s


# ------------------------------------------------------------------ Jev adapter through the real SDK
def _jev_response(request: httpx2.Request) -> httpx2.Response:
    body = json.loads(request.content)
    assert request.url.path == "/v1/systemone"
    assert request.headers["authorization"].startswith("Bearer ")
    assert set(body) >= {"state", "model", "questions"}
    answers = {}
    for name, q in body["questions"].items():
        if q["type"] == "choice":
            keys = list(q["criteria"])
            probs = {k: (0.9 if i == 0 else 0.1 / (len(keys) - 1)) for i, k in enumerate(keys)}
            answers[name] = {"type": "choice", "choice": keys[0], "confidence": 0.88, "probabilities": probs}
        else:
            answers[name] = {"type": "noul", "noul": 0.25}
    return httpx2.Response(200, json={"model": "jev-1.13", "answers": answers, "usage": {"input_tokens": 1000, "output_tokens": 5}})


def test_jev_engine_via_sdk_mock_transport():
    from typesafe_sdk import TypeSafeClient

    client = TypeSafeClient(api_key="test-key", transport=httpx2.MockTransport(_jev_response))
    eng = JevDecisionEngine(model="jev-latest", client=client, price_per_mtok_input_usd=0.042)
    [d] = eng.decide([make_event()], "MSL", "Gale")
    assert d.error is None
    assert d.model == "jev-1.13"
    assert d.answers["science_value"].choice == "none" and d.answers["science_value"].confidence == 0.88
    assert d.answers["needs_deep_analysis"].noul == 0.25
    assert d.input_tokens == 1000 and d.cost_usd == pytest.approx(1000 * 0.042 / 1e6)


def test_jev_engine_error_is_recorded_not_raised():
    from typesafe_sdk import TypeSafeClient

    client = TypeSafeClient(api_key="k", transport=httpx2.MockTransport(lambda r: httpx2.Response(500, json={"detail": "boom"})),
                            retry=None)
    [d] = JevDecisionEngine(client=client).decide([make_event()], "MSL", "Gale")
    assert d.error


# ------------------------------------------------------------------ gating
@pytest.mark.parametrize("conf,deep_avail,expected", [
    (0.95, False, GateStatus.AUTO),
    (0.80, False, GateStatus.UNCERTAIN),
    (0.50, False, GateStatus.FALLBACK),
    (0.50, True, GateStatus.ESCALATED),
])
def test_confidence_gating(cfg, conf, deep_avail, expected):
    d = make_decision(sci_conf=conf, type_conf=0.99)
    assert gate(d, cfg, deep_avail)[0] == expected


def test_gating_thresholds_are_configurable(cfg):
    d = make_decision(sci_conf=0.8, type_conf=0.99)
    strict = cfg.patched({"gating": {"auto_threshold": 0.99, "uncertain_threshold": 0.9}})
    assert gate(d, strict, False)[0] == GateStatus.FALLBACK


def test_engine_error_gates_to_rules(cfg):
    d = make_decision()
    d.error = "timeout"
    assert gate(d, cfg, True)[0] == GateStatus.ENGINE_ERROR


# ------------------------------------------------------------------ priority + objectives
def test_threshold_actions(cfg):
    t = cfg.priority.thresholds
    assert threshold_action(t.full_data, cfg) == DownlinkAction.FULL_DATA
    assert threshold_action(t.compress, cfg) == DownlinkAction.COMPRESS
    assert threshold_action(t.summary_only, cfg) == DownlinkAction.SUMMARY_ONLY
    assert threshold_action(t.summary_only - 1e-9, cfg) == DownlinkAction.DISCARD


def test_utility_is_weighted_sum_times_penalty(cfg):
    objs = load_objectives()
    e = make_event(z=6, novelty=0.5)
    d = make_decision(sci="high", sci_conf=1.0, etype="atmospheric", type_conf=1.0)
    pb, _, _ = score_event(e, d, GateStatus.AUTO, objs["balanced_science"], cfg)
    w = effective_weights(cfg, objs["balanced_science"])
    expected = sum(w[k] * getattr(pb, k) for k in w)
    assert pb.utility == pytest.approx(expected)
    assert pb.science_value == pytest.approx(0.75)
    assert pb.mission_relevance == pytest.approx(0.8)


def test_objective_changes_ranking_without_engine(cfg):
    objs = load_objectives()
    rad = make_event("RAD-1", instrument="RAD", sensors=("dose_b",), z=6)
    atm = make_event("ATM-1", sensors=("pressure",), z=6)
    d_rad = make_decision(etype="radiation")
    d_atm = make_decision(etype="atmospheric")

    def u(e, d, oid):
        return score_event(e, d, GateStatus.AUTO, objs[oid], cfg)[0].utility

    assert u(rad, d_rad, "radiation_monitoring") > u(atm, d_atm, "radiation_monitoring")
    assert u(atm, d_atm, "atmospheric_science") > u(rad, d_rad, "atmospheric_science")


def test_custom_objective_validation():
    with pytest.raises(ValueError):
        MissionObjective(id="bad", name="bad", type_weights={"atmospheric": 1.5})
    o = MissionObjective(id="c", name="c", type_weights={"thermal": 1.0})
    assert o.type_weights["radiation"] == 0.0


def test_uncertain_gate_never_discards(cfg):
    d = make_decision(action="discard")
    action, notes = decide_action(0.0, d, GateStatus.UNCERTAIN, cfg)
    assert action == DownlinkAction.SUMMARY_ONLY and any("uncertain" in n for n in notes)


def test_instrument_failure_floor(cfg):
    d = make_decision(fail_yes=0.9, action="discard")
    action, _ = decide_action(0.0, d, GateStatus.AUTO, cfg)
    assert action == DownlinkAction.SUMMARY_ONLY


def test_engine_can_only_upgrade_one_level(cfg):
    d = make_decision(action="full_data")
    u = cfg.priority.thresholds.summary_only + 0.01  # → SUMMARY_ONLY by threshold
    action, notes = decide_action(u, d, GateStatus.AUTO, cfg)
    assert action == DownlinkAction.COMPRESS
    ignore = cfg.patched({"priority": {"engine_action_policy": "ignore"}})
    assert decide_action(u, d, GateStatus.AUTO, ignore)[0] == DownlinkAction.SUMMARY_ONLY


# ------------------------------------------------------------------ counterfactuals
def test_counterfactuals_are_verified_by_recomputation(cfg):
    objs = load_objectives()
    e = make_event(z=5, novelty=0.6)
    d = make_decision(sci="medium", sci_conf=0.95, type_conf=0.95)
    cf = counterfactuals(e, d, GateStatus.AUTO, objs["balanced_science"], cfg, objs)
    assert cf["changes"], "a mid-utility event should have at least one action-changing input"
    w = effective_weights(cfg, objs["balanced_science"])
    for ch in cf["changes"]:
        assert ch["verified"] and ch["action"] != cf["current_action"]
        if ch["input"] != "confidence":
            terms = dict(cf["terms"], **{ch["input"]: ch["to"]})
            u = (1 - cfg.priority.confidence_penalty * (1 - cf["confidence"])) * sum(w[k] * terms[k] for k in w)
            assert u == pytest.approx(ch["utility"], abs=1e-3)
    assert {o["objective"] for o in cf["by_objective"]} == set(objs)
