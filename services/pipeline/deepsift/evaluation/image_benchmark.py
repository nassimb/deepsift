"""M12 — Phase 3 image-downlink baseline benchmark (no fusion, no VLM, no Jev).

Tiers (acquisition level): NONE < METADATA < THUMBNAIL < COMPRESSED < FULL. Byte costs from DownlinkOptions.
Budget = fraction × Σ FULL bytes of all acquisitions with a known FULL cost (what the mission spent at primary quality).
Allocator: greedy over a list of (acquisition, target tier) passes; each request is degraded one tier at a time until
its INCREMENTAL cost fits the remaining budget (a tier with UNKNOWN cost is skipped).

Strategies (declared before any result):
  FIFO, RANDOM (20 seeds), SIZE-AWARE (smallest FULL first), LOCAL EMBEDDING NOVELTY (desc), TELEMETRY PRIORITY (desc
  telemetry_score, ties chronological) — each run two ways:
     "policy"  single pass requesting FULL in strategy order;
     "ordering" a common first pass of thumbnails for everyone (chronological), then FULL upgrades in strategy order —
                isolates ORDERING from ACTION POLICY (Phase 2 lesson).
  THUMBNAIL-EVERYTHING  thumbnails for all, then FULL upgrades chronologically (= FIFO "ordering").
  PERCEPTUAL-HASH REPRESENTATIVES  thumbnails for all; FULL for one representative per pHash group (sharpest CLEAN
                member, else sharpest), groups in chronological order; then the rest chronologically.
Metrics are reported separately — never merged into one "science value".
"""

from __future__ import annotations

import random
from collections import defaultdict

import numpy as np

TIERS = ["NONE", "METADATA", "THUMBNAIL", "COMPRESSED", "FULL"]
RANK = {t: i for i, t in enumerate(TIERS)}
BUDGETS = [0.001, 0.0025, 0.005, 0.01, 0.02, 0.05, 0.10]
RANDOM_SEEDS = 20


def cost_table(obs: list[dict]) -> list[dict]:
    return [{"NONE": 0.0, "METADATA": float(o["downlink"]["metadata_bytes"]), "THUMBNAIL": o["downlink"]["thumbnail_bytes"],
             "COMPRESSED": o["downlink"]["compressed_bytes"], "FULL": o["downlink"]["full_bytes"]} for o in obs]


def allocate(costs: list[dict], passes: list[list[tuple[int, str]]], budget: float) -> list[str]:
    tier = ["NONE"] * len(costs)
    left = budget
    for requests in passes:
        for i, target in requests:
            cur = RANK[tier[i]]
            for r in range(RANK[target], cur, -1):
                t = TIERS[r]
                c = costs[i][t]
                if c is None:
                    continue
                inc = c - (costs[i][tier[i]] or 0.0)
                if inc <= left:
                    left -= inc
                    tier[i] = t
                    break
    return tier


def strategy_passes(obs: list[dict], seed: int = 0) -> dict[str, list[list[tuple[int, str]]]]:
    n = len(obs)
    chrono = sorted(range(n), key=lambda i: (obs[i]["utc"], obs[i]["id"]))
    rng = random.Random(seed)
    rand = chrono[:]
    rng.shuffle(rand)
    size = sorted(chrono, key=lambda i: (obs[i]["downlink"]["full_bytes"] is None, obs[i]["downlink"]["full_bytes"] or 0))
    nov = sorted(chrono, key=lambda i: -(obs[i]["image_features"].get("embedding_novelty") or 0.0))
    tel = sorted(chrono, key=lambda i: -(obs[i]["telemetry_context"].get("telemetry_score") or 0.0))
    thumbs = [(i, "THUMBNAIL") for i in chrono]
    full = lambda order: [(i, "FULL") for i in order]  # noqa: E731
    groups = defaultdict(list)
    for i in chrono:
        groups[obs[i]["near_duplicate_group"]].append(i)

    def rep(members):
        clean = [i for i in members if obs[i]["quality_state"] == "CLEAN"] or members
        return max(clean, key=lambda i: obs[i]["image_features"]["sharpness"])
    reps = [rep(m) for m in sorted(groups.values(), key=lambda m: min(chrono.index(i) for i in m))]
    rest = [i for i in chrono if i not in set(reps)]
    return {
        "FIFO|policy": [full(chrono)], "RANDOM|policy": [full(rand)], "SIZE-AWARE|policy": [full(size)],
        "EMBEDDING-NOVELTY|policy": [full(nov)], "TELEMETRY-PRIORITY|policy": [full(tel)],
        "FIFO|ordering": [thumbs, full(chrono)], "RANDOM|ordering": [thumbs, full(rand)], "SIZE-AWARE|ordering": [thumbs, full(size)],
        "EMBEDDING-NOVELTY|ordering": [thumbs, full(nov)], "TELEMETRY-PRIORITY|ordering": [thumbs, full(tel)],
        "THUMBNAIL-EVERYTHING": [thumbs, full(chrono)], "PHASH-REPRESENTATIVES": [thumbs, full(reps), full(rest)],
    }


def metrics(obs: list[dict], costs: list[dict], tiers: list[str], emb: np.ndarray | None) -> dict:
    n = len(obs)
    cnt = {t: sum(1 for x in tiers if x == t) for t in TIERS}
    sent = sum(costs[i][tiers[i]] or 0.0 for i in range(n))
    image = [i for i in range(n) if RANK[tiers[i]] >= RANK["THUMBNAIL"]]
    usable = [i for i in range(n) if RANK[tiers[i]] >= RANK["COMPRESSED"]]
    full = [i for i in range(n) if tiers[i] == "FULL"]
    scenes = {o["scene_cluster"] for o in obs}
    groups = {o["near_duplicate_group"] for o in obs}
    by_scene = defaultdict(list)
    for i in full:
        by_scene[obs[i]["scene_cluster"]].append(costs[i]["FULL"] or 0.0)
    redundant = sum(sum(sorted(v, reverse=True)[1:]) for v in by_scene.values())
    full_bytes = sum(costs[i]["FULL"] or 0.0 for i in full)
    cov = None
    if emb is not None:
        cov = float(np.mean(np.max(emb @ emb[usable].T, axis=1))) if usable else 0.0
    mb = sent / 1e6
    return {
        "bytes_transmitted": sent, "counts": cnt,
        "unique_acquisitions_with_image": len(image), "unique_acquisitions_usable": len(usable),
        "scene_clusters_total": len(scenes),
        "scene_clusters_with_image": len({obs[i]["scene_cluster"] for i in image}),
        "scene_clusters_usable": len({obs[i]["scene_cluster"] for i in usable}),
        "phash_groups_total": len(groups), "phash_groups_usable": len({obs[i]["near_duplicate_group"] for i in usable}),
        "redundant_full_bytes": redundant, "redundant_share_of_full_bytes": (redundant / full_bytes) if full_bytes else None,
        "diversity_proxy_embedding_coverage": cov,
        "usable_scene_clusters_per_mb": (len({obs[i]["scene_cluster"] for i in usable}) / mb) if mb else None,
        "usable_acquisitions_per_mb": (len(usable) / mb) if mb else None,
    }


def run(obs: list[dict], emb: np.ndarray | None) -> dict:
    costs = cost_table(obs)
    total_full = sum(c["FULL"] for c in costs if c["FULL"] is not None)
    out = {"total_full_bytes": total_full, "unknown_full_cost": sum(1 for c in costs if c["FULL"] is None), "results": {}}
    for f in BUDGETS:
        budget = f * total_full
        per = defaultdict(list)
        for seed in range(RANDOM_SEEDS):
            for name, passes in strategy_passes(obs, seed).items():
                if seed > 0 and not name.startswith("RANDOM"):
                    continue
                per[name].append(metrics(obs, costs, allocate(costs, passes, budget), emb))
        for name, runs in per.items():
            if len(runs) == 1:
                out["results"][f"{name}@{f}"] = runs[0]
            else:
                agg = {}
                for k, v in runs[0].items():
                    if isinstance(v, (int, float)) and v is not None:
                        xs = [r[k] for r in runs if r[k] is not None]
                        agg[k] = float(np.mean(xs)) if xs else None
                    elif k == "counts":
                        agg[k] = {t: float(np.mean([r[k][t] for r in runs])) for t in TIERS}
                    else:
                        agg[k] = v
                agg["seeds"] = len(runs)
                out["results"][f"{name}@{f}"] = agg
        out.setdefault("budget_bytes", {})[str(f)] = budget
    return out


# ---------------------------------------------------------------------------------------------------------------
# Phase 3.1 — SCHEDULER_V2_PROGRESSIVE (added; SCHEDULER_V1_GREEDY above is kept unchanged for the frozen baseline).
# Fixes an ALLOCATION artifact found in development: V1's greedy FULL-first purchases made coverage non-monotonic in
# budget (e.g. FIFO: 16 usable acquisitions at 0.25 % but 11 at 0.5 %). Ranking scores are not changed.
#
# V2 fills tier by tier — METADATA → THUMBNAIL → COMPRESSED → FULL — each pass walking the strategy's order and only
# upgrading acquisitions that completed the previous pass. Allocation STOPS entirely at the first increment that does
# not fit, so every pass is a prefix of the order and each prefix only grows with budget: acquisitions represented
# (≥ THUMBNAIL) and scene clusters represented are monotone non-decreasing in budget (tests/test_phase3_scheduler.py).
# A tier with UNKNOWN cost is skipped for that acquisition, which stays eligible for the next pass.
SCHEDULER_V1_GREEDY = "SCHEDULER_V1_GREEDY"
SCHEDULER_V2_PROGRESSIVE = "SCHEDULER_V2_PROGRESSIVE"
PROGRESSIVE_TIERS = ["METADATA", "THUMBNAIL", "COMPRESSED", "FULL"]


def allocate_progressive(costs: list[dict], order: list[int], budget: float, tiers: list[str] = PROGRESSIVE_TIERS) -> list[str]:
    tier = ["NONE"] * len(costs)
    left = budget
    eligible = list(order)
    for t in tiers:
        done = []
        for i in eligible:
            c = costs[i][t]
            if c is None:
                done.append(i)
                continue
            inc = max(0.0, c - (costs[i][tier[i]] or 0.0))
            if inc > left:
                return tier                                   # stop: later passes never jump ahead of this prefix
            left -= inc
            if RANK[t] > RANK[tier[i]]:
                tier[i] = t
            done.append(i)
        eligible = done
    return tier


def strategy_orders(obs: list[dict], seed: int = 0) -> dict[str, list[int]]:
    """Orders only (ranking unchanged from V1): FIFO, RANDOM, SIZE-AWARE, EMBEDDING-NOVELTY, TELEMETRY-PRIORITY and
    PHASH-REPRESENTATIVES (one representative per pHash group first, chronologically, then the rest)."""
    n = len(obs)
    chrono = sorted(range(n), key=lambda i: (obs[i]["utc"], obs[i]["id"]))
    rng = random.Random(seed)
    rand = chrono[:]
    rng.shuffle(rand)
    groups = defaultdict(list)
    for i in chrono:
        groups[obs[i]["near_duplicate_group"]].append(i)

    def rep(members):
        clean = [i for i in members if obs[i]["quality_state"] == "CLEAN"] or members
        return max(clean, key=lambda i: obs[i]["image_features"]["sharpness"])
    reps = [rep(m) for m in sorted(groups.values(), key=lambda m: min(chrono.index(i) for i in m))]
    rs = set(reps)
    return {
        "FIFO": chrono, "RANDOM": rand,
        "SIZE-AWARE": sorted(chrono, key=lambda i: (obs[i]["downlink"]["full_bytes"] is None, obs[i]["downlink"]["full_bytes"] or 0)),
        "EMBEDDING-NOVELTY": sorted(chrono, key=lambda i: -(obs[i]["image_features"].get("embedding_novelty") or 0.0)),
        "TELEMETRY-PRIORITY": sorted(chrono, key=lambda i: -(obs[i]["telemetry_context"].get("telemetry_score") or 0.0)),
        "PHASH-REPRESENTATIVES": reps + [i for i in chrono if i not in rs],
    }


def run_v2(obs: list[dict], emb: np.ndarray | None, budgets: list[float] = BUDGETS) -> dict:
    costs = cost_table(obs)
    total_full = sum(c["FULL"] for c in costs if c["FULL"] is not None)
    out = {"scheduler": SCHEDULER_V2_PROGRESSIVE, "total_full_bytes": total_full, "results": {}}
    for f in budgets:
        per = defaultdict(list)
        for seed in range(RANDOM_SEEDS):
            for name, order in strategy_orders(obs, seed).items():
                if seed > 0 and name != "RANDOM":
                    continue
                per[name].append(metrics(obs, costs, allocate_progressive(costs, order, f * total_full), emb))
        for name, runs in per.items():
            if len(runs) == 1:
                out["results"][f"{name}@{f}"] = runs[0]
                continue
            agg = {}
            for k, v in runs[0].items():
                if k == "counts":
                    agg[k] = {t: float(np.mean([r[k][t] for r in runs])) for t in TIERS}
                elif isinstance(v, (int, float)):
                    xs = [r[k] for r in runs if r[k] is not None]
                    agg[k] = float(np.mean(xs)) if xs else None
                    agg[k + "_min_over_seeds"] = float(np.min(xs)) if xs else None
            agg["seeds"] = len(runs)
            out["results"][f"{name}@{f}"] = agg
    return out
