import json
from datetime import datetime, timedelta, timezone

import httpx2
import polars as pl
import pytest

from deepsift.core.models import DownlinkAction, LabelSource
from deepsift.decision.jev import JevDecisionEngine
from deepsift.decision.questions import QUESTIONS, SINGLE_DECISION_QUESTIONS
from deepsift.decision.state import build_state_variant
from deepsift.evaluation.benchmark import Unit, allocate
from deepsift.evaluation.labels import Label
from deepsift.evaluation.metrics2 import WindowIndex, ece, evaluate_selection, pareto_front
from deepsift.evaluation.strategies import oracle_strategy
from deepsift.evaluation.sweeps import bucket

from .conftest import make_event

T = datetime(2015, 1, 20, tzinfo=timezone.utc)


def _t(h):
    return T + timedelta(hours=h)


def _iw(n=48):
    """SYNTHETIC TEST DATA — hourly RAD windows."""
    return pl.DataFrame({
        "instrument": ["RAD"] * n, "window": [f"w{i}" for i in range(n)],
        "t_start": [_t(i) for i in range(n)], "t_end": [_t(i + 1) for i in range(n)],
        "raw": [1000] * n, "full": [100] * n, "compressed": [30] * n,
    })


def _unit(i, u=1.0):
    return Unit(f"w{i}", "RAD", _t(i), _t(i + 1), u, DownlinkAction.FULL_DATA,
                {"full_data": 100, "compress": 30, "summary_only": 5, "discard": 0}, 1000)


FID = {"full_data": 1.0, "compress": 0.5, "summary_only": 0.15, "discard": 0.0}


def test_strict_vs_tolerant_and_coverage():
    lab = Label(id="FD1", source=LabelSource.DOCUMENTED_EVENT, instrument="RAD", t_start=_t(10), t_end=_t(20), severity="high")
    meta = {"FD1": {"confidence": "documented_uncertainty", "tolerance_before_s": 3 * 3600, "tolerance_after_s": 0}}
    widx = WindowIndex(_iw())
    # retain only a window 2 h before onset: tolerant hit, strict miss, zero coverage
    m = evaluate_selection(allocate([_unit(8)], 1000), [lab], meta, widx, 48000, FID)
    pl_ = m["per_label"]["FD1"]
    assert pl_["strict_hit"] is False and pl_["tolerant_hit"] is True and pl_["coverage"] == 0
    # retain 5 of the 10 windows inside the label
    m = evaluate_selection(allocate([_unit(i) for i in range(10, 15)], 1000), [lab], meta, widx, 48000, FID)
    assert m["per_label"]["FD1"]["coverage"] == pytest.approx(0.5)
    assert m["strict_recall"] == 1.0


def test_needs_verification_labels_have_no_strict_hit():
    lab = Label(id="S", source=LabelSource.DOCUMENTED_EVENT, instrument="RAD", t_start=_t(10), t_end=_t(12), severity="high")
    meta = {"S": {"confidence": "NEEDS_VERIFICATION", "tolerance_before_s": 86400, "tolerance_after_s": 86400}}
    m = evaluate_selection(allocate([_unit(11)], 1000), [lab], meta, WindowIndex(_iw()), 48000, FID)
    assert m["per_label"]["S"]["strict_hit"] is None and m["strict_n"] == 0 and m["tolerant_recall"] == 1.0


def test_no_data_labels_are_excluded():
    lab = Label(id="G", source=LabelSource.DOCUMENTED_EVENT, instrument="REMS", t_start=_t(1), t_end=_t(2), severity="high")
    m = evaluate_selection([], [lab], {"G": {}}, WindowIndex(_iw()), 48000, FID)
    assert m["labels_no_data"] == 1 and m["labels_scored"] == 0


def test_oracle_recovers_every_label_before_coverage():
    labels = [Label(id=f"L{k}", source=LabelSource.SYNTHETIC_ANOMALY, instrument="RAD", t_start=_t(5 * k), t_end=_t(5 * k + 4),
                    severity="high") for k in range(5)]
    o = oracle_strategy(_iw(), labels, {})
    m = evaluate_selection(allocate(o.units, 500), labels, {l.id: {"confidence": "documented_uncertainty"} for l in labels},
                           WindowIndex(_iw()), 48000, FID)
    assert m["strict_recall"] == 1.0          # budget of exactly 5 windows → one per label


def test_ece_perfectly_calibrated_and_overconfident():
    assert ece([0.8] * 10, [True] * 8 + [False] * 2)["ece"] == pytest.approx(0.0)
    assert ece([0.95] * 10, [True] * 5 + [False] * 5)["ece"] == pytest.approx(0.45)


def test_pareto_front():
    pts = [{"r": 0.9, "c": 10}, {"r": 0.8, "c": 5}, {"r": 0.7, "c": 6}, {"r": 0.9, "c": 12}]
    assert pareto_front(pts, ["r"], ["c"]) == [0, 1]


def test_difficulty_buckets_are_declared_boundaries():
    assert [bucket(m) for m in (1, 2, 3.9, 4, 7.9, 8, 16)] == [
        "NEAR_NOISE_FLOOR", "WEAK", "WEAK", "MODERATE", "MODERATE", "OBVIOUS", "OBVIOUS"]


def test_state_variants_never_contain_labels_and_differ():
    e = make_event(z=9, flat=0.99)
    e.synthetic_injection_ids = ["SYN-X"]
    obj = {"name": "Radiation Monitoring", "description": "SEPs first"}
    states = {v: build_state_variant(e, "MSL", "Gale", v, obj) for v in ("full_context", "no_mission_objective", "minimal", "numeric_only")}
    for s in states.values():
        assert "SYN-X" not in json.dumps(s)
    assert "mission_objective" in states["full_context"] and "mission_objective" not in states["no_mission_objective"]
    assert "sigma" not in json.dumps(states["numeric_only"]) and "robust_z" in json.dumps(states["numeric_only"])
    assert "channels" not in states["minimal"]


def _transport(record):
    def handler(request):
        body = json.loads(request.content)
        record.append(body)
        answers = {}
        for name, q in body["questions"].items():
            if q["type"] == "choice":
                keys = list(q["criteria"])
                answers[name] = {"type": "choice", "choice": keys[-1], "confidence": 0.8,
                                 "probabilities": {k: (0.8 if k == keys[-1] else 0.2 / (len(keys) - 1)) for k in keys}}
            else:
                answers[name] = {"type": "noul", "noul": 0.7}
        return httpx2.Response(200, json={"model": "jev-1.13", "answers": answers, "usage": {"input_tokens": 800, "output_tokens": 3}},
                               headers={"x-typesafe-request-id": "req_test_1"})
    return httpx2.MockTransport(handler)


@pytest.mark.parametrize("variant", ["full_context", "minimal", "numeric_only", "single_decision"])
def test_jev_variants_log_every_call(tmp_path, variant):
    from typesafe_sdk import RetryPolicy, TypeSafeClient

    sent = []
    client = TypeSafeClient(api_key="test-key", transport=_transport(sent), retry=RetryPolicy(max_retries=0))
    log = tmp_path / "calls.jsonl"
    eng = JevDecisionEngine(client=client, variant=variant, call_log=log, run_id="RUN1")
    [d] = eng.decide([make_event()], "MSL", "Gale", objective={"name": "Balanced", "description": "x"})
    expected_q = SINGLE_DECISION_QUESTIONS if variant == "single_decision" else QUESTIONS
    assert set(sent[0]["questions"]) == set(expected_q)
    rec = json.loads(log.read_text().strip())
    assert rec["run_id"] == "RUN1" and rec["variant"] == variant and rec["request_id"] == "req_test_1"
    assert rec["model_returned"] == "jev-1.13" and rec["retries"] == 0 and rec["error"] is None
    assert len(rec["payload_sha256"]) == 64 and rec["input_tokens"] == 800
    assert "test-key" not in log.read_text()
    assert d.error is None


def test_jev_retries_are_counted(tmp_path):
    from typesafe_sdk import RetryPolicy, TypeSafeClient

    n = {"i": 0}

    def flaky(request):
        n["i"] += 1
        if n["i"] == 1:
            return httpx2.Response(503, json={"detail": "busy"})
        return _transport([]).handle_request(request)

    client = TypeSafeClient(api_key="k", transport=httpx2.MockTransport(flaky), retry=RetryPolicy(max_retries=0))
    log = tmp_path / "c.jsonl"
    [d] = JevDecisionEngine(client=client, call_log=log).decide([make_event()], "MSL", "Gale")
    assert d.error is None and json.loads(log.read_text())["retries"] == 1


def test_local_edge_inference_is_pure_and_bounded():
    from deepsift.evaluation.local_edge import FEATURES, LocalEdgeModel

    m = LocalEdgeModel([0] * len(FEATURES), [1] * len(FEATURES), [0.1] * len(FEATURES), -1.0)
    p = m.predict_proba_event(make_event(z=12))
    assert 0 < p < 1
    assert m.footprint([make_event()])["parameters"] == len(FEATURES) + 1


def test_test_split_refuses_without_frozen_config(tmp_path, monkeypatch):
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    import yaml

    doc = yaml.safe_load((root / "config" / "phase2.yaml").read_text())
    if (doc.get("provenance") or {}).get("validation_choices", {}).get("frozen"):
        pytest.skip("config already frozen")
    r = subprocess.run([sys.executable, str(root / "scripts" / "run_study.py"), "--split", "test", "--no-jev"],
                       capture_output=True, text=True, cwd=root)
    assert r.returncode != 0 and "refusing to evaluate TEST" in (r.stderr + r.stdout)


# ------------------------------------------------------------------ Jev cache, budget guard, plan guard
def test_cache_prevents_second_api_call(tmp_path):
    from typesafe_sdk import RetryPolicy, TypeSafeClient

    from deepsift.decision.jev_cache import JevCache

    sent = []
    client = TypeSafeClient(api_key="k", transport=_transport(sent), retry=RetryPolicy(max_retries=0))
    cache = JevCache(tmp_path / "c.sqlite")
    e = make_event()
    eng = JevDecisionEngine(client=client, cache=cache, run_id="R1")
    [d1] = eng.decide([e], "MSL", "Gale")
    [d2] = JevDecisionEngine(client=client, cache=cache, run_id="R2").decide([e], "MSL", "Gale")
    assert len(sent) == 1, "identical request must be served from cache"
    assert d1.answers == d2.answers and d2.cost_usd == 0.0
    # a different variant is a different request
    JevDecisionEngine(client=client, cache=cache, variant="minimal").decide([e], "MSL", "Gale")
    assert len(sent) == 2
    # explicit research bypass
    JevDecisionEngine(client=client, use_cache=False).decide([e], "MSL", "Gale")
    assert len(sent) == 3


def test_objective_text_only_changes_keys_for_full_context(tmp_path):
    from deepsift.decision.jev import VARIANTS, questions_payload
    from deepsift.decision.jev_cache import request_key
    from deepsift.decision.questions import QUESTIONS

    e = make_event()
    q = questions_payload(QUESTIONS)
    k = lambda v, o: request_key(build_state_variant(e, "M", "L", VARIANTS[v][0], o), q, v, "jev-1.13.0", "0.7.1")  # noqa: E731
    a, b = {"name": "A", "description": "x"}, {"name": "B", "description": "y"}
    assert k("no_mission_objective", a) == k("no_mission_objective", b)
    assert k("full_context", a) != k("full_context", b)


def test_hard_budget_stops_live_calls(tmp_path):
    from typesafe_sdk import RetryPolicy, TypeSafeClient

    from deepsift.decision.jev import ApiBudget, JevBudgetExceeded

    sent = []
    client = TypeSafeClient(api_key="k", transport=_transport(sent), retry=RetryPolicy(max_retries=0))
    eng = JevDecisionEngine(client=client, use_cache=False, budget=ApiBudget(2, 10.0), max_concurrency=1)
    with pytest.raises(JevBudgetExceeded):
        eng.decide([make_event(eid=f"E{i}") for i in range(5)], "MSL", "Gale")
    assert len(sent) == 2


def test_plan_guard_blocks_large_or_unmeasured_runs():
    from deepsift.evaluation.jev_plan import guard

    s = {"live_calls_needed": 5000, "estimated_cost_usd": 0.2, "token_estimate_basis": "measured 3.9 chars/token"}
    assert guard(s, 1000, 1.0, None, None)[0] is False
    assert guard(s, 1000, 1.0, 5000, None)[0] is True
    s2 = {"live_calls_needed": 500, "estimated_cost_usd": 0.02, "token_estimate_basis": "ASSUMED 4.0 chars/token"}
    assert guard(s2, 1000, 1.0, None, None)[0] is False       # cost not measured yet → no bulk run
    s3 = {"live_calls_needed": 30, "estimated_cost_usd": 0.001, "token_estimate_basis": "ASSUMED 4.0 chars/token"}
    assert guard(s3, 1000, 1.0, None, None)[0] is True        # the smoke test is allowed


def test_detection_decomposition():
    from deepsift.evaluation.metrics2 import decompose, mcnemar

    scored = [{"severity": "high", "detected": True, "tolerant_hit": True},
              {"severity": "high", "detected": True, "tolerant_hit": False},
              {"severity": "high", "detected": False, "tolerant_hit": False},
              {"severity": "low", "detected": False, "tolerant_hit": True}]
    d = decompose(scored)
    assert d["detection_recall"] == 0.5 and d["conditional_retention"] == 0.5 and d["end_to_end_recall"] == 0.5
    assert d["high_detection_recall"] == pytest.approx(2 / 3) and d["high_conditional_retention"] == 0.5
    assert d["retained_undetected"] == 1
    assert mcnemar(0, 0) is None and mcnemar(10, 0) == pytest.approx(2 / 1024) and mcnemar(5, 5) == 1.0
