from datetime import datetime, timedelta, timezone

import pytest

from deepsift.core.models import DownlinkAction, GateStatus, LabelSource
from deepsift.evaluation.benchmark import Unit, allocate, evaluate
from deepsift.evaluation.labels import Label
from deepsift.simulation.scheduler import Blackout, Item, pass_times, simulate


def _item(i, t, u, full=10_000, comp=3_000, summ=500, action=DownlinkAction.FULL_DATA):
    return Item(id=f"E{i}", kind="event", arrival=t, utility=u, action=action,
                sizes={"full_data": full, "compress": comp, "summary_only": summ, "discard": 0}, raw=100_000)


# ------------------------------------------------------------------ scheduler
def test_pass_times(cfg):
    p = pass_times(10, 11, 2)
    assert len(p) == 6 and p[0] == pytest.approx(10 + 3.5 / 24) and p[1] == pytest.approx(10 + 15.5 / 24)


def test_downlink_respects_pass_budget_and_priority(cfg):
    c = cfg.patched({"downlink": {"pass_bytes": 15_000, "passes_per_sol": 1, "storage_bytes": 10**7}})
    items = [_item(1, 10.01, 0.2), _item(2, 10.02, 0.9)]
    sim = simulate(items, [(10.0, 200_000)], c, sol_range=(10, 10))
    first_pass = next(x for x in sim["log"] if x["type"] == "pass")
    assert first_pass["bytes"] == 15_000
    assert first_pass["completed"] == ["E2"], "highest utility goes first"
    assert sim["totals"]["downlinked"] == 20_000  # E1 finishes on the next pass (packetised)
    assert sim["totals"]["data_reduction"] == pytest.approx(1 - 20_000 / 200_000)


def test_storage_pressure_degrades_lowest_density_first(cfg):
    c = cfg.patched({"downlink": {"storage_bytes": 20_000, "pass_bytes": 1, "passes_per_sol": 1}})
    items = [_item(1, 10.01, 0.9), _item(2, 10.02, 0.3), _item(3, 10.03, 0.8)]
    sim = simulate(items, [], c, sol_range=(10, 10))
    by = {i["id"]: i for i in sim["items"]}
    assert by["E2"]["final"] in ("compress", "summary_only", "discard")
    assert by["E1"]["final"] == "full_data"
    degr = [x for x in sim["log"] if x["type"] == "degrade"]
    assert degr and degr[0]["item"] == "E2"
    assert all(ev["storage_used"] <= ev["capacity"] for ev in sim["timeline"])


def test_blackout_skips_passes_and_uses_blackout_capacity(cfg):
    c = cfg.patched({"downlink": {"storage_bytes": 10**7, "pass_bytes": 10**6, "passes_per_sol": 2}})
    items = [_item(i, 10.05 + i * 0.1, 0.1 * i) for i in range(1, 8)]
    b = Blackout(start=10.0, duration=1.5, storage_bytes=25_000)
    sim = simulate(items, [(10.2, 1_000_000), (12.0, 5)], c, blackout=b, sol_range=(10, 11))
    assert all(x["type"] != "pass" or not (b.start <= x["t"] < b.end) for x in sim["log"])
    assert any(x["type"] == "pass_missed" for x in sim["log"])
    during = [s for s in sim["timeline"] if s["blackout"]]
    assert during and all(s["storage_used"] <= 25_000 for s in during)
    rep = sim["blackout"]
    assert rep["events_detected"] == 7 and rep["raw_collected"] == 1_000_000
    assert rep["events_retained"] + rep["events_discarded"] == 7
    kept_utils = [i["utility"] for i in sim["items"] if i["id"] in {q["id"] for q in rep["downlink_queue"]}]
    lost_utils = [i["utility"] for i in sim["items"] if i["final"] == "discard"]
    if kept_utils and lost_utils:
        assert min(kept_utils) >= min(lost_utils)


# ------------------------------------------------------------------ benchmark metrics
def _t(h):
    return datetime(2013, 4, 10, tzinfo=timezone.utc) + timedelta(hours=h)


def test_allocator_degrades_to_fit():
    u = Unit("A", "REMS", _t(0), _t(1), 1.0, DownlinkAction.FULL_DATA, {"full_data": 100, "compress": 40, "summary_only": 5, "discard": 0}, 1000)
    [(unit, action, size)] = allocate([u], budget=50)
    assert action == DownlinkAction.COMPRESS and size == 40


def test_metrics_recall_fpr_and_proxy(cfg):
    units = [
        Unit("A", "REMS", _t(0), _t(1), 0.9, DownlinkAction.FULL_DATA, {"full_data": 100, "compress": 40, "summary_only": 5, "discard": 0}, 1000),
        Unit("B", "REMS", _t(5), _t(6), 0.8, DownlinkAction.FULL_DATA, {"full_data": 100, "compress": 40, "summary_only": 5, "discard": 0}, 1000),
        Unit("C", "RAD", _t(9), _t(10), 0.1, DownlinkAction.FULL_DATA, {"full_data": 100, "compress": 40, "summary_only": 5, "discard": 0}, 1000),
    ]
    labels = [
        Label(id="L1", source=LabelSource.SYNTHETIC_ANOMALY, instrument="REMS", t_start=_t(0.5), t_end=_t(0.6), severity="high"),
        Label(id="L2", source=LabelSource.DOCUMENTED_EVENT, instrument="RAD", t_start=_t(9.5), t_end=_t(9.6), severity="high"),
    ]
    sel = allocate(units, budget=200)  # A and B full; C discarded
    m = evaluate(sel, labels, raw_total=3000, fidelity=cfg.compression.fidelity)
    assert m["recall"] == 0.5 and m["recall_high"] == 0.5
    assert m["recall_by_source"] == {"DOCUMENTED_EVENT": 0.0, "SYNTHETIC_ANOMALY": 1.0}
    assert m["retained_unlabeled_rate"] == 0.5          # B kept but unlabeled
    assert m["downlink_bytes"] == 200 and m["data_reduction"] == pytest.approx(1 - 200 / 3000)
    assert m["science_value_per_mb_proxy"] == pytest.approx(3.0 * 1.0 / (200 / 1e6))


# ------------------------------------------------------------------ pipeline + audit reproducibility
def test_pipeline_end_to_end_on_fixture(fixture_run):
    p, r, _ = fixture_run
    assert r.events and all(e.priority and e.proposed_action and e.final_action for e in r.events)
    assert r.simulation["totals"]["downlinked"] <= r.simulation["totals"]["raw_generated"]
    assert r.performance["rows_per_sec"] > 0
    stages = {s["stage"] for s in r.events[0].trace}
    assert {"raw_data", "windowing", "feature_extraction", "candidate_filter", "decision_engine", "gating",
            "priority_engine", "scheduler"} <= stages


def test_audit_reproduces_decisions(fixture_run, cfg):
    from deepsift.core.models import ScientificEvent
    from deepsift.objectives.objective import MissionObjective
    from deepsift.pipeline import effective_decision
    from deepsift.priority.engine import score_event

    p, r, audit = fixture_run
    audit.record_config(cfg)
    audit.record_decisions("TEST-RUN", r.events, r.objective, cfg)
    for e in r.events[:10]:
        rec = audit.decision_record("TEST-RUN", e.id)
        c = audit.get_config(rec["config_version"])
        ev = ScientificEvent.model_validate(rec["event"])
        pb, act, _ = score_event(ev, effective_decision(ev, c), ev.gate or GateStatus.FALLBACK,
                                 MissionObjective.model_validate(rec["objective"]), c)
        assert pb.utility == pytest.approx(rec["priority"]["utility"], abs=1e-12)
        assert act.value == rec["proposed_action"]


def test_config_change_is_recorded(fixture_run, cfg):
    _, _, audit = fixture_run
    after = cfg.patched({"downlink": {"pass_bytes": 12345}})
    changes = audit.record_config_change(cfg, after, note="test")
    assert changes == [{"path": "downlink.pass_bytes", "before": cfg.downlink.pass_bytes, "after": 12345}]
    assert audit.config_changes()[0]["to_version"] == after.version() != cfg.version()


def test_benchmark_runs_and_labels_engine_honestly(fixture_adapter, cfg):
    from deepsift.evaluation.benchmark import run_benchmark
    from deepsift.pipeline import Pipeline

    p = Pipeline(cfg, adapter=fixture_adapter)
    res = run_benchmark(p, cfg, trials=1, save=False)
    s = res["summary"]
    assert set(s) == {"random", "rules", "statistical", "engine", "engine_deep"}
    assert s["engine_deep"]["available"] is False
    assert res["engine"]["is_real_model"] is False
    assert any("mock-heuristic" in c for c in res["caveats"])
    for k in ("random", "rules", "statistical", "engine"):
        assert s[k]["downlink_bytes"]["mean"] <= res["budget_bytes"]


def test_protected_high_utility_products_are_degraded_last(cfg):
    c = cfg.patched({"downlink": {"storage_bytes": 60_000, "pass_bytes": 1, "passes_per_sol": 1}})
    big = _item(1, 10.01, 0.9, full=50_000, comp=20_000, summ=900)       # high utility, poor density
    small = [_item(i, 10.02 + i * 0.001, 0.5, full=8_000, comp=2_000, summ=300) for i in range(2, 6)]
    sim = simulate([big, *small], [], c, sol_range=(10, 10))
    by = {i["id"]: i for i in sim["items"]}
    degr = [x for x in sim["log"] if x["type"] == "degrade"]
    first_protected = next((k for k, x in enumerate(degr) if x["protected"]), len(degr))
    assert all(not x["protected"] for x in degr[:first_protected])
    assert by["E1"]["final"] in ("full_data", "compress")
    unprot = cfg.patched({"downlink": {"storage_bytes": 60_000, "pass_bytes": 1, "passes_per_sol": 1, "protect_utility": 2.0}})
    sim2 = simulate([_item(1, 10.01, 0.9, full=50_000, comp=20_000, summ=900),
                     *[_item(i, 10.02 + i * 0.001, 0.5, full=8_000, comp=2_000, summ=300) for i in range(2, 6)]], [], unprot, sol_range=(10, 10))
    assert {i["id"]: i for i in sim2["items"]}["E1"]["history"], "without protection the low-density big item is degraded"
