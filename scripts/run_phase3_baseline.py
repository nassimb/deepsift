#!/usr/bin/env python3
"""Phase 3 baseline (M3–M12) on the DEVELOPMENT split only: acquisitions → quality → pHash → PLACES → telemetry
context → local embeddings (frozen model) → novelty → MultimodalObservation → byte accounting → baseline benchmark.

    uv run python scripts/run_phase3_baseline.py

No fusion, no VLM, no Jev, no UI. Output: artifacts/phase3/<run_id>/.
"""

from __future__ import annotations

import json
import statistics
import subprocess
import sys
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "pipeline"))

from deepsift.evaluation import image_benchmark as ib  # noqa: E402
from deepsift.imaging import similarity as sim  # noqa: E402
from deepsift.imaging.acquisitions import group_acquisitions, grouping_stats  # noqa: E402
from deepsift.imaging.embeddings import Embedder  # noqa: E402
from deepsift.imaging.features import jpeg_bytes, load_primary, phash, quality, to_work  # noqa: E402
from deepsift.multimodal import location  # noqa: E402
from deepsift.multimodal.observation import DownlinkOptions, MultimodalObservation  # noqa: E402
from deepsift.multimodal.temporal_join import TELEMETRY_CONTEXT_S, TelemetryContext  # noqa: E402

NOVELTY_LOOKBACK_SOLS = 3
JPEG_QUALITY = 50


def pct(xs, q):
    xs = [x for x in xs if x is not None]
    return float(np.percentile(xs, q)) if xs else None


def main() -> int:
    t_start = time.perf_counter()
    split = json.loads((ROOT / "data" / "splits" / "phase3_splits.json").read_text())
    man = json.loads((ROOT / "data" / "manifests" / "navcam_development.json").read_text())
    vm = json.loads((ROOT / "config" / "phase3_vision_model.json").read_text())
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-phase3-dev-baseline-" + uuid.uuid4().hex[:4]
    out = ROOT / "artifacts" / "phase3" / run_id
    out.mkdir(parents=True)
    products = man["products"]
    acqs = group_acquisitions(products)
    gstats = grouping_stats(products, acqs)
    print("M3", gstats)

    # M2/M6/M7: decode, quality, pHash, re-encoding size
    works, hashes, quals, comp = [], [], [], []
    t0 = time.perf_counter()
    for a in acqs:
        img = load_primary(a)
        quals.append(quality(img, a["primary"].get("error_pixels")))
        hashes.append(phash(img))
        works.append(to_work(img))
        comp.append(jpeg_bytes(img, JPEG_QUALITY))
    feat_ms = (time.perf_counter() - t0) * 1000 / len(acqs)
    print("M6 quality", Counter(q["quality_state"] for q in quals), f"{feat_ms:.1f} ms/acq")

    # M11: byte accounting
    dl = []
    for a, c in zip(acqs, comp):
        ests = [p["estimated_downlink_bytes"] for p in a["primaries"]]
        full = sum(ests) if all(e is not None for e in ests) else None
        meta_rec = {k: a[k] for k in ("acq_id", "sol", "utc", "sclk", "sequence_id", "site", "drive", "pose", "eyes", "primary_tier", "azimuth_deg", "elevation_deg")}
        dl.append({"full_bytes": full, "compressed_bytes": float(c), "thumbnail_bytes": a["thumbnail"]["estimated_downlink_bytes"] if a["thumbnail"] else None,
                   "metadata_bytes": len(json.dumps(meta_rec, separators=(",", ":"), default=str).encode()),
                   "archive_bytes": int(sum(p["archive_bytes_img"] + p["archive_bytes_lbl"] for p in a["primaries"] + a["thumbnails"])),
                   "full_bytes_status": "ESTIMATED_FROM_LABEL" if full is not None else "UNKNOWN"})
    sample = []
    for tier in ("F", "D", "S", "M", "T"):
        for p in [p for p in products if p["tier"] == tier][:3]:
            sample.append({"product_id": p["product_id"], "tier": tier, "lines": p["lines"], "samples": p["line_samples"],
                           "compression": p["compression"], "rate_bpp": p["compression_rate_bpp"], "ratio": p["compression_ratio"],
                           "archive_bytes_img": p["archive_bytes_img"], "estimated_downlink_bytes": p["estimated_downlink_bytes"],
                           "archive_over_downlink": (p["archive_bytes_img"] / p["estimated_downlink_bytes"]) if p["estimated_downlink_bytes"] else None})

    # M4 PLACES
    places_rec = location.fetch()
    P = location.Places()
    locs = [P.locate(a["site"], a["drive"], a["pose"]) for a in acqs]
    print("M4 places", Counter(l["match"].split("(")[0] for l in locs))

    # M5 telemetry context
    lo, hi = split["development"]["sols"]
    tc = TelemetryContext((lo, hi))
    ctxs = [tc.context(a["utc"]) for a in acqs]

    # M8 embeddings (frozen model)
    emb = Embedder(vm["chosen"])
    emb.embed(works[0])
    E, lat = [], []
    for w in works:
        v, ms = emb.embed(w)
        E.append(v)
        lat.append(ms)
    E = np.stack(E)

    # M9 causal novelty (onboard-plausible: only earlier acquisitions within the lookback)
    order = sorted(range(len(acqs)), key=lambda i: acqs[i]["utc"])
    nov = [1.0] * len(acqs)
    for k, i in enumerate(order):
        prev = [j for j in order[:k] if acqs[j]["sol"] >= acqs[i]["sol"] - NOVELTY_LOOKBACK_SOLS]
        if prev:
            nov[i] = float(1.0 - np.max(E[prev] @ E[i]))

    # groups
    fullb = [d["full_bytes"] for d in dl]
    g_ph, g_seq, g_scene = sim.phash_groups(acqs, hashes), sim.sequence_groups(acqs), sim.scene_clusters(acqs)
    groups = {"phash": sim.group_stats(g_ph, fullb), "sequence": sim.group_stats(g_seq, fullb), "scene_metadata": sim.group_stats(g_scene, fullb)}
    print("M7", {k: (v["groups"], v["largest_group"], round(v["estimated_redundant_downlink_bytes"] / 1e6, 2)) for k, v in groups.items()})

    # M10 observations
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

    # M12 benchmark
    bench = ib.run(obs, E)
    (out / "benchmark.json").write_text(json.dumps(bench, indent=1))

    summary = {
        "run_id": run_id, "split": "development", "sols": [lo, hi], "test_interval_frozen": split["test"]["sols"],
        "grouping": gstats, "quality_states": dict(Counter(q["quality_state"] for q in quals)),
        "download": {"products": len(products), "archive_bytes": man["archive_bytes"]},
        "downlink_bytes": {"full_total": sum(b for b in fullb if b is not None), "full_unknown": sum(1 for b in fullb if b is None),
                           "compressed_total": sum(d["compressed_bytes"] for d in dl), "thumbnail_total": sum(d["thumbnail_bytes"] or 0 for d in dl),
                           "metadata_total": sum(d["metadata_bytes"] for d in dl), "archive_total": sum(d["archive_bytes"] for d in dl),
                           "sample_archive_vs_downlink": sample},
        "groups": groups,
        "vision_model": {"name": vm["chosen"], **vm["candidates"][vm["chosen"]], "run_latency_p50_ms": pct(lat, 50), "run_latency_p95_ms": pct(lat, 95)},
        "telemetry_alignment": {"rems_gap_s": {"median": pct([c["rems_gap_s"] for c in ctxs], 50), "p90": pct([c["rems_gap_s"] for c in ctxs], 90)},
                                "rad_gap_s": {"median": pct([c["rad_gap_s"] for c in ctxs], 50), "p90": pct([c["rad_gap_s"] for c in ctxs], 90)},
                                "acquisitions_with_context_event": sum(1 for c in ctxs if c["context_events"]),
                                "context_window_s": TELEMETRY_CONTEXT_S, "segment": tc.segment_id, "phase2_config_version": tc.config_version},
        "places": {"matches": dict(Counter(l["match"].split("(")[0] for l in locs)), **places_rec},
        "novelty": {"lookback_sols": NOVELTY_LOOKBACK_SOLS, "median": statistics.median(nov), "p90": pct(nov, 90)},
        "feature_ms_per_acquisition": feat_ms, "wall_s": time.perf_counter() - t_start,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout.strip())
    (out / "manifest.json").write_text(json.dumps({
        "run_id": run_id, "git_commit": git, "git_dirty": dirty, "inputs": {
            "navcam_manifest": "data/manifests/navcam_development.json", "splits": "data/splits/phase3_splits.json",
            "vision_model": vm["chosen"], "vision_model_sha256": vm["chosen_sha256"], "places_sha256": places_rec["sha256"]},
        "parameters": {"phash_max_bits": sim.PHASH_MAX_BITS, "scene_max_deg": sim.SCENE_MAX_DEG, "novelty_lookback_sols": NOVELTY_LOOKBACK_SOLS,
                       "jpeg_quality": JPEG_QUALITY, "telemetry_context_s": TELEMETRY_CONTEXT_S, "budgets": ib.BUDGETS, "random_seeds": ib.RANDOM_SEEDS},
        "reproduce": "uv run python scripts/fetch_navcam.py --split development && uv run python scripts/run_phase3_baseline.py"}, indent=1))
    print(json.dumps({k: summary[k] for k in ("grouping", "quality_states", "downlink_bytes", "vision_model", "telemetry_alignment")}, indent=1, default=str)[:4000])
    print(f"→ {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
