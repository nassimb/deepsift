# DEEPSIFT — public claims checklist

Run before publishing anything: `uv run python scripts/check_public_claims.py` (regenerate this file with `--write`).
Every number below is recomputed from its frozen source; ✅ means the public wording matches the artifact exactly.

## Numerical claims

| # | claim | public value | check | source | JSON path |
|---|---|---|---|---|---|
| 1 | Final test: full-quality traverse bytes at 1/4 retention | **26.1%** | ✅ | `artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/results.json` | `primary.metrics.bytes_fraction` |
| 2 | Final test: 5 m spatial coverage | **100%** | ✅ | `artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/results.json` | `primary.metrics.coverage_5m` |
| 3 | Final test: 5 m spatial coverage (exact) | **1.000** | ✅ | `artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/results.json` | `primary.metrics.coverage_5m` |
| 4 | Final test: max distance from any archived frame to a retained frame | **2.05 m** | ✅ | `artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/results.json` | `primary.metrics.max_distance_to_kept_m_worst` |
| 5 | Final test: broken stereo pairs | **0** | ✅ | `artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/results.json` | `primary.metrics.stereo_broken` |
| 6 | Final test: stereo pairs kept whole at full quality | **174** | ✅ | `artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/results.json` | `primary.metrics.stereo_kept_full` |
| 7 | Final test: primary criterion result | **PASS** | ✅ | `artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/results.json` | `primary.RESULT` |
| 8 | Final test: Scheduler V3 monotonicity violations | **0** | ✅ | `artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/results.json` | `scheduler_v3.total_violations` |
| 9 | Final test: single-eye usable stereo pairs | **0** | ✅ | `artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/results.json` | `scheduler_v3.single_eye_usable_violations` |
| 10 | Final test: retention fraction (1/4) | **0.25** | ✅ | `config/phase3_final_test_config.json` | `evaluation.primary_fraction` |
| 11 | Final test: bytes criterion | **0.35** | ✅ | `config/phase3_final_test_config.json` | `primary.PASS_iff_all.P1` |
| 12 | Final test: distance criterion | **10 m** | ✅ | `config/phase3_final_test_config.json` | `primary.PASS_iff_all.P3` |
| 13 | Final test: config hash | **6f35d7fc** | ✅ | `config/phase3_final_test_config.json` | `config_hash` |
| 14 | Final test: traverse sequences | **12** | ✅ | `artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/dataset_report.json` | `traverse_sequences_ge_10_frames` |
| 15 | Final test: archived traverse frames | **679** | ✅ | `artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/dataset_report.json` | `traverse_frames` |
| 16 | Final test: active sols | **25** | ✅ | `artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/dataset_report.json` | `n_active_sols` |
| 17 | Final test: Navcam acquisitions | **1,194** | ✅ | `artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/dataset_report.json` | `acquisitions` |
| 18 | Final test: PDS products | **4,342** | ✅ | `artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/dataset_report.json` | `products` |
| 19 | Final test: POSITION visual-change coverage (descriptive) | **0.950** | ✅ | `artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/results.json` | `secondary_embedding.position_visual_1_4` |
| 20 | Final test: POSITION+EMBEDDING visual-change coverage | **0.956** | ✅ | `artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/results.json` | `secondary_embedding.position_plus_embedding_visual_1_4` |
| 21 | Final test: embedding visual-change gain | **+0.005** | ✅ | `artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/results.json` | `secondary_embedding.by_fraction.0.25.visual_change_gain` |
| 22 | Final test: embedding secondary conclusion | **NO MEASURABLE ADDED VALUE** | ✅ | `artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/results.json` | `secondary_embedding.CONCLUSION` |
| 23 | Final test: POSITION+EMBEDDING max distance to kept | **4.89 m** | ✅ | `artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/results.json` | `traverse.summary.0.25|POSITION_PLUS_EMBEDDING_CHANGE.max_distance_to_kept_m_worst` |
| 24 | Final test: EVERY_NTH max distance to kept | **20.04 m** | ✅ | `artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/results.json` | `traverse.summary.0.25|EVERY_NTH_FRAME.max_distance_to_kept_m_worst` |
| 25 | Embedding gain, development | **+0.044** | ✅ | `artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/results.json` | `four_period.DEVELOPMENT 412–430.embedding_gain.visual_change_gain` |
| 26 | Embedding gain, validation 1 | **+0.004** | ✅ | `artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/results.json` | `four_period.VALIDATION1 779–820.embedding_gain.visual_change_gain` |
| 27 | Embedding gain, validation 2 | **+0.001** | ✅ | `artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/results.json` | `four_period.VALIDATION2 1100–1129.embedding_gain.visual_change_gain` |
| 28 | Embedding gain, held-out test | **+0.005** | ✅ | `artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/results.json` | `four_period.TEST 950–979.embedding_gain.visual_change_gain` |
| 29 | POSITION 5 m coverage, development | **1.000** | ✅ | `artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/results.json` | `four_period.DEVELOPMENT 412–430.POSITION.coverage_5m` |
| 30 | POSITION 5 m coverage, validation 1 | **1.000** | ✅ | `artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/results.json` | `four_period.VALIDATION1 779–820.POSITION.coverage_5m` |
| 31 | POSITION 5 m coverage, validation 2 | **1.000** | ✅ | `artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/results.json` | `four_period.VALIDATION2 1100–1129.POSITION.coverage_5m` |
| 32 | POSITION max distance to kept, development | **2.64 m** | ✅ | `artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/results.json` | `four_period.DEVELOPMENT 412–430.POSITION.max_distance_to_kept_m_worst` |
| 33 | POSITION max distance to kept, validation 1 | **2.78 m** | ✅ | `artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/results.json` | `four_period.VALIDATION1 779–820.POSITION.max_distance_to_kept_m_worst` |
| 34 | POSITION max distance to kept, validation 2 | **1.94 m** | ✅ | `artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/results.json` | `four_period.VALIDATION2 1100–1129.POSITION.max_distance_to_kept_m_worst` |
| 35 | POSITION bytes, development | **0.266** | ✅ | `artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/results.json` | `four_period.DEVELOPMENT 412–430.POSITION.bytes_fraction` |
| 36 | POSITION bytes, validation 1 | **0.265** | ✅ | `artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/results.json` | `four_period.VALIDATION1 779–820.POSITION.bytes_fraction` |
| 37 | POSITION bytes, validation 2 | **0.270** | ✅ | `artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/results.json` | `four_period.VALIDATION2 1100–1129.POSITION.bytes_fraction` |
| 38 | Jev: AUROC difference vs deterministic rules | **+0.006** | ✅ | `apps/web/data/home-summary.json` | `jev.auroc_diff_vs_rules.with_objective.diff` |
| 39 | Jev: AUROC difference 95 % CI lower | **-0.020** | ✅ | `apps/web/data/home-summary.json` | `jev.auroc_diff_vs_rules.with_objective.ci95.0` |
| 40 | Jev: AUROC difference 95 % CI upper | **+0.037** | ✅ | `apps/web/data/home-summary.json` | `jev.auroc_diff_vs_rules.with_objective.ci95.1` |
| 41 | Jev: live calls in the final design pilot | **1,500** | ✅ | `apps/web/data/home-summary.json` | `jev.live_calls` |
| 42 | Telemetry ranking: usable acquisitions at 1 % (Scheduler V3) | **7** | ✅ | `artifacts/phase3_2/20260925T135920-phase3.2-dev-corrective-ceb8/results.json` | `schedulers.comparison.V3|TELEMETRY-PRIORITY|0.01.acquisitions_usable` |
| 43 | Telemetry ranking: rover positions at 1 % | **1** | ✅ | `artifacts/phase3_2/20260925T135920-phase3.2-dev-corrective-ceb8/results.json` | `schedulers.comparison.V3|TELEMETRY-PRIORITY|0.01.rover_positions_usable` |
| 44 | QUALITY_V2 false-positive rate, development | **3.6%** | ✅ | `artifacts/phase3_3/20260926T142033-phase3.3-val-2a31/results.json` | `quality_v2_real.development_fpr` |
| 45 | QUALITY_V2 false-positive rate, validation 1 | **10.6%** | ✅ | `artifacts/phase3_3/20260926T142033-phase3.3-val-2a31/results.json` | `quality_v2_real.overall` |
| 46 | Constrained pHash false merge, validation 1 (+120 s) | **0.15** | ✅ | `artifacts/phase3_3/20260926T142033-phase3.3-val-2a31/results.json` | `phash.PHASH_PLUS_TIME_120S.false_merge_rate_different_scene` |
| 47 | Constrained pHash false merge, validation 1 (+same stop) | **0.19** | ✅ | `artifacts/phase3_3/20260926T142033-phase3.3-val-2a31/results.json` | `phash.PHASH_PLUS_SAME_ROVER_STOP.false_merge_rate_different_scene` |
| 48 | Constrained pHash traverse compression (max) | **1.03×** | ✅ | `artifacts/phase3_3/20260926T142033-phase3.3-val-2a31/results.json` | `phash.PHASH_PLUS_TIME_120S.traverse_compression` |
| 49 | Test config committed before first test image | **True** | ✅ | `apps/web/data/release.json` | `reproducibility.frozen_before_download.config_before_download` |
| 50 | Test config commit time | **2026-09-26T13:03:26-04:00** | ✅ | `apps/web/data/release.json` | `reproducibility.frozen_before_download.config_commit_time` |
| 51 | First test image written (UTC) | **2026-09-26T17:03:50** | ✅ | `apps/web/data/release.json` | `reproducibility.frozen_before_download.first_test_image_written` |
| 52 | Scientific artifacts under integrity manifest | **70** | ✅ | `docs/release/science-artifacts.json` | `files` |

## Manual checks before publishing

- [ ] Links point to https://deepsift.space (site) and https://github.com/nassimb/deepsift (repository); no double-brace link placeholder remains (only the per-e-mail NAME / SENDER fields in docs/outreach-note.md).
- [ ] No text says or implies NASA/JPL endorsement, use, review or validation; no NASA logo or insignia in any media.
- [ ] No 'flight-ready', 'production-ready', 'NASA-grade', 'breakthrough', 'revolutionary'.
- [ ] No claim of scientific-value preservation or onboard-stream reconstruction; the PDS survivorship-bias caveat accompanies the headline result.
- [ ] The compressed stereo tier is called a SIMULATED product tier wherever it is mentioned.
- [ ] Visual-change coverage is described as an embedding proxy, never as scientific value.
- [ ] Jev results are described as specific to the tested role (ranking already-detected REMS/RAD candidates), not a general claim about the model.
- [ ] uv run python scripts/release_integrity.py --verify prints INTACT.
- [ ] uv run python scripts/check_public_claims.py exits 0.
