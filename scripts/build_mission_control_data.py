#!/usr/bin/env python3
"""Build apps/web/data/mission-control.json for the public Phase 3 Mission Control — frozen final-test artifacts only.

    uv run python scripts/build_mission_control_data.py

Sources (all frozen, hash-locked by docs/release/science-artifacts.json):
  artifacts/phase3_final/<run>/observations.jsonl, embeddings.npy, results.json, byte_accounting_per_eye.json
  data/manifests/navcam_test.json (product ids, tiers, PDS URLs)

For every held-out traverse and operating point (1/2, 1/4, 1/8) the POSITION retained set is re-derived with the frozen
deepsift.evaluation.traverse code, together with its farthest-point selection trace (order + distance at selection), and
ASSERTED to reproduce the stored per-traverse result rows exactly (coverage, max nearest-kept distance, bytes, frames
retained, stereo). Nothing is recomputed for publication beyond that deterministic replay; the build stops on any mismatch.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "pipeline"))

from deepsift.evaluation import traverse as T  # noqa: E402
from deepsift.imaging.acquisitions import group_acquisitions  # noqa: E402

RUN = "artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2"
OUT = ROOT / "apps" / "web" / "data" / "mission-control.json"
FRACTIONS = [0.5, 0.25, 0.125]
RADIUS = 5.0
PDS_BASE = "https://planetarydata.jpl.nasa.gov/img/data/msl/MSLNAV_0XXX/DATA/"


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "")).replace(tzinfo=timezone.utc).timestamp()


def fps_trace(D: np.ndarray, k: int) -> list[tuple[int, float]]:
    """Same algorithm as traverse.fps, keeping the selection order and the distance at which each frame was chosen."""
    sel, trace = [0], [(0, 0.0)]
    dmin = D[0].copy()
    while len(sel) < k:
        j = int(np.argmax(dmin))
        d = float(dmin[j])
        if dmin[j] <= 0:
            rest = [x for x in range(len(D)) if x not in sel]
            if not rest:
                break
            j, d = rest[0], 0.0
        sel.append(j)
        trace.append((j, d))
        dmin = np.minimum(dmin, D[j])
    return trace


def main() -> int:
    obs = [json.loads(x) for x in (ROOT / RUN / "observations.jsonl").read_text().splitlines()]
    E = np.load(ROOT / RUN / "embeddings.npy")
    R = json.loads((ROOT / RUN / "results.json").read_text())
    stored = {(r["sequence"], r["fraction"], r["method"]): r for r in R["traverse"]["rows"]}
    cost = {r["acq_id"]: r for r in json.loads((ROOT / RUN / "byte_accounting_per_eye.json").read_text())}
    acqs = {a["acq_id"]: a for a in group_acquisitions(json.loads((ROOT / "data/manifests/navcam_test.json").read_text())["products"])}
    seqs = defaultdict(list)
    for i in sorted(range(len(obs)), key=lambda i: ts(obs[i]["utc"])):
        seqs[(obs[i]["sol"], obs[i]["sequence_id"])].append(i)
    traverses = []
    for key, fr in seqs.items():
        if not key[1].startswith("trav"):
            continue
        fr = [i for i in fr if "landing_x" in obs[i]["location_context"]]
        if len(fr) < 10:
            continue
        name = f"{key[0]}:{key[1]}"
        xy = np.array([[obs[i]["location_context"]["landing_x"], obs[i]["location_context"]["landing_y"]] for i in fr])
        em = E[fr]
        Dp = np.linalg.norm(xy[:, None] - xy[None], axis=2)
        t0 = ts(obs[fr[0]]["utc"])
        frames = []
        for j, i in enumerate(fr):
            o, a, c = obs[i], acqs[obs[i]["id"]], cost[obs[i]["id"]]
            prim = sorted((p for p in a["primaries"] if p["tier"] == a["primary_tier"]), key=lambda p: p["eye"])
            thumbs = sorted(a["thumbnails"], key=lambda p: p["eye"])
            for p in prim + thumbs:     # every product URL must follow the compact base/SOL/ID.LBL form rebuilt by the web app
                assert p["url_lbl"] == f"{PDS_BASE}SOL{o['sol']:05d}/{p['product_id']}.LBL", p["url_lbl"]
            frames.append({
                "i": j, "acq_id": o["id"], "utc": o["utc"], "t_s": round(ts(o["utc"]) - t0, 3), "sol": o["sol"],
                "x": round(float(xy[j, 0] - xy[0, 0]), 3), "y": round(float(xy[j, 1] - xy[0, 1]), 3),
                "pose": o["source_metadata"]["pose"], "places_match": o["location_context"].get("match", "").split("(")[0],
                "stereo": a["stereo"], "tier": a["primary_tier"],
                "primary": [p["product_id"] for p in prim], "thumbnails": [p["product_id"] for p in thumbs],
                "size": f'{prim[0]["line_samples"]}×{prim[0]["lines"]}', "compression": prim[0]["compression"],
                "full_bytes": c["FULL_pair"], "thumb_bytes": c["THUMBNAIL_pair"]})
        policies = {}
        full_all = sum(f["full_bytes"] or 0 for f in frames)
        for f in FRACTIONS:
            k = max(1, int(np.ceil(f * len(fr))))
            trace = fps_trace(Dp, k)
            kept = sorted({j for j, _ in trace})
            assert kept == T.select("METADATA_POSITION", xy, em, f), (name, f, "trace differs from frozen selection")
            m = T.metrics(xy, em, kept, RADIUS)
            st = stored[(name, f, "METADATA_POSITION")]
            nearest = np.argmin(Dp[:, kept], axis=1)
            near_d = Dp[np.arange(len(fr)), [kept[n] for n in nearest]]
            byt = sum(frames[j]["full_bytes"] or 0 for j in kept) + sum(frames[j]["thumb_bytes"] or 0 for j in range(len(fr)) if j not in kept)
            broken = sum(1 for j in kept if frames[j]["stereo"] and frames[j]["full_bytes"] is None)
            checks = {"position_coverage": m["position_coverage"], "max_distance_to_kept_m": m["max_distance_to_kept_m"],
                      "frames_retained": m["frames_retained"], "bytes": byt, "bytes_send_all": full_all, "stereo_broken": broken}
            for kk, v in checks.items():
                assert abs(v - st[kk]) < 1e-6, (name, f, kk, v, st[kk])
            assert abs(float(near_d.max()) - st["max_distance_to_kept_m"]) < 1e-9
            policies[str(f)] = {
                "kept": kept, "trace": [[j, round(d, 3)] for j, d in trace],
                "nearest": [[int(kept[n]), round(float(d), 3)] for n, d in zip(nearest, near_d)],
                "metrics": {"bytes_fraction": st["bytes"] / st["bytes_send_all"], "coverage_5m": st["position_coverage"],
                            "max_distance_to_kept_m": st["max_distance_to_kept_m"], "frames_retained": st["frames_retained"],
                            "stereo_broken": st["stereo_broken"], "stereo_kept_full": st["stereo_kept_full"], "unique_positions": st["unique_positions"]}}
        sa = stored[(name, 1.0, "SEND_ALL")]
        traverses.append({"sequence": name, "sol": key[0], "sequence_id": key[1], "frames_count": len(fr),
                          "length_m": sa["traverse_length_m"], "duration_s": frames[-1]["t_s"], "frames": frames,
                          "send_all": {"bytes": sa["bytes_send_all"], "stereo_kept_full": sa["stereo_kept_full"]}, "policies": policies})
    S = R["traverse"]["summary"]
    op = lambda s: {k: s[k] for k in ("bytes_fraction", "coverage_5m", "max_distance_to_kept_m_worst", "stereo_broken", "stereo_kept_full",  # noqa: E731
                                      "unique_positions", "visual_change_coverage", "sequences")}
    rel = json.loads((ROOT / "apps/web/data/release.json").read_text())
    out = {"label": "HISTORICAL REPLAY · Curiosity Navcam · sols 950–979 · held-out test", "pds_base": PDS_BASE,
           "source": {"run": RUN, "results": f"{RUN}/results.json", "manifest": "data/manifests/navcam_test.json",
                      "verification": "POSITION retained sets re-derived with deepsift.evaluation.traverse and asserted equal to the stored rows"},
           "primary": {"claim": R["primary"]["claim"], "result": R["primary"]["RESULT"], **R["primary"]["metrics"]},
           "operating_points": {"send_all": op(S["1.0|SEND_ALL"]), **{str(f): op(S[f"{f}|METADATA_POSITION"]) for f in FRACTIONS}},
           "negative_results": [{"name": f["name"], "verdict": f["verdict"], "phase": f["phase"]} for f in rel["funnel"] if f["verdict"] != "KEEP"],
           "representative": rel["replay"]["representative"], "traverses": traverses}
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    print(f"→ {OUT.relative_to(ROOT)} · {len(traverses)} traverses · {sum(t['frames_count'] for t in traverses)} frames · "
          f"{OUT.stat().st_size / 1e3:.0f} kB · all retained sets verified against stored rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
