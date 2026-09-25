"""DEEPSIFT HTTP API (FastAPI). Local-first: one process holds the current run in memory."""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import polars as pl
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from deepsift.audit.log import AuditLog
from deepsift.core.config import load_config
from deepsift.core.models import DownlinkAction, GateStatus, ScientificEvent
from deepsift.decision.gating import gate
from deepsift.decision.jev import jev_available
from deepsift.decision.questions import QUESTIONS
from deepsift.evaluation.benchmark import EXPERIMENTS_DIR, run_benchmark
from deepsift.evaluation.labels import human_labels
from deepsift.objectives.objective import MissionObjective, load_objectives, save_custom
from deepsift.pipeline import Pipeline, RunResult, effective_decision
from deepsift.priority.counterfactual import counterfactuals
from deepsift.priority.engine import score_event
from deepsift.simulation.scheduler import Blackout

app = FastAPI(title="DEEPSIFT", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class State:
    def __init__(self):
        self.lock = threading.RLock()
        self.audit = AuditLog()
        self.cfg = load_config()
        self.pipeline: Pipeline | None = None
        self.run: RunResult | None = None
        self.error: str | None = None
        self.benchmark_running = False

    def boot(self):
        with self.lock:
            self.audit.record_config(self.cfg)
            self.pipeline = Pipeline(self.cfg, audit=self.audit)
            self.run = self.pipeline.run(sols=demo_sols(), note="api boot")

    def rescore(self, objective: MissionObjective, note: str):
        """Objective / priority / gating changes: no raw pipeline, no engine calls."""
        p, r = self.pipeline, self.run
        for e in r.events:  # gating thresholds may have changed; escalated verdicts are kept as recorded
            if e.decision is not None and e.gate != GateStatus.ESCALATED:
                e.gate, _, e.gate_reason = gate(e.decision, self.cfg, p.deep.available)
        p.score(r.events, objective)
        r.simulation = p.simulate(r.events, r.detection)
        r.objective = objective
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-rescore-" + uuid.uuid4().hex[:4]
        self.audit.record_run(run_id, self.cfg, p.engine.name, p.deep.name, objective.id, r.metadata["data_source"],
                              r.metadata["sols"], len(r.events), {}, note)
        self.audit.record_decisions(run_id, r.events, objective, self.cfg)
        r.run_id = run_id


def demo_sols() -> list[int]:
    """Mission Control replays the calibration segment (data/raw now also holds validation/test sols)."""
    from deepsift.evaluation.segments import segments

    seg = segments("calibration")[0]
    return list(range(seg.eval[0], seg.eval[1] + 1))


S = State()


@app.on_event("startup")
def _startup():
    try:
        S.boot()
    except Exception as exc:  # noqa: BLE001 — surface the error in /api/status instead of crashing
        S.error = f"{type(exc).__name__}: {exc}"


def _need_run() -> RunResult:
    if S.run is None:
        raise HTTPException(503, S.error or "pipeline still starting")
    return S.run


def _event(eid: str) -> ScientificEvent:
    r = _need_run()
    for e in r.events:
        if e.id == eid:
            return e
    raise HTTPException(404, f"event {eid} not found")


def _row(e: ScientificEvent, cfg) -> dict:
    d = effective_decision(e, cfg)
    et = d.answers.get("event_type")
    sv = d.answers.get("science_value")
    return {
        "id": e.id, "instrument": e.instrument, "sol": e.sol, "sol_start": e.sol_start, "sol_end": e.sol_end,
        "t_start": e.timestamp_start, "t_end": e.timestamp_end, "sensors": e.sensors,
        "event_type": et.choice if et else None, "type_probs": et.probabilities if et else {},
        "science_value": sv.choice if sv else None,
        "engine_event_type": e.decision.answers["event_type"].choice if e.decision and "event_type" in e.decision.answers else None,
        "deviation": e.features.deviation_score, "rarity": e.features.rarity_score, "duration_s": e.features.duration_s,
        "novelty": e.features.novelty, "gate": e.gate.value if e.gate else None,
        "confidence": e.priority.confidence if e.priority else None,
        "utility": e.priority.utility if e.priority else None,
        "mission_relevance": e.priority.mission_relevance if e.priority else None,
        "anomaly_strength": e.priority.anomaly_strength if e.priority else None,
        "science_expected": e.priority.science_value if e.priority else None,
        "proposed_action": e.proposed_action.value if e.proposed_action else None,
        "final_action": e.final_action.value if e.final_action else None, "status": e.status,
        "bytes": e.bytes.model_dump(), "downlink_bytes": e.downlink_bytes,
        "synthetic": bool(e.synthetic_injection_ids), "injection_ids": e.synthetic_injection_ids,
        "correlated_channels": e.features.correlated_channels,
    }


# ---------------------------------------------------------------- status / mission
@app.get("/api/status")
def status():
    r = S.run
    return {
        "online": r is not None, "error": S.error,
        "engine": S.pipeline.engine.describe() if S.pipeline else None,
        "jev_key_present": jev_available(),
        "deep_provider": S.pipeline.deep.name if S.pipeline else None,
        "deep_available": bool(S.pipeline and S.pipeline.deep.available),
        "run_id": r.run_id if r else None, "config_version": S.cfg.version(),
        "objective": r.objective.model_dump() if r else None,
        "data_source": r.metadata["data_source"] if r else None,
        "benchmark_running": S.benchmark_running,
    }


@app.get("/api/mission")
def mission():
    r = _need_run()
    return {**r.metadata, "run_id": r.run_id, "timings_ms": r.timings_ms, "performance": r.performance,
            "engine": r.engine, "deep_provider": r.deep_provider, "questions": {k: v.__dict__ for k, v in QUESTIONS.items()}}


@app.get("/api/series")
def series(channel: str, sol_from: float | None = None, sol_to: float | None = None, max_points: int = 1500):
    r = _need_run()
    s = r.detection.samples.filter(pl.col("channel") == channel)
    s = s.with_columns((pl.col("sol") + pl.col("lmst_s") / 86400).alias("solf"))
    if sol_from is not None:
        s = s.filter(pl.col("solf") >= sol_from)
    if sol_to is not None:
        s = s.filter(pl.col("solf") <= sol_to)
    if s.is_empty():
        return {"channel": channel, "points": [], "windows": []}
    s = s.sort("solf")
    n = s.height
    if n > max_points:
        lo, hi = float(s["solf"].min()), float(s["solf"].max())
        width = (hi - lo) / max_points or 1e-6
        s = s.with_columns(((pl.col("solf") - lo) / width).floor().cast(pl.Int64).alias("b")).group_by("b").agg(
            pl.col("solf").mean(), pl.col("value").mean().alias("v"), pl.col("value").min().alias("lo"),
            pl.col("value").max().alias("hi"), pl.len().alias("n"), pl.col("injection_id").drop_nulls().first().alias("inj"),
        ).sort("solf")
        pts = [[round(a, 6), round(b, 4), round(c, 4), round(d, 4), k] for a, b, c, d, k in s.select("solf", "v", "lo", "hi", "inj").iter_rows()]
    else:
        pts = [[round(a, 6), round(b, 4), round(b, 4), round(b, 4), k] for a, b, k in s.select("solf", "value", "injection_id").iter_rows()]
    w = r.detection.windows.filter(pl.col("channel") == channel).with_columns(
        (pl.col("sol") + pl.col("lmst_mid") / 86400).alias("solf"))
    if sol_from is not None:
        w = w.filter(pl.col("solf") >= sol_from)
    if sol_to is not None:
        w = w.filter(pl.col("solf") <= sol_to)
    wins = [[round(a, 6), round(b or 0, 3), round(c, 4) if c is not None else None, bool(f)]
            for a, b, c, f in w.sort("solf").select("solf", "robust_z", "baseline", "flagged").iter_rows()]
    return {"channel": channel, "raw_points": n, "points": pts, "windows": wins,
            "columns": {"points": ["sol", "mean", "min", "max", "injection_id"], "windows": ["sol", "robust_z", "baseline", "flagged"]}}


# ---------------------------------------------------------------- events
@app.get("/api/events")
def events():
    r = _need_run()
    rows = [_row(e, S.cfg) for e in r.events]
    return {"objective": r.objective.id, "events": rows, "simulation_totals": r.simulation["totals"]}


@app.get("/api/events/{eid}")
def event_detail(eid: str):
    r = _need_run()
    e = _event(eid)
    d = effective_decision(e, S.cfg)
    cf = counterfactuals(e, d, e.gate or GateStatus.FALLBACK, r.objective, S.cfg, S.pipeline.objectives)
    return {
        "event": e.model_dump(mode="json"), "row": _row(e, S.cfg), "effective_decision": d.model_dump(mode="json"),
        "effective_source": "engine" if d is e.decision else ("deep+engine" if e.gate == GateStatus.ESCALATED and e.deep and not e.deep.error else "deterministic rules"),
        "counterfactuals": cf, "audit": S.audit.decisions(event_id=eid, limit=20),
        "sim_item": next((i for i in r.simulation["items"] if i["id"] == eid), None),
    }


# ---------------------------------------------------------------- objectives
@app.get("/api/objectives")
def objectives():
    return {"active": _need_run().objective.id, "objectives": {k: v.model_dump() for k, v in S.pipeline.objectives.items()}}


class ObjectiveCompare(BaseModel):
    objective_id: str | None = None
    custom: MissionObjective | None = None
    apply: bool = False


@app.post("/api/objectives/compare")
def compare_objective(req: ObjectiveCompare):
    """Before/after rankings under another objective, computed from stored decisions only."""
    r = _need_run()
    with S.lock:
        target = req.custom or S.pipeline.objectives.get(req.objective_id or "")
        if target is None:
            raise HTTPException(404, "unknown objective")
        if req.custom:
            req.custom.custom = True
            save_custom(req.custom)
            S.pipeline.objectives = load_objectives()
        t0 = time.perf_counter()
        before = {e.id: (e.priority.utility, e.proposed_action.value) for e in r.events}
        after = {}
        for e in r.events:
            pb, act, _ = score_event(e, effective_decision(e, S.cfg), e.gate or GateStatus.FALLBACK, target, S.cfg)
            after[e.id] = (pb.utility, act.value)
        ms = (time.perf_counter() - t0) * 1000
        rank_b = {eid: i + 1 for i, eid in enumerate(sorted(before, key=lambda k: -before[k][0]))}
        rank_a = {eid: i + 1 for i, eid in enumerate(sorted(after, key=lambda k: -after[k][0]))}
        rows = [{"id": k, "utility_before": round(before[k][0], 4), "utility_after": round(after[k][0], 4),
                 "action_before": before[k][1], "action_after": after[k][1], "rank_before": rank_b[k], "rank_after": rank_a[k]}
                for k in before]
        rows.sort(key=lambda x: x["rank_after"])
        if req.apply:
            S.rescore(target, note=f"objective → {target.id}")
        return {"from": r.objective.id if not req.apply else None, "to": target.id, "rescore_ms": ms, "rows": rows,
                "applied": req.apply, "engine_calls": 0}


# ---------------------------------------------------------------- simulation
class SimReq(BaseModel):
    blackout_start: float | None = None
    duration_sols: float | None = None
    storage_bytes: int | None = None


@app.get("/api/simulation")
def simulation():
    return _need_run().simulation


@app.post("/api/simulate")
def simulate(req: SimReq):
    r = _need_run()
    b = None
    if req.blackout_start is not None:
        b = Blackout(start=req.blackout_start, duration=req.duration_sols or S.cfg.blackout.duration_sols,
                     storage_bytes=req.storage_bytes or S.cfg.blackout.storage_bytes)
    with S.lock:
        events = [e.model_copy(deep=True) for e in r.events]
        sim = S.pipeline.simulate(events, r.detection, b)
    return sim


# ---------------------------------------------------------------- config
@app.get("/api/config")
def get_config():
    return {"version": S.cfg.version(), "config": S.cfg.model_dump(mode="json"), "changes": S.audit.config_changes(50)}


class ConfigPatch(BaseModel):
    patch: dict
    note: str = ""


@app.put("/api/config")
def put_config(req: ConfigPatch):
    with S.lock:
        before = S.cfg
        try:
            after = before.patched(req.patch)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(422, str(exc)) from exc
        changes = S.audit.record_config_change(before, after, note=req.note)
        S.cfg = after
        S.pipeline.cfg = after
        heavy = any(c["path"].split(".")[0] in ("detection", "compression", "decision_engine", "deep_analysis") for c in changes)
        t0 = time.perf_counter()
        if heavy:
            S.pipeline = Pipeline(after, audit=S.audit)
            S.run = S.pipeline.run(sols=demo_sols(), objective_id=S.run.objective.id if S.run else None, note="config change (full rerun)")
        else:
            S.rescore(S.run.objective, note="config change (rescore)")
        return {"version": after.version(), "changes": changes, "rerun": "full" if heavy else "rescore",
                "ms": (time.perf_counter() - t0) * 1000}


# ---------------------------------------------------------------- audit
@app.get("/api/audit/decisions")
def audit_decisions(event_id: str | None = None, run_id: str | None = None, limit: int = 300):
    return S.audit.decisions(event_id=event_id, run_id=run_id, limit=limit)


@app.get("/api/audit/runs")
def audit_runs():
    return S.audit.runs()


class ReproReq(BaseModel):
    run_id: str
    event_id: str


@app.post("/api/audit/reproduce")
def reproduce(req: ReproReq):
    rec = S.audit.decision_record(req.run_id, req.event_id)
    if not rec:
        raise HTTPException(404, "no such decision")
    cfg = S.audit.get_config(rec["config_version"])
    if cfg is None:
        raise HTTPException(404, "config version not stored")
    e = ScientificEvent.model_validate(rec["event"])
    obj = MissionObjective.model_validate(rec["objective"])
    pb, act, _ = score_event(e, effective_decision(e, cfg), e.gate or GateStatus.FALLBACK, obj, cfg)
    stored_u = rec["priority"]["utility"] if rec["priority"] else None
    return {
        "run_id": req.run_id, "event_id": req.event_id, "config_version": rec["config_version"], "objective": obj.id,
        "stored": {"utility": stored_u, "proposed_action": rec["proposed_action"]},
        "recomputed": {"utility": pb.utility, "proposed_action": act.value},
        "match": stored_u is not None and abs(stored_u - pb.utility) < 1e-9 and act.value == rec["proposed_action"],
        "note": "recomputed from the stored event, stored engine answers, stored objective and stored config version; "
                "the decision engine is not re-queried",
    }


# ---------------------------------------------------------------- labels
class LabelReq(BaseModel):
    event_id: str
    severity: str = "medium"
    expected_type: str | None = None
    note: str = ""
    author: str = "researcher"


@app.post("/api/labels")
def add_label(req: LabelReq):
    e = _event(req.event_id)
    label = {"label_id": f"HUM-{uuid.uuid4().hex[:8]}", "source": "HUMAN_LABEL", "event_id": e.id,
             "t_start": e.timestamp_start, "t_end": e.timestamp_end, "instrument": e.instrument,
             "expected_type": req.expected_type, "severity": req.severity, "note": req.note, "author": req.author}
    S.audit.add_label(label)
    return label


@app.get("/api/labels")
def labels():
    return S.audit.labels()


# ---------------------------------------------------------------- experiments
class ExpReq(BaseModel):
    trials: int = 3


@app.post("/api/experiments")
def run_experiment(req: ExpReq):
    if S.benchmark_running:
        raise HTTPException(409, "a benchmark is already running")
    S.benchmark_running = True
    try:
        p = Pipeline(S.cfg, engine=S.pipeline.engine, deep=S.pipeline.deep)
        return run_benchmark(p, S.cfg, trials=max(1, min(req.trials, 10)), human=human_labels(S.audit.labels()))
    finally:
        S.benchmark_running = False


@app.get("/api/experiments")
def list_experiments():
    out = []
    for f in sorted(EXPERIMENTS_DIR.glob("*.json"), reverse=True)[:30]:
        d = json.loads(f.read_text())
        out.append({"id": d["id"], "created_at": d["created_at"], "engine": d["engine"], "trials": d["trials"],
                    "config_version": d["config_version"], "data_source": d["data_source"], "summary": d["summary"]})
    return out


@app.get("/api/experiments/{xid}")
def get_experiment(xid: str):
    f = EXPERIMENTS_DIR / f"{xid}.json"
    if not f.exists():
        raise HTTPException(404, "not found")
    return json.loads(f.read_text())


@app.get("/api/actions")
def actions():
    return [a.value for a in DownlinkAction]


# ---------------------------------------------------------------- Phase-2 study runs (read-only)
from fastapi.responses import FileResponse  # noqa: E402

from deepsift.core.config import ROOT as _ROOT  # noqa: E402

RUNS_ROOT = _ROOT / "artifacts" / "runs"
FIG_ROOT = _ROOT / "artifacts" / "figures"


def _run_dir(rid: str):
    d = (RUNS_ROOT / rid).resolve()
    if RUNS_ROOT.resolve() not in d.parents or not (d / "manifest.json").exists():
        raise HTTPException(404, "unknown run")
    return d


STUDY_MANIFEST_KEYS = ("run_id", "split", "started_at", "config_version")
_log = logging.getLogger("deepsift.api.runs")
LAST_RUNS_SKIPPED: list[dict] = []     # why each folder was left out of the most recent /api/runs listing


def _study_manifest(d: Path) -> tuple[dict | None, dict | None]:
    """(manifest, None) for a study run; (None, skip-record) otherwise. Never modifies the folder.

    A study run (scripts/run_study.py) always writes results.json next to its manifest. Folders without it — Jev
    smoke/probe/pilot runs, which write their own manifest schema — are not study runs and are skipped quietly.
    A folder WITH results.json whose manifest is unreadable or incomplete is a malformed study run: skipped, logged.
    """
    rid = d.name
    if not (d / "results.json").exists():
        return None, {"run_id": rid, "kind": "not_a_study_run", "reason": "no results.json (e.g. Jev smoke/probe/pilot folder)"}
    try:
        m = json.loads((d / "manifest.json").read_text())
    except (OSError, ValueError) as exc:
        return None, {"run_id": rid, "kind": "malformed_study_run", "reason": f"unreadable manifest.json: {exc}"}
    missing = [k for k in STUDY_MANIFEST_KEYS if k not in m]
    if missing:
        return None, {"run_id": rid, "kind": "malformed_study_run", "reason": f"manifest.json missing {missing}"}
    return m, None


@app.get("/api/runs")
def list_runs(response: Response):
    out, skipped = [], []
    for mf in sorted(RUNS_ROOT.glob("*/manifest.json"), reverse=True):
        m, skip = _study_manifest(mf.parent)
        if skip:
            skipped.append(skip)
            if skip["kind"] == "malformed_study_run":
                _log.warning("skipping study run %s: %s", skip["run_id"], skip["reason"])
            continue
        out.append({"run_id": m["run_id"], "split": m["split"], "started_at": m["started_at"], "git": m.get("git"),
                    "config_version": m["config_version"], "jev_status": m.get("jev_status"),
                    "engines": [e["key"] for e in m.get("engines", [])],
                    "figures": sorted(p.name for p in (FIG_ROOT / m["run_id"]).glob("*.png")) if (FIG_ROOT / m["run_id"]).exists() else []})
    LAST_RUNS_SKIPPED[:] = skipped
    response.headers["X-DEEPSIFT-Skipped-Runs"] = str(len(skipped))
    response.headers["X-DEEPSIFT-Malformed-Study-Runs"] = str(sum(1 for x in skipped if x["kind"] == "malformed_study_run"))
    return out


@app.get("/api/runs/{rid}/manifest")
def run_manifest(rid: str):
    m = json.loads((_run_dir(rid) / "manifest.json").read_text())
    m["datasets"]["raw_products"].pop("per_file", None)
    return m


@app.get("/api/runs/{rid}/results")
def run_results(rid: str):
    r = json.loads((_run_dir(rid) / "results.json").read_text())
    for row in r.get("storage", []):
        row.pop("preserved_detail", None)
    return r


@app.get("/api/runs/{rid}/failures")
def run_failures(rid: str):
    f = json.loads((_run_dir(rid) / "failures.json").read_text())
    return {cat: [{k: v for k, v in ex.items() if k != "event"} | {"has_event": "event" in ex} for ex in items]
            for cat, items in f.items()}


@app.get("/api/runs/{rid}/figures/{name}")
def run_figure(rid: str, name: str):
    p = (FIG_ROOT / rid / name).resolve()
    if (FIG_ROOT / rid).resolve() not in p.parents or not p.exists() or p.suffix not in (".png", ".csv", ".txt"):
        raise HTTPException(404, "no such figure")
    return FileResponse(p)


@app.get("/api/runs/{rid}/events/{eid}")
def run_event(rid: str, eid: str):
    """Event Inspector view for a failure-analysis example (rules scoring + computed counterfactuals)."""
    f = json.loads((_run_dir(rid) / "failures.json").read_text())
    ex = next((x for items in f.values() for x in items if x.get("event_id") == eid and "event" in x), None)
    if ex is None:
        raise HTTPException(404, "event not stored in this run's failure examples")
    from deepsift.priority.engine import explain, rules_decision

    e = ScientificEvent.model_validate(ex["event"])
    e.gate = GateStatus.FALLBACK
    d = rules_decision(e, S.cfg)
    obj = S.pipeline.objectives[S.cfg.objective] if S.pipeline else load_objectives()[S.cfg.objective]
    pb, act, notes = score_event(e, d, GateStatus.FALLBACK, obj, S.cfg)
    e.priority, e.proposed_action, e.final_action = pb, act, act
    e.gate_reason = "study replay: deterministic rules view (engine answers shown separately)"
    e.explanation = explain(e, pb, act, e.gate_reason, notes)
    cf = counterfactuals(e, d, GateStatus.FALLBACK, obj, S.cfg, S.pipeline.objectives if S.pipeline else load_objectives())
    return {"event": e.model_dump(mode="json"), "row": _row(e, S.cfg), "effective_decision": d.model_dump(mode="json"),
            "effective_source": "deterministic rules (study replay)", "counterfactuals": cf, "audit": [], "sim_item": None,
            "study": {k: v for k, v in ex.items() if k != "event"}}
