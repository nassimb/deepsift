#!/usr/bin/env python3
"""Analyse a Jev pilot run from the persistent cache — ZERO live calls (the engines get a 0-call budget).

    uv run python scripts/jev_pilot_report.py <pilot_run_id> [--schema-run <wording_run_id>]

Writes artifacts/runs/<run_id>/analysis.json. VALIDATION only; development diagnostics, not a result.

Ranking on a ~300-event stratified sample (approximation, declared before looking at the numbers):
  * population per (segment, dataset) group = the sampled candidates of that group;
  * budget = fraction × group raw bytes × (sampled candidate raw bytes / all candidate raw bytes), i.e. the same
    budget pressure per candidate byte as the full study;
  * scored labels = labels overlapped (tolerantly) by a SAMPLED candidate → retention given detection;
  * detection recall = full frozen detector on the whole batch-0 group; end-to-end = detection × retention (estimate);
  * RULES_PLUS_STATISTICAL: rules on sampled candidates + statistical windows that overlap NO candidate at all.
The stratified sample over-represents rare strata, so absolute numbers are not comparable with Phase 2.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "pipeline"))

from deepsift.core.config import load_config  # noqa: E402
from deepsift.core.env import load_dotenv  # noqa: E402
from deepsift.core.models import DownlinkAction  # noqa: E402
from deepsift.decision.jev import VARIANTS, ApiBudget, JevDecisionEngine  # noqa: E402
from deepsift.decision.jev_cache import JevCache  # noqa: E402
from deepsift.evaluation.benchmark import allocate  # noqa: E402
from deepsift.evaluation.jev_plan import MISSION, _candidate_sets, score_tier  # noqa: E402
from deepsift.evaluation.local_edge import LocalEdgeModel  # noqa: E402
from deepsift.evaluation.metrics2 import WindowIndex, ece, evaluate_selection, mcnemar, percentiles  # noqa: E402
from deepsift.evaluation.segments import eval_windows  # noqa: E402
from deepsift.evaluation.strategies import (engine_strategies, local_edge_strategy, rules_strategy,  # noqa: E402
                                            statistical_strategy)
from deepsift.evaluation.study import synthetic_labels_with_meta  # noqa: E402
from deepsift.features.detect import QUALITY_FLAGS  # noqa: E402
from deepsift.objectives.objective import load_objectives  # noqa: E402
from deepsift.priority.engine import rules_decision  # noqa: E402

BUDGETS = [0.001, 0.0025, 0.005, 0.01]
RUN_VARIANTS: list[str] = list(VARIANTS)      # replaced by the run's own variant list in main()
FIVE_Q: list[str] = [v for v in VARIANTS if VARIANTS[v][1] != "single"]
CHOICES = {
    "event_type": ["nominal", "atmospheric", "radiation", "thermal", "instrument_anomaly", "unknown"],
    "instrument_failure": ["yes", "no", "uncertain"],
    "science_value": ["none", "low", "medium", "high", "critical"],
    "downlink_action": ["discard", "summary_only", "compress", "full_data"],
}
RANDOM_SEEDS = 20


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def overlap(e, lab, meta) -> bool:
    if lab.instrument != e.instrument:
        return False
    m = meta.get(lab.id, {})
    return ts(e.timestamp_start) <= lab.t_end + timedelta(seconds=m.get("tolerance_after_s", 0)) and \
        ts(e.timestamp_end) >= lab.t_start - timedelta(seconds=m.get("tolerance_before_s", 0))


def truth_for(e, labels, meta, dataset):
    hit = [lab for lab in labels if overlap(e, lab, meta)]
    if not hit:
        return None
    lab = hit[0]
    return {"label_id": lab.id, "expected_type": lab.expected_type, "severity": lab.severity, "n_labels": len(hit),
            "source": dataset, "subtype": meta.get(lab.id, {}).get("subtype"), "bucket": meta.get(lab.id, {}).get("bucket")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_id")
    args = ap.parse_args()
    load_dotenv()
    run = ROOT / "artifacts" / "runs" / args.run_id
    global RUN_VARIANTS, FIVE_Q
    RUN_VARIANTS = json.loads((run / "summary.json").read_text())["variants"]
    FIVE_Q = [v for v in RUN_VARIANTS if VARIANTS[v][1] != "single"]
    cfg = load_config(ROOT / "config" / "phase2.yaml")
    objective = load_objectives()[cfg.objective]
    obj_json = objective.model_dump(mode="json")
    local = LocalEdgeModel.load(ROOT / "artifacts" / "models" / "local_edge.json")
    manifest = json.loads((run / "sampling_manifest.json").read_text())
    extra = json.loads((run / "pilot_extra.json").read_text())
    by_group = defaultdict(set)
    for r in manifest["events"]:
        by_group[r["group"]].add(r["event_id"])
    cache = JevCache()
    zero = ApiBudget(0, 0.0)                       # any cache miss raises: this script never calls the API
    engines = {v: JevDecisionEngine(model=cfg.decision_engine.jev_model, variant=v, cache=cache, budget=zero, max_concurrency=8)
               for v in RUN_VARIANTS}
    fid = cfg.compression.fidelity

    items = []                                     # one per sampled (group, event)
    per_label = defaultdict(list)                  # (dataset, strategy, frac) -> per-label dicts
    agg = defaultdict(lambda: {"downlink_bytes": 0, "retained": 0, "tp": 0, "actions": Counter()})
    detection = defaultdict(lambda: [0, 0])        # (dataset, severity) -> [detected, labels with data]
    auc_scores = defaultdict(list)                 # (dataset, strategy) -> [(utility, overlaps high-severity label)]
    for dataset, sd, det, b, evs, inj, seg in _candidate_sets(cfg, "validation", batches=1):
        tag = f"{seg.id}:{dataset}:{b}"
        sampled = [e for e in evs if e.id in by_group.get(tag, set())]
        if dataset == "real":
            labels, meta = sd.labels, sd.label_meta
        else:
            labels, meta = synthetic_labels_with_meta(inj)
        iw = eval_windows(det.instrument_windows, sd)
        raw_total = int(iw["raw"].sum() or 0)
        widx = WindowIndex(iw)
        det_all = {lab.id for lab in labels if any(overlap(e, lab, meta) for e in evs)}
        m0 = evaluate_selection([], labels, meta, widx, raw_total, fid, det_all)
        for v in m0["per_label"].values():
            if v["status"] == "scored":
                k = (dataset, v["severity"])
                detection[k][0] += bool(v["detected"])
                detection[k][1] += 1
        if not sampled:
            continue
        decs = {v: engines[v].decide(sampled, *MISSION, objective=obj_json) for v in RUN_VARIANTS}
        for i, e in enumerate(sampled):
            flags = {k: c.flags for k, c in e.features.channels.items() if c.flags}
            items.append({
                "group": tag, "dataset": dataset, "event_id": e.id, "instrument": e.instrument, "sol": e.sol,
                "score_tier": score_tier(e, cfg), "deviation_score": e.features.deviation_score,
                "quality_flagged": any(set(f) & QUALITY_FLAGS for f in flags.values()),
                "missing_channel_in_state": any(c.mean is None for c in e.features.channels.values()),
                "flags": flags, "sensors": e.sensors, "trigger_reasons": e.features.trigger_reasons,
                "rules": {q: a.choice for q, a in rules_decision(e, cfg).answers.items() if a.kind == "choice"},
                "truth": truth_for(e, labels, meta, dataset),
                "jev": {v: {q: ({"choice": a.choice, "confidence": a.confidence, "probabilities": a.probabilities}
                                if a.kind == "choice" else {"noul": a.noul}) for q, a in decs[v][i].answers.items()}
                        for v in RUN_VARIANTS},
                "latency_ms": {v: decs[v][i].latency_ms for v in RUN_VARIANTS},
            })
        # ranking within the sample
        det_s = {lab.id for lab in labels if any(overlap(e, lab, meta) for e in sampled)}
        scored = [lab for lab in labels if lab.id in det_s]
        all_raw = sum(e.bytes.raw for e in evs) or 1
        s_raw = sum(e.bytes.raw for e in sampled)
        strategies = [rules_strategy(sampled, objective, cfg), local_edge_strategy(sampled, local, cfg)]
        r = rules_strategy(sampled, objective, cfg)
        st = statistical_strategy(iw, det.windows, cfg.priority.anomaly_scale)
        spans = [(e.instrument, ts(e.timestamp_start), ts(e.timestamp_end)) for e in evs]
        extras = [u for u in st.units if not any(i == u.instrument and a <= u.t1 and b2 >= u.t0 for i, a, b2 in spans)]
        for u in r.units:
            u.utility += 1.0
        r.units, r.name = r.units + extras, "RULES_PLUS_STATISTICAL"
        strategies.append(r)
        for v in RUN_VARIANTS:
            for so in engine_strategies(sampled, decs[v], objective, cfg, v, single_decision=(v == "single_decision")):
                so.name = ("RULES+JEV_" if so.name == "RULES_PLUS_ENGINE" else "JEV_") + v.upper()
                strategies.append(so)
        base = strategies[0].units
        hi_pos = {e.id for e in sampled if any(lab.severity == "high" and overlap(e, lab, meta) for lab in scored)}
        for so in strategies:
            for u in so.units:
                if u.id in {e.id for e in sampled}:
                    auc_scores[(dataset, so.name)].append((u.utility, u.id in hi_pos))
        for frac in BUDGETS:
            budget = int(frac * raw_total * s_raw / all_raw)
            runs = [(so.name, so.units) for so in strategies]
            # ORDER-ONLY: each strategy's ordering with a common action (FULL_DATA, degraded to fit) — isolates ranking
            runs += [(f"ORDER:{so.name}", [replace(u, action=DownlinkAction.FULL_DATA) for u in so.units]) for so in strategies]
            rng = random.Random(int(hashlib.sha256(tag.encode()).hexdigest()[:8], 16))
            rand = [[replace(u, utility=rng.random()) for u in base] for _ in range(RANDOM_SEEDS)]
            runs += [(f"RANDOM_ORDER#{k}", u) for k, u in enumerate(rand)]
            runs += [(f"ORDER:RANDOM_ORDER#{k}", [replace(x, action=DownlinkAction.FULL_DATA) for x in u]) for k, u in enumerate(rand)]
            for name, units in runs:
                m = evaluate_selection(allocate(units, budget), scored, meta, widx, raw_total, fid, det_s)
                key = (dataset, name.split("#")[0], frac)
                for lid, pl_ in m["per_label"].items():
                    if pl_["status"] == "scored":
                        per_label[key].append({**pl_, "label_id": f"{tag}|{lid}", "seed": name})
                agg[key]["downlink_bytes"] += m["downlink_bytes"]
                agg[key]["retained"] += m["retained_units"]
                agg[key]["tp"] += m["true_positive_units"]
                agg[key]["actions"].update(m["actions"])
                agg[key]["budget_bytes"] = agg[key].get("budget_bytes", 0) + budget

    # ---------------------------------------------------------------- ranking tables
    det_rate = {f"{d}|{s}": {"detected": a, "n": n, "recall": a / n if n else None} for (d, s), (a, n) in detection.items()}
    ranking = {}
    for (dataset, name, frac), pls in per_label.items():
        seeds = max(1, len({p["seed"] for p in pls}))
        hi = [p for p in pls if p["severity"] == "high"]
        ret = sum(p["tolerant_hit"] for p in hi) / len(hi) if hi else None
        dr = det_rate.get(f"{dataset}|high", {}).get("recall")
        a = agg[(dataset, name, frac)]
        ranking[f"{dataset}|{name}|{frac}"] = {
            "high_labels_scored": len(hi) // seeds, "high_retention_given_detection": ret,
            "high_detection_recall_full_detector": dr, "high_end_to_end_estimate": (dr * ret) if (dr is not None and ret is not None) else None,
            "all_retention_given_detection": sum(p["tolerant_hit"] for p in pls) / len(pls) if pls else None,
            # a SUMMARY_ONLY product counts as a tolerant hit above; these require real data to reach the ground
            "high_retention_compress_or_better": sum(p["tolerant_hit"] and p["best_fidelity"] >= 0.5 for p in hi) / len(hi) if hi else None,
            "high_retention_full_data": sum(p["tolerant_hit"] and p["best_fidelity"] >= 1.0 for p in hi) / len(hi) if hi else None,
            "action_mix": {k: v / seeds for k, v in a["actions"].items()},
            "precision_lower_bound": a["tp"] / a["retained"] if a["retained"] else None,
            "downlink_bytes": a["downlink_bytes"] / seeds, "budget_bytes": a["budget_bytes"] / seeds,
        }
    def auroc(xs):
        pos = [u for u, y in xs if y]
        neg = [u for u, y in xs if not y]
        if not pos or not neg:
            return None
        return sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))
    ranking_auroc = {f"{d}|{n}": {"auroc_high_severity": auroc(xs), "positives": sum(y for _, y in xs), "n": len(xs)}
                     for (d, n), xs in auc_scores.items()}
    paired = {}
    for dataset in ("synthetic", "real"):
        for frac in BUDGETS:
            hits = {name: {p["label_id"]: p["tolerant_hit"] for p in pls if p["severity"] == "high"}
                    for (d, name, f), pls in per_label.items() if d == dataset and f == frac and not name.startswith("RANDOM")}
            for a in [n for n in hits if n.startswith(("JEV_", "RULES+JEV_"))]:
                for b in ("RULES", "RULES_PLUS_STATISTICAL", "LOCAL_EDGE"):
                    if b not in hits:
                        continue
                    ids = set(hits[a]) & set(hits[b])
                    ao = sum(1 for i in ids if hits[a][i] and not hits[b][i])
                    bo = sum(1 for i in ids if hits[b][i] and not hits[a][i])
                    paired[f"{dataset}|{frac}|{a}|vs|{b}"] = {"n": len(ids), "a_only": ao, "b_only": bo, "p": mcnemar(ao, bo)}

    # ---------------------------------------------------------------- distributions and class bias
    def choice(it, v, q):
        a = it["jev"][v].get(q)
        return a.get("choice") if a else None

    dist = {}
    for v in FIVE_Q:
        dist[v] = {q: dict(Counter(choice(it, v, q) for it in items)) for q in CHOICES}
        nd = [it["jev"][v]["needs_deep_analysis"]["noul"] for it in items]
        dist[v]["needs_deep_analysis"] = {"yes(>0.5)": sum(x > 0.5 for x in nd), "no": sum(x <= 0.5 for x in nd),
                                          "mean_noul": statistics.fmean(nd)}
    rt = [it["jev"]["single_decision"]["retain"]["noul"] for it in items]
    dist["single_decision"] = {"retain": {"yes(>0.5)": sum(x > 0.5 for x in rt), "no": sum(x <= 0.5 for x in rt), "mean_noul": statistics.fmean(rt)}}
    dist["RULES"] = {q: dict(Counter(it["rules"].get(q) for it in items)) for q in ("event_type", "science_value")}

    def truth_group(it):
        t = it["truth"]
        if not t:
            return "unlabelled"
        if it["dataset"] == "real":
            return "documented"
        return "synthetic_quality_fault" if t["expected_type"] == "instrument_anomaly" else "synthetic_physical"

    facets = {
        "truth_group": truth_group, "instrument": lambda it: it["instrument"], "score_tier": lambda it: it["score_tier"],
        "quality_flagged": lambda it: str(it["quality_flagged"]), "missing_channel_in_state": lambda it: str(it["missing_channel_in_state"]),
        "rules_type": lambda it: it["rules"]["event_type"],
        "synthetic_physical_x_quality_flagged": lambda it: (f"physical,flagged={it['quality_flagged']}" if truth_group(it) == "synthetic_physical" else None),
    }
    bias = {}
    for fname, f in facets.items():
        cells = defaultdict(list)
        for it in items:
            k = f(it)
            if k is not None:
                cells[k].append(it)
        bias[fname] = {k: {"n": len(xs), **{v: {"p_failure_yes": sum(choice(x, v, "instrument_failure") == "yes" for x in xs) / len(xs),
                                                 "p_type_instrument_anomaly": sum(choice(x, v, "event_type") == "instrument_anomaly" for x in xs) / len(xs)}
                                             for v in FIVE_Q},
                            "rules_p_type_instrument_anomaly": sum(x["rules"]["event_type"] == "instrument_anomaly" for x in xs) / len(xs)}
                       for k, xs in sorted(cells.items())}

    # ground-truth accuracy (synthetic + documented), clean = candidate without quality flags
    acc = {}
    for v in FIVE_Q:
        rows = []
        for it in items:
            t = it["truth"]
            if not t or t["n_labels"] != 1 or not t["expected_type"]:
                continue
            et, fl = it["jev"][v]["event_type"], it["jev"][v]["instrument_failure"]
            truth_fail = "yes" if t["expected_type"] == "instrument_anomaly" else "no"
            rows.append({"clean": not it["quality_flagged"], "type_ok": et["choice"] == t["expected_type"], "type_conf": et["confidence"],
                         "fail_ok": fl["choice"] == truth_fail, "fail_conf": fl["confidence"], "fail_uncertain": fl["choice"] == "uncertain",
                         "truth_type": t["expected_type"]})
        rr = [it for it in items if it["truth"] and it["truth"]["n_labels"] == 1 and it["truth"]["expected_type"]]
        rules_ok = [it["rules"]["event_type"] == it["truth"]["expected_type"] for it in rr]
        out = {}
        for sub, sel in (("all", rows), ("clean", [r for r in rows if r["clean"]])):
            if not sel:
                continue
            out[sub] = {
                "n": len(sel), "event_type_accuracy": sum(r["type_ok"] for r in sel) / len(sel),
                "instrument_failure_accuracy": sum(r["fail_ok"] for r in sel) / len(sel),
                "instrument_failure_uncertain_rate": sum(r["fail_uncertain"] for r in sel) / len(sel),
                "type_conf_correct": statistics.fmean([r["type_conf"] for r in sel if r["type_ok"]]) if any(r["type_ok"] for r in sel) else None,
                "type_conf_incorrect": statistics.fmean([r["type_conf"] for r in sel if not r["type_ok"]]) if any(not r["type_ok"] for r in sel) else None,
                "fail_conf_correct": statistics.fmean([r["fail_conf"] for r in sel if r["fail_ok"]]) if any(r["fail_ok"] for r in sel) else None,
                "fail_conf_incorrect": statistics.fmean([r["fail_conf"] for r in sel if not r["fail_ok"]]) if any(not r["fail_ok"] for r in sel) else None,
                "type_ece": ece([r["type_conf"] for r in sel], [r["type_ok"] for r in sel], bins=5),
                "type_accuracy_by_conf_bin": {b: (lambda xs: {"n": len(xs), "acc": sum(xs) / len(xs) if xs else None})(
                    [r["type_ok"] for r in sel if lo <= r["type_conf"] < hi]) for b, (lo, hi) in
                    {"<0.5": (0, .5), "0.5-0.7": (.5, .7), "0.7-0.9": (.7, .9), ">=0.9": (.9, 1.01)}.items()},
                "type_confusion": dict(Counter(f"{r['truth_type']}->{'ok' if r['type_ok'] else 'wrong'}" for r in sel)),
            }
        out["rules_event_type_accuracy"] = sum(rules_ok) / len(rules_ok) if rules_ok else None
        out["rules_event_type_accuracy_clean"] = (lambda xs: sum(xs) / len(xs) if xs else None)(
            [it["rules"]["event_type"] == it["truth"]["expected_type"] for it in rr if not it["quality_flagged"]])
        acc[v] = out

    # confidence
    conf = {}
    for v in FIVE_Q:
        conf[v] = {}
        for q in CHOICES:
            xs = [it["jev"][v][q]["confidence"] for it in items]
            conf[v][q] = {"mean": statistics.fmean(xs), "median": statistics.median(xs),
                          "hist_0.1": [sum(1 for x in xs if i / 10 <= x < (i + 1) / 10 or (i == 9 and x == 1.0)) for i in range(10)]}
        dl = [it["jev"][v]["downlink_action"] for it in items]
        top2 = [sorted(a["probabilities"].values(), reverse=True)[:2] for a in dl]
        conf[v]["downlink_action_detail"] = {
            "mean_top_probability": statistics.fmean(t[0] for t in top2), "mean_second_probability": statistics.fmean(t[1] for t in top2),
            "top_two_adjacent_share": sum(1 for a in dl if (lambda o: abs(CHOICES["downlink_action"].index(o[0]) - CHOICES["downlink_action"].index(o[1])) == 1)(
                sorted(a["probabilities"], key=lambda k: -a["probabilities"][k])[:2])) / len(dl),
            "mean_probability_by_option": {o: statistics.fmean(a["probabilities"].get(o, 0) for a in dl) for o in CHOICES["downlink_action"]},
        }

    # disagreement analysis (vs rules; rules are NOT ground truth)
    disagree = {}
    for v in FIVE_Q:
        mat_sv = Counter((it["rules"]["science_value"], choice(it, v, "science_value")) for it in items)
        mat_et = Counter((it["rules"]["event_type"], choice(it, v, "event_type")) for it in items)

        def resolve(it, q):
            t = it["truth"]
            if not t or t["n_labels"] != 1:
                return "UNRESOLVED DISAGREEMENT"
            if q == "event_type":
                return "JEV CORRECT (rules wrong)" if choice(it, v, q) == t["expected_type"] else (
                    "RULES CORRECT (Jev wrong)" if it["rules"]["event_type"] == t["expected_type"] else "BOTH WRONG")
            hi_truth = t["severity"] == "high"
            jhi = choice(it, v, "science_value") in ("high", "critical")
            rhi = it["rules"]["science_value"] in ("high", "critical")
            return "JEV CONSISTENT with label severity" if jhi == hi_truth else ("RULES CONSISTENT with label severity" if rhi == hi_truth else "NEITHER")

        def ex(pred, q):
            sel = [it for it in items if pred(it)]
            return {"n": len(sel), "resolution": dict(Counter(resolve(it, q) for it in sel)),
                    "examples": [{"event_id": it["event_id"], "dataset": it["dataset"], "rules": it["rules"],
                                  "jev": {k: (a.get("choice"), a.get("confidence")) if "choice" in a else a.get("noul") for k, a in it["jev"][v].items()},
                                  "truth": it["truth"], "trigger_reasons": it["trigger_reasons"][:2], "flags": it["flags"],
                                  "resolution": resolve(it, q)} for it in sel[:4]]}
        hi, lo = ("high", "critical"), ("none", "low")
        disagree[v] = {
            "science_value_matrix_rules_x_jev": {f"{a}|{b}": n for (a, b), n in sorted(mat_sv.items())},
            "event_type_matrix_rules_x_jev": {f"{a}|{b}": n for (a, b), n in sorted(mat_et.items())},
            "rules_high_jev_low": ex(lambda it: it["rules"]["science_value"] in hi and choice(it, v, "science_value") in lo, "science_value"),
            "rules_low_jev_high": ex(lambda it: it["rules"]["science_value"] in lo and choice(it, v, "science_value") in hi, "science_value"),
            "rules_atmospheric_jev_instrument": ex(lambda it: it["rules"]["event_type"] == "atmospheric" and choice(it, v, "event_type") == "instrument_anomaly", "event_type"),
            "rules_radiation_jev_instrument": ex(lambda it: it["rules"]["event_type"] == "radiation" and choice(it, v, "event_type") == "instrument_anomaly", "event_type"),
            "rules_critical_jev_noncritical": ex(lambda it: it["rules"]["science_value"] == "critical" and choice(it, v, "science_value") != "critical", "science_value"),
            "jev_high_conf_wrong_type": ex(lambda it: it["truth"] and it["truth"]["n_labels"] == 1 and it["jev"][v]["event_type"]["confidence"] >= 0.8
                                           and choice(it, v, "event_type") != it["truth"]["expected_type"], "event_type"),
            "jev_low_conf_correct_type": ex(lambda it: it["truth"] and it["truth"]["n_labels"] == 1 and it["jev"][v]["event_type"]["confidence"] < 0.5
                                            and choice(it, v, "event_type") == it["truth"]["expected_type"], "event_type"),
        }

    # representation / objective effects
    def change_rate(va, vb, q):
        return sum(choice(it, va, q) != choice(it, vb, q) for it in items) / len(items)
    rep_effects = {f"{a}~{b}": {q: change_rate(a, b, q) for q in CHOICES} for a in FIVE_Q for b in FIVE_Q if a < b}
    objc = extra.get("objective_check") or {}
    base_by_id = {it["event_id"]: it["jev"]["full_context"] for it in items}
    obj_effect = {}
    for name, ans in objc.items():
        if name.startswith("_"):
            continue
        ids = [i for i in ans if i in base_by_id]
        obj_effect[name] = {"n": len(ids), **{q: sum(ans[i][q]["choice"] != base_by_id[i][q]["choice"] for i in ids) / len(ids) for q in CHOICES},
                            "changed_examples": [{"event_id": i, **{q: (base_by_id[i][q]["choice"], ans[i][q]["choice"]) for q in CHOICES
                                                                   if ans[i][q]["choice"] != base_by_id[i][q]["choice"]}} for i in ids
                                                 if any(ans[i][q]["choice"] != base_by_id[i][q]["choice"] for q in ("event_type", "instrument_failure"))][:6]}
    obj_effect["_baseline_objective"] = objc.get("_baseline_objective")

    # repeatability (cached draw + uncached repeats)
    repeat = {}
    for v, per in (extra.get("repeat") or {}).items():
        qs = list(next(iter(per.values()))["cached"])
        stats_q = {}
        for q in qs:
            agree, rngs, sds = [], [], []
            for e in per.values():
                draws = [e["cached"]] + e["uncached"]
                if "choice" in draws[0][q]:
                    agree.append(len({d[q]["choice"] for d in draws}) == 1)
                    vals = [d[q]["confidence"] for d in draws]
                else:
                    agree.append(len({d[q]["noul"] > 0.5 for d in draws}) == 1)
                    vals = [d[q]["noul"] for d in draws]
                rngs.append(max(vals) - min(vals))
                sds.append(statistics.pstdev(vals))
            stats_q[q] = {"choice_agreement": sum(agree) / len(agree), "conf_range_mean": statistics.fmean(rngs), "conf_range_max": max(rngs),
                          "conf_sd_mean": statistics.fmean(sds), "conf_sd_max": max(sds)}
        repeat[v] = {"events": len(per), "draws_per_event": 1 + len(next(iter(per.values()))["uncached"]),
                     "exact_identical_events": sum(1 for e in per.values() if e.get("exact_all_answers_identical")), "per_question": stats_q}

    # cache determinism: cached answers vs the live-logged answers of the same request id
    log = [json.loads(x) for x in (run / "jev_calls.jsonl").read_text().splitlines()]
    by_rid = {r["request_id"]: r for r in log if not r.get("cache_hit") and r.get("request_id")}
    import sqlite3
    con = sqlite3.connect(cache.path)
    same = diff = 0
    for rid, ans in con.execute("SELECT request_id, answers_json FROM jev_cache"):
        if rid in by_rid:
            same += json.loads(ans) == by_rid[rid]["answers"]
            diff += json.loads(ans) != by_rid[rid]["answers"]
    live = [r for r in log if not r.get("cache_hit")]
    tstamps = sorted(ts(r["timestamp"]) for r in live)
    ops = {"live_requests": len(live), "cache_hits_logged": len(log) - len(live),
           "input_tokens": sum(r.get("input_tokens") or 0 for r in live), "output_tokens": sum(r.get("output_tokens") or 0 for r in live),
           "cost_usd": sum(r.get("cost_usd") or 0 for r in live), "cost_sources": dict(Counter(r.get("cost_source") for r in live)),
           "latency_ms": percentiles([r["latency_ms"] for r in live if not r.get("error")]),
           "latency_ms_by_variant": {v: percentiles([r["latency_ms"] for r in live if r["variant"] == v and not r.get("error")]) for v in RUN_VARIANTS},
           "tokens_per_request_by_variant": {v: statistics.fmean([r["input_tokens"] for r in live if r["variant"] == v and r.get("input_tokens")] or [0]) for v in RUN_VARIANTS},
           "retries": sum(r.get("retries") or 0 for r in live), "api_errors": sum(1 for r in live if r.get("error")),
           "http_statuses": dict(Counter(r.get("http_status") for r in live)), "models_returned": dict(Counter(r.get("model_returned") for r in live)),
           "api_wall_minutes": (tstamps[-1] - tstamps[0]).total_seconds() / 60 if tstamps else None,
           "cache_determinism": {"compared": same + diff, "identical": same}}
    sampling = {"n": len(items), "by_dataset": dict(Counter(it["dataset"] for it in items)), "by_instrument": dict(Counter(it["instrument"] for it in items)),
                "by_score_tier": dict(Counter(it["score_tier"] for it in items)), "by_truth_group": dict(Counter(truth_group(it) for it in items)),
                "by_rules_type": dict(Counter(it["rules"]["event_type"] for it in items)),
                "sols": {"distinct": len({it["sol"] for it in items}), "min": min(it["sol"] for it in items), "max": max(it["sol"] for it in items)},
                "duration_s": percentiles([next(r["duration_s"] for r in manifest["events"] if r["event_id"] == it["event_id"]) for it in items]),
                "quality_flagged": sum(it["quality_flagged"] for it in items)}
    out = {"run_id": args.run_id, "split": "validation", "note": "DEVELOPMENT diagnostics on VALIDATION; sample-level ranking approximation (see docstring)",
           "sampling": sampling, "operations": ops, "distributions": dist, "class_bias": bias, "ground_truth_accuracy": acc,
           "confidence": conf, "disagreement": disagree, "representation_effects_change_rate": rep_effects, "objective_effect": obj_effect,
           "repeatability": repeat, "detection_recall_full_detector": det_rate, "ranking": ranking, "ranking_auroc": ranking_auroc, "paired_high_severity": paired,
           "live_calls_by_this_script": zero.calls}
    (run / "analysis.json").write_text(json.dumps(out, indent=1, default=str))
    (run / "items.json").write_text(json.dumps(items, indent=1, default=str))
    print(f"analysis → {(run / 'analysis.json').relative_to(ROOT)} · items {len(items)} · live calls by this script {zero.calls}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
