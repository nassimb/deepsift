# DEEPSIFT Phase 3.4 — post-validation simplification + fresh validation (PHASE3_VALIDATION2)

> **Survivorship bias.** The PDS archive holds only downlinked observations. Phase 3 tests retrospective
> bandwidth-constrained prioritization of archived rover observations.
>
> **Simulated tier.** COMPRESSED_STEREO_PAIR is a SIMULATED PRODUCT TIER, not a NASA flight product.
>
> **Test interval.** The final held-out test (sols 950–979) was **not** downloaded, inspected or featurised.
> Validation1 (779–820) informed post-validation development and is **not** evidence for any Phase 3.4 claim.

Run: `artifacts/phase3_4/20260926T165307-phase3.4-val2-1248/`, produced by `scripts/run_phase3_4.py`.

## Order of operations (all in git)

| step | commit / tag |
|---|---|
| Phase 3.3 freeze verified (`e78aaff` = `phase3.3-complete`, config `87e52b59…`, seed freeze `8db6690`, 147 tests, TypeScript, ESLint) | — |
| Phase 3.3 findings recorded as final; simplified pipeline; development-only metric study; pre-registered claim, "meaningful" thresholds, final-test decision rule and VALIDATION2 selection rule | `566c323`, tag `phase3.4-config-frozen`, config hash `3498febc…` |
| VALIDATION2 selected from PDS listings only (first window from sol 1100) | `f800550`, tag `phase3.4-validation2-frozen` |
| fetch script + runner (runner verified to reproduce the development study) | `4ab647e` |
| download verified: 1,914 / 1,914 products, all SHA-256 values match | — |
| dataset report → frozen analysis | this commit |

## Phase 3.3 findings (final, unchanged)

- **Generalized:** Scheduler V3 monotonicity; Scheduler V3 stereo safety; MobileNetV2 visual-change signal.
- **Partially generalized:** POSITION + EMBEDDING_CHANGE. Bytes, coverage, visual change and stereo passed; the relative
  worst-gap criterion failed.
- **Failed:** QUALITY_V2 false-positive rate; constrained pHash safety.

## Simplified pipeline (`deepsift/evaluation/phase3_pipeline.py`)

- **Primary:** Scheduler V3, POSITION, EMBEDDING_CHANGE, POSITION + EMBEDDING_CHANGE.
- **Baselines:** FIFO, RANDOM, SIZE_AWARE, EVERY_NTH, UNIFORM_DISTANCE.
- **Diagnostic only** (code kept, cannot prioritize or discard; tested in `test_phase3_primary_pipeline.py`):
  - pHash representatives;
  - QUALITY_V2, which may only set `QUALITY_SUSPECT`;
  - telemetry;
  - Jev.
- **QUALITY_V3** was not built. It stays future research that would need its own new validation interval.

## Spatial metric (chosen on development only)

The development native spacing has a median of **0 m** (several frames per stop) and drive steps of about 19.5 m. That
rules out the gap-based candidates:

- **A (absolute max gap) and D (p95 gap):** dominated by the rover's own drive step, not by selection.
- **C (gap ÷ median spacing):** undefined on development, because the median spacing is 0 m.
- **B (gap ÷ traverse length):** depends on traverse length.

**Chosen metric: MAX_DISTANCE_TO_KEPT_M**, the distance from every archived traverse frame to its nearest kept frame
(worst over sequences). Its properties:

- it is 0 for SEND_ALL at any frame density;
- it catches dropped rover stops, which read about 20 m for EVERY_NTH and EMBEDDING_CHANGE on development;
- the threshold is **10 m**, twice the 5 m coverage radius.

The need for a density-independent metric came from the validation1 diagnosis; the metric itself was evaluated on
development only (`artifacts/phase3_4/metric_study_development.json`).

## Pre-registered primary claim (config `3498febc…`)

At 1/4 retention, POSITION + EMBEDDING_CHANGE must meet all of:

| criterion | threshold |
|---|---|
| C1 bytes | ≤ 0.35 of SEND_ALL |
| C2 5 m coverage | ≥ 0.90 |
| C3 visual-change coverage | ≥ 0.90 |
| C4 MAX_DISTANCE_TO_KEPT_M | ≤ 10 m in every sequence |
| C5 broken stereo pairs | 0 |

The result is INCONCLUSIVE with fewer than 3 traverse sequences, or with fewer than 90 % of traverse frames positioned.

**"Meaningful" embedding value:**
- gain ≥ +0.020 with a bootstrap lower bound above 0;
- material spatial cost means coverage falls by more than 0.020, or C4 fails where POSITION passes;
- equivalent means |gain| < 0.020, no material cost, and C4 met.

## VALIDATION2 = sols 1100–1129

**Selection:** the first 30-sol window from sol 1100 satisfying R1–R7:
- outside Phase 2 and 412–430 / 779–820 / 950–979;
- 24 active sols (≥ 10 required);
- 553 acquisitions (≥ 500 required);
- REMS listed on 30 of 30 sols, RAD on 29 of 30;
- no conjunction;
- listings reproducible.

The window starting at sol 1100 passed.

**Dataset:**

| | |
|---|---|
| acquisitions | 553 (404 stereo, 149 mono) |
| products | 1,914 |
| download | 1.12 GB |
| estimated full-quality downlink | 195 MB |
| sequences | 92 |
| traverse sequences (≥ 10 frames) | 8, 200 frames, 100 % with a PLACES position |

## Results

**Scheduler V3:** 0 monotonicity decreases (4 primary orders × 80 budgets × 5 metrics) and 0 single-eye usable pairs.
At 1 %:

| order | usable acquisitions | stereo pairs usable |
|---|---|---|
| FIFO | 50 | 50 |
| SIZE_AWARE | 196 | 60 |
| RANDOM | 26 | 16 |
| EMBEDDING_CHANGE | 18 | 13 |

**Primary claim — PASS.** POSITION + EMBEDDING_CHANGE at 1/4:

| criterion | value | result |
|---|---|---|
| C1 bytes | 0.269 | pass |
| C2 5 m coverage | 0.997 | pass |
| C3 visual-change coverage | 0.942 | pass |
| C4 max distance to kept | 5.54 m | pass |
| C5 broken stereo pairs | 0 | pass |

**POSITION vs POSITION + EMBEDDING at equal bytes (VALIDATION2):**

| fraction | method | bytes | 5 m cov. | visual | p95 gap | max gap (mean / worst) | max dist. to kept | stereo broken |
|---|---|---|---|---|---|---|---|---|
| 1/2 | POSITION | 0.514 | 1.000 | 0.965 | 1.99 | 1.97 / 2.83 | 0.96 | 0 |
| 1/2 | POS + EMB | 0.513 | 1.000 | 0.973 | 2.67 | 2.42 / 3.10 | 1.22 | 0 |
| 1/4 | POSITION | 0.270 | 1.000 | 0.941 | 4.25 | 3.39 / 4.73 | 1.94 | 0 |
| 1/4 | POS + EMB | 0.269 | 0.997 | 0.942 | 5.71 | 5.27 / 11.25 | 5.54 | 0 |
| 1/8 | POSITION | 0.145 | 1.000 | 0.916 | 8.49 | 5.95 / 8.56 | 3.90 | 0 |
| 1/8 | POS + EMB | 0.145 | 0.995 | 0.913 | 10.1 | 6.66 / 12.2 | 5.66 | 0 |

Baselines at 1/4 (bytes · coverage · visual · max distance to kept):
- EVERY_NTH: 0.269 · 1.000 · 0.943 · 2.39 m
- UNIFORM_DISTANCE: 0.270 · 1.000 · 0.944 · 1.89 m
- EMBEDDING_CHANGE: 0.269 · 0.987 · 0.942 · 6.93 m

**Marginal embedding value (POS + EMB − POSITION)**, paired bootstrap over sequences, 95 % CI:

| fraction | VISUAL_CHANGE_GAIN | SPATIAL_COST | sequences with visual gain | max dist. to kept Δ |
|---|---|---|---|---|
| 1/2 | +0.0077 [+0.0053, +0.0101] | 0.000 | 8 / 8 | +0.26 m |
| **1/4** | **+0.0011 [−0.0020, +0.0037]** | **−0.0027** | 6 / 8 | **+3.60 m** |
| 1/8 | −0.0029 [−0.0056, +0.0002] | −0.0053 | 2 / 8 | +1.76 m |

**Embedding signal:**
- median distances (stereo / consecutive / random): 0.047 / 0.061 / 0.418, so the ordering holds;
- change detected at OBVIOUS: localized structure 0.47, texture change 0.87; pHash detects 0;
- margin over pHash 0.67 (≥ 0.30 required);
- 0 Generator V2 contract violations.

**QUALITY_V2** (descriptive only, not used): QUALITY_SUSPECT on 3.3 % of acquisitions (1.5 % at or below the horizon,
8.1 % above it). This is **not** evidence that any quality detector is validated.

## Pre-registered decision before the final test

| condition | result |
|---|---|
| Scheduler V3 monotonic and stereo-safe | yes |
| 0 broken stereo pairs | yes |
| primary claim | PASS |
| MobileNetV2 distinct visual-change sensitivity | yes |
| embedding value | MEANINGFUL_GAIN **no** (+0.0011); MATERIAL_SPATIAL_COST no; EQUIVALENT_NO_REGRESSION **yes** |

→ **PROCEED_TO_FINAL_TEST: yes, via equivalence, not via gain.**

## Three-way generalization (not pooled; development and validation1 recomputed with the same code)

| | development 412–430 | validation1 779–820 | validation2 1100–1129 |
|---|---|---|---|
| Scheduler V3 monotonicity violations | 0 | 0 | 0 |
| POSITION 1/4: coverage / visual / max dist. to kept | 1.000 / 0.917 / 2.64 m | 1.000 / 0.928 / 2.78 m | 1.000 / 0.941 / 1.94 m |
| POS + EMB 1/4: coverage / visual / max dist. to kept | 1.000 / 0.961 / 3.67 m | 1.000 / 0.932 / 4.10 m | 0.997 / 0.942 / 5.54 m |
| VISUAL_CHANGE_GAIN at 1/4 (95 % CI) | **+0.044** [0.017, 0.076] | +0.004 [−0.002, 0.010] | +0.001 [−0.002, 0.004] |
| broken stereo pairs | 0 | 0 | 0 |
| embedding stereo < consecutive < random (p50) | 0.029 < 0.129 < 0.339 | 0.054 < 0.095 < 0.346 | 0.047 < 0.061 < 0.418 |

**Reading.** The embedding's visual-change advantage over POSITION was a development effect: it did not replicate on
either later period. POSITION alone matches its visual-change coverage while staying spatially tighter (max distance to
kept 1.9 m vs 5.5 m on validation2). The simplified traverse claim holds. Its embedding component is neutral; it adds
neither measurable value nor measurable harm.
