#!/usr/bin/env python3
"""Phase 3.3 OPTIONAL small JEV transfer check (validation split). AUXILIARY DIAGNOSTIC — never validation truth, never tuning.

    uv run python scripts/jev_pairwise_transfer.py --run artifacts/phase3_3/<validation run>          # preflight only
    DEEPSIFT_EXPERIMENTAL_JEV=1 uv run python scripts/jev_pairwise_transfer.py --run ... --live

Only question: does the JEV PAIRWISE PREFERENCE behaviour look broadly similar on validation? Uses the frozen Phase 3.2
schema (deepsift.decision.jev_pairwise, JEV_PAIRWISE_V1) unchanged. At most 20 validation disagreement pairs, sampled with
the Phase 3.1 disagreement criteria (SIZE_VS_NOVELTY 7, TELEMETRY_VS_IMAGE 7, SEQUENCE_METHODS 6), each asked in AB and
BA order. Hard cap $0.02; projected cost is checked before any call. Jev receives structured metadata/features only.
It does not see the images.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "pipeline"))

from deepsift.core.env import load_dotenv  # noqa: E402
from deepsift.decision import jev as J  # noqa: E402
from deepsift.decision import jev_pairwise as P  # noqa: E402
from deepsift.evaluation import image_benchmark as ib  # noqa: E402
from deepsift.imaging import quality_v2 as q2  # noqa: E402
from deepsift.imaging import synthetic as v1gen  # noqa: E402
from deepsift.imaging.acquisitions import group_acquisitions  # noqa: E402
from deepsift.imaging.features import hamming, load_primary  # noqa: E402

MODEL = "typesafe/jev-1.13"
CAP = 0.02
QUOTA = {"SIZE_VS_NOVELTY": 7, "TELEMETRY_VS_IMAGE": 7, "SEQUENCE_METHODS": 6}


def fps(D, k):
    sel = [0]
    dmin = D[0].copy()
    while len(sel) < k:
        j = int(np.argmax(dmin))
        if dmin[j] <= 0:
            rest = [x for x in range(len(D)) if x not in sel]
            if not rest:
                break
            j = rest[0]
        sel.append(j)
        dmin = np.minimum(dmin, D[j])
    return sorted(set(sel))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()
    load_dotenv()
    run = Path(args.run)
    obs = [json.loads(x) for x in (run / "observations.jsonl").read_text().splitlines()]
    assert obs[0]["sol"] >= 779, "validation run expected"
    E = np.load(run / "embeddings.npy")
    n = len(obs)
    H = [int(o["image_features"]["phash"], 16) for o in obs]
    orders = ib.strategy_orders(obs, 0)
    rk = lambda order: {i: r for r, i in enumerate(order)}  # noqa: E731
    r_size, r_nov = rk(orders["SIZE-AWARE"]), rk(orders["EMBEDDING-NOVELTY"])
    prng = random.Random(v1gen.seed_for("REVIEW_PAIRS_VALIDATION_TRANSFER"))
    q = n // 4
    pairs, seen = [], set()

    def add(a, b, cat):
        key = tuple(sorted((a, b)))
        if a == b or key in seen:
            return
        seen.add(key)
        if prng.random() < 0.5:
            a, b = b, a
        pairs.append({"pair_id": f"V33-{len(pairs):03d}", "a": a, "b": b, "category": cat})
    A_ = [i for i in range(n) if r_size[i] < q and r_nov[i] > 3 * q]
    B_ = [i for i in range(n) if r_nov[i] < q and r_size[i] > 3 * q]
    for _ in range(200):
        if sum(p["category"] == "SIZE_VS_NOVELTY" for p in pairs) >= QUOTA["SIZE_VS_NOVELTY"] or not A_ or not B_:
            break
        add(prng.choice(A_), prng.choice(B_), "SIZE_VS_NOVELTY")
    A_ = [i for i in range(n) if (obs[i]["telemetry_context"]["telemetry_score"] or 0) > 0 and r_nov[i] > n // 2]
    B_ = [i for i in range(n) if (obs[i]["telemetry_context"]["telemetry_score"] or 0) == 0 and r_nov[i] < q]
    for _ in range(200):
        if sum(p["category"] == "TELEMETRY_VS_IMAGE" for p in pairs) >= QUOTA["TELEMETRY_VS_IMAGE"] or not A_ or not B_:
            break
        add(prng.choice(A_), prng.choice(B_), "TELEMETRY_VS_IMAGE")
    seqs = defaultdict(list)
    for i in sorted(range(n), key=lambda i: obs[i]["sclk"]):
        seqs[(obs[i]["sol"], obs[i]["sequence_id"])].append(i)
    dis = []
    for key, fr in seqs.items():
        if key[1].startswith("trav") and len(fr) >= 10:
            xy = np.array([[obs[i]["location_context"].get("landing_x", 0.0), obs[i]["location_context"].get("landing_y", 0.0)] for i in fr])
            Dp = np.linalg.norm(xy[:, None] - xy[None], axis=2)
            Dh = np.array([[hamming(H[a], H[b]) for b in fr] for a in fr], dtype=float)
            k = max(1, math.ceil(0.25 * len(fr)))
            sp, sh = set(fps(Dp, k)), set(fps(Dh, k))
            dis += list(zip([fr[j] for j in sp - sh], [fr[j] for j in sh - sp]))
    prng.shuffle(dis)
    for a, b in dis[:QUOTA["SEQUENCE_METHODS"]]:
        add(a, b, "SEQUENCE_METHODS")
    pairs = pairs[:20]

    # --- frozen JEV_PAIRWISE_V1 state (same construction as scripts/jev_pairwise_review.py)
    acqs = group_acquisitions(json.loads((ROOT / "data" / "manifests" / "navcam_validation.json").read_text())["products"])
    full = defaultdict(float)
    for r in json.loads((run / "byte_accounting_per_eye.json").read_text()):
        full[r["acq_id"]] += r["full_bytes_NASA_LABEL_ESTIMATE"] or 0
    pose_n = Counter(tuple(o["source_metadata"]["pose"]) for o in obs)
    prev = {}
    for fr in seqs.values():
        prev[fr[0]] = None
        for a, b in zip(fr, fr[1:]):
            prev[b] = float(1.0 - E[a] @ E[b])
    TH = json.loads((ROOT / "config" / "phase3_3_validation_config.json").read_text())["quality_v2"]["thresholds"]
    need = sorted({p[s] for p in pairs for s in ("a", "b")})
    sides = {}
    for i in need:
        st, why = q2.classify(q2.features(load_primary(acqs[i]), acqs[i]["primary"].get("error_pixels")), obs[i]["primary_tier"], TH)
        sides[i] = P.side_summary(obs[i], full[obs[i]["id"]] / 1e3, prev.get(i), "passed" if st == "CLEAN" else "flagged: " + ", ".join(why),
                                  pose_n[tuple(obs[i]["source_metadata"]["pose"])])
    reqs = []
    for p in pairs:
        a, b = p["a"], p["b"]
        la, lb = obs[a]["location_context"], obs[b]["location_context"]
        d = float(np.hypot(la["landing_x"] - lb["landing_x"], la["landing_y"] - lb["landing_y"])) if "landing_x" in la and "landing_x" in lb else None
        rel = P.relation(obs[a], obs[b], d, float(1.0 - E[a] @ E[b]), hamming(H[a], H[b]))
        for order, (x, y) in (("AB", (a, b)), ("BA", (b, a))):
            s = P.pair_state(sides[x], sides[y], rel)
            P.assert_clean(s)
            reqs.append({"pair_id": p["pair_id"], "order": order, "state": s})
    qchars = len(json.dumps(P.questions_payload(), separators=(",", ":")))
    chars = sum(len(json.dumps(r["state"], separators=(",", ":"))) + qchars for r in reqs)
    proj = chars / 2.43 * 0.042 / 1e6 * 1.5
    pre = {"pairs": len(pairs), "by_category": dict(Counter(p["category"] for p in pairs)), "calls": len(reqs),
           "projected_cost_usd": round(proj, 5), "cap_usd": CAP, "schema": P.SCHEMA_VERSION}
    print(json.dumps(pre))
    if proj > CAP:
        print("STOP: projected cost exceeds the $0.02 cap — no live call")
        return 3
    if not args.live:
        return 0
    if os.environ.get("DEEPSIFT_EXPERIMENTAL_JEV") != "1" or not J.jev_available():
        print("Jev is opt-in and needs OPENROUTER_API_KEY; not run")
        return 2
    from typesafe_sdk import RetryPolicy, TypeSafeClient

    client = TypeSafeClient(api_key=os.environ[J.KEY_ENV].strip(), base_url=J.BASE_URL, timeout=15.0, retry=RetryPolicy(max_retries=0))
    questions = J.build_questions(P.QUESTIONS)
    budget = J.ApiBudget(max_calls=len(reqs), max_cost_usd=CAP)
    recs = []
    for r in reqs:
        budget.reserve()
        t0 = time.perf_counter()
        try:
            resp = client.system_one(state=r["state"], questions=questions, model=MODEL)
        except Exception as exc:  # noqa: BLE001
            recs.append({"pair_id": r["pair_id"], "order": r["order"], "error": f"{type(exc).__name__}"[:200]})
            continue
        ans = {k: v.model_dump() for k, v in J.convert_answers(resp).items()}
        ex = J.openrouter_extras(resp)
        cost = ex["cost_usd"] if ex["cost_usd"] is not None else (resp.usage.input_tokens or 0) * 0.042 / 1e6
        budget.add_cost(cost)
        recs.append({"pair_id": r["pair_id"], "order": r["order"], "label": P.LABEL, "model_requested": MODEL, "model_returned": getattr(resp, "model", None),
                     "provider": ex["provider"], "transport": J.TRANSPORT, "schema_version": P.SCHEMA_VERSION,
                     "input_hash": P.request_key(r["state"], r["order"], MODEL, P.EXPECTED_SNAPSHOT, J.sdk_version(), J.TRANSPORT),
                     "choice": ans["priority"]["choice"], "choice_confidence": ans["priority"]["confidence"], "reason": ans["reason"]["choice"],
                     "reason_confidence": ans["reason"]["confidence"], "latency_ms": (time.perf_counter() - t0) * 1000,
                     "input_tokens": resp.usage.input_tokens, "cost_usd": cost, "cache_status": "UNCACHED_TRANSFER_CHECK",
                     "timestamp": datetime.now(timezone.utc).isoformat()})
    main_ = {(x["pair_id"], x["order"]): x for x in recs if x.get("choice")}
    pm = {p["pair_id"]: p for p in pairs}

    def chosen(x):
        p = pm[x["pair_id"]]
        f, s = (p["a"], p["b"]) if x["order"] == "AB" else (p["b"], p["a"])
        return {"A": f, "B": s}.get(x["choice"], x["choice"])
    sw = [(chosen(main_[(pid, "AB")]), chosen(main_[(pid, "BA")])) for pid in pm if (pid, "AB") in main_ and (pid, "BA") in main_]
    pos = Counter(x["choice"] for x in main_.values())
    st = {(r["pair_id"], r["order"]): r["state"] for r in reqs}
    rule = {"higher_entropy": lambda a, b: a["image_quality"]["entropy_bits"] - b["image_quality"]["entropy_bits"],
            "stereo_over_single_eye": lambda a, b: a["stereo"].startswith("left") - b["stereo"].startswith("left"),
            "full_frame_over_downsampled": lambda a, b: ("1024" in a["product_resolution"]) - ("1024" in b["product_resolution"])}
    ra = {}
    for nm, f in rule.items():
        k = m = 0
        for key, x in main_.items():
            if x["choice"] not in ("A", "B"):
                continue
            v = f(st[key]["observation_A"], st[key]["observation_B"])
            if v:
                m += 1
                k += (x["choice"] == "A") == (v > 0)
        ra[nm] = {"n": m, "agreement": round(k / m, 3) if m else None}
    summ = {"label": P.LABEL + " — VALIDATION TRANSFER CHECK (auxiliary diagnostic, not validation truth)",
            "notice": "Jev receives structured metadata/features only. It does not see the images.", **pre,
            "pair_ids": [p["pair_id"] for p in pairs], "calls_ok": len(main_), "errors": sum(1 for x in recs if x.get("error")),
            "snapshots": dict(Counter(x["model_returned"] for x in recs if x.get("model_returned"))),
            "cost_usd": round(sum(x.get("cost_usd") or 0 for x in recs), 6),
            "choice_distribution": dict(pos), "reason_distribution": dict(Counter(x["reason"] for x in main_.values())),
            "choice_confidence_p50": float(np.median([x["choice_confidence"] for x in main_.values()])) if main_ else None,
            "ab_swap_consistency": round(sum(a == b for a, b in sw) / len(sw), 3) if sw else None,
            "position_A_share": round(pos["A"] / max(1, pos["A"] + pos["B"]), 3), "feature_rule_alignment": ra}
    (run / "jev_transfer_calls.jsonl").write_text("".join(json.dumps(x) + "\n" for x in recs))
    (run / "jev_transfer_summary.json").write_text(json.dumps(summ, indent=1))
    print(json.dumps(summ, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
