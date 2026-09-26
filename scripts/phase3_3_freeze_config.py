#!/usr/bin/env python3
"""Phase 3.3 step 1: freeze the exact configuration and PRE-DECLARE the generalization rules BEFORE any validation
imagery is downloaded. Writes config/phase3_3_validation_config.json with a configuration hash.

    uv run python scripts/phase3_3_freeze_config.py

No threshold, weight or rule in this file may change after validation data is inspected. run_phase3_3.py refuses to run
if the recomputed hash (or any listed source-file hash) differs.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "pipeline"))

from deepsift.imaging import similarity as sim  # noqa: E402
from deepsift.imaging import synthetic as v1gen  # noqa: E402
from deepsift.imaging import synthetic_v2 as v2gen  # noqa: E402

OUT = ROOT / "config" / "phase3_3_validation_config.json"
P31 = "artifacts/phase3_1/20260925T133727-phase3.1-dev-controls-0ceb/results.json"
P32 = "artifacts/phase3_2/20260925T135920-phase3.2-dev-corrective-ceb8/results.json"
SOURCES = [
    "services/pipeline/deepsift/evaluation/image_benchmark.py", "services/pipeline/deepsift/imaging/quality_v2.py",
    "services/pipeline/deepsift/imaging/synthetic.py", "services/pipeline/deepsift/imaging/synthetic_v2.py",
    "services/pipeline/deepsift/imaging/similarity.py", "services/pipeline/deepsift/imaging/features.py",
    "services/pipeline/deepsift/imaging/embeddings.py", "services/pipeline/deepsift/imaging/acquisitions.py",
    "services/pipeline/deepsift/imaging/pds3.py", "services/pipeline/deepsift/imaging/navcam.py",
    "services/pipeline/deepsift/multimodal/location.py", "services/pipeline/deepsift/multimodal/temporal_join.py",
    "scripts/run_phase3_baseline.py", "scripts/run_phase3_2.py", "scripts/fetch_navcam.py",
    "config/phase3_vision_model.json", "data/splits/phase3_splits.json",
]
ARTIFACTS = [P31, P32, "artifacts/phase3_2/20260925T135920-phase3.2-dev-corrective-ceb8/byte_accounting_per_eye.json",
             "artifacts/phase3/20260925T132323-phase3-dev-baseline-ff13/benchmark.json",
             "data/manifests/synthetic_controls_v1.json", "data/manifests/synthetic_controls_v2.json",
             "data/review/pairs_v1.json", "data/review/jev_pairwise_v1.json", "docs/phase3.2-report.md"]


def sha(p: str) -> str:
    return hashlib.sha256((ROOT / p).read_bytes()).hexdigest()


def config_hash(cfg: dict) -> str:
    body = {k: v for k, v in cfg.items() if k not in ("config_hash", "written_at")}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def main() -> int:
    git = lambda *a: subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True).stdout.strip()  # noqa: E731
    p31 = json.loads((ROOT / P31).read_text())
    p32 = json.loads((ROOT / P32).read_text())
    cfg = {
        "version": "PHASE3_3_VALIDATION_CONFIG_V1",
        "freeze": {"commit": git("rev-parse", "HEAD"), "tag": "phase3.2-complete", "tag_commit": git("rev-parse", "phase3.2-complete"),
                   "checks_at_freeze": {"pytest": "147 passed, 1 skipped", "typescript": "tsc --noEmit clean", "eslint": "clean"}},
        "splits": {"validation_sols": [779, 820], "test_sols_untouched": [950, 979], "development_sols": [412, 430]},
        "source_sha256": {p: sha(p) for p in SOURCES},
        "artifact_sha256": {p: sha(p) for p in ARTIFACTS},
        "scheduler_v3": {
            "name": "SCHEDULER_V3_STEREO_SAFE", "allocator": "image_benchmark.allocate_progressive over cost_table_v3 (prefix fill "
            "METADATA → THUMBNAIL → COMPRESSED → FULL, stop at first misfit)",
            "tiers": {"THUMBNAIL_PAIR": "L+R rover thumbnails, NASA label estimate", "COMPRESSED_STEREO_PAIR":
                      "L+R JPEG q50 ground re-encoding — SIMULATED PRODUCT TIER (not a NASA flight product)",
                      "FULL_STEREO_PAIR": "L+R primaries, NASA label estimate (LINES×SAMPLES×INST_CMPRS_RATE/8)"},
            "metadata_bytes": "length of the compact JSON acquisition record (run_phase3_baseline M11)", "jpeg_quality": 50,
            "report_budgets_fraction_of_full": [0.001, 0.0025, 0.005, 0.01, 0.02, 0.05, 0.10],
            "monotonicity_grid": "numpy.geomspace(0.0001, 0.30, 80)",
            "monotonicity_metrics": ["acquisitions_represented", "scene_clusters_represented", "rover_positions_represented",
                                     "stereo_pair_present", "stereo_pair_usable"]},
        "quality_v2": {"thresholds": p31["quality"]["v2_thresholds"], "source": P31, "development_false_positive_rate": 0.0361247947454844},
        "synthetic_generator_v2": {
            "generator": v2gen.GENERATOR, "dn_range": [v2gen.DN_LO, v2gen.DN_HI], "levels": v1gen.LEVELS,
            "families": {k: {"kind": v[0], "levels": v[1]} for k, v in v1gen.FAMILIES.items()}, "near_duplicate": v1gen.DUPLICATE[1],
            "per_level": 30, "near_duplicates": 120,
            "validation_source_sampling": "random.Random(seed_for('SYNTH_V2', 'VALIDATION', family)).sample(range(n), 4*30); "
                                          "near-duplicates: seed_for('SYNTH_V2', 'VALIDATION', 'NEAR_DUPLICATE')",
            "validation_control_seed": "seed_for('SYNTH_V2', 'VALIDATION', synthetic_id)",
            "tune_eval_half": "TUNE if int(sha256(acq_id)[:2], 16) % 2 == 0 else EVAL",
            "retry_on_contract_violation": False},
        "phash": {"bits": 64, "max_hamming_bits": sim.PHASH_MAX_BITS, "scope": "same sol"},
        "redundancy_constraints": {"temporal_link_s": 120, "same_rover_stop": "(site, drive)", "site_drive_pose": "(site, drive, pose)",
                                   "scene_cluster": f"same (site, drive, pose) and pointing within {sim.SCENE_MAX_DEG}°"},
        "mobilenetv2": {"model": "mobilenetv2-12", "sha256": json.loads((ROOT / "config/phase3_vision_model.json").read_text())["chosen_sha256"],
                        "preprocessing": "features.to_work: PIL resize to 256×256 (BOX when downsampling, BICUBIC otherwise), "
                                         "scale by fixed 12-bit range /4095 (no per-image stretch) → Embedder: ×255 uint8, BICUBIC 224×224, "
                                         "3-channel replicate, ImageNet mean/std; L2-normalised 1280-d output"},
        "embedding_change": {"novelty": "1 − max cosine similarity to earlier acquisitions within 3 sols (causal)", "novelty_lookback_sols": 3,
                             "change_threshold_cos": p32["embeddings"]["change_thresholds"]["cos"],
                             "change_threshold_hamming": p32["embeddings"]["change_thresholds"]["hamming"],
                             "threshold_origin": "median development stereo L/R distance (Phase 3.2); NOT recomputed on validation"},
        "traverse": {
            "sequence_definition": "same (sol, sequence_id), sequence_id starts with 'trav', ≥ 10 acquisitions, ordered by capture time",
            "positions": "PLACES landing_x / landing_y (metres)", "fractions": [0.5, 0.25, 0.125], "k": "ceil(fraction × frames)",
            "EVERY_NTH_FRAME": "frames 0, step, 2·step … with step = round(1/fraction), truncated to k",
            "UNIFORM_DISTANCE": "k equally spaced odometry targets; nearest unused frame per target",
            "METADATA_POSITION": "farthest-point sampling on Euclidean position distance, start frame 0",
            "EMBEDDING_CHANGE": "farthest-point sampling on embedding cosine distance, start frame 0",
            "POSITION_PLUS_EMBEDDING_CHANGE": "farthest-point sampling on 0.5·D_pos/max(D_pos) + 0.5·D_emb/max(D_emb), start frame 0",
            "bytes": "kept frames at FULL_STEREO_PAIR, the others at THUMBNAIL_PAIR (V3 pair costs)",
            "coverage_radius_m": 5.0, "visual_change_coverage": "mean over frames of max cosine similarity to a kept frame"},
        "strategies_validation": {"FIFO": "strategy_orders FIFO", "RANDOM": "strategy_orders RANDOM (seed 0)", "SIZE_AWARE": "strategy_orders SIZE-AWARE",
                                  "THUMBNAIL_FIRST": "inherent to V3 progressive fill (every thumbnail pair before any compressed pair); "
                                                     "reported as V3·FIFO",
                                  "PHASH_CONSTRAINED": "strategy_orders PHASH-REPRESENTATIVES with groups = pHash ≤ 10 bits AND same rover stop",
                                  "EMBEDDING_CHANGE": "strategy_orders EMBEDDING-NOVELTY",
                                  "POSITION": "traverse METADATA_POSITION (sequence-level method; not a global scheduler order)",
                                  "POSITION_PLUS_EMBEDDING_CHANGE": "traverse method (sequence-level)",
                                  "excluded": "TELEMETRY-PRIORITY (dropped in Phase 3.2; telemetry is descriptive metadata only)"},
        "rules": {
            "declared_before_validation_download": True,
            "PRIMARY_position_plus_embedding_at_one_quarter": {
                "G1_bytes": "bytes fraction of SEND_ALL ≤ 0.35 (substantial reduction)",
                "G2_coverage": "mean 5 m position coverage ≥ 0.90",
                "G3_visual": "visual-change coverage ≥ 0.90",
                "G4_gap": "worst-sequence max spatial gap ≤ 2 × SEND_ALL worst-sequence max gap",
                "G5_stereo": "0 broken stereo pairs",
                "GENERALIZES": "G1–G5 all pass", "PARTIALLY_GENERALIZES": "G1 and G5 pass and exactly one of G2–G4 fails",
                "DOES_NOT_GENERALIZE": "any other outcome", "INCONCLUSIVE": "fewer than 3 validation traverse sequences",
                "justification": "user's suggested criterion plus G1, which makes 'reduce bytes substantially' testable"},
            "S1_scheduler_v3": "GENERALIZES iff 0 monotonicity decreases (5 metrics × 6 orders × 80 budgets) AND stereo usable ≤ pairs with both eyes ≥ COMPRESSED",
            "S2_quality_v2": {"fpr": "GENERALIZES if validation FPR ≤ 2 × development (≤ 7.2 %); PARTIAL if ≤ 3 × (≤ 10.8 %); FAILS otherwise",
                              "recall": "OBVIOUS recall = 1.00 for every engineering family AND MODERATE recall within 0.15 (absolute) of "
                                        "development all-controls recall for every engineering family",
                              "overall": "GENERALIZES iff fpr GENERALIZES and recall passes; PARTIALLY if exactly one holds (or fpr PARTIAL)"},
            "S3_constrained_phash": "SAFE iff every constrained variant has false-merge (different scene) ≤ 0.05 AND duplicate retrieval ≥ 0.95; "
                                    "'pHash alone unsafe' reproduces iff pHash-only false merge ≥ 0.50",
            "S4_embeddings": "DISTINCT SIGNAL iff stereo p50 < consecutive p50 < random p50 (cosine) AND mean over LOCALIZED_STRUCTURE and "
                             "TEXTURE_CHANGE at OBVIOUS of (embedding − pHash change detection) ≥ 0.30, with frozen development thresholds",
            "S5_position": "GENERALIZES iff METADATA_POSITION at 1/4 has mean 5 m coverage ≥ 0.90 AND worst max gap ≤ 2 × SEND_ALL worst",
            "S6_generator": "0 contract violations required; violations are reported as generator failures, never regenerated",
        },
        "jev_optional_transfer_check": {"max_pairs": 20, "max_cost_usd": 0.02, "schema": "JEV_PAIRWISE_V1 unchanged",
                                        "role": "AUXILIARY DIAGNOSTIC — never validation truth, never tuning"},
    }
    cfg["config_hash"] = config_hash(cfg)
    cfg["written_at"] = datetime.now(timezone.utc).isoformat()
    OUT.write_text(json.dumps(cfg, indent=1, ensure_ascii=False))
    print("config hash", cfg["config_hash"], "→", OUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
