#!/usr/bin/env python3
"""VALIDATION-only question-wording experiment (schema q1 → q2) on a subset of a finished pilot.

    uv run python scripts/jev_wording_experiment.py <pilot_run_id> --n 150 [--dry-run] --allow-calls N --allow-cost USD

Re-asks the SAME events with the SAME state (variant NO_MISSION_OBJECTIVE) under question schema q2 and compares with
the pilot's q1 answers. q1 results are kept untouched; q2 requests have their own cache keys (the key contains the
exact question schema), so no q1 answer can ever be served for a q2 request. Writes artifacts/runs/<new_run_id>/.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "pipeline"))

from deepsift.core.config import load_config  # noqa: E402
from deepsift.core.env import load_dotenv  # noqa: E402
from deepsift.decision.jev import ApiBudget, JevDecisionEngine, jev_available, question_specs_for, questions_payload  # noqa: E402
from deepsift.decision.jev_cache import JevCache  # noqa: E402
from deepsift.decision.state import build_state_variant  # noqa: E402
from deepsift.evaluation.jev_plan import MISSION, build_plan, limits_from_env  # noqa: E402
from deepsift.evaluation.study import git_state  # noqa: E402
from deepsift.objectives.objective import load_objectives  # noqa: E402

V1, V2 = "no_mission_objective", "no_mission_objective@q2"
QS = ("event_type", "instrument_failure", "science_value", "downlink_action")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pilot_run")
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--allow-calls", type=int, default=None)
    ap.add_argument("--allow-cost", type=float, default=None)
    args = ap.parse_args()
    load_dotenv()
    pilot = ROOT / "artifacts" / "runs" / args.pilot_run
    items = json.loads((pilot / "items.json").read_text())
    cfg = load_config(ROOT / "config" / "phase2.yaml")
    objective = load_objectives()[cfg.objective].model_dump(mode="json")
    _, selected = build_plan(cfg, "pilot", [V1])
    ev = {(t, e.id): e for e, t, _ in selected}
    assert all((it["group"], it["event_id"]) in ev for it in items), "pilot sample could not be reproduced"

    # subset: every item with ground truth, then round-robin over (dataset, instrument, score tier, rules type)
    sub = [it for it in items if it["truth"]]
    cells = defaultdict(list)
    for it in items:
        if not it["truth"]:
            cells[(it["dataset"], it["instrument"], it["score_tier"], it["rules"]["event_type"])].append(it)
    keys = sorted(cells)
    while len(sub) < args.n and any(cells[k] for k in keys):
        for k in keys:
            if cells[k] and len(sub) < args.n:
                sub.append(cells[k].pop(0))
    events = [ev[(it["group"], it["event_id"])] for it in sub]

    # preflight (measured chars/token from the cache)
    cache = JevCache()
    cst = cache.stats()
    cpt = cst["measured_chars_per_token"]
    qp = questions_payload(question_specs_for(V2))
    from deepsift.decision.jev_cache import request_key
    from deepsift.decision.jev import TRANSPORT, sdk_version
    keys_ = {}
    for e in events:
        st = build_state_variant(e, *MISSION, "no_mission_objective", objective)
        keys_[request_key(st, qp, V2, cfg.decision_engine.jev_model, sdk_version(), TRANSPORT)] = len(json.dumps(st, ensure_ascii=False)) + len(json.dumps(qp, ensure_ascii=False))
    live = [k for k in keys_ if not cache.has(k)]
    tok = sum(keys_[k] for k in live) / cpt
    cost = tok * 0.042 / 1e6
    pre = {"events": len(events), "with_ground_truth": sum(1 for it in sub if it["truth"]), "unique_requests": len(keys_),
           "live_calls_needed": len(live), "estimated_input_tokens": round(tok), "estimated_cost_usd": cost,
           "chars_per_token_measured": cpt, "estimated_minutes": round(len(live) * 0.3 / 8 / 60, 2)}
    print("PREFLIGHT", json.dumps(pre))
    max_calls, max_cost = limits_from_env()
    lim_calls, lim_cost = args.allow_calls or max_calls, args.allow_cost or max_cost
    if len(live) > lim_calls or cost > lim_cost:
        print(f"GUARD BLOCKED: {len(live)} calls / ${cost:.4f} vs limits {lim_calls} / ${lim_cost}")
        return 3
    if args.dry_run or not jev_available():
        return 0

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-jev-wording-q2-" + uuid.uuid4().hex[:4]
    out = ROOT / "artifacts" / "runs" / run_id
    out.mkdir(parents=True)
    budget = ApiBudget(lim_calls, lim_cost)
    eng = JevDecisionEngine(model=cfg.decision_engine.jev_model, variant=V2, call_log=out / "jev_calls.jsonl", run_id=run_id,
                            cache=cache, budget=budget, max_concurrency=cfg.decision_engine.max_concurrency)
    ds = eng.decide(events, *MISSION, objective=objective)
    bad = [(e.id, d.error) for e, d in zip(events, ds) if d.error or set(d.answers) != set(question_specs_for(V2))]
    rows = []
    for it, d in zip(sub, ds):
        rows.append({**{k: it[k] for k in ("group", "event_id", "dataset", "instrument", "score_tier", "quality_flagged", "truth", "rules", "flags")},
                     "q1": {q: it["jev"][V1][q] for q in QS} | {"needs_deep_analysis": it["jev"][V1]["needs_deep_analysis"]},
                     "q2": {q: {"choice": a.choice, "confidence": a.confidence, "probabilities": a.probabilities} if a.kind == "choice" else {"noul": a.noul}
                            for q, a in d.answers.items()}})

    def truth_group(r):
        t = r["truth"]
        if not t:
            return "unlabelled"
        if r["dataset"] == "real":
            return "documented"
        return "synthetic_quality_fault" if t["expected_type"] == "instrument_anomaly" else "synthetic_physical"

    cmp = {"distributions": {s: {q: dict(Counter(r[s][q]["choice"] for r in rows)) for q in QS} for s in ("q1", "q2")}}
    cmp["changed_rate"] = {q: sum(r["q1"][q]["choice"] != r["q2"][q]["choice"] for r in rows) / len(rows) for q in QS}
    facets = {"truth_group": truth_group, "quality_flagged": lambda r: str(r["quality_flagged"]), "instrument": lambda r: r["instrument"]}
    cmp["class_bias"] = {}
    for fname, f in facets.items():
        cells2 = defaultdict(list)
        for r in rows:
            cells2[f(r)].append(r)
        cmp["class_bias"][fname] = {k: {"n": len(xs), **{s: {"failure": dict(Counter(x[s]["instrument_failure"]["choice"] for x in xs)),
                                                            "p_type_instrument_anomaly": sum(x[s]["event_type"]["choice"] == "instrument_anomaly" for x in xs) / len(xs)}
                                                        for s in ("q1", "q2")}} for k, xs in sorted(cells2.items())}
    acc = {}
    for s in ("q1", "q2"):
        gt = [r for r in rows if r["truth"] and r["truth"]["n_labels"] == 1 and r["truth"]["expected_type"]]
        tf = lambda r: "yes" if r["truth"]["expected_type"] == "instrument_anomaly" else "no"  # noqa: E731
        acc[s] = {"n": len(gt), "event_type_accuracy": sum(r[s]["event_type"]["choice"] == r["truth"]["expected_type"] for r in gt) / len(gt),
                  "instrument_failure_accuracy": sum(r[s]["instrument_failure"]["choice"] == tf(r) for r in gt) / len(gt),
                  "instrument_failure_on_quality_faults": dict(Counter(r[s]["instrument_failure"]["choice"] for r in gt if tf(r) == "yes")),
                  "instrument_failure_on_physical": dict(Counter(r[s]["instrument_failure"]["choice"] for r in gt if tf(r) == "no")),
                  "event_type_conf_correct": statistics.fmean([r[s]["event_type"]["confidence"] for r in gt if r[s]["event_type"]["choice"] == r["truth"]["expected_type"]] or [float("nan")]),
                  "event_type_conf_incorrect": statistics.fmean([r[s]["event_type"]["confidence"] for r in gt if r[s]["event_type"]["choice"] != r["truth"]["expected_type"]] or [float("nan")])}
        acc[s]["rules_event_type_accuracy"] = sum(r["rules"]["event_type"] == r["truth"]["expected_type"] for r in gt) / len(gt)
    cmp["ground_truth"] = acc
    cmp["confidence_mean"] = {s: {q: statistics.fmean(r[s][q]["confidence"] for r in rows) for q in QS} for s in ("q1", "q2")}
    cmp["examples_changed"] = [{"event_id": r["event_id"], "dataset": r["dataset"], "truth": r["truth"] and (r["truth"]["expected_type"], r["truth"]["subtype"]),
                                "flags": r["flags"], "rules_type": r["rules"]["event_type"],
                                **{q: (r["q1"][q]["choice"], r["q2"][q]["choice"]) for q in ("event_type", "instrument_failure")}}
                               for r in rows if r["q1"]["instrument_failure"]["choice"] != r["q2"]["instrument_failure"]["choice"]
                               or r["q1"]["event_type"]["choice"] != r["q2"]["event_type"]["choice"]][:12]
    log = [json.loads(x) for x in (out / "jev_calls.jsonl").read_text().splitlines()]
    livel = [r for r in log if not r.get("cache_hit")]
    ops = {"live_requests": len(livel), "cache_hits": len(log) - len(livel), "input_tokens": sum(r.get("input_tokens") or 0 for r in livel),
           "output_tokens": sum(r.get("output_tokens") or 0 for r in livel), "cost_usd": sum(r.get("cost_usd") or 0 for r in livel),
           "errors": sum(1 for r in livel if r.get("error")), "retries": sum(r.get("retries") or 0 for r in livel),
           "malformed": len(bad), "models_returned": dict(Counter(r.get("model_returned") for r in livel))}
    res = {"run_id": run_id, "pilot_run": args.pilot_run, "split": "validation", "variant_q1": V1, "variant_q2": V2,
           "schema_change": "instrument_failure question + event_type.instrument_anomaly criterion (see decision/questions.py QUESTIONS_V2)",
           "preflight": pre, "operations": ops, "comparison": cmp, "git": git_state(),
           "note": "VALIDATION-only wording experiment; q1 pilot results retained unchanged"}
    (out / "wording_comparison.json").write_text(json.dumps(res, indent=1, default=str))
    (out / "rows.json").write_text(json.dumps(rows, indent=1, default=str))
    print(json.dumps({k: res[k] for k in ("run_id", "operations")}, indent=1))
    print(f"→ {(out / 'wording_comparison.json').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
