# DEEPSIFT Phase 3.3 — out-of-sample validation (Navcam, sols 779–820)

> **Survivorship bias.** The PDS archive holds only observations that were actually downlinked. Phase 3 therefore tests
> retrospective bandwidth-constrained prioritization of archived rover observations, not the complete onboard stream.
>
> **Synthetic data.** All perturbed images are SYNTHETIC CONTROLS: modified copies of NASA PDS observations. None is a
> Mars event.
>
> **Compressed stereo tier.** COMPRESSED_STEREO_PAIR is a SIMULATED PRODUCT TIER (our own JPEG q50 re-encoding), not a
> NASA flight product.

**Question:** do the development findings generalize to a new Curiosity Navcam period?

**Inputs and scope**
- Validation run: `artifacts/phase3_3/20260926T142033-phase3.3-val-2a31/`, produced by `scripts/run_phase3_3.py`.
- Development reference run: `artifacts/phase3_3/20260926T134654-phase3.3-dev-32ec/`.
- Test interval (sols 950–979): not downloaded, not inspected; no image contents, features, benchmark or visual
  inspection.
- No fusion, no VLM, no Jev in the pass/fail result. Telemetry is attached as descriptive metadata only.
- **No threshold, weight, model or rule was changed** after the validation download.

## Freeze, order of operations and reproducibility

The steps below ran in this order:

1. **Freeze.** `phase3.2-complete` = `6b913fa` was verified: 147 tests pass, TypeScript and ESLint are clean, and all
   artifact hashes match.
2. **Configuration and rules committed.** `config/phase3_3_validation_config.json` was committed *before* the download:
   commit `6bce97d`, tag `phase3.3-config-frozen`, hash `87e52b59c77269fc0bb860e5a34a91a3c905ca8cb535cd383e6ffaca1f635ca0`.
   - It records Scheduler V3, the QUALITY_V2 thresholds, Generator V2, pHash (≤ 10 bits), the 120 s link, the same-stop
     definition (site, drive), MobileNetV2 preprocessing, the embedding-change score and its frozen development
     threshold, the POSITION and POSITION + EMBEDDING_CHANGE definitions, and byte accounting.
   - It records all generalization rules.
   - It also holds SHA-256 values for 17 source files. The runner refuses to start if any differs.
3. **Development reproduction.** The runner, applied to development data, reproduces Phase 3.2 exactly on every
   deterministic quantity: 609 observations, FPR 3.6 %, V3 coverage at every budget, traverse table (difference 0.0),
   embedding distances and byte totals.
4. **Seed freeze** (commit `8db6690`, before any validation analysis). This is a **reproducibility fix, not retuning**.
   - Every stochastic component reads from one `SEEDS` constant, recorded in the run manifest.
   - No bootstrap is used.
   - A rerun of the development analysis was byte-identical.
   - The pHash-only 0.850 vs 0.851 difference came from a different (already fixed) control-seed tag, not from
     unseeded randomness.
5. **Download verified.** `data/manifests/navcam_validation_verification.json`: 3,246 / 3,246 listed products, every
   SHA-256 matches, 0 problems, 0 test sols on disk.
6. **Validation dataset report** (`dataset_report.json`) produced before any metric.
7. **Frozen analysis.** The run manifest records the rules and seeds with `written_before_metrics: true`.

## Dataset (validation)

| | |
|---|---|
| active sols | 35 of 42 (779–819) |
| acquisitions | 906 (stereo 717, mono 189) |
| products | 3,246 (T 1,623 · F 739 · D 768 · S 68 · M 48; ICER 2,541, LOCO 705) |
| download | 2.00 GB |
| estimated downlink | FULL 378.1 MB · thumbnails 0.46 MB · metadata 0.21 MB; 0 unknown |
| sequences | 139 (acquisitions: NCAM 555, TRAV 350, SAPP 1); 11 traverse sequences ≥ 10 frames (343 frames) |
| PLACES join | 906 / 906 (30 exact pose, 876 nearest pose) |
| REMS context | 100 % within 30 min (median gap 336 s) |
| RAD context | 86.8 % within 30 min (median gap 288 s) |

The validation period differs from development in three ways:
- more full-frame images (F 372 vs 134 acquisitions);
- more upward-pointing images (21 % vs 9 % of acquisitions);
- traverse frames about twice as dense (median spacing 0.7 m vs 1.6 m).

## Scheduler V3 — **GENERALIZES**

- **0 monotonicity decreases** across 5 metrics × 6 orders × 80 budgets.
- **0 stereo pairs usable with a single eye.**
- Full-quality stereo starts at about 16 % of Σ FULL (development: about 18 %).

FIFO. Each cell gives acquisitions represented / usable · scene clusters · rover positions · stereo present / usable /
full · MB.

| budget | development | validation |
|---|---|---|
| 0.1 % | 21/0 · 21 · 14 · 21/0/0 · 0.16 | 256/0 · 235 · 89 · 180/0/0 · 0.38 |
| 0.25 % | 346/0 · 314 · 135 · 320/0/0 · 0.40 | 906/4 · 804 · 398 · 717/0/0 · 0.88 |
| 0.5 % | 609/16 · 548 · 226 · 550/16/0 · 0.80 | 906/28 · 804 · 398 · 717/24/0 · 1.88 |
| 1 % | 609/49 · 548 · 226 · 550/48/0 · 1.59 | 906/58 · 804 · 398 · 717/54/0 · 3.78 |
| 2 % | 609/89 · 548 · 226 · 550/88/0 · 3.22 | 906/108 · 804 · 398 · 717/82/0 · 7.56 |
| 5 % | 609/218 · 548 · 226 · 550/205/0 · 8.04 | 906/301 · 804 · 398 · 717/217/0 · 18.86 |
| 10 % | 609/461 · 548 · 226 · 550/435/0 · 16.13 | 906/584 · 804 · 398 · 717/484/0 · 37.71 |

**Validation strategies at 1 %** (usable acquisitions / scene clusters / stereo pairs / rover positions):

| strategy | usable |
|---|---|
| FIFO = THUMBNAIL_FIRST | 58 / 55 / 54 / 40 |
| RANDOM | 45 / 45 / 37 / 34 |
| SIZE_AWARE | 296 / 254 / 180 / 182 |
| PHASH_CONSTRAINED | 55 / 55 / 54 / 40 |
| EMBEDDING_CHANGE | 34 / 34 / 27 / 20 |

- **THUMBNAIL_FIRST** is inherent to progressive fill, so it equals FIFO.
- **POSITION and POSITION + EMBEDDING_CHANGE** are sequence-level methods and are reported under Traverse.
- **V2 comparison:** under V2, stereo usable stays 0 up to 5 % on validation as well (31 at 10 %).

**Stereo cost (SIMULATED PRODUCT TIER):**

| | validation | development |
|---|---|---|
| compressed stereo pair, median | 63.0 kB | 15.5 kB |
| compressed stereo pair, p90 | 166 kB | 156 kB |
| ratio to full stereo pair | 0.117 | 0.099 |
| ratio to thumbnail pair | 61.5× | 15.1× |

The larger ratio to the thumbnail pair comes from more full frames on validation.

**Thumbnail efficiency** (median thumbnail ÷ full): 0.0066 on validation vs 0.0066 on development.

## QUALITY_V2 — **PARTIALLY GENERALIZES** (pre-declared rule)

**VALIDATION FALSE-POSITIVE RATE: 10.6 %** (96/906), against a DEVELOPMENT FALSE-POSITIVE RATE of 3.6 %. That is within
3× (PARTIAL) but not within 2×.

Reasons: low sharpness 83, brightness out of range 18, V1 suspect 2, zero pixels 1.

| stratum | FPR |
|---|---|
| tier D | 17.0 % (n = 418) |
| tier F | 5.6 % |
| tier S | 5.9 % |
| tier M | 0 % |
| left eye | 10.7 % |
| right eye | 3.5 % |
| NCAM | 16.4 % |
| TRAV | 1.1 % |

By sol it ranges from 0 to 100 %, concentrated in sols 781, 783, 785, 788, 796 and 806.

**Descriptive failure analysis (not used to tune anything)**
- 83 % of the false positives point above the horizon.
- Sequence ncam00548 alone has 67 of 68 frames flagged.
- FPR at or below the horizon: 2.2 % (n = 720). Above the horizon: 43 % (n = 186).
- The low-sharpness threshold, set on development data that was 9 % upward-pointing, flags low-texture upward views as
  engineering faults.

**Synthetic engineering recall** (validation SYNTH_V2 controls; all controls, OBVIOUS / MODERATE / SUBTLE / NEAR-NOISE):

| family | validation | development |
|---|---|---|
| blur | 1.00 / 1.00 / 0.93 / 0.23 | 1.00 / 1.00 / 0.97 / 0.30 |
| exposure | 1.00 / **0.43** / 0.27 / 0.10 | 1.00 / 0.60 / 0.33 / 0.07 |
| missing region · striping · frame dropout | 1.00 at every level | 1.00 at every level |

OBVIOUS is 1.00 everywhere. Exposure MODERATE is 0.17 below development, which misses the ±0.15 criterion, so the recall
rule fails narrowly.

Cross-talk on visual controls: 7.1 % (development 3.3 %), mainly low sharpness.

**Generator V2 contracts: 0 violations** in 960 validation controls, kept separate from the development controls
(`data/manifests/synthetic_controls_v2_validation.json`).

## pHash — constrained pHash is **NOT SAFE** by the pre-declared scene criterion

A false merge here means pairs merged across different metadata scene clusters. The development false-merge rate for
pHash only was 0.85; for every constrained variant it was 0.00.

| variant | validation false merge | scene-merge errors | different-pose merge | position loss | traverse compression | duplicate retrieval |
|---|---|---|---|---|---|---|
| pHash only | 0.24 | 86 | 0.10 | 5.8 % | 1.05× | 1.00 |
| + ≤ 120 s | 0.15 | 49 | 0.04 | 2.3 % | 1.03× | 1.00 |
| + same rover stop | 0.19 | 64 | 0.04 | 2.0 % | 1.00× | 1.00 |
| + site / drive / pose | 0.16 | 50 | 0.00 | 0 % | 1.00× | 1.00 |

- **pHash alone** is still the least safe variant, but its false-merge rate (0.24) is below the ≥ 0.50 needed to
  reproduce the development "unsafe" finding.
- **Constrained variants** all exceed the ≤ 0.05 safety limit.

**Descriptive failure analysis**
- There are 59 direct real pixel-similar, different-scene pairs (development: 510). 46 % of them share a pose; their
  median pointing difference is 0.2° azimuth and 0.6° elevation.
- Most errors are frames with near-identical pointing that the metadata scene definition splits, plus same-pose pointing
  changes chained together by transitive grouping.
- Constrained pHash still removes almost nothing (compression ≤ 1.03×). Validation finds 270 POTENTIALLY_REDUNDANT pairs
  (development: 158).

## Embeddings (MobileNetV2, unchanged) — **DISTINCT SIGNAL**

**Cosine distance p50** (stereo < consecutive < random holds on validation):

| pair type | development | validation |
|---|---|---|
| stereo left/right | 0.029 | 0.054 |
| consecutive frames | 0.129 | 0.095 |
| random pairs | 0.339 | 0.346 |

pHash Hamming medians for the same pair types: 28 / 26 / 30.

**Change detection at OBVIOUS**, using the frozen development threshold:

| family | development embedding | validation embedding | pHash (both periods) |
|---|---|---|---|
| localized structure | 0.50 | 0.73 | 0.00 |
| texture change | 0.93 | 0.83 | 0.00 |
| engineering families | ≥ 0.93 | ≥ 0.93 | — |

The embedding's margin over pHash is 0.78 on validation (development 0.68).

**Resolution:** 64 px vs full frame, cosine distance 0.29 (development 0.26); against the real thumbnail, 0.49
(development 0.51). Sharpness changes 99 % at 64 px in both periods.

**Novelty** p10 / p50 / p90: 0.001 / 0.092 / 0.184 on validation, against 0.015 / 0.046 / 0.109 on development.

## Traverse sampling

11 sequences, 343 frames, all stereo. **Stereo preservation: 0 broken pairs for every method at every fraction.** Each
cell below gives bytes (fraction of SEND_ALL) · 5 m coverage · mean gap · max gap (mean / worst sequence) · visual-change
coverage.

SEND_ALL on validation: 1.00 · 1.000 · 0.67 m · 1.23 / 1.91 m · 1.000.

**Keep 1/2**

| method | validation |
|---|---|
| EVERY_NTH | 0.51 · 1.000 · 1.34 · 2.07 / 2.49 · 0.967 |
| UNIFORM_DISTANCE | 0.51 · 1.000 · 1.34 · 1.93 / 2.78 · 0.959 |
| POSITION | 0.51 · 1.000 · 1.35 · 2.36 / 3.81 · 0.962 |
| EMBEDDING_CHANGE | 0.51 · 1.000 · 1.34 · 3.21 / 4.98 · 0.968 |
| POSITION + EMBEDDING | 0.51 · 1.000 · 1.34 · 2.81 / 4.98 · 0.967 |

**Keep 1/4**

| method | validation |
|---|---|
| EVERY_NTH | 0.26 · 1.000 · 2.55 · 3.71 / 4.87 · 0.934 |
| UNIFORM_DISTANCE | 0.27 · 1.000 · 2.75 · 3.30 / 4.10 · 0.932 |
| POSITION | 0.27 · 1.000 · 2.80 · 3.89 / 6.30 · 0.928 |
| EMBEDDING_CHANGE | 0.26 · 1.000 · 2.67 · 5.15 / 7.96 · 0.932 |
| POSITION + EMBEDDING | 0.27 · 1.000 · 2.80 · 4.78 / 9.08 · 0.932 |

**Keep 1/8**

| method | validation |
|---|---|
| EVERY_NTH | 0.15 · 0.998 · 4.76 · 6.10 / 8.88 · 0.902 |
| UNIFORM_DISTANCE | 0.15 · 1.000 · 5.43 · 6.21 / 7.97 · 0.900 |
| POSITION | 0.15 · 0.994 · 5.44 · 6.80 / 13.01 · 0.898 |
| EMBEDDING_CHANGE | 0.15 · 0.960 · 5.04 · 8.16 / 14.92 · 0.893 |
| POSITION + EMBEDDING | 0.15 · 0.992 · 5.49 · 7.72 / 12.84 · 0.897 |

- **POSITION: DOES NOT GENERALIZE** by rule S5. Coverage is 1.00, but its worst gap (6.30 m) exceeds 2 × the SEND_ALL
  worst gap (3.81 m).
- **Every method at 1/4 fails that relative-gap test** on validation. UNIFORM_DISTANCE comes closest (4.10 m).
- On development, POSITION kept the SEND_ALL gap. On denser validation traverses, farthest-point sampling on position
  is not gap-optimal.

## PRIMARY GENERALIZATION RESULT — **PARTIALLY GENERALIZES**

Pre-declared criterion (config hash `87e52b59…`, committed before the download): POSITION + EMBEDDING_CHANGE at 1/4.

| | development | validation | criterion | validation result |
|---|---|---|---|---|
| G1 bytes fraction | 0.268 | 0.265 | ≤ 0.35 | pass |
| G2 5 m coverage | 1.000 | 1.000 | ≥ 0.90 | pass |
| G3 visual-change coverage | 0.961 | 0.932 | ≥ 0.90 | pass |
| G4 worst max gap | 20.4 m (SEND_ALL 19.5) | 9.08 m (SEND_ALL 1.91) | ≤ 2 × SEND_ALL | **fail** (9.08 > 3.81) |
| G5 broken stereo | 0 | 0 | 0 | pass |

G1 and G5 pass and exactly one of G2–G4 fails, so the verdict is **PARTIALLY_GENERALIZES**.

The byte reduction, 5 m coverage, visual-change coverage and stereo safety reproduced. The worst-gap guarantee did not:
the rule is relative to SEND_ALL spacing, which is about 10× tighter on validation, and the hybrid's worst gap is 4.8× the
SEND_ALL worst. The rule is reported as declared; it was not relaxed afterwards.

## Development vs validation (not pooled)

| finding | development 412–430 | validation 779–820 | status |
|---|---|---|---|
| thumbnail efficiency (median thumb/full) | 0.0066 | 0.0066 | holds |
| QUALITY_V2 FPR | 3.6 % (in-sample) | 10.6 % | worse (PARTIAL) |
| QUALITY_V2 synthetic recall (OBVIOUS / exposure MODERATE) | 1.00 / 0.60 | 1.00 / 0.43 | mostly holds |
| pHash-only false merge | 0.85 | 0.24 | still worst; less extreme |
| constrained pHash false merge | 0.00 | 0.15–0.19 | **fails** |
| stereo embedding distance p50 | 0.029 | 0.054 | ordering holds |
| visual-change sensitivity (OBVIOUS loc. / texture) | 0.50 / 0.93 | 0.73 / 0.83 | holds |
| POSITION 1/4 coverage / worst gap | 1.00 / 20.4 m | 1.00 / 6.30 m | coverage holds; relative gap fails |
| POSITION + EMBEDDING 1/4 coverage / visual | 1.00 / 0.961 | 1.00 / 0.932 | holds; relative gap fails |
| Scheduler V3 monotonicity | 0 violations | 0 violations | holds |

**VALIDATION FAILURE ANALYSIS** (`validation_failure_analysis.json`, for future work only; nothing was tuned from it):
- QUALITY_V2 false positives on upward-pointing, low-texture frames;
- the exposure MODERATE miss;
- pHash scene-merge chains at the same pose;
- visual controls attenuated below the change threshold;
- POSITION and hybrid worst-gap exceedances on dense traverses;
- Scheduler V3 needing about 16 % of Σ FULL before any full-quality stereo pair.
