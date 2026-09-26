#!/usr/bin/env python3
"""Phase 3.3 — OUT-OF-SAMPLE VALIDATION of the frozen Phase 3.2 findings (Navcam, validation sols 779–820).

    uv run python scripts/run_phase3_3.py --split validation --stage dataset      # dataset report only (step 3)
    uv run python scripts/run_phase3_3.py --split validation --stage analysis --run <run_dir>
    uv run python scripts/run_phase3_3.py --split development --stage all         # reproduction check vs Phase 3.2

Everything is read from config/phase3_3_validation_config.json (frozen before download). The script refuses to run if
the config hash or any frozen source-file hash differs, and refuses the test split outright. No threshold, weight,
model or rule is fitted on validation data: QUALITY_V2 thresholds, the pHash threshold, the 120 s / same-stop
constraints, the embedding change threshold and every traverse method come from the frozen config. No fusion, no VLM,
no Jev. Telemetry is attached as descriptive metadata only and is not a ranking input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
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

from deepsift.evaluation import image_benchmark as ib  # noqa: E402
from deepsift.imaging import quality_v2 as q2  # noqa: E402
from deepsift.imaging import similarity as sim  # noqa: E402
from deepsift.imaging import synthetic as v1gen  # noqa: E402
from deepsift.imaging import synthetic_v2 as v2gen  # noqa: E402
from deepsift.imaging.acquisitions import group_acquisitions, grouping_stats  # noqa: E402
from deepsift.imaging.embeddings import Embedder  # noqa: E402
from deepsift.imaging.features import hamming, jpeg_bytes, load_primary, phash, quality, to_work  # noqa: E402
from deepsift.imaging.pds3 import parse_label, read_image  # noqa: E402

CFG_PATH = ROOT / "config" / "phase3_3_validation_config.json"
sys.path.insert(0, str(ROOT / "scripts"))
from phase3_3_freeze_config import config_hash  # noqa: E402

LABEL = {"development": "DEVELOPMENT", "validation": "VALIDATION"}

# Every stochastic component of this runner, frozen explicitly (Phase 3.3 reproducibility fix, made BEFORE any validation
# analysis; not a retuning step — no threshold, weight, ranking, scheduler, quality, pHash or embedding logic changes).
# No bootstrap / CI resampling is used anywhere in this runner. ONNX inference was verified deterministic at model selection.
SEEDS = {
    "random_baseline_order": 0,            # image_benchmark.strategy_orders(obs, seed) → RANDOM
    "synthetic_seed_tag": {"development": "DEVREPRO", "validation": "VALIDATION"},
    "synthetic_source_sampling": "random.Random(seed_for('SYNTH_V2', tag, family)) — one stream per family",
    "near_duplicate_sampling": "random.Random(seed_for('SYNTH_V2', tag, 'NEAR_DUPLICATE'))",
    "synthetic_control": "numpy default_rng(seed_for('SYNTH_V2', tag, synthetic_id)) inside synthetic_v2.perturb / near_duplicate",
    "embedding_random_pairs": 11,          # random cross-sol pairs for the random-pair distance
    "phash_false_merge_examples": 3,       # sample of failure-analysis examples only (does not affect any metric)
    "bootstrap": None,
}


def seed_manifest(split: str) -> dict:
    tag = SEEDS["synthetic_seed_tag"][split]
    return {**SEEDS, "resolved": {"synthetic_source_sampling": {f: v1gen.seed_for(v2gen.GENERATOR, tag, f) for f in v1gen.FAMILIES},
                                  "near_duplicate_sampling": v1gen.seed_for(v2gen.GENERATOR, tag, "NEAR_DUPLICATE")}}


def load_cfg() -> dict:
    cfg = json.loads(CFG_PATH.read_text())
    if config_hash(cfg) != cfg["config_hash"]:
        raise SystemExit("STOP: config hash mismatch — the frozen validation configuration was modified")
    bad = [p for p, h in cfg["source_sha256"].items() if hashlib.sha256((ROOT / p).read_bytes()).hexdigest() != h]
    if bad:
        raise SystemExit(f"STOP: frozen source files changed since the freeze: {bad}")
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


def half(acq_id: str) -> str:
    return "TUNE" if int(hashlib.sha256(acq_id.encode()).hexdigest()[:2], 16) % 2 == 0 else "EVAL"


# ====================================================================== stage 1: observations (frozen baseline M3–M10)
def build_observations(split: str, cfg: dict, out: Path) -> dict:
    """Same pipeline as scripts/run_phase3_baseline.py (M3–M10), parameterised by split. Telemetry is descriptive only."""
    from deepsift.multimodal import location
    from deepsift.multimodal.observation import DownlinkOptions, MultimodalObservation
    from deepsift.multimodal.temporal_join import TELEMETRY_CONTEXT_S, TelemetryContext

    spec = json.loads((ROOT / "data" / "splits" / "phase3_splits.json").read_text())
    lo, hi = spec[split]["sols"]
    man = json.loads((ROOT / "data" / "manifests" / f"navcam_{split}.json").read_text())
    vm = json.loads((ROOT / "config" / "phase3_vision_model.json").read_text())
    products = man["products"]
    acqs = group_acquisitions(products)
    gstats = grouping_stats(products, acqs)
    emb = Embedder(vm["chosen"])
    hashes, quals, comp, E = [], [], [], []
    for a in acqs:
        img = load_primary(a)
        quals.append(quality(img, a["primary"].get("error_pixels")))
        hashes.append(phash(img))
        comp.append(jpeg_bytes(img, cfg["scheduler_v3"]["jpeg_quality"]))
        E.append(emb.embed(to_work(img))[0])
    E = np.stack(E)
    dl = []
    for a, c in zip(acqs, comp):
        ests = [p["estimated_downlink_bytes"] for p in a["primaries"]]
        full = sum(ests) if all(e is not None for e in ests) else None
        meta_rec = {k: a[k] for k in ("acq_id", "sol", "utc", "sclk", "sequence_id", "site", "drive", "pose", "eyes", "primary_tier", "azimuth_deg", "elevation_deg")}
        dl.append({"full_bytes": full, "compressed_bytes": float(c), "thumbnail_bytes": a["thumbnail"]["estimated_downlink_bytes"] if a["thumbnail"] else None,
                   "metadata_bytes": len(json.dumps(meta_rec, separators=(",", ":"), default=str).encode()),
                   "archive_bytes": int(sum(p["archive_bytes_img"] + p["archive_bytes_lbl"] for p in a["primaries"] + a["thumbnails"])),
                   "full_bytes_status": "ESTIMATED_FROM_LABEL" if full is not None else "UNKNOWN"})
    places_rec = location.fetch()
    P = location.Places()
    locs = [P.locate(a["site"], a["drive"], a["pose"]) for a in acqs]
    tc = TelemetryContext((lo, hi))
    ctxs = [tc.context(a["utc"]) for a in acqs]
    lb = cfg["embedding_change"]["novelty_lookback_sols"]
    order = sorted(range(len(acqs)), key=lambda i: acqs[i]["utc"])
    nov = [1.0] * len(acqs)
    for k, i in enumerate(order):
        prev = [j for j in order[:k] if acqs[j]["sol"] >= acqs[i]["sol"] - lb]
        if prev:
            nov[i] = float(1.0 - np.max(E[prev] @ E[i]))
    g_ph, g_seq, g_scene = sim.phash_groups(acqs, hashes), sim.sequence_groups(acqs), sim.scene_clusters(acqs)
    obs = []
    for i, a in enumerate(acqs):
        o = MultimodalObservation(
            id=a["acq_id"], sol=a["sol"], utc=a["utc"], sclk=a["sclk"], sequence_id=a["sequence_id"], stereo=a["stereo"],
            primary_tier=a["primary_tier"], image_products=a["product_ids"],
            image_features={**{k: v for k, v in quals[i].items() if k != "quality_state"}, "phash": f"{hashes[i]:016x}",
                            "embedding_novelty": nov[i], "embedding_model": vm["chosen"]},
            quality_state=quals[i]["quality_state"], telemetry_context=ctxs[i], location_context=locs[i],
            near_duplicate_group=g_ph[i], sequence_group=g_seq[i], scene_cluster=g_scene[i], downlink=DownlinkOptions(**dl[i]),
            source_metadata={"urls": [p["url_img"] for p in a["primaries"] + a["thumbnails"]],
                             "sha256": [p["sha256_img"] for p in a["primaries"] + a["thumbnails"]], "pose": [a["site"], a["drive"], a["pose"]]})
        obs.append(o.model_dump(mode="json"))
    with (out / "observations.jsonl").open("w") as fh:
        for o in obs:
            fh.write(json.dumps(o) + "\n")
    np.save(out / "embeddings.npy", E)

    seq_types = Counter(o["sequence_id"][:4].upper() for o in obs)
    seqs = Counter((o["sol"], o["sequence_id"]) for o in obs)
    trav = [k for k, v in seqs.items() if k[1].startswith("trav") and v >= 10]
    near = lambda gaps, s: sum(1 for g in gaps if g is not None and g <= s)  # noqa: E731
    rep = {
        "label": f"{LABEL[split]} DATASET REPORT (before any performance analysis)", "split": split, "sols_range": [lo, hi],
        "active_sols": sorted({a["sol"] for a in acqs}), "n_active_sols": len({a["sol"] for a in acqs}),
        "acquisitions": len(acqs), "stereo_acquisitions": sum(a["stereo"] for a in acqs), "mono_acquisitions": sum(not a["stereo"] for a in acqs),
        "products": len(products), "products_by_tier": dict(Counter(p["tier"] for p in products)),
        "primary_tier_by_acquisition": dict(Counter(a["primary_tier"] for a in acqs)),
        "download_bytes_archive": man.get("archive_bytes", sum(p["archive_bytes_img"] + p["archive_bytes_lbl"] for p in products)),
        "estimated_downlink_bytes": {"full_total": sum(d["full_bytes"] or 0 for d in dl), "full_unknown": sum(d["full_bytes"] is None for d in dl),
                                     "thumbnail_total": sum(d["thumbnail_bytes"] or 0 for d in dl), "metadata_total": sum(d["metadata_bytes"] for d in dl)},
        "sequences": len(seqs), "sequence_types_by_acquisition": dict(seq_types), "traverse_sequences_ge_10_frames": len(trav),
        "traverse_frames": sum(seqs[k] for k in trav), "grouping": gstats,
        "places_join": dict(Counter(loc["match"].split("(")[0] for loc in locs)), "places_source_sha256": places_rec.get("sha256"),
        "rems_context": {"median_gap_s": pctl([c["rems_gap_s"] for c in ctxs], 50), "within_30_min": near([c["rems_gap_s"] for c in ctxs], 1800) / len(ctxs)},
        "rad_context": {"median_gap_s": pctl([c["rad_gap_s"] for c in ctxs], 50), "within_30_min": near([c["rad_gap_s"] for c in ctxs], 1800) / len(ctxs)},
        "telemetry_context_events": sum(1 for c in ctxs if c["context_events"]), "telemetry_context_window_s": TELEMETRY_CONTEXT_S,
        "telemetry_role": "DESCRIPTIVE METADATA ONLY — not a ranking input",
        "quality_v1_states": dict(Counter(q["quality_state"] for q in quals)),
    }
    (out / "dataset_report.json").write_text(json.dumps(rep, indent=1, default=str))
    return rep


# ====================================================================== stage 2: frozen analyses
def analyse(split: str, cfg: dict, out: Path) -> dict:
    obs = [json.loads(x) for x in (out / "observations.jsonl").read_text().splitlines()]
    E = np.load(out / "embeddings.npy")
    acqs = group_acquisitions(json.loads((ROOT / "data" / "manifests" / f"navcam_{split}.json").read_text())["products"])
    assert [a["acq_id"] for a in acqs] == [o["id"] for o in obs]
    n = len(obs)
    TH = cfg["quality_v2"]["thresholds"]
    vm = json.loads((ROOT / "config" / "phase3_vision_model.json").read_text())
    emb = Embedder(vm["chosen"])
    H = [int(o["image_features"]["phash"], 16) for o in obs]
    t = [ts(o["utc"]) for o in obs]
    SV3, SYN, TRV = cfg["scheduler_v3"], cfg["synthetic_generator_v2"], cfg["traverse"]
    tau_c, tau_h = cfg["embedding_change"]["change_threshold_cos"], cfg["embedding_change"]["change_threshold_hamming"]
    R: dict = {"split": split, "label": LABEL[split], "config_hash": cfg["config_hash"]}
    fails: dict = {}

    @lru_cache(maxsize=48)
    def native(i):
        return load_primary(acqs[i])

    # ------------------------------------------------------------------ product-tier byte accounting (V3 pair costs)
    eye_costs, rows = [], []
    for i, a in enumerate(acqs):
        e = {"metadata": obs[i]["downlink"]["metadata_bytes"], "stereo": a["stereo"]}
        for eye in (["L", "R"] if a["stereo"] else [a["primary"]["eye"]]):
            key = "L" if not a["stereo"] else eye
            prim = [p for p in a["primaries"] if p["eye"] == eye and p["tier"] == a["primary_tier"]][0]
            th = next((x for x in a["thumbnails"] if x["eye"] == eye), None)
            img = native(i) if prim is a["primary"] else read(prim)
            e[key] = {"full": prim["estimated_downlink_bytes"], "compressed": float(jpeg_bytes(img, SV3["jpeg_quality"])),
                      "thumbnail": th["estimated_downlink_bytes"] if th else None}
            rows.append({"acq_id": a["acq_id"], "eye": eye, "stereo": a["stereo"], "tier_primary": a["primary_tier"],
                         "full_bytes_NASA_LABEL_ESTIMATE": e[key]["full"], "compressed_bytes_SIMULATED_PRODUCT_TIER": e[key]["compressed"],
                         "thumbnail_bytes_NASA_LABEL_ESTIMATE": e[key]["thumbnail"], "archive_bytes_primary": prim["archive_bytes_img"]})
        eye_costs.append(e)
    c3 = ib.cost_table_v3(eye_costs)
    c12 = ib.cost_table(obs)
    total = sum(c["FULL"] or 0 for c in c3)
    (out / "byte_accounting_per_eye.json").write_text(json.dumps(rows, indent=1))
    st_idx = [i for i in range(n) if acqs[i]["stereo"]]
    comp_pair = [c3[i]["COMPRESSED"] for i in st_idx if c3[i]["COMPRESSED"] is not None]
    ratio_full = [c3[i]["COMPRESSED"] / c3[i]["FULL"] for i in st_idx if c3[i]["COMPRESSED"] and c3[i]["FULL"]]
    ratio_th = [c3[i]["COMPRESSED"] / c3[i]["THUMBNAIL"] for i in st_idx if c3[i]["COMPRESSED"] and c3[i]["THUMBNAIL"]]
    th_eff = [c3[i]["THUMBNAIL"] / c3[i]["FULL"] for i in range(n) if c3[i]["THUMBNAIL"] and c3[i]["FULL"]]
    R["byte_accounting"] = {
        "labels": {"NASA_LABEL_ESTIMATE": "LINES×LINE_SAMPLES×INST_CMPRS_RATE/8 from the product label",
                   "SIMULATED_PRODUCT_TIER": "DEEPSIFT JPEG q50 ground re-encoding — not a NASA flight product"},
        "stereo_tier_totals_MB": {k: sum(c3[i][k] or 0 for i in st_idx) / 1e6 for k in ("THUMBNAIL", "COMPRESSED", "FULL")},
        "compressed_stereo_pair_bytes": {"median": pctl(comp_pair, 50), "p90": pctl(comp_pair, 90),
                                         "ratio_to_full_stereo_median": pctl(ratio_full, 50), "ratio_to_thumbnail_pair_median": pctl(ratio_th, 50)},
        "thumbnail_efficiency": {"thumbnail_over_full_median": pctl(th_eff, 50), "thumbnail_total_over_full_total":
                                 sum(c["THUMBNAIL"] or 0 for c in c3) / total if total else None},
        "unknown_costs": sum(1 for c in c3 for k in ("THUMBNAIL", "COMPRESSED", "FULL") if c[k] is None),
        "acquisitions_without_thumbnail_pair": sum(1 for c in c3 if c["THUMBNAIL"] is None)}

    # ------------------------------------------------------------------ constrained pHash groups (for PHASH_CONSTRAINED order)
    by_sol_real = defaultdict(list)
    for i in range(n):
        by_sol_real[obs[i]["sol"]].append(i)
    stop = lambda i: tuple(obs[i]["source_metadata"]["pose"][:2])  # noqa: E731
    uf = sim._UF(n)
    for idx in by_sol_real.values():
        for x, a in enumerate(idx):
            for b in idx[x + 1:]:
                if hamming(H[a], H[b]) <= sim.PHASH_MAX_BITS and stop(a) == stop(b):
                    uf.union(a, b)
    obs_c = [dict(o, near_duplicate_group=uf.find(i)) for i, o in enumerate(obs)]
    base_orders = ib.strategy_orders(obs, SEEDS["random_baseline_order"])
    orders = {"FIFO": base_orders["FIFO"], "RANDOM": base_orders["RANDOM"], "SIZE_AWARE": base_orders["SIZE-AWARE"],
              "EMBEDDING_CHANGE": base_orders["EMBEDDING-NOVELTY"], "PHASH_REPRESENTATIVES_UNCONSTRAINED": base_orders["PHASH-REPRESENTATIVES"],
              "PHASH_CONSTRAINED": ib.strategy_orders(obs_c, SEEDS["random_baseline_order"])["PHASH-REPRESENTATIVES"]}

    # ------------------------------------------------------------------ Scheduler V3 (V1/V2 for context only)
    budgets = SV3["report_budgets_fraction_of_full"]
    comp = {}
    for name, order in orders.items():
        for f in budgets:
            comp[f"V3|{name}|{f}"] = ib.coverage(obs, c3, ib.allocate_progressive(c3, order, f * total), True)
            comp[f"V2|{name}|{f}"] = ib.coverage(obs, c12, ib.allocate_progressive(c12, order, f * total), False)
    keys = SV3["monotonicity_metrics"]
    grid = list(np.geomspace(0.0001, 0.30, 80))
    mono, stereo_bad = {}, 0
    for name, order in orders.items():
        seq = []
        for f in grid:
            tiers = ib.allocate_progressive(c3, order, f * total)
            cv = ib.coverage(obs, c3, tiers, True)
            seq.append([cv[k] for k in keys])
            both = sum(1 for i in st_idx if ib.RANK[tiers[i]] >= ib.RANK["COMPRESSED"] and c3[i]["COMPRESSED"] is not None)
            stereo_bad += cv["stereo_pair_usable"] > both
        mono[name] = {k: sum(1 for a, b in zip(seq, seq[1:]) if b[j] < a[j]) for j, k in enumerate(keys)}
    viol = sum(sum(v.values()) for v in mono.values())
    R["scheduler_v3"] = {"budgets": budgets, "grid_points": len(grid), "comparison": comp, "monotonicity_violations": mono,
                         "total_violations": viol, "stereo_usable_exceeding_complete_pairs": stereo_bad,
                         "THUMBNAIL_FIRST": "inherent to progressive fill; equals V3|FIFO",
                         "full_stereo_starts_at_budget_fraction": next((f for f in grid if ib.coverage(obs, c3, ib.allocate_progressive(c3, orders["FIFO"], f * total), True)["stereo_pair_full"] > 0), None)}
    fifo1 = comp["V3|FIFO|0.01"]
    fails["scheduler_v3_difficult_allocations"] = {
        "at_1pct_FIFO": {"stereo_present": fifo1["stereo_pair_present"], "stereo_usable": fifo1["stereo_pair_usable"],
                         "stereo_acquisitions": fifo1["stereo_acquisitions"], "acquisitions_usable": fifo1["acquisitions_usable"]},
        "largest_pair_costs_bytes": sorted(((c3[i]["FULL"] or 0, obs[i]["id"]) for i in st_idx), reverse=True)[:5],
        "acquisitions_without_thumbnail_pair": [obs[i]["id"] for i in range(n) if c3[i]["THUMBNAIL"] is None][:10]}
    print("scheduler V3 violations", viol, "stereo bad", stereo_bad)

    # ------------------------------------------------------------------ QUALITY_V2 false-positive rate on untouched images
    real = []
    for i in range(n):
        st, why = q2.classify(q2.features(native(i), acqs[i]["primary"].get("error_pixels")), obs[i]["primary_tier"], TH)
        real.append((st, why))
    flagged = [st != "CLEAN" for st, _ in real]
    per_eye = defaultdict(list)
    for i, a in enumerate(acqs):
        for p in a["primaries"]:
            if p["tier"] != a["primary_tier"]:
                continue
            img = native(i) if p is a["primary"] else read(p)
            per_eye[p["eye"]].append(q2.classify(q2.features(img, p.get("error_pixels")), a["primary_tier"], TH)[0] != "CLEAN")
    grp = lambda key: {str(k): {"n": len(v), "fpr": float(np.mean(v))} for k, v in sorted(key.items())}  # noqa: E731
    by_sol, by_tier, by_seq = defaultdict(list), defaultdict(list), defaultdict(list)
    for i, fl in enumerate(flagged):
        by_sol[obs[i]["sol"]].append(fl)
        by_tier[obs[i]["primary_tier"]].append(fl)
        by_seq[obs[i]["sequence_id"][:4].upper()].append(fl)
    fpr = float(np.mean(flagged))
    R["quality_v2_real"] = {"label": f"{LABEL[split]} FALSE-POSITIVE RATE", "overall": fpr, "n": n, "flagged": int(sum(flagged)),
                            "reasons": dict(Counter(r for st, why in real if st != "CLEAN" for r in why)),
                            "by_sol": grp(by_sol), "by_tier": grp(by_tier), "by_eye": grp(per_eye), "by_sequence_type": grp(by_seq),
                            "development_fpr": cfg["quality_v2"]["development_false_positive_rate"]}
    fails["quality_v2_false_positives"] = [{"acq_id": obs[i]["id"], "sol": obs[i]["sol"], "tier": obs[i]["primary_tier"], "reasons": real[i][1]}
                                           for i in range(n) if flagged[i]][:25]
    print(f"QUALITY_V2 {LABEL[split]} FPR {fpr:.4f}")

    # ------------------------------------------------------------------ fresh SYNTH_V2 controls (frozen parameters, split-specific seeds)
    tag = SEEDS["synthetic_seed_tag"][split]
    sdir = ROOT / "data" / "synthetic" / f"phase3_3_{split}" / "controls_v2"
    ents = []
    fams = [f for f in v1gen.FAMILIES]
    for fam in fams:
        rng = random.Random(v1gen.seed_for(v2gen.GENERATOR, tag, fam))
        src = rng.sample(range(n), len(v1gen.LEVELS) * SYN["per_level"])
        for li, lv in enumerate(v1gen.LEVELS):
            for k in range(SYN["per_level"]):
                i = src[li * SYN["per_level"] + k]
                sid = f"SYN-P33{tag[:3]}-{fam}-{lv}-{k:03d}"
                ents.append({"synthetic_id": sid, "family": fam, "family_kind": v1gen.FAMILIES[fam][0], "severity": lv,
                             "random_seed": v1gen.seed_for(v2gen.GENERATOR, tag, sid), "source_index": i})
    rng = random.Random(v1gen.seed_for(v2gen.GENERATOR, tag, "NEAR_DUPLICATE"))
    for k, i in enumerate(rng.sample(range(n), SYN["near_duplicates"])):
        sid = f"SYN-P33{tag[:3]}-NEAR_DUPLICATE-{k:03d}"
        ents.append({"synthetic_id": sid, "family": "NEAR_DUPLICATE", "family_kind": "REDUNDANCY", "severity": "N/A",
                     "random_seed": v1gen.seed_for(v2gen.GENERATOR, tag, sid), "source_index": i})
    qf, ch_e, ch_h, dup_h = {}, {}, {}, {}
    for e in ents:
        i = e["source_index"]
        src = native(i)
        if e["family"] == "NEAR_DUPLICATE":
            y, p = v2gen.near_duplicate(src, e["random_seed"])
            box = None
        else:
            y, p, box = v2gen.perturb(src, e["family"], e["severity"], e["random_seed"])
        e["contract_violations"] = v2gen.check_contract(e["family"], src, y, p, box)
        path = sdir / f"{e['synthetic_id']}.png"
        v1gen.save_png16(path, y)
        y = v1gen.load_png16(path)
        e.update(parameters=p, bounding_region_yxyx=box, label="SYNTHETIC CONTROL", generator=v2gen.GENERATOR, split=split,
                 source_acquisition_id=obs[i]["id"], source_sha256_img=acqs[i]["primary"]["sha256_img"], source_tier=acqs[i]["primary_tier"],
                 tune_eval_half=half(obs[i]["id"]), path=str(path.relative_to(ROOT)), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        if e["family_kind"] == "REDUNDANCY":
            dup_h[e["synthetic_id"]] = phash(y)
            continue
        qf[e["synthetic_id"]] = q2.classify(q2.features(y), e["source_tier"], TH)
        ch_e[e["synthetic_id"]] = cosd(E[i], emb.embed(to_work(y))[0]) > tau_c
        ch_h[e["synthetic_id"]] = hamming(H[i], phash(y)) > tau_h
    man_path = ROOT / "data" / "manifests" / f"synthetic_controls_v2_{split}.json"
    man_path.write_text(json.dumps({"generator": v2gen.GENERATOR, "split": split, "created_at": datetime.now(timezone.utc).isoformat(),
                                    "note": "SYNTHETIC CONTROLS (V2) — perturbed copies of NASA PDS observations; originals never modified; not Mars events; "
                                            "separate from development controls",
                                    "config_hash": cfg["config_hash"], "count": len(ents), "entries": ents}, indent=1, default=str))

    def recall(kind, half_=None):
        tab = defaultdict(lambda: defaultdict(list))
        for e in ents:
            if e["family_kind"] == kind and (half_ is None or e["tune_eval_half"] == half_):
                tab[e["family"]][e["severity"]].append(qf[e["synthetic_id"]][0] != "CLEAN")
        return {f: {lv: float(np.mean(v)) for lv, v in sorted(d.items(), key=lambda kv: v1gen.LEVELS.index(kv[0]))} for f, d in tab.items()}
    sens = defaultdict(lambda: defaultdict(lambda: {"e": [], "h": []}))
    for e in ents:
        if e["family_kind"] != "REDUNDANCY":
            sens[f"{e['family_kind']}|{e['family']}"][e["severity"]]["e"].append(ch_e[e["synthetic_id"]])
            sens[f"{e['family_kind']}|{e['family']}"][e["severity"]]["h"].append(ch_h[e["synthetic_id"]])
    vis = [e for e in ents if e["family_kind"] == "VISUAL_NOVELTY"]
    R["synthetic_v2"] = {"controls": len(ents), "by_family": dict(Counter(e["family"] for e in ents)), "seeds_tag": tag,
                         "contract_violations": sum(len(e["contract_violations"]) for e in ents),
                         "violations_detail": dict(Counter(f"{e['family']}:{v}" for e in ents for v in e["contract_violations"])),
                         "visual_attenuated_share": {lv: float(np.mean([e["parameters"]["amplitude_scale"] < 1 for e in vis if e["severity"] == lv])) for lv in v1gen.LEVELS},
                         "quality_v2_recall_all": recall("ENGINEERING_QUALITY"), "quality_v2_recall_eval_half": recall("ENGINEERING_QUALITY", "EVAL"),
                         "quality_v2_cross_talk_visual": {"flagged": float(np.mean([qf[e["synthetic_id"]][0] != "CLEAN" for e in vis])),
                                                          "reasons": dict(Counter(r for e in vis for r in qf[e["synthetic_id"]][1]))},
                         "change_sensitivity": {k: {lv: {"embedding": float(np.mean(c["e"])), "phash": float(np.mean(c["h"]))}
                                                    for lv, c in sorted(d.items(), key=lambda kv: v1gen.LEVELS.index(kv[0]))} for k, d in sens.items()},
                         "manifest": str(man_path.relative_to(ROOT))}
    fails["quality_v2_misses"] = [{"synthetic_id": e["synthetic_id"], "family": e["family"], "severity": e["severity"], "source": e["source_acquisition_id"]}
                                  for e in ents if e["family_kind"] == "ENGINEERING_QUALITY" and e["severity"] in ("OBVIOUS", "MODERATE")
                                  and qf[e["synthetic_id"]][0] == "CLEAN"][:25]
    fails["embedding_missed_visual_change"] = [{"synthetic_id": e["synthetic_id"], "family": e["family"], "severity": e["severity"],
                                                "amplitude_scale": e["parameters"]["amplitude_scale"]}
                                               for e in vis if e["severity"] in ("OBVIOUS", "MODERATE") and not ch_e[e["synthetic_id"]]][:25]
    print("synthetic contracts", R["synthetic_v2"]["contract_violations"])

    # ------------------------------------------------------------------ pHash safety variants
    dups = [e for e in ents if e["family"] == "NEAR_DUPLICATE"]
    pool = [{"sol": obs[i]["sol"], "t": t[i], "stop": stop(i), "pose": tuple(obs[i]["source_metadata"]["pose"]),
             "scene": obs[i]["scene_cluster"], "h": H[i]} for i in range(n)]
    for e in dups:
        pool.append({**pool[e["source_index"]], "t": t[e["source_index"]] + 1, "h": dup_h[e["synthetic_id"]]})
    N = len(pool)
    by_sol = defaultdict(list)
    for k, p in enumerate(pool):
        by_sol[p["sol"]].append(k)
    ph = lambda a, b: hamming(a["h"], b["h"]) <= sim.PHASH_MAX_BITS  # noqa: E731
    TL = cfg["redundancy_constraints"]["temporal_link_s"]
    methods = {"PHASH_ONLY": ph, "PHASH_PLUS_TIME_120S": lambda a, b: ph(a, b) and abs(a["t"] - b["t"]) <= TL,
               "PHASH_PLUS_SAME_ROVER_STOP": lambda a, b: ph(a, b) and a["stop"] == b["stop"],
               "PHASH_PLUS_SITE_DRIVE_POSE": lambda a, b: ph(a, b) and a["pose"] == b["pose"]}
    seqs = defaultdict(list)
    for i in sorted(range(n), key=lambda i: t[i]):
        seqs[(obs[i]["sol"], obs[i]["sequence_id"])].append(i)
    trav = [i for k, v in seqs.items() if k[1].startswith("trav") for i in v]
    poses_all = {p["pose"] for p in pool[:n]}
    gres = {}
    for name, link in methods.items():
        u = sim._UF(N)
        for idx in by_sol.values():
            for x, a in enumerate(idx):
                for b in idx[x + 1:]:
                    if link(pool[a], pool[b]):
                        u.union(a, b)
        cmp_ = [u.find(k) for k in range(N)]
        mem = defaultdict(list)
        for k in range(n):
            mem[cmp_[k]].append(k)
        pairs = [(a, b) for m in mem.values() for x, a in enumerate(m) for b in m[x + 1:]]
        reps = {min(m, key=lambda k: pool[k]["t"]) for m in mem.values()}
        bad = [(a, b) for a, b in pairs if pool[a]["scene"] != pool[b]["scene"]]
        gres[name] = {"near_duplicate_retrieval": float(np.mean([cmp_[n + k] == cmp_[e["source_index"]] for k, e in enumerate(dups)])),
                      "merged_pairs": len(pairs), "scene_merge_errors": len(bad),
                      "false_merge_rate_different_scene": len(bad) / len(pairs) if pairs else 0.0,
                      "false_merge_rate_different_pose": float(np.mean([pool[a]["pose"] != pool[b]["pose"] for a, b in pairs])) if pairs else 0.0,
                      "traverse_compression": len(trav) / max(1, len({cmp_[i] for i in trav})) if trav else None,
                      "unique_position_loss": 1 - len({pool[k]["pose"] for k in reps}) / len(poses_all)}
        if name == "PHASH_ONLY":
            rr = random.Random(SEEDS["phash_false_merge_examples"])
            fails["phash_false_merges"] = [{"A": obs[a]["id"], "B": obs[b]["id"], "hamming": hamming(H[a], H[b]),
                                            "poseA": pool[a]["pose"], "poseB": pool[b]["pose"]} for a, b in rr.sample(bad, min(15, len(bad)))]
    R["phash"] = gres
    tax = Counter()
    for idx in by_sol_real.values():
        for x, a in enumerate(idx):
            for b in idx[x + 1:]:
                P_ = hamming(H[a], H[b]) <= sim.PHASH_MAX_BITS
                S_ = obs[a]["scene_cluster"] == obs[b]["scene_cluster"]
                tax["PIXEL_SIMILAR"] += P_
                tax["SCENE_SIMILAR"] += S_
                tax["SEQUENCE_RELATED"] += obs[a]["sequence_id"] == obs[b]["sequence_id"]
                tax["POTENTIALLY_REDUNDANT"] += P_ and S_
                tax["PIXEL_SIMILAR_NOT_SCENE_SIMILAR"] += P_ and not S_
    tax["STEREO_RELATED_acquisitions"] = len(st_idx)
    R["redundancy_taxonomy"] = dict(tax)

    # ------------------------------------------------------------------ embeddings
    sp = []
    for i in st_idx:
        L_ = [p for p in acqs[i]["primaries"] if p["eye"] == "L"][0]
        R_ = [p for p in acqs[i]["primaries"] if p["eye"] == "R"][0]
        a, b = read(L_), read(R_)
        sp.append((cosd(emb.embed(to_work(a))[0], emb.embed(to_work(b))[0]), hamming(phash(a), phash(b))))
    consec = [(a, b) for v in seqs.values() for a, b in zip(v, v[1:])]
    rr = random.Random(SEEDS["embedding_random_pairs"])
    randp = []
    sols = {o["sol"] for o in obs}
    while len(randp) < 2000 and len(sols) > 1:
        a, b = rr.randrange(n), rr.randrange(n)
        if obs[a]["sol"] != obs[b]["sol"]:
            randp.append((a, b))
    dstat = lambda prs: {"cos_p10_p50_p90": [pctl([cosd(E[a], E[b]) for a, b in prs], q) for q in (10, 50, 90)],  # noqa: E731
                         "hamming_p10_p50_p90": [pctl([hamming(H[a], H[b]) for a, b in prs], q) for q in (10, 50, 90)], "n": len(prs)}

    def box(x, k):
        h2, w2 = (x.shape[0] // k) * k, (x.shape[1] // k) * k
        return x[:h2, :w2].reshape(h2 // k, k, w2 // k, k).mean(axis=(1, 3))
    fidx = [i for i in range(n) if obs[i]["primary_tier"] == "F"]
    res = defaultdict(list)
    for i in fidx:
        x = native(i)
        f0 = quality(x, None)
        for nm, k in (("D_like_256", 4), ("T_like_64", 16)):
            y = box(x, k)
            res[f"cos|{nm}"].append(cosd(E[i], emb.embed(to_work(y))[0]))
            res[f"ham|{nm}"].append(hamming(H[i], phash(y)))
            f1 = quality(y, None)
            for kk in ("brightness", "contrast", "entropy_bits", "sharpness"):
                res[f"feat|{nm}|{kk}"].append(abs(f1[kk] - f0[kk]) / (abs(f0[kk]) + 1e-9))
        th = acqs[i]["thumbnail"]
        if th:
            y = read(th)
            y = (y - y.min()) / max(1e-6, float(y.max() - y.min())) * 4095.0
            res["cos|real_thumbnail"].append(cosd(E[i], emb.embed(to_work(y))[0]))
            res["ham|real_thumbnail"].append(hamming(H[i], phash(y)))
    nov = [o["image_features"]["embedding_novelty"] for o in obs]
    R["embeddings"] = {"model": vm["chosen"], "frozen_change_thresholds": {"cos": tau_c, "hamming": tau_h},
                       "stereo_left_right": {"n": len(sp), "cos_p10_p50_p90": [pctl([c for c, _ in sp], q) for q in (10, 50, 90)],
                                             "hamming_p10_p50_p90": [pctl([h for _, h in sp], q) for q in (10, 50, 90)],
                                             "within_phash_threshold": float(np.mean([h <= sim.PHASH_MAX_BITS for _, h in sp])) if sp else None},
                       "consecutive_frames": dstat(consec), "random_pairs": dstat(randp),
                       "novelty_distribution": {"p10": pctl(nov, 10), "p50": pctl(nov, 50), "p90": pctl(nov, 90),
                                                "by_sequence_type_median": {k: statistics.median([nov[i] for i in range(n) if obs[i]["sequence_id"][:4].upper() == k])
                                                                            for k in sorted({o["sequence_id"][:4].upper() for o in obs})}},
                       "resolution": {"full_frames": len(fidx), **{k: {"median": pctl(v, 50), "p90": pctl(v, 90)} for k, v in res.items()}}}

    # ------------------------------------------------------------------ traverse experiment (frozen methods)
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
        used = []
        for d in targets:
            for j in np.argsort(np.abs(cum - d), kind="stable"):
                if int(j) not in used:
                    used.append(int(j))
                    break
        return sorted(used)
    trows = []
    R_M = TRV["coverage_radius_m"]
    for key, fr in seqs.items():
        if not key[1].startswith("trav") or len(fr) < 10:
            continue
        m = len(fr)
        xy = np.array([[obs[i]["location_context"].get("landing_x", 0.0), obs[i]["location_context"].get("landing_y", 0.0)] for i in fr])
        missing_xy = sum(1 for i in fr if "landing_x" not in obs[i]["location_context"])
        Dp = np.linalg.norm(xy[:, None] - xy[None], axis=2)
        De = 1.0 - E[fr] @ E[fr].T
        cum = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))])
        path = float(cum[-1]) or 1.0
        stops = {tuple(obs[i]["source_metadata"]["pose"]) for i in fr}
        for frac in [1.0] + TRV["fractions"]:
            k = max(1, math.ceil(frac * m))
            if frac == 1.0:
                sels = {"SEND_ALL": list(range(m))}
            else:
                step = max(1, round(1 / frac))
                targets = np.linspace(0, cum[-1], k)
                sels = {"EVERY_NTH_FRAME": list(range(0, m, step))[:k] or [0], "UNIFORM_DISTANCE": uniform_distance(cum, targets),
                        "METADATA_POSITION": fps(Dp, k), "EMBEDDING_CHANGE": fps(De, k),
                        "POSITION_PLUS_EMBEDDING_CHANGE": fps(0.5 * Dp / (Dp.max() or 1.0) + 0.5 * De / (De.max() or 1.0), k)}
            for meth, s in sels.items():
                s = sorted(s)
                si = [fr[j] for j in s]
                ss = set(si)
                rest = [i for i in fr if i not in ss]
                broken = sum(1 for i in si if acqs[i]["stereo"] and c3[i]["FULL"] is None)
                byt = sum(c3[i]["FULL"] or 0 for i in si) + sum(c3[i]["THUMBNAIL"] or 0 for i in rest)
                gaps = [float(Dp[a, b]) for a, b in zip(s, s[1:])]
                trows.append({"sequence": f"{key[0]}:{key[1]}", "frames": m, "missing_positions": missing_xy, "fraction": frac, "method": meth,
                              "frames_retained": len(s), "bytes": byt, "bytes_send_all": sum(c3[i]["FULL"] or 0 for i in fr),
                              "unique_positions_retained": len({tuple(obs[i]["source_metadata"]["pose"]) for i in si}) / len(stops),
                              "position_coverage_5m": float(np.mean(np.min(Dp[:, s], axis=1) <= R_M)),
                              "traverse_distance_represented": float(sum(gaps)) / path if len(s) > 1 else 0.0,
                              "mean_spatial_gap_m": float(np.mean(gaps)) if gaps else 0.0, "max_spatial_gap_m": max(gaps) if gaps else 0.0,
                              "visual_change_coverage": float(np.mean(np.max(E[fr] @ E[si].T, axis=1))),
                              "stereo_pairs_retained_full": sum(1 for i in si if acqs[i]["stereo"]), "stereo_pairs_broken": broken})
    tagg = defaultdict(lambda: defaultdict(list))
    for r in trows:
        for k in ("bytes", "bytes_send_all", "frames_retained", "unique_positions_retained", "position_coverage_5m", "traverse_distance_represented",
                  "mean_spatial_gap_m", "max_spatial_gap_m", "visual_change_coverage", "stereo_pairs_retained_full", "stereo_pairs_broken"):
            tagg[(r["fraction"], r["method"])][k].append(r[k])
    summ = {f"{f}|{m}": {"bytes_fraction_of_send_all": float(np.sum(v["bytes"]) / np.sum(v["bytes_send_all"])),
                         "frames_retained": int(np.sum(v["frames_retained"])),
                         **{k: float(np.mean(v[k])) for k in ("unique_positions_retained", "position_coverage_5m", "traverse_distance_represented",
                                                              "mean_spatial_gap_m", "max_spatial_gap_m", "visual_change_coverage")},
                         "max_spatial_gap_m_worst": float(np.max(v["max_spatial_gap_m"])),
                         "stereo_pairs_retained_full": int(np.sum(v["stereo_pairs_retained_full"])), "stereo_pairs_broken": int(np.sum(v["stereo_pairs_broken"]))}
            for (f, m), v in sorted(tagg.items(), key=lambda kv: (-kv[0][0], kv[0][1]))}
    nseq = len({r["sequence"] for r in trows})
    R["traverse"] = {"sequences": nseq, "frames": sum({r["sequence"]: r["frames"] for r in trows}.values()),
                     "frames_missing_position": sum({r["sequence"]: r["missing_positions"] for r in trows}.values()), "summary": summ, "rows": trows}
    if nseq:
        send_worst = summ["1.0|SEND_ALL"]["max_spatial_gap_m_worst"]
        fails["position_gap_failures"] = [r for r in trows if r["method"] == "METADATA_POSITION" and r["fraction"] == 0.25
                                          and (r["position_coverage_5m"] < 0.9 or r["max_spatial_gap_m"] > 2 * send_worst)]
        fails["position_plus_embedding_failures"] = [r for r in trows if r["method"] == "POSITION_PLUS_EMBEDDING_CHANGE" and r["fraction"] == 0.25
                                                     and (r["position_coverage_5m"] < 0.9 or r["visual_change_coverage"] < 0.9 or r["max_spatial_gap_m"] > 2 * send_worst)]

    # ------------------------------------------------------------------ pre-declared rules (read from the frozen config)
    ev = {}
    ev["S1_scheduler_v3"] = {"monotonicity_violations": viol, "stereo_usable_exceeding_complete_pairs": stereo_bad,
                             "verdict": "GENERALIZES" if viol == 0 and stereo_bad == 0 else "FAILS"}
    dev_fpr = cfg["quality_v2"]["development_false_positive_rate"]
    fv = "GENERALIZES" if fpr <= 2 * dev_fpr else ("PARTIAL" if fpr <= 3 * dev_fpr else "FAILS")
    p32 = json.loads((ROOT / "artifacts/phase3_2/20260925T135920-phase3.2-dev-corrective-ceb8/results.json").read_text())
    dev_rec = p32["quality"]["recall_all"]["V2"]
    vrec = R["synthetic_v2"]["quality_v2_recall_all"]
    obv = all(vrec[f]["OBVIOUS"] == 1.0 for f in vrec)
    mod = {f: abs(vrec[f]["MODERATE"] - dev_rec[f]["MODERATE"]) for f in vrec}
    rv = obv and all(d <= 0.15 for d in mod.values())
    ev["S2_quality_v2"] = {"fpr": fpr, "fpr_verdict": fv, "obvious_all_1": obv, "moderate_abs_diff_vs_dev": mod, "recall_pass": rv,
                           "verdict": "GENERALIZES" if fv == "GENERALIZES" and rv else ("FAILS" if fv == "FAILS" and not rv else "PARTIALLY_GENERALIZES")}
    cons = [k for k in gres if k != "PHASH_ONLY"]
    safe = all(gres[k]["false_merge_rate_different_scene"] <= 0.05 and gres[k]["near_duplicate_retrieval"] >= 0.95 for k in cons)
    ev["S3_constrained_phash"] = {"constrained_safe": safe, "phash_only_unsafe_reproduces": gres["PHASH_ONLY"]["false_merge_rate_different_scene"] >= 0.5,
                                  "verdict": "SAFE" if safe else "NOT SAFE"}
    s50 = R["embeddings"]["stereo_left_right"]["cos_p10_p50_p90"][1]
    c50 = R["embeddings"]["consecutive_frames"]["cos_p10_p50_p90"][1]
    r50 = R["embeddings"]["random_pairs"]["cos_p10_p50_p90"][1]
    cs = R["synthetic_v2"]["change_sensitivity"]
    margin = float(np.mean([cs[f"VISUAL_NOVELTY|{f}"]["OBVIOUS"]["embedding"] - cs[f"VISUAL_NOVELTY|{f}"]["OBVIOUS"]["phash"]
                            for f in ("LOCALIZED_STRUCTURE", "TEXTURE_CHANGE")]))
    order_ok = s50 is not None and c50 is not None and r50 is not None and s50 < c50 < r50
    ev["S4_embeddings"] = {"stereo_lt_consecutive_lt_random": order_ok, "obvious_visual_margin_over_phash": margin,
                           "verdict": "DISTINCT SIGNAL" if order_ok and margin >= 0.30 else "NOT DEMONSTRATED"}
    if nseq >= 3:
        sa = summ["1.0|SEND_ALL"]["max_spatial_gap_m_worst"]
        pos = summ["0.25|METADATA_POSITION"]
        ev["S5_position"] = {"coverage_5m": pos["position_coverage_5m"], "worst_gap": pos["max_spatial_gap_m_worst"], "send_all_worst_gap": sa,
                             "verdict": "GENERALIZES" if pos["position_coverage_5m"] >= 0.90 and pos["max_spatial_gap_m_worst"] <= 2 * sa else "DOES NOT GENERALIZE"}
        pe = summ["0.25|POSITION_PLUS_EMBEDDING_CHANGE"]
        g = {"G1_bytes": pe["bytes_fraction_of_send_all"] <= 0.35, "G2_coverage": pe["position_coverage_5m"] >= 0.90,
             "G3_visual": pe["visual_change_coverage"] >= 0.90, "G4_gap": pe["max_spatial_gap_m_worst"] <= 2 * sa, "G5_stereo": pe["stereo_pairs_broken"] == 0}
        if all(g.values()):
            verdict = "GENERALIZES"
        elif g["G1_bytes"] and g["G5_stereo"] and sum(not g[k] for k in ("G2_coverage", "G3_visual", "G4_gap")) == 1:
            verdict = "PARTIALLY_GENERALIZES"
        else:
            verdict = "DOES_NOT_GENERALIZE"
        ev["PRIMARY"] = {"metrics": {k: pe[k] for k in ("bytes_fraction_of_send_all", "position_coverage_5m", "visual_change_coverage",
                                                        "max_spatial_gap_m_worst", "stereo_pairs_broken")},
                         "send_all_worst_gap": sa, "criteria": g, "verdict": verdict}
    else:
        ev["S5_position"] = ev["PRIMARY"] = {"verdict": "INCONCLUSIVE", "traverse_sequences": nseq}
    ev["S6_generator"] = {"violations": R["synthetic_v2"]["contract_violations"], "verdict": "PASS" if R["synthetic_v2"]["contract_violations"] == 0 else "GENERATOR FAILURE"}
    R["rules_evaluation"] = ev
    (out / f"{LABEL[split].lower()}_failure_analysis.json").write_text(json.dumps(
        {"label": f"{LABEL[split]} FAILURE ANALYSIS — for future work only; nothing was tuned from these", **fails}, indent=1, default=str))
    R["git"] = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    (out / "results.json").write_text(json.dumps(R, indent=1, default=str))
    return R


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", required=True, choices=["development", "validation", "test"])
    ap.add_argument("--stage", choices=["dataset", "analysis", "all"], default="all")
    ap.add_argument("--run", help="existing run dir (analysis stage)")
    args = ap.parse_args()
    if args.split == "test":
        raise SystemExit("STOP: the Phase 3 TEST interval (sols 950–979) is held out and untouched in Phase 3.3")
    cfg = load_cfg()
    if args.run:
        out = Path(args.run)
    else:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + f"-phase3.3-{args.split[:3]}-" + uuid.uuid4().hex[:4]
        out = ROOT / "artifacts" / "phase3_3" / run_id
        out.mkdir(parents=True)
        (out / "run_manifest.json").write_text(json.dumps({"run_id": run_id, "split": args.split, "config_hash": cfg["config_hash"],
                                                           "pre_declared_rules": cfg["rules"], "written_before_metrics": True, "seeds": seed_manifest(args.split),
                                                           "seed_note": "explicit seed freeze = reproducibility fix made before validation analysis, not retuning",
                                                           "git": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip(),
                                                           "created_at": datetime.now(timezone.utc).isoformat()}, indent=1, ensure_ascii=False))
    if args.stage in ("dataset", "all"):
        rep = build_observations(args.split, cfg, out)
        print(json.dumps({k: v for k, v in rep.items() if k not in ("grouping",)}, indent=1, default=str))
    if args.stage in ("analysis", "all"):
        R = analyse(args.split, cfg, out)
        print(json.dumps(R["rules_evaluation"], indent=1, default=str))
    print(f"→ {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
