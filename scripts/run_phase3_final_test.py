#!/usr/bin/env python3
"""Phase 3 FINAL HELD-OUT TEST (Navcam sols 950–979) — run exactly once, no post-test changes.

    uv run python scripts/fetch_navcam.py --split test --allow-test --workers 2      # only after the config commit
    uv run python scripts/run_phase3_final_test.py --stage dataset
    uv run python scripts/run_phase3_final_test.py --stage analysis --run artifacts/phase3_final/<run>

Frozen by config/phase3_final_test_config.json (committed and tagged before the first test image is downloaded); the
runner refuses to start if that config's hash or any listed source hash differs.

PRIMARY (binary): Scheduler V3 + POSITION at 1/4 retention. SECONDARY (does not affect PASS/FAIL): POSITION +
EMBEDDING_CHANGE vs POSITION. Strategies: SEND_ALL, EVERY_NTH, UNIFORM_DISTANCE, POSITION, POSITION + EMBEDDING_CHANGE.
No pHash, quality, telemetry or Jev signal is computed for ranking; none is computed at all except pHash scene grouping
fields required by the observation schema.
"""

from __future__ import annotations

import argparse
import hashlib
import json
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
from deepsift.imaging import similarity as sim  # noqa: E402
from deepsift.imaging.acquisitions import group_acquisitions, grouping_stats  # noqa: E402
from deepsift.imaging.embeddings import Embedder  # noqa: E402
from deepsift.imaging.features import jpeg_bytes, load_primary, phash, quality, to_work  # noqa: E402
from deepsift.imaging.navcam import sha256_file  # noqa: E402
from deepsift.imaging.pds3 import parse_label, read_image  # noqa: E402
from phase3_4_freeze_config import config_hash  # noqa: E402

CFG_PATH = ROOT / "config" / "phase3_final_test_config.json"
MANIFEST = ROOT / "data" / "manifests" / "navcam_test.json"
TEST = (950, 979)
PERIODS = {"DEVELOPMENT 412–430": (ROOT / "artifacts/phase3_3/20260926T134654-phase3.3-dev-32ec", ROOT / "data/manifests/navcam_development.json"),
           "VALIDATION1 779–820": (ROOT / "artifacts/phase3_3/20260926T142033-phase3.3-val-2a31", ROOT / "data/manifests/navcam_validation.json"),
           "VALIDATION2 1100–1129": (ROOT / "artifacts/phase3_4/20260926T165307-phase3.4-val2-1248", ROOT / "data/manifests/navcam_validation2.json")}
STRATEGIES = ["EVERY_NTH_FRAME", "UNIFORM_DISTANCE", "METADATA_POSITION", "POSITION_PLUS_EMBEDDING_CHANGE"]


def load_cfg() -> dict:
    cfg = json.loads(CFG_PATH.read_text())
    if config_hash(cfg) != cfg["config_hash"]:
        raise SystemExit("STOP: final-test config hash mismatch")
    bad = [p for p, h in cfg["source_sha256"].items() if hashlib.sha256((ROOT / p).read_bytes()).hexdigest() != h]
    if bad:
        raise SystemExit(f"STOP: frozen sources changed: {bad}")
    return cfg


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "")).replace(tzinfo=timezone.utc).timestamp()


def pctl(xs, q):
    xs = [x for x in xs if x is not None]
    return float(np.percentile(xs, q)) if xs else None


def read(p):
    return read_image(ROOT / p["path_img"], parse_label((ROOT / p["path_lbl"]).read_text(encoding="latin-1")))


# ====================================================================== dataset (same M3/M4/M8/M9 steps as Phase 3.4)
def build(cfg: dict, out: Path) -> dict:
    from deepsift.multimodal import location
    from deepsift.multimodal.observation import DownlinkOptions, MultimodalObservation

    man = json.loads(MANIFEST.read_text())
    products = man["products"]
    log = (ROOT / "data" / "fetch_navcam_test.log").read_text() if (ROOT / "data" / "fetch_navcam_test.log").exists() else ""
    listed = next((int(w) for line in log.splitlines() if "products listed" in line for w in line.split() if w.isdigit() and int(w) > 100), None)
    problems = Counter()
    for p in products:
        problems["sol_outside_test"] += not (TEST[0] <= p["sol"] <= TEST[1])
        img, lbl = ROOT / p["path_img"], ROOT / p["path_lbl"]
        if not img.exists() or not lbl.exists():
            problems["missing_file"] += 1
            continue
        problems["sha256_img_mismatch"] += sha256_file(img) != p["sha256_img"]
        problems["sha256_lbl_mismatch"] += sha256_file(lbl) != p["sha256_lbl"]
        problems["empty_img"] += img.stat().st_size == 0
        problems["missing_tier_metadata"] += p.get("tier") is None or (p["tier"] != "T" and p.get("estimated_downlink_bytes") is None)
    problems = {k: v for k, v in problems.items() if v}
    acqs = group_acquisitions(products)
    stereo_mismatch = sum(1 for a in acqs if a["stereo"] and len({p["eye"] for p in a["primaries"] if p["tier"] == a["primary_tier"]}) != 2)
    ver = {"listed": listed, "manifest_products": len(products), "complete": listed == len(products), "problems": problems,
           "acquisition_grouping": grouping_stats(products, acqs), "stereo_pairs_without_both_eyes_same_tier": stereo_mismatch,
           "tier_counts": dict(Counter(p["tier"] for p in products)), "compression": dict(Counter(p["compression"] for p in products))}
    ver["verdict"] = "PASS" if ver["complete"] and not problems and stereo_mismatch == 0 else "FAIL"
    (out / "download_verification.json").write_text(json.dumps(ver, indent=1, default=str))
    vm = json.loads((ROOT / "config" / "phase3_vision_model.json").read_text())
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
            telemetry_context={"status": "NOT_JOINED", "role": "not used in the final test", "telemetry_score": None},
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
    trav = {k for k, v in seqs.items() if k[1].startswith("trav") and v >= 10}
    tf = [o for o in obs if (o["sol"], o["sequence_id"]) in trav]
    rep = {"label": "FINAL TEST DATASET REPORT (before any performance analysis)", "sols": list(TEST), "download_verification": ver,
           "active_sols": sorted({a["sol"] for a in acqs}), "n_active_sols": len({a["sol"] for a in acqs}),
           "acquisitions": len(acqs), "stereo": sum(a["stereo"] for a in acqs), "mono": sum(not a["stereo"] for a in acqs),
           "products": len(products), "download_bytes_archive": man["archive_bytes"],
           "estimated_downlink_full_bytes": sum(o["downlink"]["full_bytes"] or 0 for o in obs),
           "sequences": len(seqs), "traverse_sequences_ge_10_frames": len(trav), "traverse_frames": len(tf),
           "traverse_frames_with_places_position": sum(1 for o in tf if "landing_x" in o["location_context"]),
           "places_join": dict(Counter(loc["match"].split("(")[0] for loc in locs))}
    (out / "dataset_report.json").write_text(json.dumps(rep, indent=1, default=str))
    return rep


# ====================================================================== traverse helpers (identical to Phase 3.4 runner)
def traverse_eval(obs, E, c3, stereo, fractions, radius):
    seqs = defaultdict(list)
    for i in sorted(range(len(obs)), key=lambda i: ts(obs[i]["utc"])):
        seqs[(obs[i]["sol"], obs[i]["sequence_id"])].append(i)
    seqs = {k: v for k, v in seqs.items() if k[1].startswith("trav") and len(v) >= 10}
    rows = []
    for key, fr in seqs.items():
        fr = [i for i in fr if "landing_x" in obs[i]["location_context"]]
        if len(fr) < 10:
            continue
        xy = np.array([[obs[i]["location_context"]["landing_x"], obs[i]["location_context"]["landing_y"]] for i in fr])
        em = E[fr]
        full_all = sum(c3[i]["FULL"] or 0 for i in fr)
        plan = [(1.0, "SEND_ALL", list(range(len(fr))))] + [(f, m, T.select(m, xy, em, f)) for f in fractions for m in STRATEGIES]
        for f, m, s in plan:
            kept = {fr[j] for j in s}
            byt = sum(c3[i]["FULL"] or 0 for i in kept) + sum(c3[i]["THUMBNAIL"] or 0 for i in fr if i not in kept)
            mt = T.metrics(xy, em, s, radius)
            rows.append({"sequence": f"{key[0]}:{key[1]}", "fraction": f, "method": m, "bytes": byt, "bytes_send_all": full_all,
                         "unique_positions": len({tuple(obs[i]["source_metadata"]["pose"]) for i in kept}) / len({tuple(obs[i]["source_metadata"]["pose"]) for i in fr}),
                         "stereo_broken": sum(1 for i in kept if stereo[i] and c3[i]["FULL"] is None),
                         "stereo_kept_full": sum(1 for i in kept if stereo[i]), **mt})
    agg = {}
    for (f, m) in sorted({(r["fraction"], r["method"]) for r in rows}, key=lambda x: (-x[0], x[1])):
        rs = [r for r in rows if r["fraction"] == f and r["method"] == m]
        pooled = [g for r in rs for g in r["gaps_m"]]
        agg[f"{f}|{m}"] = {"sequences": len(rs), "bytes_fraction": float(sum(r["bytes"] for r in rs) / sum(r["bytes_send_all"] for r in rs)),
                           "coverage_5m": float(np.mean([r["position_coverage"] for r in rs])),
                           "unique_positions": float(np.mean([r["unique_positions"] for r in rs])),
                           "mean_gap_m": float(np.mean([r["mean_gap_m"] for r in rs])), "p95_gap_m": pctl(pooled, 95),
                           "max_gap_m_worst": max(r["max_gap_m"] for r in rs),
                           "max_distance_to_kept_m_worst": max(r["max_distance_to_kept_m"] for r in rs),
                           "visual_change_coverage": float(np.mean([r["visual_change_coverage"] for r in rs])),
                           "stereo_broken": int(sum(r["stereo_broken"] for r in rs)), "stereo_kept_full": int(sum(r["stereo_kept_full"] for r in rs))}
    return rows, agg


def marginal(rows, frac, seed, reps):
    by = {}
    for r in rows:
        if r["fraction"] == frac and r["method"] in ("METADATA_POSITION", "POSITION_PLUS_EMBEDDING_CHANGE"):
            by.setdefault(r["sequence"], {})[r["method"]] = r
    seqs = sorted(by)
    dv = np.array([by[s]["POSITION_PLUS_EMBEDDING_CHANGE"]["visual_change_coverage"] - by[s]["METADATA_POSITION"]["visual_change_coverage"] for s in seqs])
    dc = np.array([by[s]["POSITION_PLUS_EMBEDDING_CHANGE"]["position_coverage"] - by[s]["METADATA_POSITION"]["position_coverage"] for s in seqs])
    dd = max(by[s]["POSITION_PLUS_EMBEDDING_CHANGE"]["max_distance_to_kept_m"] for s in seqs) - max(by[s]["METADATA_POSITION"]["max_distance_to_kept_m"] for s in seqs) if seqs else None
    rng = np.random.default_rng(seed)
    bv = [dv[rng.integers(0, len(dv), len(dv))].mean() for _ in range(reps)] if len(dv) else [0.0]
    bc = [dc[rng.integers(0, len(dc), len(dc))].mean() for _ in range(reps)] if len(dc) else [0.0]
    return {"sequences": len(seqs), "visual_change_gain": float(dv.mean()) if len(dv) else None,
            "visual_change_gain_95ci": [float(np.percentile(bv, 2.5)), float(np.percentile(bv, 97.5))],
            "coverage_difference": float(dc.mean()) if len(dc) else None, "coverage_difference_95ci": [float(np.percentile(bc, 2.5)), float(np.percentile(bc, 97.5))],
            "largest_distance_difference_m": dd}


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


def label_pair_costs(manifest: Path) -> tuple[list[dict], list[bool], list[str]]:
    """FULL_STEREO_PAIR / THUMBNAIL_PAIR costs straight from product-label estimates (no image read), same sums as cost_table_v3."""
    acqs = group_acquisitions(json.loads(manifest.read_text())["products"])
    out = []
    for a in acqs:
        eyes = ["L", "R"] if a["stereo"] else [a["primary"]["eye"]]
        full = [next((p["estimated_downlink_bytes"] for p in a["primaries"] if p["eye"] == e and p["tier"] == a["primary_tier"]), None) for e in eyes]
        th = [next((x["estimated_downlink_bytes"] for x in a["thumbnails"] if x["eye"] == e), None) for e in eyes]
        out.append({"FULL": sum(full) if all(v is not None for v in full) else None, "THUMBNAIL": sum(th) if all(v is not None for v in th) else None})
    return out, [a["stereo"] for a in acqs], [a["acq_id"] for a in acqs]


def previous_periods(ev) -> dict:
    four = {}
    for label, (run, manifest) in PERIODS.items():
        o2 = [json.loads(x) for x in (run / "observations.jsonl").read_text().splitlines()]
        E2 = np.load(run / "embeddings.npy")
        c2, st, ids = label_pair_costs(manifest)
        assert ids == [o["id"] for o in o2]
        rows2, agg2 = traverse_eval(o2, E2, c2, st, ev["fractions"], ev["coverage_radius_m"])
        four[label] = {"POSITION": agg2["0.25|METADATA_POSITION"], "POSITION_PLUS_EMBEDDING_CHANGE": agg2["0.25|POSITION_PLUS_EMBEDDING_CHANGE"],
                       "embedding_gain": marginal(rows2, 0.25, ev["seeds"]["bootstrap"], ev["bootstrap_resamples"])}
    return four


# ====================================================================== analysis
def analyse(cfg: dict, out: Path) -> dict:
    ev = cfg["evaluation"]
    obs = [json.loads(x) for x in (out / "observations.jsonl").read_text().splitlines()]
    E = np.load(out / "embeddings.npy")
    acqs = group_acquisitions(json.loads(MANIFEST.read_text())["products"])
    assert [a["acq_id"] for a in acqs] == [o["id"] for o in obs]
    n = len(obs)

    @lru_cache(maxsize=48)
    def native(i):
        return load_primary(acqs[i])
    c3 = costs_v3(acqs, obs, native)
    (out / "byte_accounting_per_eye.json").write_text(json.dumps(
        [{"acq_id": a["acq_id"], "stereo": a["stereo"], "FULL_pair": c3[i]["FULL"], "THUMBNAIL_pair": c3[i]["THUMBNAIL"],
          "COMPRESSED_pair_SIMULATED": c3[i]["COMPRESSED"]} for i, a in enumerate(acqs)], indent=1))
    total = sum(c["FULL"] or 0 for c in c3)
    st_idx = [i for i in range(n) if acqs[i]["stereo"]]
    R: dict = {"label": "PHASE 3 FINAL HELD-OUT TEST", "sols": list(TEST), "config_hash": cfg["config_hash"]}

    orders = PP.primary_orders(obs, ev["seeds"]["random_order"])
    keys = ["acquisitions_represented", "scene_clusters_represented", "rover_positions_represented", "stereo_pair_present", "stereo_pair_usable"]
    mono, single_eye = {}, 0
    for name, order in orders.items():
        seq = []
        for f in np.geomspace(0.0001, 0.30, 80):
            tiers = PP.allocate_primary(c3, order, f * total)
            cv = ib.coverage(obs, c3, tiers, True)
            seq.append([cv[k] for k in keys])
            single_eye += cv["stereo_pair_usable"] > sum(1 for i in st_idx if ib.RANK[tiers[i]] >= ib.RANK["COMPRESSED"] and c3[i]["COMPRESSED"] is not None)
        mono[name] = {k: sum(1 for a, b in zip(seq, seq[1:]) if b[j] < a[j]) for j, k in enumerate(keys)}
    viol = sum(sum(v.values()) for v in mono.values())
    R["scheduler_v3"] = {"monotonicity_violations": mono, "total_violations": viol, "single_eye_usable_violations": single_eye,
                         "comparison": {f"{nm}|{f}": ib.coverage(obs, c3, PP.allocate_primary(c3, o, f * total), True) for nm, o in orders.items() for f in ev["report_budgets"]}}

    rows, agg = traverse_eval(obs, E, c3, [a["stereo"] for a in acqs], ev["fractions"], ev["coverage_radius_m"])
    R["traverse"] = {"summary": agg, "rows": [{k: v for k, v in r.items() if k != "gaps_m"} for r in rows], "sequences": len({r["sequence"] for r in rows})}

    # ---------------- PRIMARY (binary)
    seq_n = Counter((o["sol"], o["sequence_id"]) for o in obs if o["sequence_id"].startswith("trav"))
    tf = [o for o in obs if o["sequence_id"].startswith("trav") and seq_n[(o["sol"], o["sequence_id"])] >= 10]
    pos_share = sum(1 for o in tf if "landing_x" in o["location_context"]) / len(tf) if tf else 0.0
    p = agg.get("0.25|METADATA_POSITION")
    enough = R["traverse"]["sequences"] >= 3 and pos_share >= 0.90 and p is not None
    crit = {"P0_sufficient_data": enough,
            "P1_bytes": bool(p and p["bytes_fraction"] <= 0.35), "P2_coverage_5m": bool(p and p["coverage_5m"] >= 0.90),
            "P3_largest_distance_to_kept": bool(p and p["max_distance_to_kept_m_worst"] <= 10.0),
            "P4_zero_broken_stereo": bool(p and p["stereo_broken"] == 0), "P5_scheduler_v3_monotonic": viol == 0 and single_eye == 0}
    R["primary"] = {"claim": "Scheduler V3 + POSITION at 1/4 retention", "criteria": crit, "metrics": p, "positioned_share": pos_share,
                    "RESULT": "PASS" if all(crit.values()) else "FAIL"}

    # ---------------- SECONDARY (does not affect the primary result)
    sec = {str(f): marginal(rows, f, ev["seeds"]["bootstrap"], ev["bootstrap_resamples"]) for f in ev["fractions"]}
    m = sec["0.25"]
    lo, hi = m["visual_change_gain_95ci"]
    if m["visual_change_gain"] is None:
        concl = "NO MEASURABLE ADDED VALUE"
    elif m["coverage_difference"] < -0.01 or (m["visual_change_gain"] <= -0.020 and hi < 0):
        concl = "HARMFUL"
    elif m["visual_change_gain"] >= 0.020 and lo > 0:
        concl = "MEANINGFUL ADDED VALUE"
    else:
        concl = "NO MEASURABLE ADDED VALUE"
    R["secondary_embedding"] = {"by_fraction": sec, "position_visual_1_4": agg.get("0.25|METADATA_POSITION", {}).get("visual_change_coverage"),
                                "position_plus_embedding_visual_1_4": agg.get("0.25|POSITION_PLUS_EMBEDDING_CHANGE", {}).get("visual_change_coverage"),
                                "CONCLUSION": concl}

    # ---------------- four-period table (earlier periods recomputed with the same code; not pooled)
    four = previous_periods(ev)
    four["TEST 950–979"] = {"POSITION": agg.get("0.25|METADATA_POSITION"), "POSITION_PLUS_EMBEDDING_CHANGE": agg.get("0.25|POSITION_PLUS_EMBEDDING_CHANGE"),
                            "embedding_gain": m}
    R["four_period"] = four
    R["git"] = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    (out / "results.json").write_text(json.dumps(R, indent=1, default=str))
    return R


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["dataset", "analysis"], required=True)
    ap.add_argument("--run")
    args = ap.parse_args()
    cfg = load_cfg()
    if args.run:
        out = Path(args.run)
    else:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-phase3-final-test-" + uuid.uuid4().hex[:4]
        out = ROOT / "artifacts" / "phase3_final" / run_id
        out.mkdir(parents=True)
        (out / "run_manifest.json").write_text(json.dumps({"run_id": run_id, "config_hash": cfg["config_hash"],
                                                           "primary": cfg["primary"], "secondary": cfg["secondary"], "seeds": cfg["evaluation"]["seeds"],
                                                           "written_before_metrics": True, "created_at": datetime.now(timezone.utc).isoformat()},
                                                          indent=1, ensure_ascii=False))
    if args.stage == "dataset":
        rep = build(cfg, out)
        print(json.dumps({k: v for k, v in rep.items() if k != "active_sols"}, indent=1, default=str))
    else:
        R = analyse(cfg, out)
        print(json.dumps({"primary": R["primary"], "secondary": R["secondary_embedding"]["CONCLUSION"]}, indent=1, default=str))
    print(f"→ {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
