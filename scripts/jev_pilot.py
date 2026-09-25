#!/usr/bin/env python3
"""Live Jev smoke test and stratified pilot on VALIDATION events (development diagnostics only).

    uv run python scripts/jev_pilot.py --mode smoke --probe-only     # exactly ONE live request, then stop
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
from deepsift.decision.jev import (ENDPOINT, KEY_ENV, TRANSPORT, VARIANTS, ApiBudget, JevDecisionEngine,  # noqa: E402
                                   jev_available, missing_key_instructions, sdk_version)
from deepsift.decision.jev_cache import JevCache  # noqa: E402
from deepsift.decision.questions import QUESTIONS, SINGLE_DECISION_QUESTIONS  # noqa: E402
from deepsift.evaluation.jev_plan import MISSION, build_plan, fmt_summary, guard, limits_from_env  # noqa: E402
from deepsift.evaluation.metrics2 import ece, percentiles  # noqa: E402
from deepsift.evaluation.study import git_state, system_info  # noqa: E402
from deepsift.objectives.objective import load_objectives  # noqa: E402
from deepsift.priority.engine import rules_decision  # noqa: E402


def payload_check(state: dict, e) -> dict:
    """Is the state a compact candidate-event description, not raw samples? Counts numbers and list lengths."""
    nums, longest = [0], [0]

    def walk(x):
        if isinstance(x, bool) or x is None:
            return
        if isinstance(x, (int, float)):
            nums[0] += 1
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, (list, tuple)):
            longest[0] = max(longest[0], len(x))
            for v in x:
                walk(v)

    walk(state)
    raw = sum(c.n for c in e.features.channels.values())
    size = len(json.dumps(state, ensure_ascii=False))
    ok = longest[0] <= 16 and nums[0] < max(64, raw // 10) and size < 8000
    return {"ok": ok, "state_chars": size, "numeric_values_in_state": nums[0], "longest_list": longest[0],
            "raw_samples_in_event_window": raw, "top_level_keys": sorted(state)}


def key_leak_scan(paths: list[Path]) -> dict:
    """Search written artifacts for the key value (never printed); returns counts only."""
    import os

    key = os.environ.get(KEY_ENV, "").strip()
    hits = {}
    for p in paths:
        if p.is_file() and key:
            hits[str(p.relative_to(ROOT))] = p.read_bytes().count(key.encode())
    return {"files_scanned": len(hits), "files_containing_key": sum(1 for v in hits.values() if v)}


def spread(ds, specs) -> dict:
    """Agreement among repeated answers to one identical request."""
    ok = [d for d in ds if not d.error]
    if len(ok) < 2:
        return {"n": len(ok)}
    per_q, max_var = {}, 0.0
    for q, spec in specs.items():
        if spec.kind == "choice":
            ch = [d.answers[q].choice for d in ok]
            per_q[q] = Counter(ch).most_common(1)[0][1] / len(ch)
            vals = [d.answers[q].confidence for d in ok]
            max_var = max(max_var, max(vals) - min(vals))
            for k in ok[0].answers[q].probabilities:
                pv = [d.answers[q].probabilities.get(k, 0.0) for d in ok]
                max_var = max(max_var, max(pv) - min(pv))
        else:
            nv = [d.answers[q].noul for d in ok]
            max_var = max(max_var, max(nv) - min(nv))
    exact = all(d.answers == ok[0].answers for d in ok)
    return {"n": len(ok), "exact_all_answers_identical": exact, "per_question_choice_agreement": per_q,
            "largest_confidence_or_probability_variation": max_var}


def answers_brief(d) -> dict:
    return {q: ({"choice": a.choice, "confidence": a.confidence} if a.kind == "choice" else {"noul": a.noul})
            for q, a in (d.answers or {}).items()}


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
    ap.add_argument("--probe-only", action="store_true", help="send exactly one live request, report, and stop")
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
    summ["live_calls_needed"] += extra if not args.probe_only else 0
    if args.probe_only:
        summ["live_calls_needed"] = min(summ["live_calls_needed"], 1)
    max_calls, max_cost = limits_from_env()
    ok, why = guard(summ, max_calls, max_cost, args.allow_calls, args.allow_cost)
    print(fmt_summary(summ))
    print(f"GUARD {'OK' if ok else 'BLOCKED'} — {why}")
    if not ok:
        return 3
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + f"-jev-{'probe' if args.probe_only else args.mode}-" + uuid.uuid4().hex[:4]
    out = ROOT / "artifacts" / "runs" / run_id
    out.mkdir(parents=True, exist_ok=True)
    budget = ApiBudget(1 if args.probe_only else (args.allow_calls or max_calls), args.allow_cost or max_cost)
    objective = load_objectives()[cfg.objective].model_dump(mode="json")
    events = [e for e, _, _ in selected]
    strata = {e.id: list(k) for e, _, k in selected}
    # single-request probe before any batch: a rejected key or schema problem costs one call, not N
    probe_eng = JevDecisionEngine(model=cfg.decision_engine.jev_model, variant=variants[0], call_log=out / "jev_calls.jsonl",
                                  run_id=run_id, cache=cache, budget=budget, max_concurrency=1,
                                  max_retries=0 if args.probe_only else 2)   # probe = exactly one HTTP request
    [pd] = probe_eng.decide(events[:1], *MISSION, objective=objective)
    specs0 = SINGLE_DECISION_QUESTIONS if VARIANTS[variants[0]][1] == "single" else QUESTIONS
    if args.probe_only:
        recs = [json.loads(x) for x in (out / "jev_calls.jsonl").read_text().splitlines()] if (out / "jev_calls.jsonl").exists() else []
        live = [r for r in recs if not r.get("cache_hit")]
        r = live[0] if live else (recs[0] if recs else {})
        pc = payload_check(pd.state_sent or {}, events[0])
        checks = {
            "exactly_one_live_request": probe_eng.stats["live_calls"] == 1 and len(live) == 1,
            "http_success": r.get("http_status") == 200 and not pd.error,
            "jev_1_13_served": str(r.get("model_returned") or "").startswith("typesafe/jev-1.13"),
            "all_questions_parse": validate(pd, specs0) is None,
            "confidences_and_probabilities_present": all(
                (a.confidence is not None and a.probabilities) if a.kind == "choice" else a.noul is not None for a in pd.answers.values()) and bool(pd.answers),
            "usage_tokens_present": r.get("input_tokens") is not None and r.get("output_tokens") is not None,
            "cost_present_or_derivable": r.get("cost_usd") is not None,
            "payload_is_candidate_event_not_raw": pc["ok"],
        }
        rep_ = {"run_id": run_id, "passed": all(checks.values()), "checks": checks, "event_id": events[0].id,
                "endpoint": ENDPOINT, "transport": TRANSPORT, "sdk": f"typesafe-sdk {sdk_version()}",
                "model_requested": cfg.decision_engine.jev_model, "model_returned": r.get("model_returned"),
                "provider": r.get("provider"), "generation_id": r.get("request_id"), "http_status": r.get("http_status"),
                "error": r.get("error"), "error_body": r.get("error_body"), "latency_ms": r.get("latency_ms"),
                "retries": r.get("retries"), "input_tokens": r.get("input_tokens"), "output_tokens": r.get("output_tokens"),
                "cost_usd": r.get("cost_usd"), "cost_source": r.get("cost_source"), "cost_usd_derived": r.get("cost_usd_derived"),
                "payload": pc, "answers": answers_brief(pd), "validate": validate(pd, specs0)}
        rep_["key_leak"] = key_leak_scan([out / "jev_calls.jsonl"])
        (out / "probe.json").write_text(json.dumps(rep_, indent=1, default=str))
        print(json.dumps(rep_, indent=1, default=str))
        return 0 if rep_["passed"] else 1
    problem = validate(pd, specs0)
    if problem:
        print(f"STOP after 1 probe request: {problem}")
        (out / "summary.json").write_text(json.dumps({"stopped": True, "probe_event": events[0].id, "problem": problem}, indent=1))
        return 1
    print(f"probe OK: {events[0].id} · {pd.latency_ms:.0f} ms · tokens {pd.input_tokens} · model {pd.model} · "
          f"live {probe_eng.stats['live_calls']} cached {probe_eng.stats['cache_hits']}")
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
    smoke_checks = None
    if args.mode == "smoke":
        v = variants[0]
        first = answers_by[v]
        calls_before = budget.calls
        eng2 = JevDecisionEngine(model=cfg.decision_engine.jev_model, variant=v, call_log=out / "jev_calls.jsonl", run_id=run_id,
                                 cache=cache, budget=budget, max_concurrency=4)
        again = eng2.decide(events, *MISSION, objective=objective)
        recs = [json.loads(x) for x in (out / "jev_calls.jsonl").read_text().splitlines()]
        live_recs = [r for r in recs if not r.get("cache_hit")]
        per_event = Counter(r["event_id"] for r in live_recs)
        payloads = {e.id: payload_check(d.state_sent or {}, e) for e, d in zip(events, again)}
        smoke_checks = {
            "one_event_one_request": all(n == 1 for n in per_event.values()),
            "live_requests_per_event": dict(Counter(per_event.values())),
            "all_questions_in_the_same_request": all(set(r.get("answers") or {}) == set(QUESTIONS) for r in live_recs if not r.get("error")),
            "no_raw_rows_sent": all(p["ok"] for p in payloads.values()),
            "max_state_chars": max(p["state_chars"] for p in payloads.values()),
            "max_numeric_values_in_state": max(p["numeric_values_in_state"] for p in payloads.values()),
            "min_raw_samples_in_event_window": min(p["raw_samples_in_event_window"] for p in payloads.values()),
            "identical_repeat_live_calls": budget.calls - calls_before,
            "identical_repeat_cache_hits": eng2.stats["cache_hits"],
            "cache_determinism_answers_identical": all(first[e.id].answers == d.answers for e, d in zip(events, again)),
            "probe_event_first_request_cache_miss_then_hit": None,
        }
        pr = [r for r in recs if r["event_id"] == events[0].id]
        smoke_checks["probe_event_first_request_cache_miss_then_hit"] = [bool(r.get("cache_hit")) for r in pr]
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
        specs = SINGLE_DECISION_QUESTIONS if VARIANTS[v][1] == "single" else QUESTIONS
        for e in events[:3]:
            ds = eng.decide([e] * args.repeat, *MISSION, objective=objective)
            # the cached first answer + N uncached identical repeats
            repeat[e.id] = spread([answers_by[v][e.id]] + ds, specs) | {"uncached_repeats": len(ds),
                                                                          "errors": sum(1 for d in ds if d.error)}
    # representative events: rules decision vs Jev answers
    v = variants[0]
    reps = []
    for e in events:
        d = answers_by[v][e.id]
        rd = rules_decision(e, cfg)
        reps.append({"event_id": e.id, "stratum": strata[e.id], "instrument": e.instrument, "sensors": e.sensors,
                     "features": {"deviation_score": round(e.features.deviation_score, 2), "rarity": round(e.features.rarity_score, 3),
                                  "duration_s": e.features.duration_s, "correlated_channels": e.features.correlated_channels,
                                  "cross_instrument": e.features.cross_instrument_coincidence, "lmst_hour": round(e.features.lmst_hour, 2),
                                  "trigger_reasons": e.features.trigger_reasons,
                                  "flags": {k: c.flags for k, c in e.features.channels.items() if c.flags}},
                     "rules": {"science_value": rd.answers["science_value"].choice, "event_type": rd.answers["event_type"].choice},
                     "jev": answers_brief(d), "latency_ms": d.latency_ms, "input_tokens": d.input_tokens,
                     "disagrees_on_type": bool(d.answers) and d.answers["event_type"].choice != rd.answers["event_type"].choice,
                     "disagrees_on_value": bool(d.answers) and d.answers["science_value"].choice != rd.answers["science_value"].choice})
    recs = [json.loads(x) for x in (out / "jev_calls.jsonl").read_text().splitlines()]
    live_recs = [r for r in recs if not r.get("cache_hit")]
    ops = {"live_requests": len(live_recs), "cache_hits_logged": len(recs) - len(live_recs),
           "input_tokens": sum(r.get("input_tokens") or 0 for r in live_recs),
           "output_tokens": sum(r.get("output_tokens") or 0 for r in live_recs),
           "cost_usd_reported": sum(r.get("cost_usd") or 0 for r in live_recs if r.get("cost_source") == "usage.cost"),
           "cost_usd_derived": sum(r.get("cost_usd_derived") or 0 for r in live_recs),
           "cost_sources": dict(Counter(r.get("cost_source") for r in live_recs)),
           "latency_ms_live": percentiles([r["latency_ms"] for r in live_recs if not r.get("error")]),
           "retries": sum(r.get("retries") or 0 for r in live_recs),
           "api_errors": sum(1 for r in live_recs if r.get("error")),
           "http_statuses": dict(Counter(r.get("http_status") for r in live_recs)),
           "models_returned": dict(Counter(r.get("model_returned") for r in live_recs)),
           "providers": dict(Counter(r.get("provider") for r in live_recs)),
           "malformed_responses": sum(p["invalid"] for p in per_variant.values())}
    summary = {"run_id": run_id, "mode": args.mode, "split": "validation", "variants": variants, "preflight": summ,
               "transport": TRANSPORT, "endpoint": ENDPOINT, "sdk": f"typesafe-sdk {sdk_version()}",
               "model_requested": cfg.decision_engine.jev_model, "operations": ops, "smoke_checks": smoke_checks,
               "representative_candidates": reps,
               "per_variant": per_variant, "event_type_agreement_between_variants": agree, "repeat_variability": repeat,
               "strata": Counter(tuple(s) for s in strata.values()).most_common(), "budget_used": {"calls": budget.calls, "cost_usd": budget.cost_usd},
               "note": "DEVELOPMENT diagnostics on VALIDATION only; not a performance result."}
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    (out / "manifest.json").write_text(json.dumps({"run_id": run_id, "split": "validation", "mode": args.mode, "git": git_state(),
                                                   "config_version": cfg.version(), "model": cfg.decision_engine.jev_model,
                                                   "transport": TRANSPORT, "endpoint": ENDPOINT,
                                                   "models_returned": ops["models_returned"], "providers": ops["providers"],
                                                   "sdk": sdk_version(), "system": system_info(), "event_ids": [e.id for e in events]}, indent=1, default=str))
    leak = key_leak_scan(list(out.iterdir()) + [cache.path])
    summary["key_leak"] = leak
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    print(json.dumps({"operations": ops, "smoke_checks": smoke_checks, "repeat": repeat, "key_leak": leak}, indent=1, default=str))
    print(f"{args.mode} complete → {out.relative_to(ROOT)} · live calls {budget.calls} · cost ${budget.cost_usd:.5f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
