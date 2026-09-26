# DEEPSIFT Phase 3 — FINAL HELD-OUT TEST (Navcam sols 950–979)

> **Survivorship bias.** The PDS archive holds only observations that were actually downlinked. This result concerns
> retrospective bandwidth-constrained prioritization of archived rover observations. It is not a reconstruction of the
> onboard image stream, not flight readiness, not NASA validation and not a measure of scientific-value preservation.
>
> **Simulated tier.** COMPRESSED_STEREO_PAIR is a SIMULATED PRODUCT TIER. Traverse bytes use NASA label estimates only.

## Frozen configuration

- **Config:** `config/phase3_final_test_config.json`, hash `6f35d7fc205cdffe4a971974362cf77a5bbeb7a6ce518e8831b172292539b49e`.
- **Commit:** `96e0694`, tag `phase3-final-test-config-frozen`.
- **Order:** the config was committed and tagged before the first test image was downloaded. The runner was dry-run on a
  validation2 copy beforehand. No code, threshold, seed or criterion changed after the download.
- **Run:** `artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/`. The analysis ran exactly once.

## Test dataset

| | |
|---|---|
| sols | 950–979 (25 active) |
| acquisitions | 1,194 (977 stereo, 217 mono) |
| products | 4,342 (all listed products present; SHA-256 verified; 0 problems) |
| stereo pairing | every stereo pair has both eyes at the same tier |
| download | 1.71 GB |
| estimated full-quality downlink | 311 MB |
| sequences | 103 |
| traverse sequences (≥ 10 frames) | 12, 679 frames, 100 % with a PLACES position |
| PLACES join | 131 exact pose, 1,063 nearest pose |

## PRIMARY CLAIM — Scheduler V3 + POSITION, 1/4 retention — **PASS**

| criterion | threshold | test | result |
|---|---|---|---|
| sufficient data | ≥ 3 sequences, ≥ 90 % positioned | 12 sequences, 100 % | pass |
| bytes fraction of SEND_ALL | ≤ 0.35 | **0.261** | pass |
| 5 m coverage | ≥ 0.90 | **1.000** | pass |
| largest distance, archived frame → nearest kept frame (every sequence) | ≤ 10 m | **2.05 m** | pass |
| broken stereo pairs | 0 | **0** (174 kept pairs complete) | pass |
| Scheduler V3 monotonicity and stereo safety | 0 violations | **0 / 0** | pass |

Descriptive only (not part of the criterion) for POSITION at 1/4:
- visual-change coverage: 0.950;
- unique rover positions retained: 0.27;
- mean gap: 3.58 m; p95 gap: 4.86 m;
- max inter-kept gap: 20.2 m (the native SEND_ALL maximum is 19.7 m).

## All strategies (test)

Each cell: bytes · 5 m coverage · largest distance to kept · p95 gap · worst gap · visual-change coverage.

SEND_ALL: 1.000 · 1.000 · 0 m · 1.21 m · 19.7 m · 1.000.

| method | 1/2 | 1/4 | 1/8 |
|---|---|---|---|
| EVERY_NTH | 0.505 · 1.000 · 2.46 · 2.21 · 20.2 · 0.976 | 0.261 · 0.996 · **20.0** · 4.10 · 39.9 · 0.954 | 0.136 · 0.983 · 20.6 · 9.02 · 41.8 · 0.928 |
| UNIFORM_DISTANCE | 0.507 · 1.000 · 1.74 · 2.92 · 19.7 · 0.973 | 0.260 · 1.000 · 3.03 · 5.89 · 19.7 · 0.950 | 0.136 · 0.974 · 6.53 · 12.0 · 20.2 · 0.925 |
| **POSITION** | 0.514 · 1.000 · 1.00 · 2.77 · 20.2 · 0.972 | **0.261 · 1.000 · 2.05 · 4.86 · 20.2 · 0.950** | 0.138 · 0.983 · 6.53 · 11.1 · 20.2 · 0.925 |
| POSITION + EMBEDDING | 0.501 · 1.000 · 4.31 · 3.61 · 20.8 · 0.980 | 0.257 · 1.000 · 4.89 · 7.77 · 20.8 · 0.956 | 0.135 · **0.947** · 7.35 · 13.9 · 22.9 · 0.926 |

Stereo: 0 broken pairs for every method at every fraction.

## SECONDARY — POSITION + EMBEDDING vs POSITION — **NO MEASURABLE ADDED VALUE**

At 1/4 retention, with paired resampling over 12 sequences:

| | value |
|---|---|
| POSITION visual-change coverage | 0.950 |
| POSITION + EMBEDDING visual-change coverage | 0.956 |
| gain | +0.0054, 95 % CI [+0.0021, +0.0093] |
| 5 m coverage difference | 0.000 |
| largest-distance difference | +2.84 m (worse) |

The gain is statistically above zero but about a quarter of the pre-registered 0.020 threshold, so it is not meaningful.
At 1/8, the embedding term costs 0.036 of 5 m coverage (95 % CI −0.066 to −0.014). That is context only and does not
change the pre-registered 1/4 verdict.

## Four-period generalization

1/4 retention; periods are not pooled; earlier periods recomputed with the frozen code.

| period | POSITION: bytes / 5 m cov. / largest dist. / broken stereo | POS + EMB: bytes / 5 m cov. / largest dist. / broken stereo / visual | embedding gain (95 % CI) |
|---|---|---|---|
| development 412–430 | 0.266 / 1.000 / 2.64 m / 0 | 0.268 / 1.000 / 3.67 m / 0 / 0.961 | +0.044 [+0.018, +0.076] |
| validation1 779–820 | 0.265 / 1.000 / 2.78 m / 0 | 0.265 / 1.000 / 4.10 m / 0 / 0.932 | +0.004 [−0.002, +0.010] |
| validation2 1100–1129 | 0.270 / 1.000 / 1.94 m / 0 | 0.269 / 0.997 / 5.54 m / 0 / 0.942 | +0.001 [−0.002, +0.004] |
| **test 950–979** | **0.261 / 1.000 / 2.05 m / 0** | 0.257 / 1.000 / 4.89 m / 0 / 0.956 | +0.005 [+0.002, +0.009] |

POSITION's visual-change coverage by period: 0.917, 0.928, 0.941 and 0.950. Scheduler V3 monotonicity violations:
0 in every period.

## Conclusion

Across one development period (412–430), two validation periods (779–820 and 1100–1129) and a final held-out Curiosity
Navcam interval (950–979), position-based traverse sampling with a stereo-safe progressive scheduler behaved consistently.
On the held-out test it:

- used **26.1 %** of full-quality traverse bytes;
- kept **1.000** of archived traverse frames within 5 m of a kept full-quality frame;
- left **no archived traverse frame more than 2.05 m** from a kept frame;
- broke **0** stereo pairs;
- kept Scheduler V3 monotonic.

The embedding-change term added no measurable value over position sampling outside development.

**Limitations**
- PDS survivorship bias: only downlinked observations exist in the archive.
- Positions are PLACES interpolations (mostly nearest pose within a site/drive), not per-frame onboard localization.
- The byte model uses label estimates plus a simulated compressed tier.
- "Visual-change coverage" is a MobileNetV2 proxy, not a scientific judgement.
- Traverse sequences only, and only four sol windows from one rover and camera.
- 5 m coverage and the distance-to-kept metric are geometric; they do not measure scientific value.
- QUALITY_V2 and constrained pHash did not generalize (Phase 3.3) and are excluded from the claim.
