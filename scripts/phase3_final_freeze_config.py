#!/usr/bin/env python3
"""Freeze the Phase 3 FINAL HELD-OUT TEST configuration BEFORE any test imagery (sols 950–979) is downloaded.

    uv run python scripts/phase3_final_freeze_config.py

Writes config/phase3_final_test_config.json (primary binary criterion, secondary embedding question, metrics, seeds,
source hashes). Commit + tag it before `fetch_navcam.py --split test --allow-test`.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from phase3_4_freeze_config import config_hash  # noqa: E402

OUT = ROOT / "config" / "phase3_final_test_config.json"
SOURCES = ["scripts/run_phase3_final_test.py", "scripts/fetch_navcam.py", "scripts/phase3_4_freeze_config.py",
           "services/pipeline/deepsift/evaluation/traverse.py", "services/pipeline/deepsift/evaluation/phase3_pipeline.py",
           "services/pipeline/deepsift/evaluation/image_benchmark.py", "services/pipeline/deepsift/imaging/embeddings.py",
           "services/pipeline/deepsift/imaging/features.py", "services/pipeline/deepsift/imaging/acquisitions.py",
           "services/pipeline/deepsift/imaging/pds3.py", "services/pipeline/deepsift/imaging/navcam.py",
           "services/pipeline/deepsift/imaging/similarity.py", "services/pipeline/deepsift/multimodal/location.py",
           "services/pipeline/deepsift/multimodal/observation.py", "config/phase3_vision_model.json", "data/splits/phase3_splits.json",
           "config/phase3_3_validation_config.json", "config/phase3_4_validation_config.json"]
PRIOR = ["artifacts/phase3_3/20260926T134654-phase3.3-dev-32ec/results.json", "artifacts/phase3_3/20260926T142033-phase3.3-val-2a31/results.json",
         "artifacts/phase3_4/20260926T165307-phase3.4-val2-1248/results.json", "docs/phase3.3-report.md", "docs/phase3.4-report.md"]


def sha(p):
    return hashlib.sha256((ROOT / p).read_bytes()).hexdigest()


def main() -> int:
    git = lambda *a: subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True).stdout.strip()  # noqa: E731
    places = ROOT / "data" / "raw" / "places" / "localized_interp.csv"
    cfg = {
        "version": "PHASE3_FINAL_TEST_CONFIG_V1",
        "test": {"sols": [950, 979], "camera": "MSL Navcam raw EDR (MSLNAV_0XXX)",
                 "status_at_freeze": "never downloaded, inspected, featurised or used for tuning; single use; no replacement interval",
                 "download": "uv run python scripts/fetch_navcam.py --split test --allow-test --workers 2 (only after this config is committed and tagged)"},
        "freeze": {"head_at_freeze": git("rev-parse", "HEAD"), "phase3_4_complete": git("rev-parse", "phase3.4-complete")},
        "source_sha256": {p: sha(p) for p in SOURCES}, "prior_results_sha256": {p: sha(p) for p in PRIOR},
        "places_localized_interp_sha256": hashlib.sha256(places.read_bytes()).hexdigest(),
        "scheduler_v3": {"name": "SCHEDULER_V3_STEREO_SAFE", "implementation": "deepsift.evaluation.phase3_pipeline.allocate_primary → "
                         "image_benchmark.allocate_progressive over image_benchmark.cost_table_v3",
                         "tiers": {"THUMBNAIL_PAIR": "L+R thumbnails, NASA label estimate", "COMPRESSED_STEREO_PAIR": "L+R JPEG q50 — SIMULATED PRODUCT TIER",
                                   "FULL_STEREO_PAIR": "L+R primaries, NASA label estimate LINES×SAMPLES×INST_CMPRS_RATE/8"},
                         "stereo_rule": "a stereo acquisition is usable only when BOTH eyes are sent at COMPRESSED or better; a traverse stereo pair is broken "
                                        "if a kept stereo acquisition has no FULL_STEREO_PAIR cost",
                         "orders_for_monotonicity": ["FIFO", "RANDOM", "SIZE_AWARE", "EMBEDDING_CHANGE"],
                         "monotonicity": "0 decreases in acquisitions / scene clusters / rover positions / stereo present / stereo usable over "
                                         "numpy.geomspace(0.0001, 0.30, 80) × Σ FULL, and 0 single-eye usable stereo pairs"},
        "traverse": {"sequence_definition": "same (sol, sequence_id), id starts with 'trav', ≥ 10 acquisitions with a PLACES position, ordered by UTC",
                     "positions": "PLACES localized_interp landing_x / landing_y (site, drive, pose; nearest pose within site/drive)",
                     "POSITION": "METADATA_POSITION: farthest-point sampling on Euclidean position distance from frame 0, k = ceil(fraction × frames)",
                     "POSITION_PLUS_EMBEDDING_CHANGE": "farthest-point sampling on 0.5·D_pos/max + 0.5·D_emb/max (MobileNetV2 cosine distance), from frame 0",
                     "EVERY_NTH_FRAME": "every round(1/fraction)-th frame from 0, truncated to k", "UNIFORM_DISTANCE": "nearest unused frame to k equal odometry targets",
                     "bytes": "kept frames at FULL_STEREO_PAIR, the others at THUMBNAIL_PAIR; fraction of SEND_ALL (all frames at FULL)",
                     "strategies": ["SEND_ALL", "EVERY_NTH_FRAME", "UNIFORM_DISTANCE", "METADATA_POSITION", "POSITION_PLUS_EMBEDDING_CHANGE"],
                     "not_used": ["pHash ranking", "QUALITY routing", "telemetry ranking", "Jev ranking", "new algorithms"]},
        "embedding_preprocessing": "features.to_work (256×256, fixed /4095) → Embedder mobilenetv2-12 (224×224 bicubic, ImageNet mean/std, L2-normalised 1280-d)",
        "evaluation": {"fractions": [0.5, 0.25, 0.125], "primary_fraction": 0.25, "coverage_radius_m": 5.0,
                       "report_budgets": [0.001, 0.0025, 0.005, 0.01, 0.02, 0.05, 0.10],
                       "metrics": ["bytes fraction", "5 m coverage", "unique rover positions retained", "mean spatial gap", "95th-percentile spatial gap (pooled)",
                                   "largest distance from any archived frame to nearest kept frame (worst sequence)", "max inter-kept gap (worst sequence)",
                                   "visual-change coverage (descriptive)", "stereo pairs preserved", "broken stereo pairs", "Scheduler V3 monotonicity"],
                       "seeds": {"random_order": 0, "bootstrap": 20260926}, "bootstrap_resamples": 10000,
                       "bootstrap": "paired resampling of traverse sequences, 95 % percentile interval"},
        "primary": {"claim": "Scheduler V3 + POSITION at 1/4 retention", "binary": True,
                    "PASS_iff_all": {"P0": "≥ 3 qualifying traverse sequences AND ≥ 90 % of traverse frames with a PLACES position (otherwise FAIL: "
                                           "the claim cannot be demonstrated)",
                                     "P1": "bytes fraction ≤ 0.35 of SEND_ALL", "P2": "mean 5 m coverage ≥ 0.90",
                                     "P3": "largest distance from any archived frame to its nearest kept frame ≤ 10 m in every qualifying sequence",
                                     "P4": "0 broken stereo pairs", "P5": "Scheduler V3 monotonic and stereo-safe (see scheduler_v3.monotonicity)"},
                    "not_in_criterion": "visual-change coverage (reported descriptively only)",
                    "no_rescue": "1/2 and 1/8 are context only; no other operating point, metric or method may replace a failed primary"},
        "secondary": {"question": "Does POSITION + EMBEDDING_CHANGE provide ≥ 0.020 absolute visual-change gain over POSITION at 1/4 retention "
                                  "without reducing 5 m coverage by more than 0.01?",
                      "report": ["visual-change gain", "5 m coverage difference", "largest-distance difference", "95 % resampling intervals"],
                      "MEANINGFUL ADDED VALUE": "gain ≥ 0.020 AND 95 % lower bound > 0 AND coverage difference ≥ −0.01",
                      "HARMFUL": "coverage difference < −0.01, OR gain ≤ −0.020 with 95 % upper bound < 0",
                      "NO MEASURABLE ADDED VALUE": "otherwise",
                      "role": "does not affect the primary PASS/FAIL"},
        "diagnostics": "pHash fields exist only because the observation schema requires them; no quality, pHash, telemetry or Jev signal is "
                       "computed for ranking or used in any criterion",
        "post_download_rule": "after the first test image is downloaded nothing listed here may change; failures are reported, not fixed",
    }
    cfg["config_hash"] = config_hash(cfg)
    cfg["written_at"] = datetime.now(timezone.utc).isoformat()
    OUT.write_text(json.dumps(cfg, indent=1, ensure_ascii=False))
    print("config hash", cfg["config_hash"], "→", OUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
