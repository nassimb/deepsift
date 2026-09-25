"""Phase-2 study runner: real + synthetic evaluation, budget curve, storage/policy curve,
gating-threshold sweep, confidence calibration, failure analysis, latency and cost.

Writes artifacts/runs/<run_id>/{manifest.json, results.json, rows.jsonl, failures.json, jev_calls.jsonl}.
Nothing here reads a label before a strategy has produced its selection.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import time
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from deepsift.core.config import ROOT, Config
from deepsift.core.models import DownlinkAction, LabelSource
from deepsift.decision.gating import gate
from deepsift.decision.jev import JevDecisionEngine, jev_available, sdk_version
from deepsift.decision.mock import MockDecisionEngine
from deepsift.evaluation.benchmark import allocate, event_units
from deepsift.evaluation.labels import Label
from deepsift.evaluation.local_edge import LocalEdgeModel
from deepsift.evaluation.metrics2 import WindowIndex, ece, evaluate_selection, mean_ci, pareto_front, percentiles
from deepsift.evaluation.segments import eval_filter_events, eval_windows, load_segment, segments
from deepsift.evaluation.strategies import (
    ORACLE_LABEL, StrategyOutput, engine_strategies, local_edge_strategy, oracle_strategy, random_strategy,
    rules_plus_statistical, rules_strategy, statistical_strategy, unavailable,
)
from deepsift.evaluation.sweeps import plan_sweep_batch
from deepsift.features.detect import detect_events
from deepsift.features.novelty import assign_novelty
from deepsift.objectives.objective import load_objectives
from deepsift.priority.engine import rules_decision, score_event
from deepsift.simulation.scheduler import Blackout, Item, simulate

BUDGET_FRACTIONS = [0.001, 0.0025, 0.005, 0.01, 0.02, 0.05, 0.10, 0.25]
REFERENCE_BUDGET = 0.005          # declared operating point for sweeps / failure analysis
RANDOM_SEEDS = 30
STORAGE_BYTES = [16_384, 32_768, 65_536, 131_072, 262_144, 524_288, 1_048_576, 2_097_152, 4_194_304, 8_388_608]
GATING_GRID = [(a, u) for a in (0.5, 0.6, 0.7, 0.8, 0.9, 0.95) for u in (0.3, 0.5, 0.6, 0.7, 0.8) if u <= a]
JEV_VARIANTS = ["full_context", "no_mission_objective", "minimal", "numeric_only", "single_decision"]


@dataclass
class EngineSpec:
    key: str             # e.g. MOCK, JEV_FULL_CONTEXT
    engine: object
    single: bool = False


def git_state() -> dict:
    def run(*a):
        try:
            return subprocess.check_output(["git", *a], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
        except Exception:  # noqa: BLE001
            return None
    porcelain = run("status", "--porcelain") or ""
    return {"commit": run("rev-parse", "HEAD"), "dirty": bool(porcelain), "describe": run("describe", "--always", "--dirty"),
            "dirty_paths": [ln[3:] for ln in porcelain.splitlines()][:200]}


def dataset_hashes(sols: list[int]) -> dict:
    man = json.loads((ROOT / "data" / "raw" / "manifest.json").read_text())["files"]
    rel = {k: v["sha256"] for k, v in sorted(man.items()) if v.get("sol") in set(sols)}
    return {"files": len(rel), "digest": hashlib.sha256(json.dumps(rel, sort_keys=True).encode()).hexdigest(), "per_file": rel}


def system_info() -> dict:
    cpu = None
    try:
        cpu = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip()
    except Exception:  # noqa: BLE001
        cpu = platform.processor()
    import polars
    return {"platform": platform.platform(), "python": platform.python_version(), "cpu": cpu, "polars": polars.__version__,
            "typesafe_sdk": sdk_version()}


def synthetic_labels_with_meta(injections) -> tuple[list[Label], dict]:
    labels, meta = [], {}
    for inj in injections:
        inst = "RAD" if set(inj.channels) <= {"dose_b", "dose_e"} else "REMS"
        labels.append(Label(id=inj.id, source=LabelSource.SYNTHETIC_ANOMALY, instrument=inst, t_start=inj.t_start,
                            t_end=inj.t_end, expected_type=inj.expected_type, severity=inj.severity))
        pad = 1200.0 if inst == "RAD" else 0.0   # RAD injections hit observations starting within ±20 min
        meta[inj.id] = {"subtype": inj.kind, "bucket": inj.meta.get("bucket"), "confidence": "documented_uncertainty",
                        "tolerance_before_s": pad, "tolerance_after_s": pad, "magnitude": {k: v for k, v in inj.meta.items() if k != "abs_magnitude"}}
    return labels, meta


class Study:
    def __init__(self, cfg: Config, split: str, run_id: str | None = None, n_batches: int = 25, use_jev: bool = True,
                 jev_variants: list[str] | None = None, experiments: set[str] | None = None, out_root: Path | None = None,
                 budget=None, use_cache: bool = True):
        self.cfg = cfg
        self.split = split
        self.run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + f"-{split}-" + uuid.uuid4().hex[:4]
        self.out = (out_root or ROOT / "artifacts" / "runs") / self.run_id
        self.out.mkdir(parents=True, exist_ok=True)
        self.n_batches = n_batches
        self.experiments = experiments or {"real", "synthetic", "storage", "gating", "calibration"}
        self.objective = load_objectives()[cfg.objective]
        self.local = LocalEdgeModel.load(ROOT / "artifacts" / "models" / "local_edge.json")
        self.engines = [EngineSpec("MOCK", MockDecisionEngine())]
        self.jev_status = "not requested"
        if use_jev:
            if jev_available():
                for v in (jev_variants or JEV_VARIANTS):
                    eng = JevDecisionEngine(model=cfg.decision_engine.jev_model, timeout_s=cfg.decision_engine.timeout_s,
                                            max_concurrency=cfg.decision_engine.max_concurrency,
                                            price_per_mtok_input_usd=cfg.decision_engine.price_per_mtok_input_usd,
                                            variant=v, call_log=self.out / "jev_calls.jsonl", run_id=self.run_id,
                                            budget=budget, use_cache=use_cache)
                    self.engines.append(EngineSpec("JEV_" + v.upper(), eng, single=(v == "single_decision")))
                self.jev_status = "enabled"
            else:
                self.jev_status = "UNAVAILABLE: OPENROUTER_API_KEY not set"
        self.git_at_start = git_state()          # captured before any work: the code actually executed
        self.rows: list[dict] = []
        self.calib: dict[str, dict[str, list]] = {}
        self.failures: dict[str, list] = {}
        self.latency: dict[str, list[float]] = {}
        self.timing: dict[str, float] = {}
        self.jev_usage = {"calls": 0, "errors": 0, "cost_usd": 0.0, "input_tokens": 0}

    # ------------------------------------------------------------------ helpers
    def _engine_decisions(self, spec: EngineSpec, events, sd):
        if not events:
            return []
        t0 = time.perf_counter()
        ds = spec.engine.decide(events, sd.mission.metadata.short_name, sd.mission.metadata.location,
                                objective=self.objective.model_dump(mode="json"))
        self.timing[f"engine_wall_ms:{spec.key}"] = self.timing.get(f"engine_wall_ms:{spec.key}", 0) + (time.perf_counter() - t0) * 1000
        self.latency.setdefault(f"engine_call_ms:{spec.key}", []).extend(d.latency_ms for d in ds)
        if spec.key != "MOCK":
            self.jev_usage["calls"] += len(ds)
            self.jev_usage["live_calls"] = sum(sp.engine.stats["live_calls"] for sp in self.engines if sp.key != "MOCK")
            self.jev_usage["cache_hits"] = sum(sp.engine.stats["cache_hits"] for sp in self.engines if sp.key != "MOCK")
            self.jev_usage["errors"] += sum(1 for d in ds if d.error)
            self.jev_usage["cost_usd"] += sum(d.cost_usd or 0 for d in ds)
            self.jev_usage["input_tokens"] += sum(d.input_tokens or 0 for d in ds)
        return ds

    def _strategies(self, det, sd, events, iw, labels, label_meta, engine_decisions) -> list[StrategyOutput]:
        out = [statistical_strategy(iw, det.windows, self.cfg.priority.anomaly_scale),
               rules_strategy(events, self.objective, self.cfg),
               rules_plus_statistical(events, iw, det.windows, self.objective, self.cfg),
               local_edge_strategy(events, self.local, self.cfg)]
        for spec in self.engines:
            ds = engine_decisions[spec.key]
            for s in engine_strategies(events, ds, self.objective, self.cfg, spec.key, single_decision=spec.single):
                s.name = f"{spec.key}/{s.name}"
                out.append(s)
        # measured per-event latency: priority/rules computation, and complete routing per engine
        pre = self._pre_ms_per_event
        rules_lat = out[1].per_unit_latency_ms
        self.latency.setdefault("priority_ms_per_event", []).extend(rules_lat)
        for spec in self.engines:
            eng_lat = [d.latency_ms for d in engine_decisions[spec.key]]
            self.latency.setdefault(f"routing_ms_per_event:{spec.key}", []).extend(
                pre + e + p for e, p in zip(eng_lat, rules_lat))
        self.latency.setdefault("routing_ms_per_event:RULES", []).extend(pre + p for p in rules_lat)
        self.latency.setdefault("routing_ms_per_event:LOCAL_EDGE", []).extend(pre + p for p in out[3].per_unit_latency_ms)
        out.append(unavailable("ENGINE_PLUS_DEEP", "deep analysis disabled in Phase 2 (no Anthropic spend until the Jev benchmark indicates what to escalate)"))
        tol = {lid: (m.get("tolerance_before_s", 0), m.get("tolerance_after_s", 0)) for lid, m in label_meta.items()}
        out.append(oracle_strategy(iw, labels, tol))
        return out

    def _evaluate_all(self, dataset, sd, batch, strategies, iw, labels, label_meta, raw_total, events=None):
        widx = WindowIndex(iw)
        detected = {lab.id for lab in labels if any(self._overlap(e, lab, label_meta) for e in (events or []))} if events is not None else None
        fid = self.cfg.compression.fidelity
        # RANDOM: one unit list per seed (ordering is budget-independent), re-used for every budget
        seg_seed = int(hashlib.sha256(f"{sd.segment.id}:{batch}".encode()).hexdigest()[:6], 16) * 100
        base = random_strategy(iw, 0).units
        rand_orders = []
        for seed in range(RANDOM_SEEDS):
            rng = __import__("random").Random(seg_seed + seed)
            rand_orders.append([replace(u, utility=rng.random()) for u in base])
        for frac in BUDGET_FRACTIONS:
            budget = int(frac * raw_total)
            for s in strategies:
                if not s.available:
                    continue
                m = evaluate_selection(allocate(s.units, budget), labels, label_meta, widx, raw_total, fid, detected)
                self.rows.append(self._row(dataset, sd, batch, s.name, frac, None, m))
            for seed, units in enumerate(rand_orders):
                m = evaluate_selection(allocate(units, budget), labels, label_meta, widx, raw_total, fid, detected)
                self.rows.append(self._row(dataset, sd, batch, "RANDOM", frac, seed, m))

    @staticmethod
    def _row(dataset, sd, batch, strategy, frac, seed, m) -> dict:
        return {"dataset": dataset, "segment": sd.segment.id, "batch": batch, "strategy": strategy, "budget_fraction": frac,
                "seed": seed, **{k: v for k, v in m.items() if k not in ("per_label",)}, "per_label": m["per_label"]}

    # ------------------------------------------------------------------ experiments
    def run_segment(self, seg):
        t0 = time.perf_counter()
        sd = load_segment(seg, self.cfg.detection.rems_window_s, self.cfg.compression.decimation_factor, self.cfg.compression.zlib_level)
        self.timing[f"load_ms:{seg.id}"] = (time.perf_counter() - t0) * 1000
        t1 = time.perf_counter()
        det0 = detect_events(sd.mission, sd.adapter, self.cfg)
        assign_novelty(det0.events)
        pre_ms = (time.perf_counter() - t1) * 1000
        self.timing[f"detect_ms:{seg.id}"] = pre_ms
        events0 = eval_filter_events(det0.events, sd)
        iw0 = eval_windows(det0.instrument_windows, sd)
        raw0 = int(iw0["raw"].sum() or 0)
        # local preprocessing latency amortized per candidate event (measured batch time / events)
        self._pre_ms_per_event = pre_ms / max(len(det0.events), 1)
        self.latency.setdefault("preprocessing_ms_per_event", []).extend([self._pre_ms_per_event] * len(events0))

        if "real" in self.experiments or "storage" in self.experiments or "gating" in self.experiments:
            dec0 = {spec.key: self._engine_decisions(spec, events0, sd) for spec in self.engines}
            strat0 = self._strategies(det0, sd, events0, iw0, sd.labels, sd.label_meta, dec0)
            if "real" in self.experiments:
                self._evaluate_all("real", sd, None, strat0, iw0, sd.labels, sd.label_meta, raw0, events0)
                self._failure_examples("real", sd, events0, strat0, sd.labels, sd.label_meta, iw0, raw0)
            if "storage" in self.experiments:
                self._storage_curve("real", sd, events0, strat0, sd.labels, sd.label_meta)
            if "gating" in self.experiments:
                self._gating_sweep("real", sd, events0, dec0, iw0, sd.labels, sd.label_meta, raw0)
            if "calibration" in self.experiments:
                self._calibration("real", events0, dec0, sd.labels, sd.label_meta)

        if "synthetic" in self.experiments:
            n = max(10, int(0.8 * (seg.eval[1] - seg.eval[0] + 1)))
            floors = self.cfg.detection.min_sigma or {}
            base_seed = int(hashlib.sha256(f"{self.split}:{seg.id}".encode()).hexdigest()[:8], 16) % 1_000_000
            for b in range(self.n_batches):
                inj = plan_sweep_batch(sd.mission.samples, det0.windows, seg.eval, n, base_seed + b, floors, f"{seg.id}-B{b:02d}")
                t2 = time.perf_counter()
                det = detect_events(sd.mission, sd.adapter, self.cfg, injections=inj)
                assign_novelty(det.events)
                self._pre_ms_per_event = (time.perf_counter() - t2) * 1000 / max(len(det.events), 1)
                events = eval_filter_events(det.events, sd)
                iw = eval_windows(det.instrument_windows, sd)
                raw = int(iw["raw"].sum() or 0)
                labels, meta = synthetic_labels_with_meta(inj)
                dec = {spec.key: self._engine_decisions(spec, events, sd) for spec in self.engines}
                strat = self._strategies(det, sd, events, iw, labels, meta, dec)
                self._evaluate_all("synthetic", sd, b, strat, iw, labels, meta, raw, events)
                self._failure_examples("synthetic", sd, events, strat, labels, meta, iw, raw)
                if "calibration" in self.experiments:
                    self._calibration("synthetic", events, dec, labels, meta)
                if "gating" in self.experiments and b < 5:
                    self._gating_sweep("synthetic", sd, events, dec, iw, labels, meta, raw)
                if "storage" in self.experiments and b == 0:
                    self._storage_curve("synthetic", sd, events, strat, labels, meta)
                self.rows_injections = getattr(self, "rows_injections", []) + [
                    {"id": i.id, "segment": seg.id, "batch": b, "kind": i.kind, "channels": i.channels, "duration_s": i.duration_s,
                     **{k: v for k, v in i.meta.items() if k != "abs_magnitude"}} for i in inj]

    def _gating_sweep(self, dataset, sd, events, decs, iw, labels, meta, raw):
        budget = int(REFERENCE_BUDGET * raw)
        widx = WindowIndex(iw)
        for spec in self.engines:
            if spec.single:
                continue
            ds = decs[spec.key]
            for auto, unc in GATING_GRID:
                cfg = self.cfg.patched({"gating": {"auto_threshold": auto, "uncertain_threshold": unc}})
                evs, deep_would = [], 0
                for e, d in zip(events, ds):
                    ev = e.model_copy(deep=True)
                    st, conf, _ = gate(d, cfg, deep_available=False)
                    if st.value == "fallback":
                        deep_would += 1
                    eff = rules_decision(ev, cfg) if st.value in ("fallback", "engine_error") else d
                    pb, act, _ = score_event(ev, eff, st, self.objective, cfg)
                    ev.priority, ev.proposed_action = pb, act
                    evs.append(ev)
                m = evaluate_selection(allocate(event_units(evs), budget), labels, meta, widx, raw, cfg.compression.fidelity)
                self.rows.append({"dataset": dataset, "experiment": "gating", "segment": sd.segment.id, "engine": spec.key,
                                  "auto": auto, "uncertain": unc, "would_escalate": deep_would, "events": len(evs),
                                  **{k: m[k] for k in ("tolerant_recall", "strict_recall", "high_tolerant_recall", "precision_lower_bound",
                                                       "downlink_bytes", "false_positive_units", "retained_units", "tolerant_n")}})

    def _storage_curve(self, dataset, sd, events, strategies, labels, meta):
        by_name = {s.name: s for s in strategies if s.available}
        pick = [n for n in ("RULES", "MOCK/RULES_PLUS_ENGINE") + tuple(f"JEV_{v.upper()}/RULES_PLUS_ENGINE" for v in JEV_VARIANTS) if n in by_name]
        ev_time = {e.id: e for e in events}
        for name in pick:
            units = by_name[name].units
            for policy, protect in (("VALUE_PER_BYTE_ONLY", 99.0), ("PROTECTED_HIGH_VALUE_TIER", None)):
                for cap in STORAGE_BYTES:
                    cfg = self.cfg.patched({"downlink": {"protect_utility": protect}})
                    items = [Item(id=u.id, kind="event", arrival=ev_time[u.id].sol_end, utility=u.utility, action=u.action,
                                  sizes=dict(u.sizes), raw=u.raw, cost_exponent=cfg.priority.cost_exponent) for u in units if u.id in ev_time]
                    b = Blackout(start=sd.segment.eval[0], duration=sd.segment.eval[1] - sd.segment.eval[0] + 1, storage_bytes=cap)
                    sim = simulate(items, [], cfg, blackout=b, sol_range=(sd.segment.eval[0], sd.segment.eval[1]))
                    kept = {i["id"]: i for i in sim["items"] if i["final"] != "discard"}
                    uidx = {u.id: u for u in units}
                    preserved = []
                    for lab in labels:
                        mm = meta.get(lab.id, {})
                        tb, ta = timedelta(seconds=mm.get("tolerance_before_s", 0)), timedelta(seconds=mm.get("tolerance_after_s", 0))
                        hit = [k for k in kept if uidx[k].instrument == lab.instrument and uidx[k].t0 <= lab.t_end + ta and uidx[k].t1 >= lab.t_start - tb]
                        preserved.append({"label": lab.id, "severity": lab.severity, "preserved": bool(hit),
                                          "best": max((kept[k]["final"] for k in hit), key=lambda a: ["summary_only", "compress", "full_data"].index(a), default=None)})
                    fin = [i["final"] for i in sim["items"]]
                    self.rows.append({
                        "dataset": dataset, "experiment": "storage", "segment": sd.segment.id, "strategy": name, "policy": policy,
                        "storage_bytes": cap, "labels": len(labels),
                        "labels_preserved": sum(p["preserved"] for p in preserved),
                        "high_preserved": sum(p["preserved"] for p in preserved if p["severity"] == "high"),
                        "high_labels": sum(1 for p in preserved if p["severity"] == "high"),
                        "full": fin.count("full_data"), "compress": fin.count("compress"), "summary": fin.count("summary_only"),
                        "discard": fin.count("discard"), "stored_bytes": sum(i["bytes"] for i in sim["items"]),
                        "utility_retained": sum(i["utility"] for i in sim["items"] if i["final"] != "discard"),
                        "preserved_detail": [p for p in preserved if p["severity"] == "high"][:20],
                    })

    def _calibration(self, dataset, events, decs, labels, meta):
        for spec in self.engines:
            if spec.single:
                rec = self.calib.setdefault(f"{dataset}:{spec.key}:retain", {"conf": [], "correct": []})
                for e, d in zip(events, decs[spec.key]):
                    if d.error or "retain" not in d.answers:
                        continue
                    rec["conf"].append(d.answers["retain"].noul)
                    rec["correct"].append(self._overlaps_label(e, labels, meta))
                continue
            imp = self.calib.setdefault(f"{dataset}:{spec.key}:importance", {"conf": [], "correct": []})
            typ = self.calib.setdefault(f"{dataset}:{spec.key}:event_type", {"conf": [], "correct": []})
            for e, d in zip(events, decs[spec.key]):
                if d.error or "science_value" not in d.answers:
                    continue
                sv = d.answers["science_value"].probabilities
                p_imp = sum(p for k, p in sv.items() if k in ("medium", "high", "critical"))
                imp["conf"].append(p_imp)
                imp["correct"].append(self._overlaps_label(e, labels, meta))
                hit = [lab for lab in labels if self._overlap(e, lab, meta)]
                if dataset == "synthetic" and len(hit) == 1 and "event_type" in d.answers:
                    et = d.answers["event_type"]
                    typ["conf"].append(et.confidence)
                    typ["correct"].append(et.choice == hit[0].expected_type)

    @staticmethod
    def _overlap(e, lab, meta) -> bool:
        if lab.instrument != e.instrument:
            return False
        m = meta.get(lab.id, {})
        t0 = datetime.fromisoformat(e.timestamp_start.replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(e.timestamp_end.replace("Z", "+00:00"))
        return t0 <= lab.t_end + timedelta(seconds=m.get("tolerance_after_s", 0)) and t1 >= lab.t_start - timedelta(seconds=m.get("tolerance_before_s", 0))

    def _overlaps_label(self, e, labels, meta) -> bool:
        return any(self._overlap(e, lab, meta) for lab in labels)

    def _failure_examples(self, dataset, sd, events, strategies, labels, meta, iw, raw):
        budget = int(REFERENCE_BUDGET * raw)
        by = {s.name: s for s in strategies if s.available}
        ev_by_id = {e.id: e for e in events}
        eng_names = [n for n in by if n.endswith("/RULES_PLUS_ENGINE")]
        sel = {n: {u.id for u, a, _ in allocate(by[n].units, budget) if a != DownlinkAction.DISCARD} for n in ["RULES", *eng_names]}

        def add(cat, payload):
            lst = self.failures.setdefault(cat, [])
            if len(lst) < 40:
                lst.append(payload)

        for lab in labels:
            cands = [e for e in events if self._overlap(e, lab, meta)]
            base = {"dataset": dataset, "segment": sd.segment.id, "label": lab.id, "severity": lab.severity,
                    "label_type": lab.expected_type, "subtype": meta.get(lab.id, {}).get("subtype"), "bucket": meta.get(lab.id, {}).get("bucket")}
            if not cands:
                add("lost_to_detection", {**base, "note": "no candidate event overlaps the label — every event-based strategy misses it"})
                continue
            for eng in eng_names:
                r_ok = any(e.id in sel["RULES"] for e in cands)
                j_ok = any(e.id in sel[eng] for e in cands)
                cat = {(True, True): "both_correct", (True, False): "rules_correct_engine_wrong",
                       (False, True): "engine_correct_rules_wrong", (False, False): "both_wrong"}[(r_ok, j_ok)]
                e0 = cands[0]
                add(f"{eng}:{cat}", {**base, "event_id": e0.id, "engine": eng,
                                     "rules_decision": by["RULES"].decisions.get(e0.id), "engine_decision": by[eng].decisions.get(e0.id),
                                     "event": e0.model_dump(mode="json", exclude={"decision", "trace"})})
                if not r_ok and not j_ok:
                    add("lost_to_budget", {**base, "event_id": e0.id, "note": f"candidate existed but was not selected at {REFERENCE_BUDGET:.1%} budget by RULES or {eng}",
                                           "event": e0.model_dump(mode="json", exclude={"decision", "trace"})})
        for eng in eng_names:
            dec = by[eng].decisions
            for e in events:
                d = dec.get(e.id) or {}
                hit = [lab for lab in labels if self._overlap(e, lab, meta)]
                if dataset == "synthetic" and len(hit) == 1 and d.get("type_conf") is not None:
                    wrong = d["type"] != hit[0].expected_type
                    if wrong and d["type_conf"] >= 0.9:
                        add(f"{eng}:high_confidence_error", {"dataset": dataset, "segment": sd.segment.id, "event_id": e.id, "label": hit[0].id,
                                                             "expected_type": hit[0].expected_type, "engine_decision": d,
                                                             "event": e.model_dump(mode="json", exclude={"decision", "trace"})})
                    if not wrong and d["type_conf"] < 0.7:
                        add(f"{eng}:low_confidence_correct", {"dataset": dataset, "segment": sd.segment.id, "event_id": e.id, "label": hit[0].id,
                                                              "expected_type": hit[0].expected_type, "engine_decision": d,
                                                              "event": e.model_dump(mode="json", exclude={"decision", "trace"})})
        _ = ev_by_id

    # ------------------------------------------------------------------ run
    def run(self) -> Path:
        started = datetime.now(timezone.utc)
        segs = segments(self.split)
        for seg in segs:
            print(f"[{self.run_id}] segment {seg.id}", flush=True)
            self.run_segment(seg)
        results = self.summarize()
        (self.out / "results.json").write_text(json.dumps(results, default=str))
        with (self.out / "rows.jsonl").open("w") as fh:
            for r in self.rows:
                fh.write(json.dumps(r, default=str) + "\n")
        (self.out / "failures.json").write_text(json.dumps(self.failures, default=str))
        (self.out / "injections.json").write_text(json.dumps(getattr(self, "rows_injections", []), default=str))
        sols = sorted({s for seg in segs for s in seg.load_sols})
        manifest = {
            "run_id": self.run_id, "split": self.split, "started_at": started.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(), "git": self.git_at_start, "git_at_finish": git_state(),
            "config_version": self.cfg.version(), "config": self.cfg.model_dump(mode="json"),
            "segments": [{"id": s.id, "warmup": s.warmup, "eval": s.eval} for s in segs],
            "datasets": {"raw_products": dataset_hashes(sols),
                         "ground_truth_sha256": hashlib.sha256((ROOT / "data/ground_truth/documented_events.json").read_bytes()).hexdigest(),
                         "splits_sha256": hashlib.sha256((ROOT / "data/splits/splits.json").read_bytes()).hexdigest(),
                         "local_edge_sha256": hashlib.sha256((ROOT / "artifacts/models/local_edge.json").read_bytes()).hexdigest()},
            "strategies": _strategy_docs(),
            "engines": [{"key": s.key, **s.engine.describe()} for s in self.engines], "jev_status": self.jev_status,
            "seeds": {"random_strategy_seeds": RANDOM_SEEDS, "synthetic_batches_per_segment": self.n_batches,
                      "synthetic_seed_rule": "sha256(split:segment)[:8] % 1e6 + batch", "local_edge_training_seed_base": 10_000},
            "budgets": {"fractions_of_generated_raw_bytes": BUDGET_FRACTIONS, "reference": REFERENCE_BUDGET},
            "storage_bytes": STORAGE_BYTES, "gating_grid": GATING_GRID,
            "system": system_info(),
            "results_files": {k: str((self.out / k).relative_to(ROOT)) for k in
                              ("results.json", "rows.jsonl", "failures.json", "injections.json", "jev_calls.jsonl")
                              if (self.out / k).exists() or k == "jev_calls.jsonl" and self.jev_status == "enabled"},
            "reproduce": f"uv run python scripts/run_study.py --split {self.split} --batches {self.n_batches}",
        }
        (self.out / "manifest.json").write_text(json.dumps(manifest, indent=1, default=str))
        return self.out

    def summarize(self) -> dict:
        from collections import defaultdict

        res: dict = {"run_id": self.run_id, "split": self.split, "jev_status": self.jev_status}
        # ---- real & synthetic budget curves: pool per-label outcomes across segments/batches
        for dataset in ("real", "synthetic"):
            curves = defaultdict(dict)
            rows = [r for r in self.rows if r.get("dataset") == dataset and r.get("experiment") is None]
            strategies = sorted({r["strategy"] for r in rows})
            for s in strategies:
                for frac in BUDGET_FRACTIONS:
                    rs = [r for r in rows if r["strategy"] == s and r["budget_fraction"] == frac]
                    if s == "RANDOM":
                        per_seed = defaultdict(list)
                        for r in rs:
                            per_seed[r["seed"]].append(r)
                        pooled = [self._pool(v) for v in per_seed.values()]
                        curves[s][frac] = {k: mean_ci([p[k] for p in pooled]) for k in pooled[0]} if pooled else {}
                    else:
                        curves[s][frac] = self._pool(rs)
                        if dataset == "synthetic":
                            per_batch = [self._pool([r]) for r in rs]
                            curves[s][frac]["batch_ci"] = {k: mean_ci([p[k] for p in per_batch]) for k in ("tolerant_recall", "high_tolerant_recall", "coverage")}
            res[f"{dataset}_curves"] = curves
            ref = {s: curves[s].get(REFERENCE_BUDGET) for s in strategies}
            res[f"{dataset}_reference"] = ref
            res[f"{dataset}_by_group"] = self._by_group(rows)
        # ---- storage, gating
        res["storage"] = [r for r in self.rows if r.get("experiment") == "storage"]
        g = [r for r in self.rows if r.get("experiment") == "gating"]
        gating = {}
        for dataset in ("real", "synthetic"):
            for eng in sorted({r["engine"] for r in g}):
                pts = []
                for auto, unc in GATING_GRID:
                    rs = [r for r in g if r["dataset"] == dataset and r["engine"] == eng and r["auto"] == auto and r["uncertain"] == unc]
                    if not rs:
                        continue
                    n = sum(r["tolerant_n"] for r in rs) or 1
                    pts.append({"auto": auto, "uncertain": unc,
                                "tolerant_recall": sum((r["tolerant_recall"] or 0) * r["tolerant_n"] for r in rs) / n,
                                "high_tolerant_recall": float(np.mean([r["high_tolerant_recall"] for r in rs if r["high_tolerant_recall"] is not None] or [0])),
                                "precision_lower_bound": float(np.mean([r["precision_lower_bound"] for r in rs if r["precision_lower_bound"] is not None] or [0])),
                                "downlink_bytes": sum(r["downlink_bytes"] for r in rs), "false_positive_units": sum(r["false_positive_units"] for r in rs),
                                "would_escalate": sum(r["would_escalate"] for r in rs), "events": sum(r["events"] for r in rs)})
                front = pareto_front(pts, ["high_tolerant_recall", "precision_lower_bound"], ["would_escalate", "downlink_bytes"])
                for i, p in enumerate(pts):
                    p["pareto"] = i in front
                gating[f"{dataset}:{eng}"] = pts
        res["gating"] = gating
        res["paired_tests"] = self._paired_tests()
        res["calibration"] = {k: ece(v["conf"], v["correct"]) for k, v in self.calib.items()}
        res["latency"] = {k: percentiles(v) for k, v in self.latency.items()}
        res["timing_ms"] = self.timing
        res["jev_usage"] = self.jev_usage
        res["local_edge_footprint"] = self.local.meta | {"note": "see artifacts/models/local_edge.json"}
        return res

    def _paired_tests(self) -> dict:
        """Exact McNemar on paired high-severity tolerant hits (same labels, same budget)."""
        from deepsift.evaluation.metrics2 import mcnemar

        out = {}
        rows = [r for r in self.rows if r.get("experiment") is None and r["strategy"] != "RANDOM"]
        names = sorted({r["strategy"] for r in rows})
        engines = [n for n in names if "/" in n]
        refs = [n for n in ("RULES", "RULES_PLUS_STATISTICAL", "LOCAL_EDGE") if n in names]
        for dataset in ("real", "synthetic"):
            for frac in BUDGET_FRACTIONS:
                idx = {}
                for r in rows:
                    if r["dataset"] == dataset and r["budget_fraction"] == frac:
                        for lid, v in r["per_label"].items():
                            if v["status"] == "scored" and v["severity"] == "high":
                                idx[(r["strategy"], r["segment"], r["batch"], lid)] = v["tolerant_hit"]
                for a in engines:
                    for b_ in refs + [e for e in engines if e != a]:
                        keys = [(k[1], k[2], k[3]) for k in idx if k[0] == a]
                        pairs = [(idx[(a, *k)], idx.get((b_, *k))) for k in keys if (b_, *k) in idx]
                        if not pairs:
                            continue
                        bb = sum(1 for x, y in pairs if x and not y)
                        cc = sum(1 for x, y in pairs if y and not x)
                        out[f"{dataset}|{frac}|{a}|vs|{b_}"] = {"n_pairs": len(pairs), "a_only": bb, "b_only": cc,
                                                                 "net_gain_labels": bb - cc, "p_value": mcnemar(bb, cc)}
        return out

    @staticmethod
    def _pool(rows: list[dict]) -> dict:
        labels = [v for r in rows for v in r["per_label"].values() if v["status"] == "scored"]

        def rate(pred, key):
            xs = [v[key] for v in labels if pred(v) and v.get(key) is not None]
            return sum(bool(x) for x in xs) / len(xs) if xs else None

        cov = [v["coverage"] for v in labels]
        hi = [v["coverage"] for v in labels if v["severity"] == "high"]
        ret = sum(r["retained_units"] for r in rows)
        tp = sum(r["true_positive_units"] for r in rows)
        dl = sum(r["downlink_bytes"] for r in rows)
        raw = sum(r["raw_bytes"] for r in rows)
        val = sum(r["labeled_value_proxy"] for r in rows)
        from deepsift.evaluation.metrics2 import decompose

        dec = decompose(labels)
        return {**dec, "labels": len(labels), "strict_recall": rate(lambda v: True, "strict_hit"),
                "tolerant_recall": rate(lambda v: True, "tolerant_hit"),
                "high_tolerant_recall": rate(lambda v: v["severity"] == "high", "tolerant_hit"),
                "high_strict_recall": rate(lambda v: v["severity"] == "high", "strict_hit"),
                "coverage": float(np.mean(cov)) if cov else None, "high_coverage": float(np.mean(hi)) if hi else None,
                "precision_lower_bound": tp / ret if ret else None, "false_positive_units": ret - tp, "retained_units": ret,
                "downlink_bytes": dl, "raw_bytes": raw, "data_reduction": 1 - dl / raw if raw else None,
                "value_per_mb_proxy": val / (dl / 1e6) if dl else None}

    def _by_group(self, rows: list[dict]) -> dict:
        from collections import defaultdict

        out = defaultdict(dict)
        ref = [r for r in rows if r["budget_fraction"] == REFERENCE_BUDGET and r["strategy"] != "RANDOM"]
        for s in sorted({r["strategy"] for r in ref}):
            labels = [v for r in ref if r["strategy"] == s for v in r["per_label"].values() if v["status"] == "scored"]
            for key in ("bucket", "subtype", "severity"):
                for g in sorted({str(v.get(key)) for v in labels}):
                    xs = [v for v in labels if str(v.get(key)) == g]
                    out[s][f"{key}={g}"] = {"n": len(xs), "tolerant_recall": sum(v["tolerant_hit"] for v in xs) / len(xs),
                                            "coverage": float(np.mean([v["coverage"] for v in xs]))}
        return out


def _strategy_docs() -> dict:
    from deepsift.evaluation import strategies as st

    return {"doc": st.__doc__, "oracle_label": ORACLE_LABEL, "allocator": "greedy by utility; degrade one product level until it fits (evaluation/benchmark.py:allocate)"}


def load_env_and_check() -> None:
    from deepsift.core.env import load_dotenv

    load_dotenv()
    os.environ.setdefault("POLARS_MAX_THREADS", "8")
