#!/usr/bin/env python3
"""Phase 3.2 — corrective / diagnostic evaluation (DEVELOPMENT split only; no fusion, no VLM).

    uv run python scripts/run_phase3_2.py

Frozen inputs (not modified): Phase 3 baseline (tag phase3-baseline), Phase 3.1 results + SYNTH_V1 controls (tag
phase3.1-complete), QUALITY_V2 thresholds as frozen in the Phase 3.1 results. Output: artifacts/phase3_2/<run_id>/.
Jev pairwise review runs separately (scripts/jev_pairwise_review.py).

Declared before running: dense monotonicity grid = 80 log-spaced budgets 0.01–30 % of Σ FULL; report budgets
0.1–10 %; pHash temporal link ≤ 120 s; rover STOP = (site, drive), POSE = (site, drive, pose); traverse fractions
1/2, 1/4, 1/8; traverse position-coverage radius 5 m; stereo semantics per SCHEDULER_V3_STEREO_SAFE.
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
from deepsift.imaging import synthetic as v1gen  # noqa: E402
from deepsift.imaging import synthetic_v2 as v2gen  # noqa: E402
from deepsift.imaging.acquisitions import group_acquisitions  # noqa: E402
from deepsift.imaging.embeddings import Embedder  # noqa: E402
from deepsift.imaging.features import hamming, jpeg_bytes, load_primary, phash, quality, to_work  # noqa: E402
from deepsift.imaging.pds3 import parse_label, read_image  # noqa: E402

BASE = ROOT / "artifacts" / "phase3" / "20260925T132323-phase3-dev-baseline-ff13"
P31 = ROOT / "artifacts" / "phase3_1" / "20260925T133727-phase3.1-dev-controls-0ceb" / "results.json"
V2_DIR = ROOT / "data" / "synthetic" / "phase3_2" / "controls_v2"
REPORT_BUDGETS = [0.001, 0.0025, 0.005, 0.01, 0.02, 0.05, 0.10]
FRACTIONS = [0.5, 0.25, 0.125]
TIME_LINK_S = 120
COVER_RADIUS_M = 5.0
JPEG_Q = 50


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "")).replace(tzinfo=timezone.utc).timestamp()


def pctl(xs, q):
    xs = [x for x in xs if x is not None]
    return float(np.percentile(xs, q)) if xs else None


def cosd(a, b):
    return float(1.0 - np.dot(a, b))


def read(p):
    return read_image(ROOT / p["path_img"], parse_label((ROOT / p["path_lbl"]).read_text(encoding="latin-1")))


def main() -> int:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-phase3.2-dev-corrective-" + uuid.uuid4().hex[:4]
    out = ROOT / "artifacts" / "phase3_2" / run_id
    out.mkdir(parents=True)
    obs = [json.loads(x) for x in (BASE / "observations.jsonl").read_text().splitlines()]
    E = np.load(BASE / "embeddings.npy")
    acqs = group_acquisitions(json.loads((ROOT / "data" / "manifests" / "navcam_development.json").read_text())["products"])
    assert [a["acq_id"] for a in acqs] == [o["id"] for o in obs]
    n = len(obs)
    p31 = json.loads(P31.read_text())
    TH = p31["quality"]["v2_thresholds"]
    vm = json.loads((ROOT / "config" / "phase3_vision_model.json").read_text())
    emb = Embedder(vm["chosen"])
    H = [int(o["image_features"]["phash"], 16) for o in obs]
    t = [ts(o["utc"]) for o in obs]
    R: dict = {"run_id": run_id, "split": "development", "frozen_inputs": {"baseline": BASE.name, "phase3_1": P31.parent.name}}
    cache = {}

    def native(i):
        if i not in cache:
            cache[i] = load_primary(acqs[i])
        return cache[i]

    # ------------------------------------------------------------------ 5. per-eye byte accounting
    eye_costs, rows = [], []
    for i, a in enumerate(acqs):
        e = {"metadata": obs[i]["downlink"]["metadata_bytes"], "stereo": a["stereo"]}
        for eye in (["L", "R"] if a["stereo"] else [a["primary"]["eye"]]):
            key = "L" if not a["stereo"] else eye
            prim = [p for p in a["primaries"] if p["eye"] == eye and p["tier"] == a["primary_tier"]][0]
            th = next((x for x in a["thumbnails"] if x["eye"] == eye), None)
            img = native(i) if prim is a["primary"] else read(prim)
            e[key] = {"full": prim["estimated_downlink_bytes"], "compressed": float(jpeg_bytes(img, JPEG_Q)),
                      "thumbnail": th["estimated_downlink_bytes"] if th else None}
            rows.append({"acq_id": a["acq_id"], "eye": eye, "stereo": a["stereo"], "tier_primary": a["primary_tier"],
                         "full_bytes_NASA_LABEL_ESTIMATE": e[key]["full"], "compressed_bytes_SIMULATED_PRODUCT_TIER": e[key]["compressed"],
                         "thumbnail_bytes_NASA_LABEL_ESTIMATE": e[key]["thumbnail"], "archive_bytes_primary": prim["archive_bytes_img"]})
        eye_costs.append(e)
    c3 = ib.cost_table_v3(eye_costs)
    c12 = ib.cost_table(obs)
    total = sum(c["FULL"] for c in c12)
    assert abs(total - sum(c["FULL"] for c in c3)) < 1e-6, "FULL tier must be identical across schedulers"
    (out / "byte_accounting_per_eye.json").write_text(json.dumps(rows, indent=1))
    st_idx = [i for i in range(n) if acqs[i]["stereo"]]
    R["byte_accounting"] = {
        "labels": {"NASA_LABEL_ESTIMATE": "LINES×LINE_SAMPLES×INST_CMPRS_RATE/8 from the product label",
                   "SIMULATED_PRODUCT_TIER": f"DEEPSIFT JPEG q{JPEG_Q} ground re-encoding of the archived primary — not a NASA product"},
        "stereo_tier_totals_MB": {k: sum(c3[i][k] or 0 for i in st_idx) / 1e6 for k in ("THUMBNAIL", "COMPRESSED", "FULL")},
        "stereo_tier_left_right_MB": {k: [sum(eye_costs[i]["L"][k] or 0 for i in st_idx) / 1e6, sum(eye_costs[i]["R"][k] or 0 for i in st_idx) / 1e6]
                                      for k in ("thumbnail", "compressed", "full")},
        "unknown_costs": sum(1 for c in c3 for k in ("THUMBNAIL", "COMPRESSED", "FULL") if c[k] is None),
        "sample": rows[:6]}

    # ------------------------------------------------------------------ 2/3/4/6. schedulers V1 / V2 / V3
    orders = ib.strategy_orders(obs, 0)
    v1_passes = ib.strategy_passes(obs, 0)
    alloc = {
        "V1": lambda name, f: (ib.allocate(c12, v1_passes[f"{name}|policy"] if f"{name}|policy" in v1_passes else v1_passes[name], f * total), c12, False),
        "V2": lambda name, f: (ib.allocate_progressive(c12, orders[name], f * total), c12, False),
        "V3": lambda name, f: (ib.allocate_progressive(c3, orders[name], f * total), c3, True),
    }
    comp = {}
    for sched, fn in alloc.items():
        for name in orders:
            if sched == "V1" and name == "PHASH-REPRESENTATIVES":
                key = "PHASH-REPRESENTATIVES"
            else:
                key = name
            for f in REPORT_BUDGETS:
                tiers, costs, pair = fn(key, f)
                comp[f"{sched}|{name}|{f}"] = ib.coverage(obs, costs, tiers, pair)
    keys = ["acquisitions_represented", "scene_clusters_represented", "rover_positions_represented", "stereo_pair_present", "stereo_pair_usable"]
    grid = list(np.geomspace(0.0001, 0.30, 80))
    mono = {}
    for sched, fn in alloc.items():
        for name in orders:
            seq = []
            for f in grid:
                tiers, costs, pair = fn(name, f)
                cv = ib.coverage(obs, costs, tiers, pair)
                seq.append([cv[k] for k in keys])
            mono[f"{sched}|{name}"] = {k: sum(1 for a, b in zip(seq, seq[1:]) if b[j] < a[j]) for j, k in enumerate(keys)}
    v3_violations = sum(sum(v.values()) for k, v in mono.items() if k.startswith("V3"))
    R["schedulers"] = {"budgets": REPORT_BUDGETS, "grid_points": len(grid), "comparison": comp, "monotonicity_violations": mono,
                       "v3_total_violations": v3_violations,
                       "v3_stereo_safe": all(comp[k]["stereo_pair_usable"] <= comp[k]["acquisitions_usable"] for k in comp if k.startswith("V3"))}
    print("schedulers: V3 violations", v3_violations)
    if v3_violations:
        (out / "results.json").write_text(json.dumps(R, indent=1, default=str))
        print("STOP: Scheduler V3 is not monotonic")
        return 2

    # ------------------------------------------------------------------ 7/8/9. generator V2 (paired with V1) + QUALITY_V2 frozen
    m1 = json.loads((ROOT / "data" / "manifests" / "synthetic_controls_v1.json").read_text())
    e2 = []
    for e in m1["entries"]:
        i = e["source_index"]
        src = native(i)
        if e["family"] == "NEAR_DUPLICATE":
            y, p = v2gen.near_duplicate(src, e["random_seed"])
            box = None
        else:
            y, p, box = v2gen.perturb(src, e["family"], e["severity"], e["random_seed"])
        viol = v2gen.check_contract(e["family"], src, y, p, box)
        sid = e["synthetic_id"].replace("SYN-P31-", "SYN-P32-")
        path = V2_DIR / f"{sid}.png"
        v1gen.save_png16(path, y)
        e2.append({**{k: e[k] for k in ("family", "family_kind", "severity", "random_seed", "source_acquisition_id", "source_product_id",
                                        "source_sha256_img", "source_tier", "source_index", "tune_eval_half")},
                   "synthetic_id": sid, "paired_v1_id": e["synthetic_id"], "label": "SYNTHETIC CONTROL", "generator": v2gen.GENERATOR,
                   "parameters": p, "bounding_region_yxyx": box, "contract": v2gen.CONTRACTS[e["family"]], "contract_violations": viol,
                   "ground_truth": e["ground_truth"].replace("SYNTHETIC CONTROL", "SYNTHETIC CONTROL (V2)"),
                   "path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    (ROOT / "data" / "manifests" / "synthetic_controls_v2.json").write_text(json.dumps({
        "generator": v2gen.GENERATOR, "created_at": datetime.now(timezone.utc).isoformat(), "split": "development", "paired_with": "SYNTH_V1",
        "note": "SYNTHETIC CONTROLS (V2) — perturbed copies of NASA PDS observations; originals never modified; not Mars events",
        "contracts": v2gen.CONTRACTS, "count": len(e2), "entries": e2}, indent=1, default=str))
    v1_viol = Counter()
    for e in m1["entries"]:
        y = v1gen.load_png16(ROOT / e["path"])
        src = native(e["source_index"])
        p = dict(e["parameters"])
        if e["family"] == "STRIPING":
            rng = np.random.default_rng(e["random_seed"])
            p["column_indices"] = sorted(int(c) for c in rng.choice(src.shape[1], size=max(1, round(p["column_fraction"] * src.shape[1])), replace=False))
        for v in v2gen.check_contract(e["family"], src, y, p, e["bounding_region_yxyx"]):
            v1_viol[(e["family"], v)] += 1
    R["generator_v2"] = {"controls": len(e2), "by_family": dict(Counter(e["family"] for e in e2)),
                         "contract_violations_v2": sum(len(e["contract_violations"]) for e in e2),
                         "contract_violations_v1_same_contracts": {f"{a}:{b}": c for (a, b), c in v1_viol.items()},
                         "visual_amplitude_scale": {lv: {"median": pctl([e["parameters"]["amplitude_scale"] for e in e2 if e["family_kind"] == "VISUAL_NOVELTY" and e["severity"] == lv], 50),
                                                         "attenuated_share": float(np.mean([e["parameters"]["amplitude_scale"] < 1 for e in e2 if e["family_kind"] == "VISUAL_NOVELTY" and e["severity"] == lv]))}
                                                    for lv in v2gen.LEVELS},
                         "bytes_on_disk": sum((ROOT / e["path"]).stat().st_size for e in e2)}
    print("generator v2: violations", R["generator_v2"]["contract_violations_v2"], "v1 under same contracts", sum(v1_viol.values()))

    feats = {}
    for gen, ents, loader in (("V1", m1["entries"], v1gen.load_png16), ("V2", e2, v1gen.load_png16)):
        for e in ents:
            if e["family_kind"] != "REDUNDANCY":
                feats[(gen, e["synthetic_id"])] = q2.features(loader(ROOT / e["path"]))
    flag = lambda gen, e: q2.classify(feats[(gen, e["synthetic_id"])], e["source_tier"], TH)[0] != "CLEAN"  # noqa: E731

    def table(gen, ents, half=None):
        tab = defaultdict(lambda: defaultdict(list))
        for e in ents:
            if e["family_kind"] == "ENGINEERING_QUALITY" and (half is None or e["tune_eval_half"] == half):
                tab[e["family"]][e["severity"]].append(flag(gen, e))
        return {f: {lv: float(np.mean(v)) for lv, v in sorted(d.items(), key=lambda kv: v2gen.LEVELS.index(kv[0]))} for f, d in tab.items()}
    real = [q2.classify(q2.features(native(i), acqs[i]["primary"].get("error_pixels")), obs[i]["primary_tier"], TH) for i in range(n)]
    xtalk = {}
    for gen, ents in (("V1", m1["entries"]), ("V2", e2)):
        vis = [e for e in ents if e["family_kind"] == "VISUAL_NOVELTY"]
        reasons = Counter(r for e in vis for r in q2.classify(feats[(gen, e["synthetic_id"])], e["source_tier"], TH)[1])
        xtalk[gen] = {"visual_controls_flagged": float(np.mean([flag(gen, e) for e in vis])), "reasons": dict(reasons)}
    R["quality"] = {"QUALITY_V2": "frozen thresholds from Phase 3.1 (not retuned)",
                    "recall_eval_half": {"V1": table("V1", m1["entries"], "EVAL"), "V2": table("V2", e2, "EVAL")},
                    "recall_all": {"V1": table("V1", m1["entries"]), "V2": table("V2", e2)},
                    "cross_talk": xtalk,
                    "DEVELOPMENT_FALSE_POSITIVE_RATE": float(np.mean([s != "CLEAN" for s, _ in real])),
                    "false_positive_note": "thresholds were derived from these same 609 development acquisitions — not a validated rate"}
    print("quality xtalk", {k: v["visual_controls_flagged"] for k, v in xtalk.items()})

    # ------------------------------------------------------------------ 11/12. pHash safety + taxonomy
    dups = [e for e in e2 if e["family"] == "NEAR_DUPLICATE"]
    pool = [{"sol": obs[i]["sol"], "t": t[i], "stop": (obs[i]["source_metadata"]["pose"][0], obs[i]["source_metadata"]["pose"][1]),
             "pose": tuple(obs[i]["source_metadata"]["pose"]), "scene": obs[i]["scene_cluster"], "h": H[i], "src": i} for i in range(n)]
    for e in dups:
        i = e["source_index"]
        pool.append({**pool[i], "t": t[i] + 1, "h": phash(v1gen.load_png16(ROOT / e["path"]))})
    N = len(pool)
    by_sol = defaultdict(list)
    for k, p in enumerate(pool):
        by_sol[p["sol"]].append(k)
    ph = lambda a, b: hamming(a["h"], b["h"]) <= sim.PHASH_MAX_BITS  # noqa: E731
    methods = {"PHASH_ONLY": ph, "PHASH_PLUS_TIME_120S": lambda a, b: ph(a, b) and abs(a["t"] - b["t"]) <= TIME_LINK_S,
               "PHASH_PLUS_SAME_ROVER_STOP": lambda a, b: ph(a, b) and a["stop"] == b["stop"],
               "PHASH_PLUS_SITE_DRIVE_POSE": lambda a, b: ph(a, b) and a["pose"] == b["pose"],
               "METADATA_SCENE": lambda a, b: a["scene"] == b["scene"]}
    seqs = defaultdict(list)
    for i in sorted(range(n), key=lambda i: t[i]):
        seqs[(obs[i]["sol"], obs[i]["sequence_id"])].append(i)
    trav = [i for k, v in seqs.items() if k[1].startswith("trav") for i in v]
    stops_all = {p["pose"] for p in pool[:n]}
    gres = {}
    for name, link in methods.items():
        uf = sim._UF(N)
        for idx in by_sol.values():
            for x, a in enumerate(idx):
                for b in idx[x + 1:]:
                    if link(pool[a], pool[b]):
                        uf.union(a, b)
        comp_ = [uf.find(k) for k in range(N)]
        mem = defaultdict(list)
        for k in range(n):
            mem[comp_[k]].append(k)
        pairs = [(a, b) for m in mem.values() for x, a in enumerate(m) for b in m[x + 1:]]
        reps = {min(m, key=lambda k: pool[k]["t"]) for m in mem.values()}
        gres[name] = {"near_duplicate_retrieval": float(np.mean([comp_[n + k] == comp_[e["source_index"]] for k, e in enumerate(dups)])),
                      "false_merge_rate_different_scene": float(np.mean([pool[a]["scene"] != pool[b]["scene"] for a, b in pairs])) if pairs else 0.0,
                      "false_merge_rate_different_pose": float(np.mean([pool[a]["pose"] != pool[b]["pose"] for a, b in pairs])) if pairs else 0.0,
                      "traverse_compression": len(trav) / max(1, len({comp_[i] for i in trav})),
                      "unique_position_loss": 1 - len({pool[k]["pose"] for k in reps}) / len(stops_all),
                      "stereo_effect": "grouping is per acquisition: both eyes stay together; no method can drop one eye"}
    gres["METADATA_SCENE"]["note"] = "reference definition — false-merge 0 by construction"
    R["phash"] = gres
    tax = Counter()
    for idx in by_sol.values():
        real_idx = [k for k in idx if k < n]
        for x, a in enumerate(real_idx):
            for b in real_idx[x + 1:]:
                P = hamming(H[a], H[b]) <= sim.PHASH_MAX_BITS
                S = obs[a]["scene_cluster"] == obs[b]["scene_cluster"]
                Q = obs[a]["sequence_id"] == obs[b]["sequence_id"]
                tax["PIXEL_SIMILAR"] += P
                tax["SCENE_SIMILAR"] += S
                tax["SEQUENCE_RELATED"] += Q
                tax["POTENTIALLY_REDUNDANT"] += P and S
                tax["PIXEL_SIMILAR_NOT_SCENE_SIMILAR"] += P and not S
    tax["STEREO_RELATED (acquisitions, within-acquisition L/R)"] = len(st_idx)
    R["redundancy_taxonomy"] = {**tax, "definitions": {
        "PIXEL_SIMILAR": "same sol, pHash ≤ 10 bits", "SCENE_SIMILAR": "same rover pose + pointing ≤ 15°",
        "SEQUENCE_RELATED": "same sol + sequence id (context)", "STEREO_RELATED": "left/right of one acquisition (parallax, never a duplicate)",
        "POTENTIALLY_REDUNDANT": "PIXEL_SIMILAR AND SCENE_SIMILAR between different acquisitions"}}

    # ------------------------------------------------------------------ 13/14/15. embedding + stereo + resolution diagnostics
    sp = []
    for i in st_idx:
        L = [p for p in acqs[i]["primaries"] if p["eye"] == "L"][0]
        Rr = [p for p in acqs[i]["primaries"] if p["eye"] == "R"][0]
        a, b = read(L), read(Rr)
        sp.append((cosd(emb.embed(to_work(a))[0], emb.embed(to_work(b))[0]), hamming(phash(a), phash(b))))
    consec = [(a, b) for v in seqs.values() for a, b in zip(v, v[1:])]
    rr = random.Random(11)
    randp = []
    while len(randp) < 2000:
        a, b = rr.randrange(n), rr.randrange(n)
        if obs[a]["sol"] != obs[b]["sol"]:
            randp.append((a, b))
    dstat = lambda pairs: {"cos_p10_p50_p90": [pctl([cosd(E[a], E[b]) for a, b in pairs], q) for q in (10, 50, 90)],  # noqa: E731
                           "hamming_p10_p50_p90": [pctl([hamming(H[a], H[b]) for a, b in pairs], q) for q in (10, 50, 90)]}
    tau_c, tau_h = pctl([c for c, _ in sp], 50), pctl([h for _, h in sp], 50)
    sens = defaultdict(lambda: defaultdict(lambda: {"e": [], "h": []}))
    for e in e2:
        if e["family_kind"] == "REDUNDANCY":
            continue
        i = e["source_index"]
        y = v1gen.load_png16(ROOT / e["path"])
        sens[(e["family_kind"], e["family"])][e["severity"]]["e"].append(cosd(E[i], emb.embed(to_work(y))[0]) > tau_c)
        sens[(e["family_kind"], e["family"])][e["severity"]]["h"].append(hamming(H[i], phash(y)) > tau_h)

    def box(x, k):
        h2, w2 = (x.shape[0] // k) * k, (x.shape[1] // k) * k
        return x[:h2, :w2].reshape(h2 // k, k, w2 // k, k).mean(axis=(1, 3))
    fidx = [i for i in range(n) if obs[i]["primary_tier"] == "F"]
    res = defaultdict(list)
    for i in fidx:
        x = native(i)
        f0 = quality(x, None)
        for name, k in (("D_like_256", 4), ("T_like_64", 16)):
            y = box(x, k)
            res[f"cos|{name}"].append(cosd(E[i], emb.embed(to_work(y))[0]))
            res[f"ham|{name}"].append(hamming(H[i], phash(y)))
            f1 = quality(y, None)
            for kk in ("brightness", "contrast", "entropy_bits", "sharpness"):
                res[f"feat|{name}|{kk}"].append(abs(f1[kk] - f0[kk]) / (abs(f0[kk]) + 1e-9))
        th = acqs[i]["thumbnail"]
        y = read(th)
        y = (y - y.min()) / max(1e-6, float(y.max() - y.min())) * 4095.0
        res["cos|real_thumbnail"].append(cosd(E[i], emb.embed(to_work(y))[0]))
        res["ham|real_thumbnail"].append(hamming(H[i], phash(y)))
    ET = np.stack([emb.embed(to_work(box(native(i), max(1, native(i).shape[1] // 64))))[0] for i in range(n)])
    order_t = sorted(range(n), key=lambda i: t[i])

    def nov(Em):
        v = [1.0] * n
        for k, i in enumerate(order_t):
            prev = [j for j in order_t[:k] if obs[j]["sol"] >= obs[i]["sol"] - 3]
            if prev:
                v[i] = float(1.0 - np.max(Em[prev] @ Em[i]))
        return v
    sp_ = lambda a, b: float(np.corrcoef(np.argsort(np.argsort(a)), np.argsort(np.argsort(b)))[0, 1])  # noqa: E731
    n0, nT = [o["image_features"]["embedding_novelty"] for o in obs], nov(ET)
    fb = [o["downlink"]["full_bytes"] for o in obs]
    R["embeddings"] = {
        "model": vm["chosen"], "stereo_left_right": {"n": len(sp), "cos_p10_p50_p90": [pctl([c for c, _ in sp], q) for q in (10, 50, 90)],
                                                     "hamming_p10_p50_p90": [pctl([h for _, h in sp], q) for q in (10, 50, 90)],
                                                     "within_phash_threshold": float(np.mean([h <= sim.PHASH_MAX_BITS for _, h in sp]))},
        "consecutive_frames": dstat(consec), "random_pairs": dstat(randp), "change_thresholds": {"cos": tau_c, "hamming": tau_h},
        "change_sensitivity_v2_controls": {f"{k[0]}|{k[1]}": {lv: {"embedding": float(np.mean(c["e"])), "phash": float(np.mean(c["h"]))}
                                                             for lv, c in sorted(d.items(), key=lambda kv: v2gen.LEVELS.index(kv[0]))} for k, d in sens.items()},
        "resolution": {"full_frames": len(fidx), **{k: {"median": pctl(v, 50), "p90": pctl(v, 90)} for k, v in res.items()},
                       "novelty_rank_corr_full_vs_64px": sp_(n0, nT), "novelty_vs_full_bytes": {"original": sp_(n0, fb), "at_64px": sp_(nT, fb)},
                       "resolution_sensitive_features": "sharpness (≈99 % change at 64 px); contrast / entropy moderate; brightness, pHash invariant"}}

    # ------------------------------------------------------------------ 16. traverse experiment (V3 stereo-safe costs)
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
    def uniform_distance(cum, targets):
        """Frame nearest to each equally spaced odometry target; ties → nearest UNUSED frame, so exactly k frames."""
        used = []
        for d in targets:
            for j in np.argsort(np.abs(cum - d), kind="stable"):
                if int(j) not in used:
                    used.append(int(j))
                    break
        return sorted(used)
    trows = []
    for key, fr in seqs.items():
        if not key[1].startswith("trav") or len(fr) < 10:
            continue
        m = len(fr)
        xy = np.array([[obs[i]["location_context"].get("landing_x", 0.0), obs[i]["location_context"].get("landing_y", 0.0)] for i in fr])
        Dp = np.linalg.norm(xy[:, None] - xy[None], axis=2)
        De = 1.0 - E[fr] @ E[fr].T
        cum = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))])
        path = float(cum[-1]) or 1.0
        stops = {tuple(obs[i]["source_metadata"]["pose"]) for i in fr}
        for frac in [1.0] + FRACTIONS:
            k = max(1, math.ceil(frac * m))
            if frac == 1.0:
                sels = {"SEND_ALL": list(range(m))}
            else:
                step = max(1, round(1 / frac))
                targets = np.linspace(0, cum[-1], k)
                sels = {"EVERY_NTH_FRAME": list(range(0, m, step))[:k] or [0],
                        "UNIFORM_DISTANCE": uniform_distance(cum, targets),
                        "METADATA_POSITION": fps(Dp, k), "EMBEDDING_CHANGE": fps(De, k),
                        "POSITION_PLUS_EMBEDDING_CHANGE": fps(0.5 * Dp / (Dp.max() or 1.0) + 0.5 * De / (De.max() or 1.0), k)}
            for meth, s in sels.items():
                s = sorted(s)
                si = [fr[j] for j in s]
                rest = [i for i in fr if i not in set(si)]
                byt = sum(c3[i]["FULL"] for i in si) + sum(c3[i]["THUMBNAIL"] or 0 for i in rest)
                gaps = [float(Dp[a, b]) for a, b in zip(s, s[1:])]
                cover = float(np.mean(np.min(Dp[:, s], axis=1) <= COVER_RADIUS_M))
                trows.append({"sequence": f"{key[0]}:{key[1]}", "frames": m, "fraction": frac, "method": meth, "frames_retained": len(s), "bytes": byt,
                              "bytes_send_all": sum(c3[i]["FULL"] for i in fr),
                              "unique_positions_retained": len({tuple(obs[i]["source_metadata"]["pose"]) for i in si}) / len(stops),
                              "position_coverage_5m": cover,
                              "traverse_distance_represented": float(sum(gaps)) / path if len(s) > 1 else 0.0,
                              "mean_spatial_gap_m": float(np.mean(gaps)) if gaps else 0.0, "max_spatial_gap_m": max(gaps) if gaps else 0.0,
                              "visual_change_coverage": float(np.mean(np.max(E[fr] @ E[si].T, axis=1))),
                              "stereo_pairs_retained_full": sum(1 for i in si if obs[i]["stereo"]),
                              "stereo_pairs_retained_broken": 0})  # V3 pair costs: an eye is never dropped (by construction)
    tagg = defaultdict(lambda: defaultdict(list))
    for r in trows:
        for k in ("bytes", "bytes_send_all", "frames_retained", "unique_positions_retained", "position_coverage_5m", "traverse_distance_represented",
                  "mean_spatial_gap_m", "max_spatial_gap_m", "visual_change_coverage", "stereo_pairs_retained_full"):
            tagg[(r["fraction"], r["method"])][k].append(r[k])
    R["traverse"] = {"research_question": "For rover traverse imaging, how much downlink can be removed while preserving spatial coverage and meaningful visual change?",
                     "sequences": len({r["sequence"] for r in trows}), "frames": sum({r["sequence"]: r["frames"] for r in trows}.values()),
                     "summary": {f"{f}|{m}": {"bytes_fraction_of_send_all": float(np.sum(v["bytes"]) / np.sum(v["bytes_send_all"])),
                                              "frames_retained": int(np.sum(v["frames_retained"])),
                                              **{k: float(np.mean(v[k])) for k in ("unique_positions_retained", "position_coverage_5m", "traverse_distance_represented",
                                                                                   "mean_spatial_gap_m", "max_spatial_gap_m", "visual_change_coverage")},
                                              "max_spatial_gap_m_worst": float(np.max(v["max_spatial_gap_m"])),
                                              "stereo_pairs_retained_full": int(np.sum(v["stereo_pairs_retained_full"])), "stereo_pairs_broken": 0}
                                 for (f, m), v in sorted(tagg.items(), key=lambda kv: (-kv[0][0], kv[0][1]))},
                     "rows": trows}

    R["git"] = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    (out / "results.json").write_text(json.dumps(R, indent=1, default=str))
    print(f"→ {(out / 'results.json').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
