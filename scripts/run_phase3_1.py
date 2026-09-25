#!/usr/bin/env python3
"""Phase 3.1 — controlled evaluation of the visual primitives (DEVELOPMENT split only; no fusion, no VLM, no Jev).

    uv run python scripts/run_phase3_1.py

Reuses the frozen Phase 3 baseline (tag phase3-baseline: observations + embeddings) without modifying it, and writes a
new versioned run to artifacts/phase3_1/<run_id>/. Synthetic controls (copies only) → data/synthetic/phase3_1/
(git-ignored) + data/manifests/synthetic_controls_v1.json. Review pairs → data/review/pairs_v1.json.

Declared before running (in addition to the generators' own declarations):
  change-detection thresholds for pHash / embeddings = median of the LEFT/RIGHT stereo-pair distances (a real
  same-instant, different-viewpoint difference); temporal-proximity link ≤ 120 s; sequence retention fractions 1/2,
  1/4, 1/8; fine monotonicity grid = 40 log-spaced budgets 0.05–20 %; visual-control retention budgets 0.5, 1, 2 %.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import subprocess
import sys
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "pipeline"))

from deepsift.evaluation import image_benchmark as ib  # noqa: E402
from deepsift.imaging import quality_v2 as q2  # noqa: E402
from deepsift.imaging import similarity as sim  # noqa: E402
from deepsift.imaging import synthetic as syn  # noqa: E402
from deepsift.imaging.acquisitions import group_acquisitions  # noqa: E402
from deepsift.imaging.embeddings import Embedder  # noqa: E402
from deepsift.imaging.features import hamming, load_primary, phash, to_work  # noqa: E402
from deepsift.imaging.pds3 import parse_label, read_image  # noqa: E402

BASE = ROOT / "artifacts" / "phase3" / "20260925T132323-phase3-dev-baseline-ff13"
SYN_DIR = ROOT / "data" / "synthetic" / "phase3_1" / "controls_v1"
PER_LEVEL = 30
N_DUP = 120
TIME_LINK_S = 120
FRACTIONS = [0.5, 0.25, 0.125]
CTRL_BUDGETS = [0.005, 0.01, 0.02]
NOVELTY_LOOKBACK_SOLS = 3


def ts(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "")).replace(tzinfo=timezone.utc).timestamp()


def cosd(a, b):
    return float(1.0 - np.dot(a, b))


def pctl(xs, q):
    xs = [x for x in xs if x is not None]
    return float(np.percentile(xs, q)) if xs else None


def half(acq_id: str) -> str:
    return "TUNE" if int(hashlib.sha256(acq_id.encode()).hexdigest()[:2], 16) % 2 == 0 else "EVAL"


def main() -> int:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-phase3.1-dev-controls-" + uuid.uuid4().hex[:4]
    out = ROOT / "artifacts" / "phase3_1" / run_id
    out.mkdir(parents=True)
    obs = [json.loads(x) for x in (BASE / "observations.jsonl").read_text().splitlines()]
    E = np.load(BASE / "embeddings.npy")
    man = json.loads((ROOT / "data" / "manifests" / "navcam_development.json").read_text())
    acqs = group_acquisitions(man["products"])
    assert [a["acq_id"] for a in acqs] == [o["id"] for o in obs], "baseline observation order mismatch"
    n = len(obs)
    vm = json.loads((ROOT / "config" / "phase3_vision_model.json").read_text())
    emb = Embedder(vm["chosen"])
    H = [int(o["image_features"]["phash"], 16) for o in obs]
    t = [ts(o["utc"]) for o in obs]
    cache: dict[int, np.ndarray] = {}

    def native(i):
        if i not in cache:
            cache[i] = load_primary(acqs[i])
        return cache[i]
    R: dict = {"run_id": run_id, "baseline_run": BASE.name, "split": "development"}

    # ------------------------------------------------------------------ 1. scheduler V1 vs V2
    v1 = ib.run(obs, E)
    base_bench = json.loads((BASE / "benchmark.json").read_text())
    v1_reproduces = all(abs((v1["results"][k].get("scene_clusters_usable") or 0) - (base_bench["results"][k].get("scene_clusters_usable") or 0)) < 1e-9
                        for k in base_bench["results"])
    v2 = ib.run_v2(obs, E)
    costs = ib.cost_table(obs)
    total = v2["total_full_bytes"]
    grid = list(np.geomspace(0.0005, 0.20, 40))

    def cover(tiers):
        img = [i for i in range(n) if ib.RANK[tiers[i]] >= ib.RANK["THUMBNAIL"]]
        use = [i for i in range(n) if ib.RANK[tiers[i]] >= ib.RANK["COMPRESSED"]]
        return len(img), len({obs[i]["scene_cluster"] for i in img}), len(use), len({obs[i]["scene_cluster"] for i in use})

    mono = {}
    v1_passes = ib.strategy_passes(obs, 0)
    v2_orders = ib.strategy_orders(obs, 0)
    for name, passes in v1_passes.items():
        seq = [cover(ib.allocate(costs, passes, f * total)) for f in grid]
        mono[f"V1|{name}"] = {m: sum(1 for a, b in zip(seq, seq[1:]) if b[k] < a[k]) for k, m in enumerate(["acq_repr", "scene_repr", "acq_usable", "scene_usable"])}
    for name, order in v2_orders.items():
        seq = [cover(ib.allocate_progressive(costs, order, f * total)) for f in grid]
        mono[f"V2|{name}"] = {m: sum(1 for a, b in zip(seq, seq[1:]) if b[k] < a[k]) for k, m in enumerate(["acq_repr", "scene_repr", "acq_usable", "scene_usable"])}
    R["scheduler"] = {"v1_reproduces_frozen_baseline": v1_reproduces, "fine_grid_budgets": len(grid),
                      "monotonicity_violations": mono, "v2": v2}
    print("1 scheduler: V1 reproduces baseline", v1_reproduces, "| V2 violations", sum(sum(v.values()) for k, v in mono.items() if k.startswith("V2")))

    # ------------------------------------------------------------------ 2. synthetic controls
    entries = []
    fam_names = list(syn.FAMILIES)
    for fam in fam_names:
        rng = random.Random(syn.seed_for(syn.GENERATOR, fam))
        src = rng.sample(range(n), syn.LEVELS.__len__() * PER_LEVEL)
        for li, level in enumerate(syn.LEVELS):
            for k in range(PER_LEVEL):
                i = src[li * PER_LEVEL + k]
                sid = f"SYN-P31-{fam}-{level}-{k:03d}"
                seed = syn.seed_for(syn.GENERATOR, sid)
                y, params, box = syn.perturb(native(i), fam, level, seed)
                path = SYN_DIR / f"{sid}.png"
                syn.save_png16(path, y)
                entries.append({"synthetic_id": sid, "label": "SYNTHETIC CONTROL", "generator": syn.GENERATOR,
                                "family": fam, "family_kind": syn.FAMILIES[fam][0], "severity": level, "parameters": params,
                                "random_seed": seed, "bounding_region_yxyx": box, "source_acquisition_id": obs[i]["id"],
                                "source_product_id": acqs[i]["primary"]["product_id"], "source_sha256_img": acqs[i]["primary"]["sha256_img"],
                                "source_tier": acqs[i]["primary_tier"], "source_index": i, "tune_eval_half": half(obs[i]["id"]),
                                "ground_truth": f"SYNTHETIC CONTROL — {fam} ({syn.FAMILIES[fam][0]}), severity {level}",
                                "path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    rng = random.Random(syn.seed_for(syn.GENERATOR, "NEAR_DUPLICATE"))
    for k, i in enumerate(rng.sample(range(n), N_DUP)):
        sid = f"SYN-P31-NEAR_DUPLICATE-{k:03d}"
        seed = syn.seed_for(syn.GENERATOR, sid)
        y, params = syn.near_duplicate(native(i), seed)
        path = SYN_DIR / f"{sid}.png"
        syn.save_png16(path, y)
        entries.append({"synthetic_id": sid, "label": "SYNTHETIC CONTROL", "generator": syn.GENERATOR, "family": "NEAR_DUPLICATE",
                        "family_kind": "REDUNDANCY", "severity": "N/A", "parameters": params, "random_seed": seed, "bounding_region_yxyx": None,
                        "source_acquisition_id": obs[i]["id"], "source_product_id": acqs[i]["primary"]["product_id"],
                        "source_sha256_img": acqs[i]["primary"]["sha256_img"], "source_tier": acqs[i]["primary_tier"], "source_index": i,
                        "tune_eval_half": half(obs[i]["id"]), "ground_truth": "SYNTHETIC CONTROL — true near-duplicate of its source",
                        "path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    (ROOT / "data" / "manifests" / "synthetic_controls_v1.json").write_text(json.dumps({
        "generator": syn.GENERATOR, "created_at": datetime.now(timezone.utc).isoformat(), "split": "development",
        "note": "SYNTHETIC CONTROLS — perturbed copies of NASA PDS observations; originals never modified; not Mars events",
        "families": {k: {"kind": v[0], "levels": v[1]} for k, v in syn.FAMILIES.items()}, "near_duplicate": syn.DUPLICATE[1],
        "count": len(entries), "entries": entries}, indent=1))
    ctrl = {}
    for e in entries:
        ctrl[e["synthetic_id"]] = syn.load_png16(ROOT / e["path"])
    R["synthetic"] = {"count": len(entries), "by_family": dict(Counter(e["family"] for e in entries)),
                      "by_severity": dict(Counter(e["severity"] for e in entries)), "by_half": dict(Counter(e["tune_eval_half"] for e in entries)),
                      "bytes_on_disk": sum((ROOT / e["path"]).stat().st_size for e in entries)}
    print("2 synthetic", R["synthetic"]["count"], R["synthetic"]["bytes_on_disk"] / 1e6, "MB")

    # ------------------------------------------------------------------ 3. quality stage
    real = [(obs[i]["primary_tier"], q2.features(native(i), acqs[i]["primary"].get("error_pixels"))) for i in range(n)]
    eng = [e for e in entries if e["family_kind"] == "ENGINEERING_QUALITY"]
    vis = [e for e in entries if e["family_kind"] == "VISUAL_NOVELTY"]
    cf = {e["synthetic_id"]: q2.features(ctrl[e["synthetic_id"]]) for e in entries if e["family_kind"] != "REDUNDANCY"}
    choice = {}
    for p in q2.SHARP_PERCENTILE_CHOICES:
        th = q2.fit(real, p)
        rec = np.mean([q2.classify(cf[e["synthetic_id"]], e["source_tier"], th)[0] != "CLEAN" for e in eng if e["tune_eval_half"] == "TUNE"])
        fa = np.mean([q2.classify(f, tier, th)[0] != "CLEAN" for tier, f in real])
        choice[p] = {"tune_recall": float(rec), "real_false_alarm": float(fa), "score": float(rec - 2 * fa)}
    best_p = max(choice, key=lambda p: choice[p]["score"])
    TH = q2.fit(real, best_p)

    def rec_table(items, flag):
        tab = defaultdict(lambda: defaultdict(list))
        for e in items:
            tab[e["family"]][e["severity"]].append(flag(e))
        return {f: {lv: {"recall": float(np.mean(v)), "n": len(v)} for lv, v in sorted(d.items(), key=lambda kv: syn.LEVELS.index(kv[0]))}
                for f, d in tab.items()}
    v1flag = lambda e: cf[e["synthetic_id"]]["quality_state"] != "CLEAN"  # noqa: E731
    v2flag = lambda e: q2.classify(cf[e["synthetic_id"]], e["source_tier"], TH)[0] != "CLEAN"  # noqa: E731
    evl = [e for e in eng if e["tune_eval_half"] == "EVAL"]
    R["quality"] = {
        "v1_recall_eval_half": rec_table(evl, v1flag), "v2_recall_eval_half": rec_table(evl, v2flag),
        "v1_recall_all": rec_table(eng, v1flag), "v2_recall_all": rec_table(eng, v2flag),
        "v1_false_alarm_real": float(np.mean([f["quality_state"] != "CLEAN" for _, f in real])),
        "v2_false_alarm_real_in_sample": float(np.mean([q2.classify(f, tier, TH)[0] != "CLEAN" for tier, f in real])),
        "v2_real_alarm_reasons": dict(Counter(r for tier, f in real for r in q2.classify(f, tier, TH)[1])),
        "visual_controls_flagged_v1": float(np.mean([v1flag(e) for e in vis])), "visual_controls_flagged_v2": float(np.mean([v2flag(e) for e in vis])),
        "v2_thresholds": TH, "v2_sharpness_percentile_choice": choice, "v2_chosen_percentile": best_p}
    print("3 quality: v1 FA", R["quality"]["v1_false_alarm_real"], "v2 FA", R["quality"]["v2_false_alarm_real_in_sample"])

    # ------------------------------------------------------------------ 4/5/11. pHash, embeddings, stereo, resolution
    stereo_pairs = []
    for i, a in enumerate(acqs):
        if a["stereo"]:
            L = [p for p in a["primaries"] if p["eye"] == "L" and p["tier"] == a["primary_tier"]]
            Rr = [p for p in a["primaries"] if p["eye"] == "R" and p["tier"] == a["primary_tier"]]
            if L and Rr:
                imgs = [read_image(ROOT / p["path_img"], parse_label((ROOT / p["path_lbl"]).read_text(encoding="latin-1"))) for p in (L[0], Rr[0])]
                ev = [emb.embed(to_work(x))[0] for x in imgs]
                stereo_pairs.append({"i": i, "cos_dist": cosd(ev[0], ev[1]), "hamming": hamming(phash(imgs[0]), phash(imgs[1]))})
    tau_cos = pctl([p["cos_dist"] for p in stereo_pairs], 50)
    tau_ham = pctl([p["hamming"] for p in stereo_pairs], 50)
    seqs = defaultdict(list)
    for i in sorted(range(n), key=lambda i: t[i]):
        seqs[(obs[i]["sol"], obs[i]["sequence_id"])].append(i)
    consec = [(a, b) for v in seqs.values() for a, b in zip(v, v[1:])]
    rr = random.Random(11)
    randp = []
    while len(randp) < 2000:
        a, b = rr.randrange(n), rr.randrange(n)
        if obs[a]["sol"] != obs[b]["sol"]:
            randp.append((a, b))

    def dist_stats(pairs):
        c = [cosd(E[a], E[b]) for a, b in pairs]
        h = [hamming(H[a], H[b]) for a, b in pairs]
        return {"n": len(pairs), "cos_dist_p10_p50_p90": [pctl(c, 10), pctl(c, 50), pctl(c, 90)], "hamming_p10_p50_p90": [pctl(h, 10), pctl(h, 50), pctl(h, 90)]}
    R["stereo"] = {"pairs": len(stereo_pairs), "cos_dist_p10_p50_p90": [pctl([p["cos_dist"] for p in stereo_pairs], q) for q in (10, 50, 90)],
                   "hamming_p10_p50_p90": [pctl([p["hamming"] for p in stereo_pairs], q) for q in (10, 50, 90)],
                   "left_right_within_phash_threshold": float(np.mean([p["hamming"] <= sim.PHASH_MAX_BITS for p in stereo_pairs])),
                   "stereo_acquisitions": sum(o["stereo"] for o in obs), "relationship": "STEREO_PAIR (both eyes kept together in the FULL tier; never de-duplicated)",
                   "consecutive_sequence_frames": dist_stats(consec), "random_pairs_different_sols": dist_stats(randp),
                   "change_thresholds": {"cos_dist": tau_cos, "hamming": tau_ham, "definition": "median left/right stereo distance"}}

    # synthetic-change sensitivity (source vs perturbed, working scale)
    sens = defaultdict(lambda: defaultdict(lambda: {"emb": [], "ham": [], "cos": [], "hd": []}))
    for e in entries:
        if e["family_kind"] == "REDUNDANCY":
            continue
        i = e["source_index"]
        v = emb.embed(to_work(ctrl[e["synthetic_id"]]))[0]
        d = cosd(E[i], v)
        hd = hamming(H[i], phash(ctrl[e["synthetic_id"]]))
        cell = sens[e["family"]][e["severity"]]
        cell["emb"].append(d > tau_cos)
        cell["ham"].append(hd > tau_ham)
        cell["cos"].append(d)
        cell["hd"].append(hd)
        e["_cos"], e["_ham"], e["_vec"] = d, hd, v
    R["change_sensitivity"] = {f: {lv: {"embedding_recall": float(np.mean(c["emb"])), "phash_recall": float(np.mean(c["ham"])),
                                        "cos_dist_median": pctl(c["cos"], 50), "hamming_median": pctl(c["hd"], 50), "n": len(c["emb"])}
                                   for lv, c in sorted(d.items(), key=lambda kv: syn.LEVELS.index(kv[0]))} for f, d in sens.items()}

    # resolution invariance: full frames vs synthetic D-like (4×4 box) vs T-like (16×16 box) vs the rover's real thumbnail
    def box(x, k):
        h2, w2 = (x.shape[0] // k) * k, (x.shape[1] // k) * k
        return x[:h2, :w2].reshape(h2 // k, k, w2 // k, k).mean(axis=(1, 3))
    fidx = [i for i in range(n) if obs[i]["primary_tier"] == "F"]
    res = {"cos": {"D_like": [], "T_like": [], "real_thumbnail": []}, "ham": {"D_like": [], "T_like": [], "real_thumbnail": []},
           "feat_rel_change": {"D_like": defaultdict(list), "T_like": defaultdict(list)}}
    E_T = E.copy()
    from deepsift.imaging.features import quality as q1
    for i in range(n):
        x = native(i)
        tl = box(x, max(1, x.shape[1] // 64))
        E_T[i] = emb.embed(to_work(tl))[0]
    for i in fidx:
        x = native(i)
        f0 = q1(x, None)
        for name, k in (("D_like", 4), ("T_like", 16)):
            y = box(x, k)
            v = emb.embed(to_work(y))[0]
            res["cos"][name].append(cosd(E[i], v))
            res["ham"][name].append(hamming(H[i], phash(y)))
            f1 = q1(y, None)
            for key in ("brightness", "contrast", "entropy_bits", "sharpness"):
                res["feat_rel_change"][name][key].append(abs(f1[key] - f0[key]) / (abs(f0[key]) + 1e-9))
        th = acqs[i]["thumbnail"]
        if th:
            y = read_image(ROOT / th["path_img"], parse_label((ROOT / th["path_lbl"]).read_text(encoding="latin-1")))
            y = (y - y.min()) / max(1e-6, float(y.max() - y.min())) * 4095.0          # rover thumbnail uses a different DN scale
            res["cos"]["real_thumbnail"].append(cosd(E[i], emb.embed(to_work(y))[0]))
            res["ham"]["real_thumbnail"].append(hamming(H[i], phash(y)))

    def novelty(Em):
        order = sorted(range(n), key=lambda i: t[i])
        nv = [1.0] * n
        for k, i in enumerate(order):
            prev = [j for j in order[:k] if obs[j]["sol"] >= obs[i]["sol"] - NOVELTY_LOOKBACK_SOLS]
            if prev:
                nv[i] = float(1.0 - np.max(Em[prev] @ Em[i]))
        return nv

    def spearman(a, b):
        ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
        return float(np.corrcoef(ra, rb)[0, 1])
    nov0 = [o["image_features"]["embedding_novelty"] for o in obs]
    novT = novelty(E_T)
    fullb = [o["downlink"]["full_bytes"] for o in obs]
    hnov = []
    order = sorted(range(n), key=lambda i: t[i])
    for k, i in enumerate(order):
        prev = [j for j in order[:k] if obs[j]["sol"] >= obs[i]["sol"] - NOVELTY_LOOKBACK_SOLS]
        hnov.append((i, min((hamming(H[i], H[j]) for j in prev), default=64) / 64))
    hn = [0.0] * n
    for i, v in hnov:
        hn[i] = v
    seqtype = Counter()
    R["resolution"] = {
        "full_frames": len(fidx),
        "cos_dist_median": {k: pctl(v, 50) for k, v in res["cos"].items()}, "cos_dist_p90": {k: pctl(v, 90) for k, v in res["cos"].items()},
        "hamming_median": {k: pctl(v, 50) for k, v in res["ham"].items()}, "hamming_p90": {k: pctl(v, 90) for k, v in res["ham"].items()},
        "feature_rel_change_median": {k: {kk: pctl(vv, 50) for kk, vv in d.items()} for k, d in res["feat_rel_change"].items()},
        "novelty_spearman_original_vs_all_at_64px": spearman(nov0, novT),
        "spearman_novelty_vs_full_bytes": {"original": spearman(nov0, fullb), "all_at_64px": spearman(novT, fullb), "phash_novelty": spearman(hn, fullb)},
        "novelty_median_by_sequence_type": {k: pctl([nov0[i] for i in range(n) if obs[i]["sequence_id"][:4] == k], 50)
                                            for k in sorted({o["sequence_id"][:4] for o in obs})},
        "novelty_median_by_tier": {k: pctl([nov0[i] for i in range(n) if obs[i]["primary_tier"] == k], 50) for k in sorted({o["primary_tier"] for o in obs})},
        "ranking_by_tier_note": "same-scene multi-tier real data exist only as primary + rover thumbnail; D/T-like tiers are box-averaged copies"}
    del seqtype
    print("5 resolution", R["resolution"]["cos_dist_median"], R["resolution"]["spearman_novelty_vs_full_bytes"])

    # pHash grouping variants with synthetic near-duplicates in the pool
    dups = [e for e in entries if e["family"] == "NEAR_DUPLICATE"]
    pool = [{"sol": obs[i]["sol"], "t": t[i], "stop": tuple(obs[i]["source_metadata"]["pose"]), "scene": obs[i]["scene_cluster"],
             "h": H[i], "real": True, "src": i} for i in range(n)]
    for e in dups:
        i = e["source_index"]
        pool.append({"sol": obs[i]["sol"], "t": t[i] + 1, "stop": tuple(obs[i]["source_metadata"]["pose"]), "scene": obs[i]["scene_cluster"],
                     "h": phash(ctrl[e["synthetic_id"]]), "real": False, "src": i})
    N = len(pool)
    by_sol = defaultdict(list)
    for k, p in enumerate(pool):
        by_sol[p["sol"]].append(k)
    methods = {
        "PHASH_ONLY": lambda a, b: hamming(a["h"], b["h"]) <= sim.PHASH_MAX_BITS,
        "PHASH_PLUS_TIME": lambda a, b: hamming(a["h"], b["h"]) <= sim.PHASH_MAX_BITS and abs(a["t"] - b["t"]) <= TIME_LINK_S,
        "PHASH_PLUS_POSE": lambda a, b: hamming(a["h"], b["h"]) <= sim.PHASH_MAX_BITS and a["stop"] == b["stop"],
        "METADATA_SCENE": lambda a, b: a["scene"] == b["scene"],
    }
    stops_all = {p["stop"] for p in pool if p["real"]}
    trav = {k for k, v in seqs.items() if k[1].startswith("trav")}
    grp_res = {}
    for name, link in methods.items():
        uf = sim._UF(N)
        for idx in by_sol.values():
            for x, a in enumerate(idx):
                for b in idx[x + 1:]:
                    if link(pool[a], pool[b]):
                        uf.union(a, b)
        comp = [uf.find(k) for k in range(N)]
        retrieved = np.mean([comp[n + k] == comp[e["source_index"]] for k, e in enumerate(dups)])
        members = defaultdict(list)
        for k in range(n):
            members[comp[k]].append(k)
        pairs = [(a, b) for m in members.values() for x, a in enumerate(m) for b in m[x + 1:]]
        false = [pool[a]["scene"] != pool[b]["scene"] for a, b in pairs]
        diff_stop = [pool[a]["stop"] != pool[b]["stop"] for a, b in pairs]
        reps = {min(m, key=lambda k: pool[k]["t"]) for m in members.values()}
        lost = 1 - len({pool[k]["stop"] for k in reps}) / len(stops_all)
        tr_frames = [i for k, v in seqs.items() if k in trav for i in v]
        tr_groups = len({comp[i] for i in tr_frames})
        grp_res[name] = {"synthetic_duplicate_retrieval": float(retrieved), "groups_real": len(members),
                         "within_group_pairs_real": len(pairs), "false_merge_rate_scene": float(np.mean(false)) if false else 0.0,
                         "false_merge_rate_different_stop": float(np.mean(diff_stop)) if diff_stop else 0.0,
                         "traverse_frames": len(tr_frames), "traverse_groups": tr_groups,
                         "traverse_compression_ratio": len(tr_frames) / max(1, tr_groups),
                         "unique_rover_stop_loss_if_one_rep_per_group": float(lost)}
    grp_res["METADATA_SCENE"]["note"] = "false-merge rate is 0 by construction (the reference IS the metadata scene); duplicates share metadata"
    R["phash_grouping"] = grp_res
    print("4 phash", {k: (round(v["synthetic_duplicate_retrieval"], 2), round(v["false_merge_rate_scene"], 2)) for k, v in grp_res.items()})

    # ------------------------------------------------------------------ 12. redundancy concepts
    pix = scene = seqrel = seqred = both = pix_not_scene = 0
    for idx in by_sol.values():
        real_idx = [k for k in idx if k < n]
        for x, a in enumerate(real_idx):
            for b in real_idx[x + 1:]:
                P = hamming(H[a], H[b]) <= sim.PHASH_MAX_BITS
                S = obs[a]["scene_cluster"] == obs[b]["scene_cluster"]
                Q = obs[a]["sequence_id"] == obs[b]["sequence_id"]
                pix += P
                scene += S
                seqrel += Q
                seqred += Q and S
                both += P and S
                pix_not_scene += P and not S
    R["redundancy_concepts"] = {"PIXEL_SIMILAR_pairs": pix, "SCENE_SIMILAR_pairs": scene, "SEQUENCE_RELATED_pairs": seqrel,
                                "SEQUENCE_REDUNDANT_pairs (same sequence AND same scene)": seqred,
                                "STEREO_RELATED_acquisitions": sum(o["stereo"] for o in obs),
                                "PIXEL_AND_SCENE_pairs": both, "PIXEL_SIMILAR_but_DIFFERENT_SCENE_pairs": pix_not_scene,
                                "definitions": {"PIXEL_SIMILAR": "same sol, pHash Hamming ≤ 10", "SCENE_SIMILAR": "same stop + pointing ≤ 15°",
                                                "SEQUENCE_RELATED": "same sol + sequence id (context, not redundancy)",
                                                "SEQUENCE_REDUNDANT": "same sequence AND same scene (a repeated capture)",
                                                "STEREO_RELATED": "left/right of one acquisition (parallax; never a duplicate)"}}

    # ------------------------------------------------------------------ 13. sequence representation experiment
    def fps(D, k, start=0):
        sel = [start]
        dmin = D[start].copy()
        while len(sel) < k:
            j = int(np.argmax(dmin))
            if dmin[j] <= 0 and len(sel) >= 1:
                rest = [x for x in range(len(D)) if x not in sel]
                if not rest:
                    break
                j = rest[0]
            sel.append(j)
            dmin = np.minimum(dmin, D[j])
        return sorted(set(sel))
    seq_rows = []
    for key, fr in seqs.items():
        if not key[1].startswith("trav") or len(fr) < 10:
            continue
        m = len(fr)
        xy = np.array([[obs[i]["location_context"].get("landing_x", 0.0), obs[i]["location_context"].get("landing_y", 0.0)] for i in fr])
        Dp = np.linalg.norm(xy[:, None] - xy[None], axis=2)
        Dh = np.array([[hamming(H[a], H[b]) for b in fr] for a in fr], dtype=float)
        scale = Dp.max() or 1.0
        Dx = 0.5 * Dp / scale + 0.5 * Dh / 64.0
        stops = {tuple(obs[i]["source_metadata"]["pose"]) for i in fr}
        scenes = {obs[i]["scene_cluster"] for i in fr}
        for frac in [1.0] + FRACTIONS:
            k = max(1, math.ceil(frac * m))
            sels = {"SEND_ALL": list(range(m))} if frac == 1.0 else {
                "UNIFORM_TEMPORAL_SAMPLE": sorted(set(int(round(x)) for x in np.linspace(0, m - 1, k))),
                "PHASH_REPRESENTATIVES": fps(Dh, k), "METADATA_POSITION_SAMPLE": fps(Dp, k), "HYBRID_POSITION_VISUAL_CHANGE": fps(Dx, k)}
            for meth, s in sels.items():
                si = [fr[j] for j in s]
                rest = [i for i in fr if i not in set(si)]
                byt = sum(costs[i]["FULL"] for i in si) + sum(costs[i]["THUMBNAIL"] or 0 for i in rest)
                gaps = [float(Dp[a, b]) for a, b in zip(s, s[1:])]
                seq_rows.append({"sequence": f"{key[0]}:{key[1]}", "frames": m, "fraction": frac, "method": meth, "selected": len(s), "bytes": byt,
                                 "bytes_send_all": sum(costs[i]["FULL"] for i in fr),
                                 "positions_represented": len({tuple(obs[i]["source_metadata"]["pose"]) for i in si}) / len(stops),
                                 "scene_clusters_represented": len({obs[i]["scene_cluster"] for i in si}) / len(scenes),
                                 "embedding_coverage": float(np.mean(np.max(E[fr] @ E[si].T, axis=1))),
                                 "phash_mean_min_hamming": float(np.mean(np.min(Dh[:, s], axis=1))),
                                 "max_spatial_gap_m": max(gaps) if gaps else 0.0, "path_extent_m": float(scale)})
    agg = defaultdict(lambda: defaultdict(list))
    for r in seq_rows:
        for k in ("bytes", "bytes_send_all", "positions_represented", "scene_clusters_represented", "embedding_coverage", "phash_mean_min_hamming", "max_spatial_gap_m", "selected"):
            agg[(r["fraction"], r["method"])][k].append(r[k])
    R["sequence_experiment"] = {"sequences": len({r["sequence"] for r in seq_rows}), "frames": sum({r["sequence"]: r["frames"] for r in seq_rows}.values()),
                                "summary": {f"{f}|{m}": {"bytes_total": float(np.sum(v["bytes"])), "bytes_fraction_of_send_all": float(np.sum(v["bytes"]) / np.sum(v["bytes_send_all"])),
                                                         **{k: float(np.mean(v[k])) for k in ("positions_represented", "scene_clusters_represented", "embedding_coverage", "phash_mean_min_hamming", "max_spatial_gap_m")},
                                                         "max_spatial_gap_m_worst": float(np.max(v["max_spatial_gap_m"]))}
                                            for (f, m), v in sorted(agg.items(), key=lambda kv: (-kv[0][0], kv[0][1]))},
                                "rows": seq_rows}

    # ------------------------------------------------------------------ 16. visual-control retention + telemetry
    order_t = sorted(range(n), key=lambda i: t[i])
    pos_in = {i: k for k, i in enumerate(order_t)}
    base_tiers = {(name, f): ib.allocate_progressive(costs, o, f * total) for name, o in v2_orders.items() for f in CTRL_BUDGETS}
    ret = defaultdict(lambda: defaultdict(lambda: {"ctrl": [], "src": []}))
    groups_members = defaultdict(list)
    for i, o in enumerate(obs):
        groups_members[o["near_duplicate_group"]].append(i)
    for e in vis:
        i = e["source_index"]
        v = e["_vec"]
        prev = [j for j in order_t[:pos_in[i]] if obs[j]["sol"] >= obs[i]["sol"] - NOVELTY_LOOKBACK_SOLS]
        nv = float(1.0 - np.max(E[prev] @ v)) if prev else 1.0
        hnew = phash(ctrl[e["synthetic_id"]])
        mod = [dict(o) for o in obs]
        mod[i] = dict(obs[i])
        mod[i]["image_features"] = {**obs[i]["image_features"], "embedding_novelty": nv}
        if any(hamming(hnew, H[j]) > sim.PHASH_MAX_BITS for j in groups_members[obs[i]["near_duplicate_group"]] if j != i) or len(groups_members[obs[i]["near_duplicate_group"]]) == 1:
            mod[i]["near_duplicate_group"] = -1 - i
        orders = ib.strategy_orders(mod, 0)
        for name, o in orders.items():
            if name == "RANDOM":
                continue
            for f in CTRL_BUDGETS:
                tiers = ib.allocate_progressive(costs, o, f * total)
                cell = ret[f"{name}@{f}"][e["severity"]]
                cell["ctrl"].append(ib.RANK[tiers[i]] >= ib.RANK["COMPRESSED"])
                cell["src"].append(ib.RANK[base_tiers[(name, f)][i]] >= ib.RANK["COMPRESSED"])
    R["visual_control_retention"] = {k: {lv: {"control_retained": float(np.mean(c["ctrl"])), "source_retained": float(np.mean(c["src"])),
                                              "lift": float(np.mean(c["ctrl"]) - np.mean(c["src"])), "n": len(c["ctrl"])}
                                         for lv, c in sorted(d.items(), key=lambda kv: syn.LEVELS.index(kv[0]))} for k, d in ret.items()}
    R["telemetry_after_controls"] = {"note": "TELEMETRY-PRIORITY scores do not depend on image content, so a controlled visual change can "
                                             "never alter its ranking: lift is 0 by construction (measured below)",
                                     "lift": {f: R["visual_control_retention"][f"TELEMETRY-PRIORITY@{f}"] for f in CTRL_BUDGETS}}

    # ------------------------------------------------------------------ 14/15. disagreement sampler → review pairs
    rk = lambda order: {i: r for r, i in enumerate(order)}  # noqa: E731
    r_size, r_nov, r_tel, r_ph = rk(v2_orders["SIZE-AWARE"]), rk(v2_orders["EMBEDDING-NOVELTY"]), rk(v2_orders["TELEMETRY-PRIORITY"]), rk(v2_orders["PHASH-REPRESENTATIVES"])
    prng = random.Random(syn.seed_for("REVIEW_PAIRS_V1"))
    pairs, seen = [], set()

    def add(a, b, cat):
        key = tuple(sorted((a, b)))
        if a == b or key in seen:
            return False
        seen.add(key)
        if prng.random() < 0.5:
            a, b = b, a
        pairs.append({"pair_id": f"P31-{len(pairs):03d}", "A": obs[a]["id"], "B": obs[b]["id"], "category": cat,
                      "scores": {x: {"size_rank": r_size[x], "novelty_rank": r_nov[x], "telemetry_rank": r_tel[x], "phash_rep_rank": r_ph[x],
                                     "embedding_novelty": obs[x]["image_features"]["embedding_novelty"],
                                     "telemetry_score": obs[x]["telemetry_context"]["telemetry_score"], "full_bytes": obs[x]["downlink"]["full_bytes"]}
                                 for x in (a, b)}})
        return True
    q = n // 4
    cand = []
    for idx in by_sol.values():
        real_idx = [k for k in idx if k < n]
        for x, a in enumerate(real_idx):
            for b in real_idx[x + 1:]:
                hd, cd = hamming(H[a], H[b]), cosd(E[a], E[b])
                if (hd <= sim.PHASH_MAX_BITS and cd > pctl([p["cos_dist"] for p in stereo_pairs], 90)) or (hd > 3 * sim.PHASH_MAX_BITS and cd < tau_cos):
                    cand.append((a, b))
    prng.shuffle(cand)
    for a, b in cand[:25]:
        add(a, b, "PHASH_VS_EMBEDDING")
    A_ = [i for i in range(n) if r_size[i] < q and r_nov[i] > 3 * q]
    B_ = [i for i in range(n) if r_nov[i] < q and r_size[i] > 3 * q]
    for _ in range(200):
        if sum(p["category"] == "SIZE_VS_NOVELTY" for p in pairs) >= 25 or not A_ or not B_:
            break
        add(prng.choice(A_), prng.choice(B_), "SIZE_VS_NOVELTY")
    A_ = [i for i in range(n) if obs[i]["telemetry_context"]["telemetry_score"] > 0 and r_nov[i] > n // 2]
    B_ = [i for i in range(n) if obs[i]["telemetry_context"]["telemetry_score"] == 0 and r_nov[i] < q]
    for _ in range(200):
        if sum(p["category"] == "TELEMETRY_VS_IMAGE" for p in pairs) >= 25 or not A_ or not B_:
            break
        add(prng.choice(A_), prng.choice(B_), "TELEMETRY_VS_IMAGE")
    dis = []
    for key, fr in seqs.items():
        if key[1].startswith("trav") and len(fr) >= 10:
            rows = {r["method"]: r for r in seq_rows if r["sequence"] == f"{key[0]}:{key[1]}" and r["fraction"] == 0.25}
            del rows
            m = len(fr)
            xy = np.array([[obs[i]["location_context"].get("landing_x", 0.0), obs[i]["location_context"].get("landing_y", 0.0)] for i in fr])
            Dp = np.linalg.norm(xy[:, None] - xy[None], axis=2)
            Dh = np.array([[hamming(H[a], H[b]) for b in fr] for a in fr], dtype=float)
            k = max(1, math.ceil(0.25 * m))
            sp, sh = set(fps(Dp, k)), set(fps(Dh, k))
            only_p, only_h = [fr[j] for j in sp - sh], [fr[j] for j in sh - sp]
            for a, b in zip(only_p, only_h):
                dis.append((a, b))
    prng.shuffle(dis)
    for a, b in dis[:25]:
        add(a, b, "SEQUENCE_METHODS")
    rev_dir = ROOT / "data" / "review"
    rev_dir.mkdir(parents=True, exist_ok=True)
    (rev_dir / "pairs_v1.json").write_text(json.dumps({"version": "REVIEW_PAIRS_V1", "created_at": datetime.now(timezone.utc).isoformat(),
                                                        "split": "development", "question": "Which observation would you prioritize for downlink?",
                                                        "choices": ["A", "B", "EQUAL", "UNSURE"],
                                                        "blinding": "reviewers see images + basic metadata only; categories and scores are revealed after the answer",
                                                        "pairs": pairs}, indent=1))
    R["review"] = {"pairs": len(pairs), "by_category": dict(Counter(p["category"] for p in pairs))}
    ann = rev_dir / "annotations_v1.jsonl"
    R["review"]["annotations_collected"] = len(ann.read_text().splitlines()) if ann.exists() else 0

    # ------------------------------------------------------------------ write
    for e in entries:
        for k in ("_cos", "_ham", "_vec"):
            e.pop(k, None)
    R["git"] = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    R["declared"] = {"per_level": PER_LEVEL, "near_duplicates": N_DUP, "time_link_s": TIME_LINK_S, "sequence_fractions": FRACTIONS,
                     "control_budgets": CTRL_BUDGETS, "fine_grid": [float(g) for g in grid], "phash_max_bits": sim.PHASH_MAX_BITS,
                     "scene_max_deg": sim.SCENE_MAX_DEG, "vision_model": vm["chosen"]}
    (out / "results.json").write_text(json.dumps(R, indent=1, default=str))
    print(f"→ {(out / 'results.json').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
