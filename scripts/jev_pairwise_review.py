#!/usr/bin/env python3
"""JEV PAIRWISE REVIEWER — experimental, TEXT-ONLY, opt-in (Phase 3.2, development split only).

    uv run python scripts/jev_pairwise_review.py                       # preflight only (no network)
    DEEPSIFT_EXPERIMENTAL_JEV=1 uv run python scripts/jev_pairwise_review.py --live

Jev receives structured metadata/features only. It does not see the images. Output is JEV PAIRWISE PREFERENCE:
preference alignment, not accuracy; not human review, not expert review, not ground truth. Never used for tuning.

Pairs: exactly the 77 pairs in data/review/pairs_v1.json (Phase 3.1 disagreement sampler). Calls:
  1. every pair in stored order (AB)         — cached
  2. every pair swapped (BA)                  — cached (order is part of the key)
  3. 12 stratified pairs × 2 uncached repeats (AB) — model repeatability, never written to the cache
  4. every AB request re-read from the cache  — cache determinism (no network)
Hard stop: JEV_PAIRWISE_MAX_COST_USD (default and maximum 0.05). If the projected cost exceeds it, stop before any call.

Strategy preferences compared afterwards (declared before running): FIFO = earlier capture; SIZE-AWARE, EMBEDDING-NOVELTY,
TELEMETRY-PRIORITY, PHASH-REPRESENTATIVES = lower Phase 3.1 V2 rank (TELEMETRY: no preference when both telemetry scores
are equal); POSITION_SAMPLING = acquisition whose rover position (site, drive, pose) has fewer development acquisitions
(no preference if equal).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import uuid
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "pipeline"))

from deepsift.core.env import load_dotenv  # noqa: E402
from deepsift.decision import jev as J  # noqa: E402
from deepsift.decision import jev_pairwise as P  # noqa: E402
from deepsift.imaging import quality_v2 as q2  # noqa: E402
from deepsift.imaging.acquisitions import group_acquisitions  # noqa: E402
from deepsift.imaging.features import hamming, load_primary  # noqa: E402

BASE = ROOT / "artifacts" / "phase3" / "20260925T132323-phase3-dev-baseline-ff13"
P31 = ROOT / "artifacts" / "phase3_1" / "20260925T133727-phase3.1-dev-controls-0ceb" / "results.json"
PAIRS = ROOT / "data" / "review" / "pairs_v1.json"
OUT = ROOT / "data" / "review" / "jev_pairwise_v1.json"
MODEL = "typesafe/jev-1.13"
CAP_MAX = 0.05
CHARS_PER_TOKEN = 2.43           # measured in Phase 2b on this API
PRICE_PER_MTOK = 0.042           # measured in Phase 2b (usage.cost)
SAFETY = 1.5                     # projection margin
REPEAT_PAIRS, REPEATS = 12, 2
STRATEGIES = ["FIFO", "SIZE-AWARE", "EMBEDDING-NOVELTY", "TELEMETRY-PRIORITY", "PHASH-REPRESENTATIVES", "POSITION_SAMPLING"]


def build_states():
    obs = [json.loads(x) for x in (BASE / "observations.jsonl").read_text().splitlines()]
    E = np.load(BASE / "embeddings.npy")
    idx = {o["id"]: i for i, o in enumerate(obs)}
    p32 = sorted((ROOT / "artifacts" / "phase3_2").glob("*/byte_accounting_per_eye.json"))[-1]
    full = defaultdict(float)
    for r in json.loads(p32.read_text()):
        full[r["acq_id"]] += r["full_bytes_NASA_LABEL_ESTIMATE"]
    pose_n = Counter(tuple(o["source_metadata"]["pose"]) for o in obs)
    prev = {}
    seqs = defaultdict(list)
    for i in sorted(range(len(obs)), key=lambda i: obs[i]["sclk"]):
        seqs[(obs[i]["sol"], obs[i]["sequence_id"])].append(i)
    for fr in seqs.values():
        prev[fr[0]] = None
        for a, b in zip(fr, fr[1:]):
            prev[b] = float(1.0 - E[a] @ E[b])
    pairs = json.loads(PAIRS.read_text())["pairs"]
    need = sorted({idx[p[s]] for p in pairs for s in ("A", "B")})
    acqs = group_acquisitions(json.loads((ROOT / "data" / "manifests" / "navcam_development.json").read_text())["products"])
    TH = json.loads(P31.read_text())["quality"]["v2_thresholds"]
    qv2 = {}
    for i in need:
        st, reasons = q2.classify(q2.features(load_primary(acqs[i]), acqs[i]["primary"].get("error_pixels")), obs[i]["primary_tier"], TH)
        qv2[i] = "passed" if st == "CLEAN" else "flagged: " + ", ".join(reasons)
    sides = {i: P.side_summary(obs[i], full[obs[i]["id"]] / 1e3, prev.get(i), qv2[i], pose_n[tuple(obs[i]["source_metadata"]["pose"])]) for i in need}

    def xy(i):
        lc = obs[i]["location_context"]
        return None if "landing_x" not in lc else np.array([lc["landing_x"], lc["landing_y"]])
    reqs = []
    for p in pairs:
        a, b = idx[p["A"]], idx[p["B"]]
        pa, pb = xy(a), xy(b)
        d = float(np.linalg.norm(pa - pb)) if pa is not None and pb is not None else None
        rel = P.relation(obs[a], obs[b], d, float(1.0 - E[a] @ E[b]), hamming(int(obs[a]["image_features"]["phash"], 16), int(obs[b]["image_features"]["phash"], 16)))
        for order, (x, y) in (("AB", (a, b)), ("BA", (b, a))):
            s = P.pair_state(sides[x], sides[y], rel)
            P.assert_clean(s)
            reqs.append({"pair_id": p["pair_id"], "order": order, "state": s})
    overlap = [abs(prev[i] - obs[i]["image_features"]["embedding_novelty"]) < 1e-6 for i in need if prev.get(i) is not None]
    reqs[0]["_overlap"] = {"sides_with_previous_frame": len(overlap), "previous_frame_difference_equals_novelty_input": int(sum(overlap))}
    return obs, idx, pairs, pose_n, reqs


def strategy_pref(p, obs, idx, pose_n):
    a, b = idx[p["A"]], idx[p["B"]]
    sa, sb = p["scores"][str(a)], p["scores"][str(b)]
    lower = lambda k: None if sa[k] == sb[k] else (p["A"] if sa[k] < sb[k] else p["B"])  # noqa: E731
    na, nb = pose_n[tuple(obs[a]["source_metadata"]["pose"])], pose_n[tuple(obs[b]["source_metadata"]["pose"])]
    return {"FIFO": p["A"] if obs[a]["sclk"] < obs[b]["sclk"] else p["B"], "SIZE-AWARE": lower("size_rank"),
            "EMBEDDING-NOVELTY": lower("novelty_rank"),
            "TELEMETRY-PRIORITY": None if sa["telemetry_score"] == sb["telemetry_score"] else lower("telemetry_rank"),
            "PHASH-REPRESENTATIVES": lower("phash_rep_rank"),
            "POSITION_SAMPLING": None if na == nb else (p["A"] if na < nb else p["B"])}


def wilson(k, n, z=1.96):
    if n == 0:
        return None
    ph = k / n
    d = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / d
    h = z * ((ph * (1 - ph) / n + z * z / (4 * n * n)) ** 0.5) / d
    return [round(c - h, 3), round(c + h, 3)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--experimental-jev", action="store_true")
    args = ap.parse_args()
    load_dotenv()
    cap = float(os.environ.get("JEV_PAIRWISE_MAX_COST_USD", CAP_MAX))
    if cap > CAP_MAX:
        print(f"STOP: JEV_PAIRWISE_MAX_COST_USD={cap} exceeds the approved maximum {CAP_MAX}; the cap is not raised silently.")
        return 3
    obs, idx, pairs, pose_n, reqs = build_states()
    sdkv = J.sdk_version()
    cache = P.PairwiseCache()
    for r in reqs:
        r["input_hash"] = P.request_key(r["state"], r["order"], MODEL, P.EXPECTED_SNAPSHOT, sdkv, J.TRANSPORT)
    rng = random.Random(20260925)
    by_cat = defaultdict(list)
    for p in pairs:
        by_cat[p["category"]].append(p["pair_id"])
    quota = {"SIZE_VS_NOVELTY": 4, "TELEMETRY_VS_IMAGE": 4, "SEQUENCE_METHODS": 3, "PHASH_VS_EMBEDDING": 1}
    rep_ids = sorted(x for c, k in quota.items() for x in rng.sample(sorted(by_cat[c]), min(k, len(by_cat[c]))))
    rep_reqs = [dict(r, repeat=k) for r in reqs if r["order"] == "AB" and r["pair_id"] in rep_ids for k in (1, 2)]
    qchars = len(json.dumps(P.questions_payload(), separators=(",", ":")))
    live_main = [r for r in reqs if cache.get(r["input_hash"], P.EXPECTED_SNAPSHOT) is None]
    planned = live_main + rep_reqs
    chars = sum(len(json.dumps(r["state"], separators=(",", ":"))) + qchars for r in planned)
    proj = chars / CHARS_PER_TOKEN * PRICE_PER_MTOK / 1e6 * SAFETY
    pre = {"schema_version": P.SCHEMA_VERSION, "pairs": len(pairs), "requests_AB_BA": len(reqs), "cached": len(reqs) - len(live_main),
           "live_main": len(live_main), "live_repeats": len(rep_reqs), "repeat_pair_ids": rep_ids, "projected_input_chars": chars,
           "projected_cost_usd_with_1.5x_margin": round(proj, 5), "cap_usd": cap, "model_requested": MODEL,
           "expected_snapshot": P.EXPECTED_SNAPSHOT, "transport": J.TRANSPORT, "sdk": sdkv,
           "feature_overlap_with_strategy_inputs": reqs[0]["_overlap"], "sample_state_AB": reqs[0]["state"]}
    print(json.dumps({k: v for k, v in pre.items() if k != "sample_state_AB"}, indent=1))
    if proj > cap:
        print("STOP: projected cost exceeds JEV_PAIRWISE_MAX_COST_USD — no live call made.")
        return 3
    if not args.live:
        print("preflight only (pass --live with DEEPSIFT_EXPERIMENTAL_JEV=1 to call Jev)")
        return 0
    if not (args.experimental_jev or os.environ.get("DEEPSIFT_EXPERIMENTAL_JEV") == "1"):
        print("Jev is opt-in: set DEEPSIFT_EXPERIMENTAL_JEV=1 or pass --experimental-jev")
        return 2
    if not J.jev_available():
        print(J.missing_key_instructions())
        return 2

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-jev-pairwise-" + uuid.uuid4().hex[:4]
    out = ROOT / "artifacts" / "phase3_2" / run_id
    out.mkdir(parents=True)
    (out / "preflight.json").write_text(json.dumps(pre, indent=1))
    (out / "states.jsonl").write_text("".join(json.dumps({k: r[k] for k in ("pair_id", "order", "input_hash", "state")}) + "\n" for r in reqs))
    log = out / "calls.jsonl"
    budget = J.ApiBudget(max_calls=len(planned), max_cost_usd=cap)
    from typesafe_sdk import RetryPolicy, TypeSafeClient

    client = TypeSafeClient(api_key=os.environ[J.KEY_ENV].strip(), base_url=J.BASE_URL, timeout=15.0, retry=RetryPolicy(max_retries=0))
    questions = J.build_questions(P.QUESTIONS)
    fatal = {"err": None}

    def record(r, status, ans, meta):
        pr, rs = ans.get("priority", {}), ans.get("reason", {})
        return {"run_id": run_id, "timestamp": datetime.now(timezone.utc).isoformat(), "label": P.LABEL, "pair_id": r["pair_id"],
                "order": r["order"], "repeat": r.get("repeat", 0), "model_requested": MODEL, "model_returned": meta.get("model_returned"),
                "transport": J.TRANSPORT, "provider": meta.get("provider"), "input_hash": r["input_hash"], "schema_version": P.SCHEMA_VERSION,
                "choice": pr.get("choice"), "choice_confidence": pr.get("confidence"), "choice_probabilities": pr.get("probabilities"),
                "reason": rs.get("choice"), "reason_confidence": rs.get("confidence"), "latency_ms": meta.get("latency_ms"),
                "input_tokens": meta.get("input_tokens"), "output_tokens": meta.get("output_tokens"), "cost_usd": meta.get("cost_usd"),
                "cache_status": status, "error": meta.get("error")}

    def call(r, use_cache: bool):
        if use_cache:
            hit = cache.get(r["input_hash"], P.EXPECTED_SNAPSHOT)
            if hit is not None:
                return record(r, "HIT", hit["answers"], {**hit, "cost_usd": 0.0})
        if fatal["err"]:
            return record(r, "NOT_SENT", {}, {"error": fatal["err"]})
        budget.reserve()
        t0, resp, err = time.perf_counter(), None, None
        for attempt in range(3):
            try:
                resp = client.system_one(state=r["state"], questions=questions, model=MODEL)
                err = None
                break
            except Exception as exc:  # noqa: BLE001
                err = f"{type(exc).__name__}: {exc}"[:300]
                if type(exc).__name__ in J.FATAL:
                    fatal["err"] = err
                    break
                if type(exc).__name__ not in J.RETRYABLE:
                    break
                time.sleep(0.5 * 2 ** attempt)
        lat = (time.perf_counter() - t0) * 1000
        if resp is None:
            return record(r, "ERROR", {}, {"latency_ms": lat, "error": err})
        ans = {k: v.model_dump() for k, v in J.convert_answers(resp).items()}
        ex = J.openrouter_extras(resp)
        meta = {"model_returned": getattr(resp, "model", None), "provider": ex["provider"], "latency_ms": lat,
                "input_tokens": getattr(resp.usage, "input_tokens", None), "output_tokens": getattr(resp.usage, "output_tokens", None),
                "cost_usd": ex["cost_usd"] if ex["cost_usd"] is not None else (getattr(resp.usage, "input_tokens", 0) or 0) * PRICE_PER_MTOK / 1e6}
        budget.add_cost(meta["cost_usd"])
        if use_cache and meta["model_returned"] == P.EXPECTED_SNAPSHOT:
            cache.put(r["input_hash"], pair_id=r["pair_id"], order=r["order"], model_requested=MODEL, transport=J.TRANSPORT,
                      answers=ans, run_id=run_id, **meta)
        return record(r, "BYPASS_REPEAT" if not use_cache else "MISS_LIVE", ans, meta)

    recs = []
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            recs += list(pool.map(lambda r: call(r, True), reqs))
            recs += list(pool.map(lambda r: call(r, False), rep_reqs))
    except J.JevBudgetExceeded as exc:
        print("STOP:", exc)
    determinism = [call(r, True) for r in reqs if r["order"] == "AB"]
    with log.open("w") as fh:
        for x in recs + [dict(d, phase="cache_determinism_reread") for d in determinism]:
            fh.write(json.dumps(x) + "\n")

    # ------------------------------------------------------------------ analysis (preference alignment, not accuracy)
    main_ = {(x["pair_id"], x["order"]): x for x in recs if x["repeat"] == 0}
    ok = [x for x in main_.values() if x["choice"]]
    pmap = {p["pair_id"]: p for p in pairs}

    def chosen(x):
        p = pmap[x["pair_id"]]
        first, second = (p["A"], p["B"]) if x["order"] == "AB" else (p["B"], p["A"])
        return {"A": first, "B": second}.get(x["choice"], x["choice"])
    swap = []
    for p in pairs:
        ab, ba = main_.get((p["pair_id"], "AB")), main_.get((p["pair_id"], "BA"))
        if ab and ba and ab["choice"] and ba["choice"]:
            swap.append((p["pair_id"], chosen(ab), chosen(ba)))
    consistent = {pid for pid, a, b in swap if a == b}
    agree = {}
    for s in STRATEGIES:
        rows = {"all": [], "swap_consistent": []}
        for x in (v for v in ok if v["order"] == "AB"):
            p = pmap[x["pair_id"]]
            pref = strategy_pref(p, obs, idx, pose_n)[s]
            c = chosen(x)
            if pref is None or c not in (p["A"], p["B"]):
                continue
            rows["all"].append(c == pref)
            if x["pair_id"] in consistent:
                rows["swap_consistent"].append(c == pref)
        agree[s] = {k: {"n": len(v), "agreement": round(float(np.mean(v)), 3) if v else None, "wilson95": wilson(sum(v), len(v))} for k, v in rows.items()}
    by_cat_agree = {}
    for c in by_cat:
        by_cat_agree[c] = Counter(x["choice"] for x in ok if x["order"] == "AB" and pmap[x["pair_id"]]["category"] == c)
    reps = defaultdict(list)
    for x in recs:
        if x["pair_id"] in rep_ids and x["order"] == "AB" and x["choice"]:
            reps[x["pair_id"]].append((x["choice"], x["reason"], x["choice_confidence"]))
    det_match = sum(1 for d in determinism if main_.get((d["pair_id"], "AB")) and d["choice"] == main_[(d["pair_id"], "AB")]["choice"]
                    and d["reason"] == main_[(d["pair_id"], "AB")]["reason"])
    pos = Counter(x["choice"] for x in ok)
    live = [x for x in recs if x["cache_status"] in ("MISS_LIVE", "BYPASS_REPEAT")]
    lat = sorted(x["latency_ms"] for x in live if x["latency_ms"])
    summary = {
        "label": P.LABEL, "notice": "Jev receives structured metadata/features only. It does not see the images.",
        "not": list(P.FORBIDDEN_LABELS) + ["TELEMETRY VALIDATION"], "run_id": run_id, "schema_version": P.SCHEMA_VERSION,
        "pairs_file": str(PAIRS.relative_to(ROOT)), "pair_ids_included": [p["pair_id"] for p in pairs],
        "model_requested": MODEL, "snapshots_returned": dict(Counter(x["model_returned"] for x in recs if x["model_returned"])),
        "providers": dict(Counter(x["provider"] for x in live if x["provider"])), "transport": J.TRANSPORT,
        "calls": {"total_records": len(recs), "live": len(live), "cache_hits": sum(x["cache_status"] == "HIT" for x in recs),
                  "errors": sum(x["cache_status"] in ("ERROR", "NOT_SENT") for x in recs)},
        "cost_usd": round(sum(x["cost_usd"] or 0 for x in live), 6), "cap_usd": cap,
        "tokens": {"input": sum(x["input_tokens"] or 0 for x in live), "output": sum(x["output_tokens"] or 0 for x in live)},
        "latency_ms_p50_p95": [lat[len(lat) // 2], lat[int(len(lat) * 0.95)]] if lat else None,
        "choice_distribution_AB": dict(Counter(x["choice"] for x in ok if x["order"] == "AB")),
        "choice_distribution_all_main": dict(pos),
        "reason_distribution_AB": dict(Counter(x["reason"] for x in ok if x["order"] == "AB")),
        "choice_confidence_p10_p50_p90": [round(float(np.percentile([x["choice_confidence"] for x in ok], q)), 3) for q in (10, 50, 90)] if ok else None,
        "reason_confidence_p50": round(float(np.median([x["reason_confidence"] for x in ok])), 3) if ok else None,
        "choice_by_category_AB": {k: dict(v) for k, v in by_cat_agree.items()},
        "ab_swap": {"pairs_compared": len(swap), "consistent": len(consistent),
                    "consistency_rate": round(len(consistent) / len(swap), 3) if swap else None,
                    "position_A_share_among_A_or_B": round(pos["A"] / max(1, pos["A"] + pos["B"]), 3),
                    "position_A_share_wilson95": wilson(pos["A"], pos["A"] + pos["B"])},
        "repeatability_uncached": {"pairs": rep_ids, "repeats_per_pair": REPEATS,
                                   "choice_identical_across_all_draws": sum(1 for v in reps.values() if len({c for c, _, _ in v}) == 1),
                                   "reason_identical_across_all_draws": sum(1 for v in reps.values() if len({r for _, r, _ in v}) == 1),
                                   "pairs_with_three_draws": sum(1 for v in reps.values() if len(v) == 3), "draws": {k: v for k, v in reps.items()}},
        "cache_determinism": {"rereads": len(determinism), "identical_to_first_answer": det_match,
                              "note": "cache hits replay one recorded draw — this is NOT model repeatability"},
        "feature_overlap_with_strategy_inputs": pre["feature_overlap_with_strategy_inputs"],
        "agreement_with_strategies": agree,
        "agreement_note": "preference alignment only; no strategy is correct by construction and Jev is not ground truth. SIZE-AWARE and "
                          "POSITION_SAMPLING use inputs Jev also sees (downlink size, same-position count); the previous-frame visual difference Jev sees "
                          "often equals the EMBEDDING-NOVELTY input (see feature_overlap_with_strategy_inputs). FIFO, TELEMETRY-PRIORITY and "
                          "PHASH-REPRESENTATIVES scores/ranks are withheld.",
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    OUT.write_text(json.dumps({**summary, "answers": [{k: x[k] for k in ("pair_id", "order", "repeat", "choice", "choice_confidence", "reason",
                                                                          "reason_confidence", "model_returned", "cache_status")} for x in recs]},
                              indent=1, default=str))
    print(json.dumps({k: summary[k] for k in ("calls", "cost_usd", "snapshots_returned", "choice_distribution_AB", "reason_distribution_AB",
                                              "ab_swap", "cache_determinism")}, indent=1, default=str))
    print(json.dumps(agree, indent=1))
    print(f"→ {out.relative_to(ROOT)}  ·  {OUT.relative_to(ROOT)}")
    return 0 if summary["calls"]["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
