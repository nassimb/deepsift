#!/usr/bin/env python3
"""Phase 3.4 — FRESH VALIDATION (PHASE3_VALIDATION2) of the simplified primary pipeline.

    uv run python scripts/run_phase3_4.py --stage dataset
    uv run python scripts/run_phase3_4.py --stage analysis --run artifacts/phase3_4/<run>

Everything comes from config/phase3_4_validation_config.json (committed before the interval was selected). The runner
refuses to start if that config's hash or any listed source hash differs, and refuses any sol in 950–979. It runs only the
simplified stack: Scheduler V3 with the primary orders, POSITION, EMBEDDING_CHANGE, POSITION + EMBEDDING_CHANGE and the
baselines FIFO / RANDOM / SIZE_AWARE / EVERY_NTH / UNIFORM_DISTANCE. pHash is used only as the research comparison inside
the pre-registered embedding rule; QUALITY_V2 only as a descriptive QUALITY_SUSPECT rate; no telemetry join, no Jev.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import sys
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "pipeline"))
sys.path.insert(0, str(ROOT / "scripts"))

from deepsift.evaluation import image_benchmark as ib  # noqa: E402
from deepsift.evaluation import phase3_pipeline as PP  # noqa: E402
from deepsift.evaluation import traverse as T  # noqa: E402
from deepsift.imaging import quality_v2 as q2  # noqa: E402
from deepsift.imaging import similarity as sim  # noqa: E402
from deepsift.imaging import synthetic as v1gen  # noqa: E402
from deepsift.imaging import synthetic_v2 as v2gen  # noqa: E402
from deepsift.imaging.acquisitions import group_acquisitions, grouping_stats  # noqa: E402
from deepsift.imaging.embeddings import Embedder  # noqa: E402
from deepsift.imaging.features import hamming, jpeg_bytes, load_primary, phash, quality, to_work  # noqa: E402
from deepsift.imaging.navcam import sha256_file  # noqa: E402
from deepsift.imaging.pds3 import parse_label, read_image  # noqa: E402
from phase3_4_freeze_config import config_hash  # noqa: E402

CFG_PATH = ROOT / "config" / "phase3_4_validation_config.json"
SPLIT = ROOT / "data" / "splits" / "phase3_validation2.json"
MANIFEST = ROOT / "data" / "manifests" / "navcam_validation2.json"
DEV_RUN = ROOT / "artifacts" / "phase3_3" / "20260926T134654-phase3.3-dev-32ec"
VAL1_RUN = ROOT / "artifacts" / "phase3_3" / "20260926T142033-phase3.3-val-2a31"
TEST = (950, 979)


def load_cfg() -> dict:
    cfg = json.loads(CFG_PATH.read_text())
    if config_hash(cfg) != cfg["config_hash"]:
        raise SystemExit("STOP: Phase 3.4 config hash mismatch")
    bad = [p for p, h in cfg["source_sha256"].items() if hashlib.sha256((ROOT / p).read_bytes()).hexdigest() != h]
    if bad:
        raise SystemExit(f"STOP: frozen sources changed: {bad}")
    return cfg


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "")).replace(tzinfo=timezone.utc).timestamp()


def pctl(xs, q):
    xs = [x for x in xs if x is not None]
    return float(np.percentile(xs, q)) if xs else None


def cosd(a, b):
    return float(1.0 - np.dot(a, b))


def read(p):
    return read_image(ROOT / p["path_img"], parse_label((ROOT / p["path_lbl"]).read_text(encoding="latin-1")))


# ====================================================================== dataset
def build(cfg: dict, out: Path) -> dict:
    from deepsift.multimodal import location
    from deepsift.multimodal.observation import DownlinkOptions, MultimodalObservation

    lo, hi = json.loads(SPLIT.read_text())["sols"]
    man = json.loads(MANIFEST.read_text())
    products = man["products"]
    if any(TEST[0] <= p["sol"] <= TEST[1] for p in products):
        raise SystemExit("STOP: test-interval product present")
    problems = Counter()
    for p in products:
        if not (lo <= p["sol"] <= hi):
            problems["sol_outside_interval"] += 1
        img, lbl = ROOT / p["path_img"], ROOT / p["path_lbl"]
        if not img.exists() or not lbl.exists():
            problems["missing_file"] += 1
            continue
        problems["sha256_img_mismatch"] += sha256_file(img) != p["sha256_img"]
        problems["sha256_lbl_mismatch"] += sha256_file(lbl) != p["sha256_lbl"]
        problems["empty_img"] += img.stat().st_size == 0
    problems = {k: v for k, v in problems.items() if v}
    verification = {"listed": man["n_listed"], "manifest_products": len(products), "complete": man["n_listed"] == len(products),
                    "problems": problems, "verdict": "PASS" if man["n_listed"] == len(products) and not problems else "FAIL"}
    if verification["verdict"] != "PASS":
        (out / "download_verification.json").write_text(json.dumps(verification, indent=1))
        raise SystemExit(f"STOP: download verification failed {verification}")
    vm = json.loads((ROOT / "config" / "phase3_vision_model.json").read_text())
    acqs = group_acquisitions(products)
    emb = Embedder(vm["chosen"])
    hashes, quals, comp, E = [], [], [], []
    for a in acqs:
        img = load_primary(a)
        quals.append(quality(img, a["primary"].get("error_pixels")))
        hashes.append(phash(img))
        comp.append(jpeg_bytes(img, 50))
        E.append(emb.embed(to_work(img))[0])
    E = np.stack(E)
    P = location.Places()
    locs = [P.locate(a["site"], a["drive"], a["pose"]) for a in acqs]
    order = sorted(range(len(acqs)), key=lambda i: acqs[i]["utc"])
    nov = [1.0] * len(acqs)
    for k, i in enumerate(order):
        prev = [j for j in order[:k] if acqs[j]["sol"] >= acqs[i]["sol"] - 3]
        if prev:
            nov[i] = float(1.0 - np.max(E[prev] @ E[i]))
    g_ph, g_seq, g_scene = sim.phash_groups(acqs, hashes), sim.sequence_groups(acqs), sim.scene_clusters(acqs)
    obs = []
    for i, a in enumerate(acqs):
        ests = [p["estimated_downlink_bytes"] for p in a["primaries"]]
        full = sum(ests) if all(e is not None for e in ests) else None
        meta_rec = {k: a[k] for k in ("acq_id", "sol", "utc", "sclk", "sequence_id", "site", "drive", "pose", "eyes", "primary_tier", "azimuth_deg", "elevation_deg")}
        dl = {"full_bytes": full, "compressed_bytes": float(comp[i]), "thumbnail_bytes": a["thumbnail"]["estimated_downlink_bytes"] if a["thumbnail"] else None,
              "metadata_bytes": len(json.dumps(meta_rec, separators=(",", ":"), default=str).encode()),
              "archive_bytes": int(sum(p["archive_bytes_img"] + p["archive_bytes_lbl"] for p in a["primaries"] + a["thumbnails"])),
              "full_bytes_status": "ESTIMATED_FROM_LABEL" if full is not None else "UNKNOWN"}
        o = MultimodalObservation(
            id=a["acq_id"], sol=a["sol"], utc=a["utc"], sclk=a["sclk"], sequence_id=a["sequence_id"], stereo=a["stereo"],
            primary_tier=a["primary_tier"], image_products=a["product_ids"],
            image_features={**{k: v for k, v in quals[i].items() if k != "quality_state"}, "phash": f"{hashes[i]:016x}",
                            "embedding_novelty": nov[i], "embedding_model": vm["chosen"]},
            quality_state=quals[i]["quality_state"],
            telemetry_context={"status": "NOT_JOINED", "role": "telemetry is descriptive only and not joined in Phase 3.4", "telemetry_score": None},
            location_context=locs[i], near_duplicate_group=g_ph[i], sequence_group=g_seq[i], scene_cluster=g_scene[i],
            downlink=DownlinkOptions(**dl),
            source_metadata={"urls": [p["url_img"] for p in a["primaries"] + a["thumbnails"]],
                             "sha256": [p["sha256_img"] for p in a["primaries"] + a["thumbnails"]], "pose": [a["site"], a["drive"], a["pose"]]})
        obs.append(o.model_dump(mode="json"))
    with (out / "observations.jsonl").open("w") as fh:
        for o in obs:
            fh.write(json.dumps(o) + "\n")
    np.save(out / "embeddings.npy", E)
    seqs = Counter((o["sol"], o["sequence_id"]) for o in obs)
    trav = [k for k, v in seqs.items() if k[1].startswith("trav") and v >= 10]
    trav_frames = [o for o in obs if (o["sol"], o["sequence_id"]) in set(trav)]
    rep = {"label": "VALIDATION2 DATASET REPORT (before any performance analysis)", "interval": [lo, hi], "download_verification": verification,
           "active_sols": sorted({a["sol"] for a in acqs}), "n_active_sols": len({a["sol"] for a in acqs}),
           "acquisitions": len(acqs), "stereo": sum(a["stereo"] for a in acqs), "mono": sum(not a["stereo"] for a in acqs),
           "products": len(products), "products_by_tier": dict(Counter(p["tier"] for p in products)),
           "download_bytes_archive": man["archive_bytes"],
           "estimated_downlink_bytes": {"full_total": sum(o["downlink"]["full_bytes"] or 0 for o in obs),
                                        "thumbnail_total": sum(o["downlink"]["thumbnail_bytes"] or 0 for o in obs)},
           "sequences": len(seqs), "sequence_types_by_acquisition": dict(Counter(o["sequence_id"][:4].upper() for o in obs)),
           "traverse_sequences_ge_10_frames": len(trav), "traverse_frames": len(trav_frames),
           "traverse_frames_with_places_position": sum(1 for o in trav_frames if "landing_x" in o["location_context"]),
           "places_join": dict(Counter(loc["match"].split("(")[0] for loc in locs)), "grouping": grouping_stats(products, acqs)}
    (out / "dataset_report.json").write_text(json.dumps(rep, indent=1, default=str))
    return rep


# ====================================================================== traverse evaluation (shared by all three periods)
def traverse_eval(obs, E, c3, stereo, fractions, radius):
    seqs = defaultdict(list)
    for i in sorted(range(len(obs)), key=lambda i: ts(obs[i]["utc"])):
        seqs[(obs[i]["sol"], obs[i]["sequence_id"])].append(i)
    seqs = {k: v for k, v in seqs.items() if k[1].startswith("trav") and len(v) >= 10}
    rows = []
    for key, fr in seqs.items():
        have = [i for i in fr if "landing_x" in obs[i]["location_context"]]
        if len(have) < len(fr):
            fr = have
        if len(fr) < 10:
            continue
        xy = np.array([[obs[i]["location_context"]["landing_x"], obs[i]["location_context"]["landing_y"]] for i in fr])
        em = E[fr]
        full_all = sum(c3[i]["FULL"] or 0 for i in fr)
        plan = [(1.0, "SEND_ALL", list(range(len(fr))))] + [(f, m, T.select(m, xy, em, f)) for f in fractions for m in T.METHODS]
        for f, m, s in plan:
            kept = {fr[j] for j in s}
            byt = sum(c3[i]["FULL"] or 0 for i in kept) + sum(c3[i]["THUMBNAIL"] or 0 for i in fr if i not in kept)
            mt = T.metrics(xy, em, s, radius)
            rows.append({"sequence": f"{key[0]}:{key[1]}", "fraction": f, "method": m, "bytes": byt, "bytes_send_all": full_all,
                         "unique_positions": len({tuple(obs[i]["source_metadata"]["pose"]) for i in kept}) / len({tuple(obs[i]["source_metadata"]["pose"]) for i in fr}),
                         "stereo_broken": sum(1 for i in kept if stereo[i] and c3[i]["FULL"] is None),
                         "stereo_kept_full": sum(1 for i in kept if stereo[i]), **{k: v for k, v in mt.items()}})
    agg = {}
    for (f, m) in sorted({(r["fraction"], r["method"]) for r in rows}, key=lambda x: (-x[0], x[1])):
        rs = [r for r in rows if r["fraction"] == f and r["method"] == m]
        pooled = [g for r in rs for g in r["gaps_m"]]
        agg[f"{f}|{m}"] = {"sequences": len(rs), "bytes_fraction": float(sum(r["bytes"] for r in rs) / sum(r["bytes_send_all"] for r in rs)),
                           "coverage_5m": float(np.mean([r["position_coverage"] for r in rs])),
                           "unique_positions": float(np.mean([r["unique_positions"] for r in rs])),
                           "mean_gap_m": float(np.mean([r["mean_gap_m"] for r in rs])), "p95_gap_m": pctl(pooled, 95),
                           "max_gap_m_mean": float(np.mean([r["max_gap_m"] for r in rs])), "max_gap_m_worst": max(r["max_gap_m"] for r in rs),
                           "max_distance_to_kept_m_worst": max(r["max_distance_to_kept_m"] for r in rs),
                           "visual_change_coverage": float(np.mean([r["visual_change_coverage"] for r in rs])),
                           "stereo_broken": int(sum(r["stereo_broken"] for r in rs)), "stereo_kept_full": int(sum(r["stereo_kept_full"] for r in rs))}
    return rows, agg


def marginal(rows, frac, seed):
    by = {}
    for r in rows:
        if r["fraction"] == frac and r["method"] in ("METADATA_POSITION", "POSITION_PLUS_EMBEDDING_CHANGE"):
            by.setdefault(r["sequence"], {})[r["method"]] = r
    seqs = sorted(by)
    dv = np.array([by[s]["POSITION_PLUS_EMBEDDING_CHANGE"]["visual_change_coverage"] - by[s]["METADATA_POSITION"]["visual_change_coverage"] for s in seqs])
    dc = np.array([by[s]["POSITION_PLUS_EMBEDDING_CHANGE"]["position_coverage"] - by[s]["METADATA_POSITION"]["position_coverage"] for s in seqs])
    rng = np.random.default_rng(seed)
    bs = [dv[rng.integers(0, len(dv), len(dv))].mean() for _ in range(10000)] if len(dv) else [0.0]
    bc = [dc[rng.integers(0, len(dc), len(dc))].mean() for _ in range(10000)] if len(dc) else [0.0]
    return {"sequences": len(seqs), "VISUAL_CHANGE_GAIN": float(dv.mean()) if len(dv) else None,
            "VISUAL_CHANGE_GAIN_95ci": [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))],
            "SPATIAL_COST": float(dc.mean()) if len(dc) else None, "SPATIAL_COST_95ci": [float(np.percentile(bc, 2.5)), float(np.percentile(bc, 97.5))],
            "sequences_with_visual_gain": int((dv > 0).sum()), "sequences_with_spatial_loss": int((dc < 0).sum())}


def costs_v3(acqs, obs, native):
    eye_costs = []
    for i, a in enumerate(acqs):
        e = {"metadata": obs[i]["downlink"]["metadata_bytes"], "stereo": a["stereo"]}
        for eye in (["L", "R"] if a["stereo"] else [a["primary"]["eye"]]):
            key = "L" if not a["stereo"] else eye
            prim = [p for p in a["primaries"] if p["eye"] == eye and p["tier"] == a["primary_tier"]][0]
            th = next((x for x in a["thumbnails"] if x["eye"] == eye), None)
            img = native(i) if prim is a["primary"] else read(prim)
            e[key] = {"full": prim["estimated_downlink_bytes"], "compressed": float(jpeg_bytes(img, 50)), "thumbnail": th["estimated_downlink_bytes"] if th else None}
        eye_costs.append(e)
    return ib.cost_table_v3(eye_costs)


# ====================================================================== analysis
def analyse(cfg: dict, out: Path) -> dict:
    VP = cfg["validation2_pipeline"]
    obs = [json.loads(x) for x in (out / "observations.jsonl").read_text().splitlines()]
    assert not any(TEST[0] <= o["sol"] <= TEST[1] for o in obs)
    E = np.load(out / "embeddings.npy")
    acqs = group_acquisitions(json.loads(MANIFEST.read_text())["products"])
    assert [a["acq_id"] for a in acqs] == [o["id"] for o in obs]
    n = len(obs)

    @lru_cache(maxsize=48)
    def native(i):
        return load_primary(acqs[i])
    c3 = costs_v3(acqs, obs, native)
    total = sum(c["FULL"] or 0 for c in c3)
    st_idx = [i for i in range(n) if acqs[i]["stereo"]]
    R: dict = {"label": "VALIDATION2", "interval": json.loads(SPLIT.read_text())["sols"], "config_hash": cfg["config_hash"]}

    # --- Scheduler V3 (primary orders only)
    orders = PP.primary_orders(obs, VP["seeds"]["random_order"])
    keys = ["acquisitions_represented", "scene_clusters_represented", "rover_positions_represented", "stereo_pair_present", "stereo_pair_usable"]
    comp = {f"{name}|{f}": ib.coverage(obs, c3, PP.allocate_primary(c3, order, f * total), True) for name, order in orders.items() for f in VP["report_budgets"]}
    mono, bad = {}, 0
    for name, order in orders.items():
        seq = []
        for f in np.geomspace(0.0001, 0.30, 80):
            tiers = PP.allocate_primary(c3, order, f * total)
            cv = ib.coverage(obs, c3, tiers, True)
            seq.append([cv[k] for k in keys])
            bad += cv["stereo_pair_usable"] > sum(1 for i in st_idx if ib.RANK[tiers[i]] >= ib.RANK["COMPRESSED"] and c3[i]["COMPRESSED"] is not None)
        mono[name] = {k: sum(1 for a, b in zip(seq, seq[1:]) if b[j] < a[j]) for j, k in enumerate(keys)}
    viol = sum(sum(v.values()) for v in mono.values())
    R["scheduler_v3"] = {"orders": list(orders), "comparison": comp, "monotonicity_violations": mono, "total_violations": viol,
                         "single_eye_usable_violations": bad}

    # --- traverse + marginal value
    stereo = [a["stereo"] for a in acqs]
    rows, agg = traverse_eval(obs, E, c3, stereo, VP["fractions"], VP["coverage_radius_m"])
    R["traverse"] = {"summary": agg, "rows": [{k: v for k, v in r.items() if k != "gaps_m"} for r in rows],
                     "sequences": len({r["sequence"] for r in rows})}
    R["marginal_embedding_value"] = {str(f): marginal(rows, f, VP["seeds"]["bootstrap"]) for f in VP["fractions"]}

    # --- embeddings: relationships + visual-change sensitivity (pHash only as research comparison)
    H = [int(o["image_features"]["phash"], 16) for o in obs]
    vm = json.loads((ROOT / "config" / "phase3_vision_model.json").read_text())
    emb = Embedder(vm["chosen"])
    sp = []
    for i in st_idx:
        L_ = [p for p in acqs[i]["primaries"] if p["eye"] == "L"][0]
        R_ = [p for p in acqs[i]["primaries"] if p["eye"] == "R"][0]
        sp.append(cosd(emb.embed(to_work(read(L_)))[0], emb.embed(to_work(read(R_)))[0]))
    seqs = defaultdict(list)
    for i in sorted(range(n), key=lambda i: ts(obs[i]["utc"])):
        seqs[(obs[i]["sol"], obs[i]["sequence_id"])].append(i)
    consec = [cosd(E[a], E[b]) for v in seqs.values() for a, b in zip(v, v[1:])]
    rr = random.Random(VP["seeds"]["embedding_random_pairs"])
    randp = []
    while len(randp) < 2000:
        a, b = rr.randrange(n), rr.randrange(n)
        if obs[a]["sol"] != obs[b]["sol"]:
            randp.append(cosd(E[a], E[b]))
    tau_c, tau_h = 0.028908073902130127, 26
    tag = VP["seeds"]["synthetic_tag"]
    sens = defaultdict(lambda: defaultdict(lambda: {"e": [], "h": []}))
    syn_viol = 0
    for fam in ("LOCALIZED_STRUCTURE", "TEXTURE_CHANGE"):
        src = random.Random(v1gen.seed_for(v2gen.GENERATOR, tag, fam)).sample(range(n), len(v1gen.LEVELS) * 30)
        for li, lv in enumerate(v1gen.LEVELS):
            for k in range(30):
                i = src[li * 30 + k]
                sid = f"SYN-P34V2-{fam}-{lv}-{k:03d}"
                y, p, box = v2gen.perturb(native(i), fam, lv, v1gen.seed_for(v2gen.GENERATOR, tag, sid))
                syn_viol += len(v2gen.check_contract(fam, native(i), y, p, box))
                y = np.clip(np.rint(y), 0, 4095)
                sens[fam][lv]["e"].append(cosd(E[i], emb.embed(to_work(y))[0]) > tau_c)
                sens[fam][lv]["h"].append(hamming(H[i], phash(y)) > tau_h)
    cs = {f: {lv: {"embedding": float(np.mean(v["e"])), "phash": float(np.mean(v["h"]))} for lv, v in d.items()} for f, d in sens.items()}
    s50, c50, r50 = pctl(sp, 50), pctl(consec, 50), pctl(randp, 50)
    margin = float(np.mean([cs[f]["OBVIOUS"]["embedding"] - cs[f]["OBVIOUS"]["phash"] for f in cs]))
    R["embeddings"] = {"stereo_p50": s50, "consecutive_p50": c50, "random_p50": r50, "ordering_holds": bool(s50 < c50 < r50),
                       "visual_change_sensitivity": cs, "obvious_margin_over_phash": margin, "synthetic_contract_violations": syn_viol,
                       "distinct_signal": bool(s50 < c50 < r50 and margin >= 0.30)}

    # --- QUALITY_V2 descriptive only
    TH = json.loads((ROOT / "config" / "phase3_3_validation_config.json").read_text())["quality_v2"]["thresholds"]
    flags = [PP.quality_flag(q2.classify(q2.features(native(i), acqs[i]["primary"].get("error_pixels")), obs[i]["primary_tier"], TH)) for i in range(n)]
    el = [acqs[i]["elevation_deg"] for i in range(n)]
    sus = [f["flag"] == PP.QUALITY_SUSPECT for f in flags]
    R["quality_v2_descriptive"] = {"role": "DIAGNOSTIC ONLY — QUALITY_SUSPECT flags, not used in ranking; not tuned",
                                   "quality_suspect_rate": float(np.mean(sus)), "n": n,
                                   "rate_elevation_le_0": float(np.mean([s for s, e in zip(sus, el) if e is not None and e <= 0])),
                                   "rate_elevation_gt_0": float(np.mean([s for s, e in zip(sus, el) if e is not None and e > 0])) if any(e is not None and e > 0 for e in el) else None,
                                   "reasons": dict(Counter(r for f in flags for r in f["reasons"]))}

    # --- pre-registered claim + decision rule
    tr = [o for o in obs if o["sequence_id"].startswith("trav")]
    seq_n = Counter((o["sol"], o["sequence_id"]) for o in tr)
    trav_frames = [o for o in tr if seq_n[(o["sol"], o["sequence_id"])] >= 10]
    pos_share = (sum(1 for o in trav_frames if "landing_x" in o["location_context"]) / len(trav_frames)) if trav_frames else 0.0
    pe = agg.get("0.25|POSITION_PLUS_EMBEDDING_CHANGE")
    if R["traverse"]["sequences"] < 3 or pos_share < 0.90 or pe is None:
        claim = {"verdict": "INCONCLUSIVE", "sequences": R["traverse"]["sequences"], "position_share": pos_share}
    else:
        c = {"C1_bytes": pe["bytes_fraction"] <= 0.35, "C2_coverage": pe["coverage_5m"] >= 0.90, "C3_visual": pe["visual_change_coverage"] >= 0.90,
             "C4_max_distance_to_kept": pe["max_distance_to_kept_m_worst"] <= 10.0, "C5_stereo": pe["stereo_broken"] == 0}
        claim = {"criteria": c, "metrics": pe, "position_share": pos_share, "verdict": "PASS" if all(c.values()) else "FAIL"}
    mv = R["marginal_embedding_value"]["0.25"]
    pos = agg.get("0.25|METADATA_POSITION", {})
    meaningful = mv["VISUAL_CHANGE_GAIN"] is not None and mv["VISUAL_CHANGE_GAIN"] >= 0.020 and mv["VISUAL_CHANGE_GAIN_95ci"][0] > 0
    material_cost = (mv["SPATIAL_COST"] is not None and mv["SPATIAL_COST"] < -0.020) or \
                    (pe is not None and pe["max_distance_to_kept_m_worst"] > 10.0 and pos.get("max_distance_to_kept_m_worst", 99) <= 10.0)
    equivalent = mv["VISUAL_CHANGE_GAIN"] is not None and abs(mv["VISUAL_CHANGE_GAIN"]) < 0.020 and mv["SPATIAL_COST"] >= -0.020 \
        and pe is not None and pe["max_distance_to_kept_m_worst"] <= 10.0
    all_broken = sum(v["stereo_broken"] for v in agg.values())
    d = {"scheduler_v3_ok": R["scheduler_v3"]["total_violations"] == 0 and bad == 0,
         "zero_broken_stereo": all_broken == 0, "primary_claim_pass": claim["verdict"] == "PASS",
         "embedding_distinct": R["embeddings"]["distinct_signal"],
         "embedding_value": (meaningful and not material_cost) or equivalent,
         "meaningful_gain": meaningful, "material_spatial_cost": material_cost, "equivalent_no_regression": equivalent}
    d["PROCEED_TO_FINAL_TEST"] = all(d[k] for k in ("scheduler_v3_ok", "zero_broken_stereo", "primary_claim_pass", "embedding_distinct", "embedding_value"))
    R["primary_claim"] = claim
    R["decision"] = d

    # --- three-way table (development and validation1 recomputed with the same code — descriptive, not evidence)
    three = {}
    for label, run in (("DEVELOPMENT 412–430", DEV_RUN), ("VALIDATION1 779–820", VAL1_RUN)):
        o2 = [json.loads(x) for x in (run / "observations.jsonl").read_text().splitlines()]
        E2 = np.load(run / "embeddings.npy")
        per_eye = json.loads((run / "byte_accounting_per_eye.json").read_text())
        full, thumb, st = defaultdict(float), defaultdict(float), {}
        for r in per_eye:
            full[r["acq_id"]] += r["full_bytes_NASA_LABEL_ESTIMATE"] or 0
            thumb[r["acq_id"]] += r["thumbnail_bytes_NASA_LABEL_ESTIMATE"] or 0
            st[r["acq_id"]] = r["stereo"]
        c2 = [{"FULL": full[o["id"]], "THUMBNAIL": thumb[o["id"]]} for o in o2]
        rows2, agg2 = traverse_eval(o2, E2, c2, [st[o["id"]] for o in o2], VP["fractions"], VP["coverage_radius_m"])
        prev = json.loads((run / "results.json").read_text())
        three[label] = {"scheduler_v3_violations": prev["scheduler_v3"]["total_violations"], "traverse": agg2,
                        "marginal_0.25": marginal(rows2, 0.25, VP["seeds"]["bootstrap"]),
                        "embedding_p50": [prev["embeddings"]["stereo_left_right"]["cos_p10_p50_p90"][1], prev["embeddings"]["consecutive_frames"]["cos_p10_p50_p90"][1],
                                          prev["embeddings"]["random_pairs"]["cos_p10_p50_p90"][1]]}
    three["VALIDATION2 " + "–".join(map(str, R["interval"]))] = {"scheduler_v3_violations": R["scheduler_v3"]["total_violations"], "traverse": agg,
                                                                 "marginal_0.25": mv, "embedding_p50": [s50, c50, r50]}
    R["three_way"] = three
    R["git"] = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    (out / "results.json").write_text(json.dumps(R, indent=1, default=str))
    return R


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["dataset", "analysis"], required=True)
    ap.add_argument("--run")
    args = ap.parse_args()
    cfg = load_cfg()
    lo, hi = json.loads(SPLIT.read_text())["sols"]
    if lo <= TEST[1] and hi >= TEST[0]:
        raise SystemExit("STOP: validation2 overlaps the held-out test interval")
    if args.run:
        out = Path(args.run)
    else:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-phase3.4-val2-" + uuid.uuid4().hex[:4]
        out = ROOT / "artifacts" / "phase3_4" / run_id
        out.mkdir(parents=True)
        (out / "run_manifest.json").write_text(json.dumps({"run_id": run_id, "interval": [lo, hi], "config_hash": cfg["config_hash"],
                                                           "pre_registered": {k: cfg[k] for k in ("primary_claim", "marginal_embedding_value", "decision_rule_before_final_test")},
                                                           "seeds": cfg["validation2_pipeline"]["seeds"], "written_before_metrics": True,
                                                           "created_at": datetime.now(timezone.utc).isoformat()}, indent=1, ensure_ascii=False))
    if args.stage == "dataset":
        rep = build(cfg, out)
        print(json.dumps({k: v for k, v in rep.items() if k not in ("grouping", "active_sols")}, indent=1, default=str))
    else:
        R = analyse(cfg, out)
        print(json.dumps({"primary_claim": R["primary_claim"].get("verdict"), "decision": R["decision"]}, indent=1, default=str))
    print(f"→ {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
