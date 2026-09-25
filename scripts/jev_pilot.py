#!/usr/bin/env python3
"""Live Jev smoke test and stratified pilot on VALIDATION events (development diagnostics only).

    uv run python scripts/jev_pilot.py --mode smoke [--repeat 3]     # ~30 events, one variant (+ repeat variability)
    uv run python scripts/jev_pilot.py --mode pilot                  # ~300 events × 5 variants

Always runs the preflight and the budget guard first; stops at the first malformed answer.
Outputs artifacts/runs/<run_id>/{summary.json, jev_calls.jsonl, manifest.json}. Never reads TEST data.
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
from deepsift.decision.jev import VARIANTS, ApiBudget, JevDecisionEngine, jev_available, missing_key_instructions, sdk_version  # noqa: E402
from deepsift.decision.jev_cache import JevCache  # noqa: E402
from deepsift.decision.questions import QUESTIONS, SINGLE_DECISION_QUESTIONS  # noqa: E402
from deepsift.evaluation.jev_plan import MISSION, build_plan, fmt_summary, guard, limits_from_env  # noqa: E402
from deepsift.evaluation.metrics2 import ece, percentiles  # noqa: E402
from deepsift.evaluation.study import git_state, system_info  # noqa: E402
from deepsift.objectives.objective import load_objectives  # noqa: E402


def validate(d, specs) -> str | None:
    if d.error:
        return f"error: {d.error}"
    if set(d.answers) != set(specs):
        return f"answer keys {sorted(d.answers)} != questions {sorted(specs)}"
    for name, q in specs.items():
        a = d.answers[name]
        if q.kind == "choice":
            if a.choice not in q.criteria:
                return f"{name}: choice {a.choice!r} not in criteria"
            if set(a.probabilities) != set(q.criteria):
                return f"{name}: probability keys mismatch"
            if abs(sum(a.probabilities.values()) - 1) > 0.05:
                return f"{name}: probabilities sum {sum(a.probabilities.values()):.3f}"
            if a.confidence is None or not 0 <= a.confidence <= 1:
                return f"{name}: confidence {a.confidence}"
        elif a.noul is None or not 0 <= a.noul <= 1:
            return f"{name}: noul {a.noul}"
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["smoke", "pilot"], required=True)
    ap.add_argument("--variants", default=None)
    ap.add_argument("--n", type=int, default=None)
    ap.add_argument("--repeat", type=int, default=0, help="smoke only: re-ask 3 events N times live (no cache) to measure variability")
    ap.add_argument("--allow-calls", type=int, default=None)
    ap.add_argument("--allow-cost", type=float, default=None)
    args = ap.parse_args()
    load_dotenv()
    if not jev_available():
        print(missing_key_instructions())
        return 2
    cfg = load_config(ROOT / "config" / "phase2.yaml")
    variants = args.variants.split(",") if args.variants else (["no_mission_objective"] if args.mode == "smoke" else list(VARIANTS))
    plan, selected = build_plan(cfg, args.mode, variants, n_sample=args.n)
    cache = JevCache()
    summ = plan.summary(cache)
    extra = 3 * args.repeat if args.mode == "smoke" else 0
    summ["live_calls_needed"] += extra
    max_calls, max_cost = limits_from_env()
    ok, why = guard(summ, max_calls, max_cost, args.allow_calls, args.allow_cost)
    print(fmt_summary(summ))
    print(f"GUARD {'OK' if ok else 'BLOCKED'} — {why}")
    if not ok:
        return 3
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + f"-jev-{args.mode}-" + uuid.uuid4().hex[:4]
    out = ROOT / "artifacts" / "runs" / run_id
    out.mkdir(parents=True, exist_ok=True)
    budget = ApiBudget(args.allow_calls or max_calls, args.allow_cost or max_cost)
    objective = load_objectives()[cfg.objective].model_dump(mode="json")
    events = [e for e, _, _ in selected]
    strata = {e.id: list(k) for e, _, k in selected}
    # single-request probe before any batch: a rejected key or schema problem costs one call, not N
    probe_eng = JevDecisionEngine(model=cfg.decision_engine.jev_model, variant=variants[0], call_log=out / "jev_calls.jsonl",
                                  run_id=run_id, cache=cache, budget=budget, max_concurrency=1)
    [pd] = probe_eng.decide(events[:1], *MISSION, objective=objective)
    specs0 = SINGLE_DECISION_QUESTIONS if VARIANTS[variants[0]][1] == "single" else QUESTIONS
    problem = validate(pd, specs0)
    if problem:
        print(f"STOP after 1 probe request: {problem}")
        (out / "summary.json").write_text(json.dumps({"stopped": True, "probe_event": events[0].id, "problem": problem}, indent=1))
        return 1
    print(f"probe OK: {events[0].id} · {pd.latency_ms:.0f} ms · tokens {pd.input_tokens} · model {pd.model}")
    per_variant, answers_by = {}, defaultdict(dict)
    for v in variants:
        eng = JevDecisionEngine(model=cfg.decision_engine.jev_model, timeout_s=cfg.decision_engine.timeout_s,
                                max_concurrency=cfg.decision_engine.max_concurrency, price_per_mtok_input_usd=cfg.decision_engine.price_per_mtok_input_usd,
                                variant=v, call_log=out / "jev_calls.jsonl", run_id=run_id, cache=cache, budget=budget)
        ds = eng.decide(events, *MISSION, objective=objective)
        specs = SINGLE_DECISION_QUESTIONS if VARIANTS[v][1] == "single" else QUESTIONS
        bad = [(e.id, validate(d, specs)) for e, d in zip(events, ds)]
        bad = [b for b in bad if b[1]]
        if bad and args.mode == "smoke":
            print(f"STOP: malformed/failed answers for {v}: {bad[:5]}")
            (out / "summary.json").write_text(json.dumps({"stopped": True, "bad": bad}, indent=1))
            return 1
        lat = [d.latency_ms for d in ds if not d.error]
        toks = [d.input_tokens for d in ds if d.input_tokens]
        for e, d in zip(events, ds):
            answers_by[v][e.id] = d
        dist = {q: Counter(d.answers[q].choice for d in ds if not d.error and q in d.answers and d.answers[q].choice)
                for q in specs if specs[q].kind == "choice"}
        conf = {q: statistics.fmean([d.answers[q].confidence for d in ds if not d.error and q in d.answers]) for q in specs if specs[q].kind == "choice"} if specs else {}
        # cheap label diagnostics (validation only): importance vs overlap with an injection; type vs injected type
        imp_c, imp_y, typ_c, typ_y = [], [], [], []
        for e, d in zip(events, ds):
            if d.error:
                continue
            labelled = bool(e.synthetic_injection_ids)
            if "science_value" in d.answers:
                p = sum(pp for k, pp in d.answers["science_value"].probabilities.items() if k in ("medium", "high", "critical"))
                imp_c.append(p)
                imp_y.append(labelled)
            elif "retain" in d.answers:
                imp_c.append(d.answers["retain"].noul)
                imp_y.append(labelled)
        per_variant[v] = {"events": len(events), "invalid": len(bad), "invalid_examples": bad[:10], "live_calls": eng.stats["live_calls"],
                          "cache_hits": eng.stats["cache_hits"], "latency_ms": percentiles(lat),
                          "input_tokens_per_request": statistics.fmean(toks) if toks else None,
                          "choice_distributions": {q: dict(c) for q, c in dist.items()}, "mean_confidence": conf,
                          "importance_calibration_vs_injection_overlap": ece(imp_c, imp_y, bins=5)}
        print(f"{v}: invalid {len(bad)}/{len(events)} · live {eng.stats['live_calls']} · cached {eng.stats['cache_hits']} · "
              f"p50 {per_variant[v]['latency_ms'].get('p50', 0):.0f} ms · tokens/req {per_variant[v]['input_tokens_per_request']}")
    agree = {}
    five = [v for v in variants if VARIANTS[v][1] != "single"]
    for i, a in enumerate(five):
        for b in five[i + 1:]:
            same = [answers_by[a][eid].answers["event_type"].choice == answers_by[b][eid].answers["event_type"].choice
                    for eid in answers_by[a] if not answers_by[a][eid].error and not answers_by[b][eid].error]
            agree[f"{a}~{b}"] = sum(same) / len(same) if same else None
    repeat = None
    if args.mode == "smoke" and args.repeat:
        v = variants[0]
        eng = JevDecisionEngine(model=cfg.decision_engine.jev_model, variant=v, call_log=out / "jev_calls.jsonl", run_id=run_id,
                                use_cache=False, budget=budget, max_concurrency=1)
        repeat = {}
        for e in events[:3]:
            ds = eng.decide([e] * args.repeat, *MISSION, objective=objective)
            probs = [d.answers["science_value"].probabilities for d in ds if not d.error]
            repeat[e.id] = {"n": len(probs), "max_abs_spread_science_value": max(
                (max(p[k] for p in probs) - min(p[k] for p in probs)) for k in probs[0]) if probs else None,
                "choices": Counter(d.answers["science_value"].choice for d in ds if not d.error)}
    summary = {"run_id": run_id, "mode": args.mode, "split": "validation", "variants": variants, "preflight": summ,
               "per_variant": per_variant, "event_type_agreement_between_variants": agree, "repeat_variability": repeat,
               "strata": Counter(tuple(s) for s in strata.values()).most_common(), "budget_used": {"calls": budget.calls, "cost_usd": budget.cost_usd},
               "note": "DEVELOPMENT diagnostics on VALIDATION only; not a performance result."}
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    (out / "manifest.json").write_text(json.dumps({"run_id": run_id, "split": "validation", "mode": args.mode, "git": git_state(),
                                                   "config_version": cfg.version(), "model": cfg.decision_engine.jev_model,
                                                   "sdk": sdk_version(), "system": system_info(), "event_ids": [e.id for e in events]}, indent=1, default=str))
    print(f"{args.mode} complete → {out.relative_to(ROOT)} · live calls {budget.calls} · cost ${budget.cost_usd:.5f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
