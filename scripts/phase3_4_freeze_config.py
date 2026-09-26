#!/usr/bin/env python3
"""Phase 3.4: record the Phase 3.3 findings as final, freeze the simplified pipeline, and PRE-REGISTER the new traverse
claim, the marginal-embedding-value definitions, the final-test decision rule and the VALIDATION2 selection rule —
BEFORE any validation2 interval is selected or downloaded. Writes config/phase3_4_validation_config.json.

    uv run python scripts/phase3_4_freeze_config.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "config" / "phase3_4_validation_config.json"
STUDY = "artifacts/phase3_4/metric_study_development.json"
SOURCES = ["services/pipeline/deepsift/evaluation/traverse.py", "services/pipeline/deepsift/evaluation/phase3_pipeline.py",
           "services/pipeline/deepsift/evaluation/image_benchmark.py", "services/pipeline/deepsift/imaging/embeddings.py",
           "services/pipeline/deepsift/imaging/features.py", "services/pipeline/deepsift/imaging/acquisitions.py",
           "services/pipeline/deepsift/imaging/synthetic.py", "services/pipeline/deepsift/imaging/synthetic_v2.py",
           "services/pipeline/deepsift/imaging/quality_v2.py", "services/pipeline/deepsift/multimodal/location.py",
           "config/phase3_vision_model.json", "config/phase3_3_validation_config.json", "data/splits/phase3_splits.json", STUDY]
PHASE33 = ["artifacts/phase3_3/20260926T142033-phase3.3-val-2a31/results.json", "docs/phase3.3-report.md",
           "data/manifests/navcam_validation.json", "data/manifests/navcam_validation_verification.json"]


def sha(p):
    return hashlib.sha256((ROOT / p).read_bytes()).hexdigest()


def config_hash(cfg: dict) -> str:
    body = {k: v for k, v in cfg.items() if k not in ("config_hash", "written_at")}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def main() -> int:
    git = lambda *a: subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True).stdout.strip()  # noqa: E731
    study = json.loads((ROOT / STUDY).read_text())
    c = study["candidates"]
    cfg = {
        "version": "PHASE3_4_VALIDATION2_CONFIG_V1",
        "freeze": {"phase3_3_commit": git("rev-parse", "phase3.3-complete"), "phase3_3_config_hash": "87e52b59c77269fc0bb860e5a34a91a3c905ca8cb535cd383e6ffaca1f635ca0",
                   "seed_freeze_commit": "8db6690", "head_at_freeze": git("rev-parse", "HEAD")},
        "phase3_3_findings_FINAL_never_rewritten": {
            "GENERALIZED": ["Scheduler V3 monotonicity", "Scheduler V3 stereo safety", "MobileNetV2 retains a distinct visual-change signal"],
            "PARTIALLY_GENERALIZED": {"POSITION + EMBEDDING_CHANGE": {"bytes": "pass", "spatial coverage": "pass", "visual-change coverage": "pass",
                                                                      "stereo preservation": "pass", "relative worst-gap criterion": "FAIL"}},
            "FAILED_NOT_GENERALIZED": ["QUALITY_V2 false-positive rate (validation 10.6 % vs development 3.6 %)",
                                       "constrained pHash safety (false merge 0.15–0.19)"],
            "evidence_sha256": {p: sha(p) for p in PHASE33}},
        "validation1_status": "sols 779–820 informed post-validation development; they are NOT evidence for any Phase 3.4 claim",
        "source_sha256": {p: sha(p) for p in SOURCES},
        "simplified_pipeline": {
            "primary": ["SCHEDULER_V3_STEREO_SAFE", "METADATA_POSITION", "EMBEDDING_CHANGE", "POSITION_PLUS_EMBEDDING_CHANGE"],
            "baselines": ["FIFO", "RANDOM", "SIZE_AWARE", "EVERY_NTH_FRAME", "UNIFORM_DISTANCE"],
            "diagnostic_only": ["PHASH_REPRESENTATIVES", "QUALITY_V2 (QUALITY_SUSPECT flag only)", "TELEMETRY", "JEV"],
            "module": "services/pipeline/deepsift/evaluation/phase3_pipeline.py",
            "traverse_methods": "unchanged frozen Phase 3.3 definitions, now in deepsift/evaluation/traverse.py (reproduction asserted on development)",
            "quality_v3": "not built; orientation-aware quality is FUTURE RESEARCH (POST-VALIDATION DEVELOPMENT), needs its own new validation interval, not a blocker"},
        "spatial_metric_decision": {
            "chosen": "MAX_DISTANCE_TO_KEPT_M = max over every archived traverse frame of the distance (PLACES landing x/y) to its nearest kept frame",
            "why": ["development native spacing has median 0 m (several frames per rover stop) and ~19.5 m drive steps between stops, so any "
                    "gap-between-kept-frames metric (A absolute max gap, D p95 gap) is dominated by the rover's own drive step, not by selection",
                    "C (gap / median native spacing) is undefined on development (median 0 m); B (gap / traverse length) depends on sequence length "
                    "(4.6–116 m on development) and has no mission meaning",
                    "MAX_DISTANCE_TO_KEPT_M is 0 for SEND_ALL at any density, is measured only at archived viewpoints, and has a direct mission "
                    "reading: no archived viewpoint is farther than X m from a downlinked full-quality viewpoint",
                    "on development it separates methods that drop whole rover stops (EVERY_NTH 19.9 m, EMBEDDING_CHANGE 20.0 m at 1/4) from those "
                    "that do not (POSITION 2.6 m, POSITION+EMBEDDING 3.7 m, UNIFORM_DISTANCE 4.4 m)",
                    "threshold 10 m = 2 × the 5 m coverage radius: an isolated uncovered frame is tolerated, a dropped ~20 m stop is not",
                    "motivation disclosed: the need for a density-independent metric came from the Phase 3.3 validation1 diagnosis; the metric "
                    "and threshold were evaluated on development data only"],
            "rejected": {"A_absolute_max_gap": "dominated by native drive step", "B_gap_over_length": "length-dependent, not interpretable",
                         "C_gap_over_native_spacing": "undefined on development (median spacing 0 m)",
                         "D_p95_gap": "reported descriptively; dominated by native drive step on development",
                         "E_coverage_within_x": "kept as the coverage criterion (5 m)"},
            "development_values_at_quarter": {m: {"max_distance_to_kept_m": c[f"0.25|{m}"]["F_max_distance_to_kept_m_worst"],
                                                  "coverage_5m": c[f"0.25|{m}"]["E_coverage_5m"], "visual": c[f"0.25|{m}"]["visual_change_coverage"],
                                                  "p95_gap_m": c[f"0.25|{m}"]["D_p95_gap_m_pooled"]}
                                              for m in ("METADATA_POSITION", "POSITION_PLUS_EMBEDDING_CHANGE", "EMBEDDING_CHANGE", "EVERY_NTH_FRAME", "UNIFORM_DISTANCE")},
            "study": STUDY},
        "primary_claim": {
            "text": "At 1/4-frame retention on traverse sequences, POSITION + EMBEDDING_CHANGE uses ≤ 35 % of SEND_ALL bytes, keeps ≥ 90 % of "
                    "archived traverse frames within 5 m of a kept full-quality frame, keeps ≥ 0.90 visual-change coverage, leaves no archived "
                    "traverse frame farther than 10 m from a kept frame in any sequence, and breaks 0 stereo pairs.",
            "C1_bytes": "bytes fraction of SEND_ALL ≤ 0.35", "C2_coverage": "mean 5 m position coverage ≥ 0.90",
            "C3_visual": "visual-change coverage (mean best cosine similarity to a kept frame) ≥ 0.90",
            "C4_max_distance_to_kept": "max over sequences of MAX_DISTANCE_TO_KEPT_M ≤ 10.0 m", "C5_stereo": "0 broken stereo pairs",
            "PASS": "C1–C5 all hold", "FAIL": "any of C1–C5 fails",
            "INCONCLUSIVE": "fewer than 3 traverse sequences (≥ 10 frames) OR fewer than 90 % of traverse frames with a PLACES position",
            "development_check": {k: c["0.25|POSITION_PLUS_EMBEDDING_CHANGE"][k] for k in ("E_coverage_5m", "visual_change_coverage", "F_max_distance_to_kept_m_worst")},
            "reported_but_not_criteria": ["unique rover positions", "mean gap", "p95 gap", "max gap", "traverse distance represented"]},
        "marginal_embedding_value": {
            "VISUAL_CHANGE_GAIN": "visual-change coverage(POSITION+EMBEDDING) − visual-change coverage(POSITION), at 1/4",
            "SPATIAL_COST": "5 m coverage(POSITION+EMBEDDING) − 5 m coverage(POSITION), at 1/4 (negative = cost)",
            "GAP_DIFFERENCES": "differences in MAX_DISTANCE_TO_KEPT_M, p95 gap, max gap (reported)",
            "uncertainty": "paired bootstrap over traverse sequences, 10,000 resamples, seed 20260926, 95 % percentile interval",
            "MEANINGFUL_GAIN": "VISUAL_CHANGE_GAIN ≥ +0.020 AND bootstrap 95 % lower bound > 0",
            "MATERIAL_SPATIAL_COST": "SPATIAL_COST < −0.020 OR POSITION+EMBEDDING fails C4 while POSITION passes",
            "EQUIVALENT_NO_REGRESSION": "|VISUAL_CHANGE_GAIN| < 0.020 AND SPATIAL_COST ≥ −0.020 AND POSITION+EMBEDDING meets C4",
            "why_0.020": "twice the development spread between the two simple baselines at 1/4 (UNIFORM 0.922 vs EVERY_NTH 0.931, Δ 0.009); "
                         "about half the development gain (+0.044)",
            "development_values": {"VISUAL_CHANGE_GAIN": c["0.25|POSITION_PLUS_EMBEDDING_CHANGE"]["visual_change_coverage"] - c["0.25|METADATA_POSITION"]["visual_change_coverage"],
                                   "SPATIAL_COST": c["0.25|POSITION_PLUS_EMBEDDING_CHANGE"]["E_coverage_5m"] - c["0.25|METADATA_POSITION"]["E_coverage_5m"]}},
        "embedding_distinct_rule": "same as Phase 3.3 S4: stereo p50 < consecutive p50 < random p50 (cosine) AND mean over LOCALIZED_STRUCTURE and "
                                   "TEXTURE_CHANGE at OBVIOUS of (embedding − pHash change detection) ≥ 0.30, frozen development thresholds "
                                   "(cos 0.028908073902130127, Hamming 26); SYNTH_V2 visual controls only (30 per level per family), pHash used "
                                   "as a research comparison only",
        "decision_rule_before_final_test": {
            "PROCEED_TO_FINAL_TEST_950_979_ONLY_IF": ["Scheduler V3: 0 monotonicity decreases (acquisitions, scene clusters, rover positions, stereo "
                                                      "present, stereo usable; primary orders × 80 budgets) and 0 single-eye usable stereo pairs",
                                                      "0 broken stereo pairs in every traverse selection", "primary claim PASS",
                                                      "embedding_distinct_rule holds",
                                                      "MEANINGFUL_GAIN without MATERIAL_SPATIAL_COST, OR EQUIVALENT_NO_REGRESSION"],
            "otherwise": "STOP; do not consume the final test; report that the Phase 3 result did not generalize robustly enough",
            "even_if_passed": "STOP and wait for explicit approval before downloading 950–979"},
        "validation2_selection_rule": {
            "name": "PHASE3_VALIDATION2",
            "text": "Scan windows [s, s+29] for s = 1100, 1101, … and take the FIRST satisfying ALL of: R1 outside every Phase 2 interval "
                    "(evaluation + warm-up sols), outside 412–430, 779–820 and 950–979; R2 ≥ 10 sols with ≥ 1 Navcam acquisition; R3 ≥ 500 "
                    "Navcam acquisitions (unique SCLK with ≥ 1 non-thumbnail EDR); R4 REMS RMD product listed for ≥ 27 of 30 sols; R5 RAD RDR "
                    "product listed for ≥ 27 of 30 sols; R6 no overlap with a known solar-conjunction command moratorium; R7 every Navcam listing "
                    "retrievable, every .IMG has a .LBL, no zero-size .IMG, INDEX.TAB answers. PDS listings only; no image content is read. "
                    "If no window passes before sol 1700 (the 2017 conjunction is not in the moratorium list), STOP and report.",
            "start": 1100, "length": 30, "stop_before": 1700,
            "implementation": "scripts/phase3_4_select_validation2.py (same listing checks as scripts/phase3_select_test.py)"},
        "validation2_pipeline": {"observations": "same M3/M4/M8/M9 steps as Phase 3.3 (acquisitions, PLACES, MobileNetV2, causal novelty); "
                                                 "telemetry NOT joined (not a ranking input; no Phase 2 segment covers these sols)",
                                 "quality_v2": "descriptive FPR only (QUALITY_SUSPECT flags), frozen thresholds, never ranking",
                                 "fractions": [0.5, 0.25, 0.125], "coverage_radius_m": 5.0, "report_budgets": [0.001, 0.0025, 0.005, 0.01, 0.02, 0.05, 0.10],
                                 "monotonicity_grid": "numpy.geomspace(0.0001, 0.30, 80)", "jev": "none", "seeds": {"random_order": 0, "bootstrap": 20260926,
                                 "synthetic_tag": "VALIDATION2", "embedding_random_pairs": 11}},
        "final_test_unchanged": {"sols": [950, 979], "status": "untouched: not downloaded, not inspected, no features"},
    }
    cfg["config_hash"] = config_hash(cfg)
    cfg["written_at"] = datetime.now(timezone.utc).isoformat()
    OUT.write_text(json.dumps(cfg, indent=1, ensure_ascii=False))
    print("config hash", cfg["config_hash"], "→", OUT.relative_to(ROOT))
    print(json.dumps(cfg["marginal_embedding_value"]["development_values"]), json.dumps(cfg["primary_claim"]["development_check"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
