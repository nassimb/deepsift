#!/usr/bin/env python3
"""JEV_SCHEMA_V3 pilot — VALIDATION ONLY, final Jev redesign pilot.

    uv run python scripts/jev_v3_pilot.py --dry-run                 # sample + preflight, no calls
    uv run python scripts/jev_v3_pilot.py --allow-calls N           # live (stops if projected new cost > --max-new-cost)
    uv run python scripts/jev_v3_pilot.py --analyze-only <run_id>   # re-analyse from the cache, zero live calls

Order of work: sample → preflight → calls → OUTPUT HEALTH (written first) → ranking. Declared before any V3 answer:
  * sample: real groups = every candidate overlapping a documented label + REAL_UNLABELLED random unlabelled per segment;
    synthetic groups = batches 0..B−1 of the existing validation sweep (B = smallest number reaching NEED_HIGH detected
    high-severity AND NEED_MEDIUM medium-severity labelled candidates, max 25); per group: every medium-severity labelled
    candidate, high-severity labelled candidates kept with probability HIGH_TARGET / (all high in B batches), up to
    LOW_PER_GROUP low-severity labelled candidates, DISTRACTORS random unlabelled candidates. Seeded. A labelled candidate
    left out is neither scored nor competing (same for every strategy). Injections are the study's own (unchanged).
  * ranking approximation as in scripts/jev_pilot_report.py: budget scaled by sampled/all candidate raw bytes per group;
    scored labels = labels overlapped by a sampled candidate; detection recall from the full frozen detector.
  * disagreement: a deterministic method's "high"/"low" = top/bottom tercile of its utility within the dataset;
    Jev high = interest in {high, exceptional}, low = {none, low}.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
import sys
import uuid
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "pipeline"))

from deepsift.core.config import load_config  # noqa: E402
from deepsift.core.env import load_dotenv  # noqa: E402
from deepsift.core.models import DownlinkAction  # noqa: E402
from deepsift.decision.jev import (TRANSPORT, ApiBudget, JevDecisionEngine, jev_available, question_specs_for,  # noqa: E402
                                   questions_payload, sdk_version, v3_thresholds)
from deepsift.decision.jev_cache import JevCache, request_key  # noqa: E402
from deepsift.decision.state import build_state_v3, data_quality_state  # noqa: E402
from deepsift.evaluation.benchmark import allocate  # noqa: E402
from deepsift.evaluation.jev_plan import MISSION, _candidate_sets, limits_from_env, score_tier  # noqa: E402
from deepsift.evaluation.local_edge import LocalEdgeModel  # noqa: E402
from deepsift.evaluation.metrics2 import WindowIndex, evaluate_selection, mcnemar, percentiles  # noqa: E402
from deepsift.evaluation.segments import eval_windows  # noqa: E402
from deepsift.evaluation.strategies import local_edge_strategy, rules_strategy, statistical_strategy  # noqa: E402
from deepsift.evaluation.study import git_state, synthetic_labels_with_meta  # noqa: E402
from deepsift.evaluation.v3_adapter import (INTEREST_VALUE, QC_FACTOR, RELEVANCE_VALUE, RULES_PLUS_JEV_WEIGHT,  # noqa: E402
                                            rules_plus_v3, v3_strategy)
from deepsift.objectives.objective import load_objectives  # noqa: E402
from deepsift.priority.engine import rules_decision  # noqa: E402

SEED = 20260925
BUDGETS = [0.001, 0.0025, 0.005, 0.01]
NEED_HIGH, NEED_MEDIUM, HIGH_TARGET, LOW_PER_GROUP, REAL_UNLABELLED, DISTRACTORS, DIAG_N = 100, 100, 150, 2, 60, 5, 100
DIAG_OBJECTIVES = ["radiation_monitoring", "engineering_health"]
RANDOM_SEEDS = 20


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def overlap(e, lab, meta) -> bool:
    if lab.instrument != e.instrument:
        return False
    m = meta.get(lab.id, {})
    return ts(e.timestamp_start) <= lab.t_end + timedelta(seconds=m.get("tolerance_after_s", 0)) and \
        ts(e.timestamp_end) >= lab.t_start - timedelta(seconds=m.get("tolerance_before_s", 0))


SEV_RANK = {"low": 0, "medium": 1, "high": 2}


def build_groups(cfg):
    groups = []
    for dataset, sd, det, b, evs, inj, seg in _candidate_sets(cfg, "validation", batches=25):
        labels, meta = (sd.labels, sd.label_meta) if dataset == "real" else synthetic_labels_with_meta(inj)
        lab_of = {}
        for e in evs:
            hit = [lab for lab in labels if overlap(e, lab, meta)]
            if hit:
                top = max(hit, key=lambda x: SEV_RANK.get(x.severity, 0))
                lab_of[e.id] = {"label_id": top.id, "severity": top.severity, "expected_type": top.expected_type,
                                "n_labels": len(hit), "subtype": meta.get(top.id, {}).get("subtype"), "bucket": meta.get(top.id, {}).get("bucket")}
        groups.append({"tag": f"{seg.id}:{dataset}:{b}", "dataset": dataset, "b": b, "seg": seg, "sd": sd, "det": det, "evs": evs,
                       "labels": labels, "meta": meta, "lab_of": lab_of})
    return groups


def choose_batches(groups) -> int:
    hi = med = 0
    for b in range(25):
        for g in groups:
            if g["dataset"] == "synthetic" and g["b"] == b:
                hi += sum(1 for v in g["lab_of"].values() if v["severity"] == "high")
                med += sum(1 for v in g["lab_of"].values() if v["severity"] == "medium")
        if hi >= NEED_HIGH and med >= NEED_MEDIUM:
            return b + 1
    return 25


def sample(groups, n_batches):
    chosen = []
    n_high = sum(1 for g in groups if g["dataset"] == "synthetic" and g["b"] < n_batches
                 for v in g["lab_of"].values() if v["severity"] == "high")
    p_high = min(1.0, HIGH_TARGET / max(n_high, 1))
    for g in groups:
        if g["dataset"] == "synthetic" and g["b"] >= n_batches:
            continue
        rng = random.Random(int(hashlib.sha256(f"{SEED}:{g['tag']}".encode()).hexdigest()[:8], 16))
        lab = [e for e in g["evs"] if e.id in g["lab_of"]]
        unl = [e for e in g["evs"] if e.id not in g["lab_of"]]
        rng.shuffle(unl)
        if g["dataset"] == "synthetic":
            sev = lambda e: g["lab_of"][e.id]["severity"]  # noqa: E731
            low = [e for e in lab if sev(e) == "low"]
            rng.shuffle(low)
            lab = [e for e in lab if sev(e) == "medium"] + [e for e in lab if sev(e) == "high" and rng.random() < p_high] + low[:LOW_PER_GROUP]
        k = REAL_UNLABELLED if g["dataset"] == "real" else DISTRACTORS
        g["sampled"] = lab + unl[:k]
        chosen.append(g)
    return chosen


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--analyze-only", default=None)
    ap.add_argument("--allow-calls", type=int, default=None)
    ap.add_argument("--max-new-cost", type=float, default=0.10)
    args = ap.parse_args()
    load_dotenv()
    cfg = load_config(ROOT / "config" / "phase2.yaml")
    objs = load_objectives()
    objective = objs[cfg.objective]
    thr = v3_thresholds(cfg)
    groups = build_groups(cfg)
    nb = choose_batches(groups)
    groups = sample(groups, nb)
    items = [(g, e) for g in groups for e in g["sampled"]]

    # diagnostic subset: stratified by (dataset, instrument, labelled) round-robin
    cells = defaultdict(list)
    seen = set()
    for g, e in items:
        if e.id not in seen:
            seen.add(e.id)
            cells[(g["dataset"], e.instrument, e.id in g["lab_of"])].append((g["tag"], e))
    diag_te, keys = [], sorted(cells)
    while len(diag_te) < DIAG_N and any(cells[k] for k in keys):
        for k in keys:
            if cells[k] and len(diag_te) < DIAG_N:
                diag_te.append(cells[k].pop(0))
    diag = [e for _, e in diag_te]
    diag_ids = {e.id for e in diag}

    # unique requests (dedupe so identical natural candidates in several groups cost one call)
    cache = JevCache()
    sdkv, model = sdk_version(), cfg.decision_engine.jev_model

    def plan(variant, events, obj):
        q = questions_payload(question_specs_for(variant))
        out = {}
        for e in events:
            st = build_state_v3(e, *MISSION, thr, obj.model_dump(mode="json") if (obj and variant != "v3_science") else None)
            k = request_key(st, q, variant, model, sdkv, TRANSPORT)
            out.setdefault(k, (e, len(json.dumps(st, ensure_ascii=False)) + len(json.dumps(q, ensure_ascii=False))))
        return out

    all_events = list({e.id + "|" + g["tag"]: e for g, e in items}.values())
    jobs = [("v3_science", None, all_events, "science"), ("v3_relevance", objective, all_events, f"relevance:{cfg.objective}")]
    for o in DIAG_OBJECTIVES:
        jobs.append(("v3_relevance", objs[o], diag, f"relevance:{o}"))
        jobs.append(("v3_science_objective_diag", objs[o], diag, f"science_with_objective_diag:{o}"))
    plans = [(v, o, name, plan(v, evs, o)) for v, o, evs, name in jobs]
    cpt = cache.stats()["measured_chars_per_token"] or 4.0
    live = sum(sum(1 for k in p if not cache.has(k)) for *_, p in plans) + len(diag)       # + uncached repeat baseline
    chars = sum(c for *_, p in plans for k, (_, c) in p.items() if not cache.has(k)) + sum(c for e_, c in plans[0][3].values() if e_.id in diag_ids)
    est_tok = chars / cpt
    est_cost = est_tok * 0.042 / 1e6
    n_lab = {"synthetic": Counter(g["lab_of"][e.id]["severity"] for g, e in items if g["dataset"] == "synthetic" and e.id in g["lab_of"]),
             "real": Counter(g["lab_of"][e.id]["severity"] for g, e in items if g["dataset"] == "real" and e.id in g["lab_of"])}
    pre = {"schema": "JEV_SCHEMA_V3", "synthetic_batches_used": nb, "events": len(items), "unique_candidates": len({e.id for _, e in items}),
           "by_dataset": dict(Counter(g["dataset"] for g, _ in items)), "labelled_by_severity": {k: dict(v) for k, v in n_lab.items()},
           "unlabelled": sum(1 for g, e in items if e.id not in g["lab_of"]),
           "variants": ["JEV_V3_NO_OBJECTIVE (v3_science)", "JEV_V3_WITH_OBJECTIVE (v3_science + v3_relevance)"],
           "unique_requests": {name: len(p) for _, _, name, p in plans}, "diag_uncached_repeat": len(diag),
           "live_calls_needed": live, "estimated_input_tokens": round(est_tok), "estimated_cost_usd": round(est_cost, 5),
           "chars_per_token_basis": round(cpt, 3), "estimated_minutes": round(live * 0.3 / 8 / 60, 2)}
    print("PREFLIGHT", json.dumps(pre, indent=1))
    if args.analyze_only is None:
        if est_cost > args.max_new_cost:
            print(f"STOP: projected new cost ${est_cost:.4f} > ${args.max_new_cost}")
            return 3
        max_calls, _ = limits_from_env()
        lim = args.allow_calls or max_calls
        if live > lim:
            print(f"STOP: {live} live calls > limit {lim} (JEV_MAX_CALLS or --allow-calls)")
            return 3
        if args.dry_run or not jev_available():
            return 0
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-jev-v3-pilot-" + uuid.uuid4().hex[:4]
        budget = ApiBudget(lim, args.max_new_cost)
    else:
        run_id, budget = args.analyze_only, ApiBudget(0, 0.0)                                  # cache only
    out = ROOT / "artifacts" / "runs" / run_id
    out.mkdir(parents=True, exist_ok=True)
    log = out / ("jev_calls.jsonl" if args.analyze_only is None else "reanalysis_calls.jsonl")

    answers = {}
    for v, o, name, p in plans:
        eng = JevDecisionEngine(model=model, variant=v, call_log=log, run_id=run_id, cache=cache, budget=budget,
                                max_concurrency=cfg.decision_engine.max_concurrency, v3_thresholds=thr)
        evs = [e for e, _ in p.values()]
        ds = eng.decide(evs, *MISSION, objective=o.model_dump(mode="json") if o else None)
        by_key = dict(zip(p.keys(), ds))
        q = questions_payload(question_specs_for(v))
        res = {}
        for g, e in items:
            st = build_state_v3(e, *MISSION, thr, o.model_dump(mode="json") if (o and v != "v3_science") else None)
            k = request_key(st, q, v, model, sdkv, TRANSPORT)
            if k in by_key:
                res[(g["tag"], e.id)] = by_key[k]
        answers[name] = res
    if args.analyze_only is None:
        eng = JevDecisionEngine(model=model, variant="v3_science", call_log=log, run_id=run_id, use_cache=False, budget=budget,
                                max_concurrency=cfg.decision_engine.max_concurrency, v3_thresholds=thr)
        rep = dict(zip([f"{t}|{e.id}" for t, e in diag_te], eng.decide(diag, *MISSION)))
        (out / "diag_repeat.json").write_text(json.dumps({k: {q: {"choice": a.choice, "confidence": a.confidence} for q, a in d.answers.items()}
                                                          for k, d in rep.items()}, indent=1))
    rep_ans = json.loads((out / "diag_repeat.json").read_text())

    # ------------------------------------------------------------------ per-item table
    local = LocalEdgeModel.load(ROOT / "artifacts" / "models" / "local_edge.json")
    rows = []
    for g, e in items:
        sci = answers["science"][(g["tag"], e.id)]
        rel = answers[f"relevance:{cfg.objective}"][(g["tag"], e.id)]
        rd = rules_decision(e, cfg)
        rows.append({"tag": g["tag"], "dataset": g["dataset"], "event_id": e.id, "instrument": e.instrument, "sol": e.sol,
                     "score_tier": score_tier(e, cfg), "dq": data_quality_state(e)[0], "truth": g["lab_of"].get(e.id),
                     "rules": {"science_value": rd.answers["science_value"].choice, "event_type": rd.answers["event_type"].choice},
                     "interest": {"choice": sci.answers["scientific_interest"].choice, "confidence": sci.answers["scientific_interest"].confidence} if not sci.error else None,
                     "phenomenon": {"choice": sci.answers["phenomenon_class"].choice, "confidence": sci.answers["phenomenon_class"].confidence} if not sci.error else None,
                     "relevance": {"choice": rel.answers["mission_relevance"].choice, "confidence": rel.answers["mission_relevance"].confidence} if not rel.error else None,
                     "errors": [x for x in (sci.error, rel.error) if x], "p_local_edge": local.predict_proba_event(e)})
    (out / "items.json").write_text(json.dumps(rows, indent=1, default=str))

    # ------------------------------------------------------------------ OUTPUT HEALTH (before any ranking)
    def dist(key, rr=rows):
        return dict(Counter(r[key]["choice"] for r in rr if r[key]))

    def top_share(d):
        return max(d.values()) / sum(d.values()) if d else None
    uniq = {r["event_id"]: r for r in rows}.values()          # health on unique candidates (duplicates across batches)
    health = {"n_items": len(rows), "n_unique_candidates": len(uniq), "errors": sum(1 for r in rows if r["errors"]),
              "scientific_interest": dist("interest", list(uniq)), "phenomenon_class": dist("phenomenon", list(uniq)),
              f"mission_relevance[{cfg.objective}]": dist("relevance", list(uniq))}
    health["top_share"] = {q: top_share(health[q]) for q in ("scientific_interest", "phenomenon_class", f"mission_relevance[{cfg.objective}]")}
    health["interest_by_group"] = {}
    for fname, f in {"truth": lambda r: ("unlabelled" if not r["truth"] else f"{r['dataset']}:{r['truth']['severity']}"),
                     "data_quality": lambda r: r["dq"], "instrument": lambda r: r["instrument"], "score_tier": lambda r: r["score_tier"]}.items():
        c = defaultdict(list)
        for r in rows:
            c[f(r)].append(r)
        health["interest_by_group"][fname] = {k: {"n": len(v), **dist("interest", v)} for k, v in sorted(c.items())}
    health["phenomenon_by_instrument"] = {i: dist("phenomenon", [r for r in uniq if r["instrument"] == i]) for i in ("REMS", "RAD")}
    # relevance across objectives (diag subset)
    rel_obj = {}
    for o in [cfg.objective] + DIAG_OBJECTIVES:
        key = f"relevance:{o}"
        vals = [(e, answers[key][(t, e.id)]) for t, e in diag_te if (t, e.id) in answers[key]]
        rel_obj[o] = {"n": len(vals), "all": dict(Counter(d.answers["mission_relevance"].choice for _, d in vals if not d.error)),
                      **{inst: dict(Counter(d.answers["mission_relevance"].choice for e, d in vals if not d.error and e.instrument == inst))
                         for inst in ("REMS", "RAD")}}
    health["mission_relevance_by_objective_diag"] = rel_obj
    # phenomenon class vs objective: (1) by construction identical (V3 science state has no objective);
    # (2) diagnostic: if the objective WERE in the state; baseline = uncached repeat of the objective-free request
    base = {f"{t}|{eid}": d for (t, eid), d in answers["science"].items()}
    ph = {}
    for o in DIAG_OBJECTIVES:
        dd = {f"{t}|{eid}": d for (t, eid), d in answers[f"science_with_objective_diag:{o}"].items()}
        ids = [f"{t}|{e.id}" for t, e in diag_te if f"{t}|{e.id}" in dd]
        ph[o] = {"n": len(ids), "phenomenon_changed": sum(dd[i].answers["phenomenon_class"].choice != base[i].answers["phenomenon_class"].choice for i in ids) / len(ids),
                 "interest_changed": sum(dd[i].answers["scientific_interest"].choice != base[i].answers["scientific_interest"].choice for i in ids) / len(ids)}
    ids = [i for i in rep_ans if i in base]
    ph["repeat_baseline_no_objective"] = {"n": len(ids),
                                          "phenomenon_changed": sum(rep_ans[i]["phenomenon_class"]["choice"] != base[i].answers["phenomenon_class"].choice for i in ids) / len(ids),
                                          "interest_changed": sum(rep_ans[i]["scientific_interest"]["choice"] != base[i].answers["scientific_interest"].choice for i in ids) / len(ids)}
    ph["used_for_priority_and_reported"] = "objective-free V3_SCIENCE request only (identical across objectives by construction)"
    health["phenomenon_vs_objective"] = ph
    # confidence vs correctness (phenomenon class on physical labels; interest vs label severity)
    gt = [r for r in rows if r["truth"] and r["truth"]["n_labels"] == 1 and r["truth"]["expected_type"] in ("atmospheric", "radiation", "thermal") and r["phenomenon"]]
    ok = [r["phenomenon"]["choice"] == r["truth"]["expected_type"] for r in gt]
    conf = [r["phenomenon"]["confidence"] for r in gt]
    health["phenomenon_ground_truth"] = {
        "n": len(gt), "accuracy": sum(ok) / len(ok) if ok else None,
        "rules_accuracy": sum(r["rules"]["event_type"] == r["truth"]["expected_type"] for r in gt) / len(gt) if gt else None,
        "conf_correct": statistics.fmean([c for c, o in zip(conf, ok) if o]) if any(ok) else None,
        "conf_incorrect": statistics.fmean([c for c, o in zip(conf, ok) if not o]) if not all(ok) else None,
        "accuracy_by_conf": {b: (lambda xs: {"n": len(xs), "acc": sum(xs) / len(xs) if xs else None})([o for c, o in zip(conf, ok) if lo <= c < hi])
                             for b, (lo, hi) in {"<0.5": (0, .5), "0.5-0.7": (.5, .7), "0.7-0.9": (.7, .9), ">=0.9": (.9, 1.01)}.items()},
        "confusion": dict(Counter(f"{r['truth']['expected_type']}->{r['phenomenon']['choice']}" for r in gt))}
    lab = [r for r in rows if r["truth"] and r["interest"]]
    hi_ok = [(r["interest"]["choice"] in ("high", "exceptional")) == (r["truth"]["severity"] == "high") for r in lab if r["truth"]["severity"] in ("high", "low")]
    health["interest_vs_label_severity"] = {
        sev: {"n": sum(1 for r in lab if r["truth"]["severity"] == sev and r["dataset"] == ds), **dist("interest", [r for r in lab if r["truth"]["severity"] == sev and r["dataset"] == ds])}
        for ds in ("synthetic", "real") for sev in ("high", "medium", "low")} | {"agreement_high_vs_low": sum(hi_ok) / len(hi_ok) if hi_ok else None}
    health["confidence"] = {q: {"mean": statistics.fmean(r[q]["confidence"] for r in uniq if r[q]),
                                "median": statistics.median(r[q]["confidence"] for r in uniq if r[q])} for q in ("interest", "phenomenon", "relevance")}
    flags = []
    for q, s in health["top_share"].items():
        if s and s > 0.9:
            flags.append(f"{q}: one category has {s:.0%} of outputs")
    rl = health[f"mission_relevance[{cfg.objective}]"]
    if len([v for v in rl.values() if v / sum(rl.values()) >= 0.05]) <= 1:
        flags.append("mission_relevance nearly constant")
    for o in DIAG_OBJECTIVES:
        if ph[o]["phenomenon_changed"] > ph["repeat_baseline_no_objective"]["phenomenon_changed"] + 0.10:
            flags.append(f"DIAGNOSTIC: phenomenon class shifts with objective {o} when the objective is in the state "
                         f"({ph[o]['phenomenon_changed']:.0%} vs repeat baseline {ph['repeat_baseline_no_objective']['phenomenon_changed']:.0%}) "
                         f"— excluded by design in V3")
    pg = health["phenomenon_ground_truth"]
    if pg["conf_correct"] is not None and pg["conf_incorrect"] is not None and pg["conf_correct"] - pg["conf_incorrect"] < 0.05:
        flags.append("confidence does not separate correct from incorrect phenomenon classes (not used for routing)")
    health["flags"] = flags
    (out / "health.json").write_text(json.dumps(health, indent=1, default=str))
    print("HEALTH", json.dumps(health, indent=1, default=str))

    # ------------------------------------------------------------------ ranking (after health)
    fid = cfg.compression.fidelity
    per_label, agg = defaultdict(list), defaultdict(lambda: {"bytes": 0, "ret": 0, "tp": 0, "budget": 0})
    detection = defaultdict(lambda: [0, 0])
    auc = defaultdict(list)
    utilities = defaultdict(dict)
    for g in groups:
        sd, det, evs, sampled = g["sd"], g["det"], g["evs"], g["sampled"]
        labels, meta, tag = g["labels"], g["meta"], g["tag"]
        iw = eval_windows(det.instrument_windows, sd)
        raw_total = int(iw["raw"].sum() or 0)
        widx = WindowIndex(iw)
        det_all = {lab.id for lab in labels if any(overlap(e, lab, meta) for e in evs)}
        for v in evaluate_selection([], labels, meta, widx, raw_total, fid, det_all)["per_label"].values():
            if v["status"] == "scored":
                detection[(g["dataset"], v["severity"])][0] += bool(v["detected"])
                detection[(g["dataset"], v["severity"])][1] += 1
        if not sampled:
            continue
        det_s = {lab.id for lab in labels if any(overlap(e, lab, meta) for e in sampled)}
        scored = [lab for lab in labels if lab.id in det_s]
        s_raw, all_raw = sum(e.bytes.raw for e in sampled), sum(e.bytes.raw for e in evs) or 1
        sci = [answers["science"][(tag, e.id)] for e in sampled]
        rel = [answers[f"relevance:{cfg.objective}"][(tag, e.id)] for e in sampled]
        rules = rules_strategy(sampled, objective, cfg)
        rps = rules_strategy(sampled, objective, cfg)
        st = statistical_strategy(iw, det.windows, cfg.priority.anomaly_scale)
        spans = [(e.instrument, ts(e.timestamp_start), ts(e.timestamp_end)) for e in evs]
        extras = [u for u in st.units if not any(i == u.instrument and a <= u.t1 and b2 >= u.t0 for i, a, b2 in spans)]
        for u in rps.units:
            u.utility += 1.0
        rps.units, rps.name = rps.units + extras, "RULES_PLUS_STATISTICAL"
        strategies = [rules, rps, local_edge_strategy(sampled, local, cfg),
                      v3_strategy("V3_ADAPTER_NO_JEV (control)", sampled, None, None, objective, cfg, constant=0.5),
                      v3_strategy("JEV_V3_NO_OBJECTIVE", sampled, sci, None, objective, cfg),
                      v3_strategy("JEV_V3_WITH_OBJECTIVE", sampled, sci, rel, objective, cfg),
                      rules_plus_v3("RULES+JEV_V3_NO_OBJECTIVE", rules, sampled, sci, None),
                      rules_plus_v3("RULES+JEV_V3_WITH_OBJECTIVE", rules, sampled, sci, rel)]
        hi_pos = {e.id for e in sampled if g["lab_of"].get(e.id, {}).get("severity") == "high"}
        ids = {e.id for e in sampled}
        for so in strategies:
            for u in so.units:
                if u.id in ids:
                    auc[(g["dataset"], so.name)].append((u.utility, u.id in hi_pos, tag))
                    utilities[(g["dataset"], so.name)][(tag, u.id)] = u.utility
        rng = random.Random(int(hashlib.sha256(f"{SEED}:{tag}".encode()).hexdigest()[:8], 16))
        rand = [[replace(u, utility=rng.random()) for u in rules.units] for _ in range(RANDOM_SEEDS)]
        for frac in BUDGETS:
            budget_b = int(frac * raw_total * s_raw / all_raw)
            runs = [(so.name, so.units) for so in strategies] + [(f"RANDOM_ORDER#{k}", u) for k, u in enumerate(rand)]
            runs += [(f"ORDER:{n}", [replace(x, action=DownlinkAction.FULL_DATA) for x in u]) for n, u in list(runs)]
            for name, units in runs:
                m = evaluate_selection(allocate(units, budget_b), scored, meta, widx, raw_total, fid, det_s)
                key = (g["dataset"], name.split("#")[0], frac)
                for lid, p in m["per_label"].items():
                    if p["status"] == "scored":
                        per_label[key].append({**p, "label_id": f"{tag}|{lid}", "seed": name})
                a = agg[key]
                a["bytes"] += m["downlink_bytes"]
                a["ret"] += m["retained_units"]
                a["tp"] += m["true_positive_units"]
                a["budget"] += budget_b
    det_rate = {f"{d}|{s}": {"detected": a, "n": n, "recall": a / n if n else None} for (d, s), (a, n) in detection.items()}
    ranking = {}
    for (ds, name, frac), pls in per_label.items():
        seeds = max(1, len({p["seed"] for p in pls}))
        for sev in ("high", "medium"):
            xs = [p for p in pls if p["severity"] == sev]
            if not xs:
                continue
            any_f = sum(p["tolerant_hit"] for p in xs) / len(xs)
            full_f = sum(p["tolerant_hit"] and p["best_fidelity"] >= 1.0 for p in xs) / len(xs)
            dr = det_rate.get(f"{ds}|{sev}", {}).get("recall")
            a = agg[(ds, name, frac)]
            ranking[f"{ds}|{sev}|{name}|{frac}"] = {
                "labels": len(xs) // seeds, "retention_any_fidelity": any_f, "retention_full_fidelity": full_f,
                "detection_recall": dr, "end_to_end_any": dr * any_f if dr is not None else None,
                "end_to_end_full": dr * full_f if dr is not None else None,
                "precision_lower_bound": a["tp"] / a["ret"] if a["ret"] else None, "bytes": a["bytes"] / seeds, "budget_bytes": a["budget"] / seeds}

    def auroc(xs):
        from scipy.stats import rankdata

        y = np.array([p for _, p, _ in xs], bool)
        s = np.array([u for u, _, _ in xs], float)
        if y.all() or not y.any():
            return None
        r = rankdata(s)                                   # average ranks for ties
        return float((r[y].sum() - y.sum() * (y.sum() + 1) / 2) / (y.sum() * (~y).sum()))

    boot = {}
    rng = np.random.default_rng(SEED)
    for ds in ("synthetic", "real"):
        names = [n for (d, n) in auc if d == ds]
        tags = sorted({t for n in names for *_, t in auc[(ds, n)]})
        by_tag = {n: defaultdict(list) for n in names}
        for n in names:
            for x in auc[(ds, n)]:
                by_tag[n][x[2]].append(x)
        for n in names:
            boot[f"{ds}|{n}"] = {"auroc": auroc(auc[(ds, n)]), "positives": sum(p for _, p, _ in auc[(ds, n)]), "n": len(auc[(ds, n)])}
        for a_ in [n for n in names if "JEV" in n]:
            for b_ in ("RULES", "RULES_PLUS_STATISTICAL", "LOCAL_EDGE", "V3_ADAPTER_NO_JEV (control)"):
                diffs = []
                for _ in range(1000):
                    pick = rng.choice(tags, size=len(tags), replace=True)
                    xa = [x for t in pick for x in by_tag[a_][t]]
                    xb = [x for t in pick for x in by_tag[b_][t]]
                    ra, rb = auroc(xa), auroc(xb)
                    if ra is not None and rb is not None:
                        diffs.append(ra - rb)
                if diffs:
                    boot[f"{ds}|{a_}-minus-{b_}"] = {"diff": boot[f"{ds}|{a_}"]["auroc"] - boot[f"{ds}|{b_}"]["auroc"]
                                                     if boot[f"{ds}|{a_}"]["auroc"] is not None and boot[f"{ds}|{b_}"]["auroc"] is not None else None,
                                                     "ci95_cluster_bootstrap": [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))]}
    paired = {}
    for ds in ("synthetic", "real"):
        for frac in BUDGETS:
            for mode in ("", "ORDER:"):
                hits = {n: {p["label_id"]: (p["tolerant_hit"], p["best_fidelity"] >= 1.0) for p in pls if p["severity"] == "high"}
                        for (d, n, f), pls in per_label.items() if d == ds and f == frac and n.startswith(mode) and "RANDOM" not in n
                        and (mode or not n.startswith("ORDER:"))}
                for a_ in [n for n in hits if "JEV" in n]:
                    for b_ in [mode + x for x in ("RULES", "RULES_PLUS_STATISTICAL", "LOCAL_EDGE", "V3_ADAPTER_NO_JEV (control)")]:
                        if b_ not in hits:
                            continue
                        ids_ = set(hits[a_]) & set(hits[b_])
                        for j, lab_ in ((0, "any"), (1, "full")):
                            ao = sum(1 for i in ids_ if hits[a_][i][j] and not hits[b_][i][j])
                            bo = sum(1 for i in ids_ if hits[b_][i][j] and not hits[a_][i][j])
                            paired[f"{ds}|{frac}|{lab_}|{a_}|vs|{b_}"] = {"n": len(ids_), "a_only": ao, "b_only": bo, "p": mcnemar(ao, bo)}

    # ------------------------------------------------------------------ disagreement
    def terciles(ds, name):
        u = utilities[(ds, name)]
        vals = sorted(u.values())
        lo, hi = np.percentile(vals, 33.3), np.percentile(vals, 66.7)
        return {k: ("high" if x >= hi else "low" if x <= lo else "mid") for k, x in u.items()}
    dis = {}
    for ds in ("synthetic", "real"):
        tr, tl = terciles(ds, "RULES"), terciles(ds, "LOCAL_EDGE")
        rr = [r for r in rows if r["dataset"] == ds and r["interest"]]

        def jl(r):
            c = r["interest"]["choice"]
            return "high" if c in ("high", "exceptional") else "low" if c in ("none", "low") else "mid"

        def resolve(r, jev_says):
            t = r["truth"]
            if not t:
                return "UNRESOLVED"
            if t["severity"] == "medium":
                return "PARTIAL (medium-severity label)"
            truth_hi = t["severity"] == "high"
            return "JEV CORRECT" if (jev_says == "high") == truth_hi else "JEV INCORRECT"

        cats = {"rules_high_jev_low": lambda r: tr[(r["tag"], r["event_id"])] == "high" and jl(r) == "low",
                "rules_low_jev_high": lambda r: tr[(r["tag"], r["event_id"])] == "low" and jl(r) == "high",
                "local_edge_high_jev_low": lambda r: tl[(r["tag"], r["event_id"])] == "high" and jl(r) == "low",
                "jev_high_all_deterministic_low": lambda r: jl(r) == "high" and tr[(r["tag"], r["event_id"])] == "low" and tl[(r["tag"], r["event_id"])] == "low"}
        dis[ds] = {}
        for c, pred in cats.items():
            sel = [r for r in rr if pred(r)]
            dis[ds][c] = {"n": len(sel), "resolution": dict(Counter(resolve(r, jl(r)) for r in sel)),
                          "examples": [{k: r[k] for k in ("event_id", "instrument", "dq", "truth", "rules", "interest", "phenomenon", "score_tier")} for r in sel[:3]]}

    logf = [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []
    livel = [r for r in logf if not r.get("cache_hit")]
    ops = {"live_requests": len(livel), "cache_hits_logged": len(logf) - len(livel), "input_tokens": sum(r.get("input_tokens") or 0 for r in livel),
           "output_tokens": sum(r.get("output_tokens") or 0 for r in livel), "cost_usd": sum(r.get("cost_usd") or 0 for r in livel),
           "errors": sum(1 for r in livel if r.get("error")), "retries": sum(r.get("retries") or 0 for r in livel),
           "latency_ms": percentiles([r["latency_ms"] for r in livel if not r.get("error")]),
           "models_returned": dict(Counter(r.get("model_returned") for r in livel))}
    res = {"run_id": run_id, "split": "validation", "schema": "JEV_SCHEMA_V3", "preflight": pre, "operations": ops, "health": health,
           "declared": {"INTEREST_VALUE": INTEREST_VALUE, "RELEVANCE_VALUE": RELEVANCE_VALUE, "QC_FACTOR": QC_FACTOR,
                        "RULES_PLUS_JEV_WEIGHT": RULES_PLUS_JEV_WEIGHT, "budgets": BUDGETS, "sample": {"NEED_HIGH": NEED_HIGH, "NEED_MEDIUM": NEED_MEDIUM, "HIGH_TARGET": HIGH_TARGET,
                                   "LOW_PER_GROUP": LOW_PER_GROUP, "REAL_UNLABELLED": REAL_UNLABELLED, "DISTRACTORS": DISTRACTORS}},
           "detection_recall": det_rate, "ranking": ranking, "auroc": boot, "paired": paired, "disagreement": dis, "git": git_state(),
           "sample_manifest": [{"group": g["tag"], "event_id": e.id, "labelled": g["lab_of"].get(e.id)} for g, e in items]}
    (out / "analysis.json").write_text(json.dumps(res, indent=1, default=str))
    print(f"→ {(out / 'analysis.json').relative_to(ROOT)} · live {ops['live_requests']} · ${ops['cost_usd']:.5f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
