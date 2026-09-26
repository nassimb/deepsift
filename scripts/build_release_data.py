#!/usr/bin/env python3
"""Build apps/web/data/release.json for the DEEPSIFT v1 research release — from frozen artifacts and git only.

    uv run python scripts/build_release_data.py

No experiment is re-run and no result is recomputed for publication. Replay geometry (which frames POSITION keeps) is
re-derived with the frozen deepsift.evaluation.traverse code and ASSERTED to reproduce the stored per-sequence rows of the
final-test run exactly; if it does not, the build stops. Every published number carries the artifact path it came from.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "pipeline"))

from deepsift.evaluation import traverse as T  # noqa: E402
from deepsift.imaging.acquisitions import group_acquisitions  # noqa: E402

FINAL = "artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2"
VAL2 = "artifacts/phase3_4/20260926T165307-phase3.4-val2-1248"
VAL1 = "artifacts/phase3_3/20260926T142033-phase3.3-val-2a31"
DEV = "artifacts/phase3_3/20260926T134654-phase3.3-dev-32ec"
P32 = "artifacts/phase3_2/20260925T135920-phase3.2-dev-corrective-ceb8"
OUT = ROOT / "apps" / "web" / "data" / "release.json"


def J(p):
    return json.loads((ROOT / p).read_text())


def sha(p):
    return hashlib.sha256((ROOT / p).read_bytes()).hexdigest()


def git(*a):
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def tag(t):
    c = git("rev-list", "-n", "1", t)
    return {"tag": t, "commit": c[:7], "date": git("log", "-1", "--format=%cI", c)}


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "")).replace(tzinfo=timezone.utc).timestamp()


def replay_geometry():
    """Frames of every qualifying final-test traverse + the frames POSITION keeps (re-derived, asserted equal to stored rows)."""
    obs = [json.loads(x) for x in (ROOT / FINAL / "observations.jsonl").read_text().splitlines()]
    E = np.load(ROOT / FINAL / "embeddings.npy")
    acqs = group_acquisitions(J("data/manifests/navcam_test.json")["products"])
    cost = {r["acq_id"]: r for r in J(f"{FINAL}/byte_accounting_per_eye.json")}
    stored = {(r["sequence"], r["fraction"], r["method"]): r for r in J(f"{FINAL}/results.json")["traverse"]["rows"]}
    seqs = defaultdict(list)
    for i in sorted(range(len(obs)), key=lambda i: ts(obs[i]["utc"])):
        seqs[(obs[i]["sol"], obs[i]["sequence_id"])].append(i)
    out = []
    for key, fr in seqs.items():
        if not key[1].startswith("trav"):
            continue
        fr = [i for i in fr if "landing_x" in obs[i]["location_context"]]
        if len(fr) < 10:
            continue
        name = f"{key[0]}:{key[1]}"
        xy = np.array([[obs[i]["location_context"]["landing_x"], obs[i]["location_context"]["landing_y"]] for i in fr])
        em = E[fr]
        kept = {}
        for f in (0.5, 0.25, 0.125):
            s = T.select("METADATA_POSITION", xy, em, f)
            m = T.metrics(xy, em, s)
            st = stored[(name, f, "METADATA_POSITION")]
            for k in ("position_coverage", "max_distance_to_kept_m", "max_gap_m", "visual_change_coverage", "frames_retained"):
                assert abs(m[k] - st[k]) < 1e-9, (name, f, k)
            kept[str(f)] = s
        s4 = kept["0.25"]
        d = np.linalg.norm(xy[:, None, :] - xy[s4][None, :, :], axis=2)
        near = d.min(axis=1)
        o0 = xy[0]
        out.append({"sequence": name, "sol": key[0], "frames": len(fr),
                    "length_m": stored[(name, 1.0, "SEND_ALL")]["traverse_length_m"],
                    "points": [{"x": round(float(p[0] - o0[0]), 3), "y": round(float(p[1] - o0[1]), 3), "utc": obs[i]["utc"],
                                "stereo": acqs[i]["stereo"], "pose": obs[i]["source_metadata"]["pose"],
                                "full_bytes": cost[obs[i]["id"]]["FULL_pair"], "thumb_bytes": cost[obs[i]["id"]]["THUMBNAIL_pair"],
                                "nearest_kept_m_quarter": round(float(near[j]), 3)} for j, (i, p) in enumerate(zip(fr, xy))],
                    "kept_position": kept,
                    "metrics": {str(f): {k: stored[(name, f, "METADATA_POSITION")][k] for k in
                                         ("bytes", "bytes_send_all", "position_coverage", "max_distance_to_kept_m", "stereo_broken", "frames_retained")}
                                for f in (0.5, 0.25, 0.125)}})
    return out


def main() -> int:
    F = J(f"{FINAL}/results.json")
    cfg = J("config/phase3_final_test_config.json")
    ds = J(f"{FINAL}/dataset_report.json")
    p34, p33 = J(f"{VAL2}/results.json"), J(f"{VAL1}/results.json")
    home = J("apps/web/data/home-summary.json")
    p32 = J(f"{P32}/results.json")
    four = F["four_period"]
    rename = {"DEVELOPMENT 412–430": "development", "VALIDATION1 779–820": "validation1", "VALIDATION2 1100–1129": "validation2", "TEST 950–979": "test"}
    periods = [{"id": rename[k], "label": k, "sols": [int(x) for x in k.split()[-1].split("–")],
                "position": {m: v["POSITION"][m] for m in ("bytes_fraction", "coverage_5m", "max_distance_to_kept_m_worst", "stereo_broken", "stereo_kept_full",
                                                          "visual_change_coverage", "sequences")},
                "position_plus_embedding": {m: v["POSITION_PLUS_EMBEDDING_CHANGE"][m] for m in ("bytes_fraction", "coverage_5m", "max_distance_to_kept_m_worst",
                                                                                                "stereo_broken", "visual_change_coverage")},
                "embedding_gain": v["embedding_gain"]} for k, v in four.items()]
    test_files = sorted((ROOT / "data/raw/navcam/MSLNAV_0XXX/DATA").glob("SOL0095*/*.IMG")) + sorted((ROOT / "data/raw/navcam/MSLNAV_0XXX/DATA").glob("SOL0096*/*.IMG"))
    first_test_file = min(p.stat().st_mtime for p in test_files)
    frozen = tag("phase3-final-test-config-frozen")
    rel = {
        "generated_at": datetime.now(timezone.utc).isoformat(), "git_head": git("rev-parse", "--short", "HEAD"),
        "sources": {"final": f"{FINAL}/results.json", "final_dataset": f"{FINAL}/dataset_report.json", "final_config": "config/phase3_final_test_config.json",
                    "validation2": f"{VAL2}/results.json", "validation1": f"{VAL1}/results.json", "development": f"{DEV}/results.json",
                    "phase2_jev": "apps/web/data/home-summary.json (jev block, run " + home["jev"]["run_id"] + ")", "phase3_2": f"{P32}/results.json",
                    "integrity": "docs/release/science-artifacts.json"},
        "headline": {"claim": F["primary"]["claim"], "result": F["primary"]["RESULT"], "fraction": 0.25, **F["primary"]["metrics"],
                     "criteria": F["primary"]["criteria"], "scheduler_violations": F["scheduler_v3"]["total_violations"],
                     "single_eye_violations": F["scheduler_v3"]["single_eye_usable_violations"], "config_hash": cfg["config_hash"],
                     "config_commit": frozen["commit"], "result_commit": tag("phase3-final-test-complete")["commit"]},
        "test_dataset": {k: ds[k] for k in ("n_active_sols", "acquisitions", "stereo", "mono", "products", "download_bytes_archive", "sequences",
                                            "traverse_sequences_ge_10_frames", "traverse_frames", "traverse_frames_with_places_position", "estimated_downlink_full_bytes")},
        "final_summary": F["traverse"]["summary"],
        "secondary": F["secondary_embedding"],
        "periods": periods,
        "funnel": [
            {"name": "Jev semantic ranking", "verdict": "DROP", "phase": "Phase 2", "evidence":
             f"AUROC difference vs deterministic rules {home['jev']['auroc_diff_vs_rules']['with_objective']['diff']:+.4f} "
             f"(95 % CI {home['jev']['auroc_diff_vs_rules']['with_objective']['ci95'][0]:+.3f} to {home['jev']['auroc_diff_vs_rules']['with_objective']['ci95'][1]:+.3f}); "
             f"{home['jev']['live_calls']:,} live calls; pre-registered stop rule → discontinued for ranking", "source": f"apps/web/data/home-summary.json · run {home['jev']['run_id']}"},
            {"name": "Telemetry image ranking", "verdict": "DROP", "phase": "Phase 3.1–3.2", "evidence":
             f"image-independent by construction (0 response to controlled visual change); at 1 % under Scheduler V3 it made "
             f"{p32['schedulers']['comparison']['V3|TELEMETRY-PRIORITY|0.01']['acquisitions_usable']} acquisitions usable at "
             f"{p32['schedulers']['comparison']['V3|TELEMETRY-PRIORITY|0.01']['rover_positions_usable']} rover position — the fewest of six strategies",
             "source": f"{P32}/results.json"},
            {"name": "pHash representative selection", "verdict": "DROP", "phase": "Phase 3.3", "evidence":
             "constrained pHash false-merge rate {:.2f}–{:.2f} on validation1 (limit 0.05); ≤ {:.2f}× traverse compression".format(
                 min(p33["phash"][k]["false_merge_rate_different_scene"] for k in p33["phash"] if k != "PHASH_ONLY"),
                 max(p33["phash"][k]["false_merge_rate_different_scene"] for k in p33["phash"] if k != "PHASH_ONLY"),
                 max(p33["phash"][k]["traverse_compression"] for k in p33["phash"] if k != "PHASH_ONLY")), "source": f"{VAL1}/results.json"},
            {"name": "QUALITY_V2 as a priority modifier", "verdict": "DROP", "phase": "Phase 3.3", "evidence":
             f"false-positive rate {p33['quality_v2_real']['development_fpr']:.1%} in development → {p33['quality_v2_real']['overall']:.1%} on validation1; "
             "kept only as a diagnostic QUALITY_SUSPECT flag", "source": f"{VAL1}/results.json"},
            {"name": "Embedding-assisted selection", "verdict": "NO MEASURABLE ADDED VALUE", "phase": "Phase 3.4 + final test", "evidence":
             "visual-change gain over POSITION at 1/4: " + ", ".join(f"{p['id']} {p['embedding_gain']['visual_change_gain']:+.3f}" for p in periods) +
             " (pre-registered meaningful threshold 0.020)", "source": f"{FINAL}/results.json"},
            {"name": "Rover-position sampling (POSITION)", "verdict": "KEEP", "phase": "all four periods", "evidence":
             "5 m coverage " + ", ".join(f"{p['position']['coverage_5m']:.3f}" for p in periods) + " across development, validation1, validation2, test",
             "source": f"{FINAL}/results.json"},
            {"name": "Scheduler V3 (stereo-safe progressive)", "verdict": "KEEP", "phase": "all four periods", "evidence":
             f"0 monotonicity violations and 0 single-eye stereo pairs in development, validation1 ({p33['scheduler_v3']['total_violations']}), "
             f"validation2 ({p34['scheduler_v3']['total_violations']}) and test ({F['scheduler_v3']['total_violations']})", "source": f"{FINAL}/results.json"},
        ],
        "reproducibility": {
            "periods": [{"id": "development", "sols": [412, 430], "manifest": "data/manifests/navcam_development.json", "run": DEV},
                        {"id": "validation1", "sols": [779, 820], "manifest": "data/manifests/navcam_validation.json", "run": VAL1},
                        {"id": "validation2", "sols": [1100, 1129], "manifest": "data/manifests/navcam_validation2.json", "run": VAL2},
                        {"id": "test", "sols": [950, 979], "manifest": "data/manifests/navcam_test.json", "run": FINAL}],
            "manifest_sha256": {p: sha(p) for p in ("data/manifests/navcam_development.json", "data/manifests/navcam_validation.json",
                                                    "data/manifests/navcam_validation2.json", "data/manifests/navcam_test.json",
                                                    "data/splits/phase3_splits.json", "data/splits/phase3_validation2.json")},
            "configs": [{"path": "config/phase3_3_validation_config.json", "hash": J("config/phase3_3_validation_config.json")["config_hash"]},
                        {"path": "config/phase3_4_validation_config.json", "hash": J("config/phase3_4_validation_config.json")["config_hash"]},
                        {"path": "config/phase3_final_test_config.json", "hash": cfg["config_hash"]}],
            "seeds": {"phase3_3": J(f"{VAL1}/run_manifest.json")["seeds"], "phase3_4": J(f"{VAL2}/run_manifest.json")["seeds"], "final": cfg["evaluation"]["seeds"]},
            "timeline": [dict(tag(t), label=l) for t, l in [
                ("v0.1-baseline", "Phase 1 · telemetry triage prototype"), ("phase2-complete", "Phase 2 · Jev semantic decision evaluation"),
                ("phase3-baseline", "Phase 3 · Navcam downlink baseline"), ("phase3.1-complete", "Phase 3.1 · controlled visual tests"),
                ("phase3.2-complete", "Phase 3.2 · stereo-safe scheduler"), ("phase3.3-config-frozen", "Phase 3.3 · config + rules frozen before validation1 download"),
                ("phase3.3-complete", "Phase 3.3 · validation1 (779–820)"), ("phase3.4-config-frozen", "Phase 3.4 · claim + decision rule pre-registered"),
                ("phase3.4-validation2-frozen", "Phase 3.4 · validation2 interval frozen from listings"), ("phase3.4-complete", "Phase 3.4 · fresh validation (1100–1129)"),
                ("phase3-final-test-config-frozen", "Final test config frozen before download"), ("phase3-final-test-complete", "Final held-out test (950–979)")]],
            "frozen_before_download": {"config_commit_time": frozen["date"],
                                       "first_test_image_written": datetime.fromtimestamp(first_test_file, timezone.utc).isoformat(),
                                       "config_before_download": ts(frozen["date"]) < first_test_file},
            "integrity": {"file": "docs/release/science-artifacts.json", **{k: J("docs/release/science-artifacts.json")[k] for k in ("files", "aggregate_sha256")}},
            "commands": ["uv run python scripts/release_integrity.py --verify", "uv run python scripts/run_phase3_final_test.py --stage analysis --run " + FINAL,
                         "uv run python scripts/build_release_data.py", "uv run python scripts/make_release_figures.py"]},
        "replay": {"label": "HISTORICAL REPLAY · Curiosity Navcam · sols 950–979", "sequences": replay_geometry(),
                   "representative_rule": "the qualifying final-test traverse with the longest path length"},
    }
    rep = max(rel["replay"]["sequences"], key=lambda s: s["length_m"])
    rel["replay"]["representative"] = rep["sequence"]
    OUT.write_text(json.dumps(rel, indent=1, default=str))
    print(f"→ {OUT.relative_to(ROOT)} · {len(rel['replay']['sequences'])} replay sequences · representative {rep['sequence']} "
          f"· frozen before download: {rel['reproducibility']['frozen_before_download']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
