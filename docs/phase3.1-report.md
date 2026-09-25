# DEEPSIFT Phase 3.1 — controlled evaluation of the visual primitives (development only)

> **Survivorship bias.** The PDS archive holds only observations that were actually downlinked; Phase 3 tests
> retrospective bandwidth-constrained prioritization of archived rover observations, not the complete onboard stream.
> **Synthetic data.** Every perturbed image here is a SYNTHETIC CONTROL — a modified copy of a NASA PDS OBSERVATION made
> by us. None is a Mars anomaly or a scientific event.

Run `artifacts/phase3_1/20260925T133727-phase3.1-dev-controls-0ceb/results.json` (script `scripts/run_phase3_1.py`).
Frozen baseline (tag `phase3-baseline` → `577d5be`) reused unchanged; the baseline tables/report are not modified.
Development sols 412–430 only. No fusion, no VLM, no Jev. Validation / test imagery not downloaded.

## Scheduler

`SCHEDULER_V1_GREEDY` is kept (it reproduces the frozen baseline exactly). `SCHEDULER_V2_PROGRESSIVE`
(`evaluation/image_benchmark.py`) fixes an allocation artifact found in development: it fills METADATA → THUMBNAIL →
COMPRESSED → FULL tier by tier in strategy order and stops at the first increment that does not fit, so coverage is a
prefix and can only grow with budget. Ranking scores are unchanged. On a 40-budget grid (0.05–20 %): V1 shows 1–18
coverage decreases per policy strategy; **V2 shows 0** on acquisitions and scene clusters represented and usable.
Property test: `tests/test_phase3_scheduler.py` (200 random cost tables × 27 budgets).
**Regression to decide:** V2 reaches usable coverage through the COMPRESSED tier, which is a *mono* (left-eye) ground
re-encoding. Stereo pairs delivered with both eyes at usable fidelity, FIFO: V1 10/23 at 1 %, V2 **0/84**; V2 keeps no
stereo pair below 10 %. A stereo-preserving compressed tier (both eyes re-encoded) is needed before V2 can be adopted
wherever stereo matters.

## Synthetic controls (`data/manifests/synthetic_controls_v1.json`, generator SYNTH_V1)

960 controls from development sources (copies; originals untouched; 317 MB PNG-16 under `data/synthetic/`, git-ignored):
7 families × 4 difficulty levels × 30 + 120 near-duplicates. ENGINEERING QUALITY: blur, exposure, missing region,
striping, frame dropout. VISUAL NOVELTY: localized structure, texture change. REDUNDANCY: near-duplicate. Difficulty is
defined by parameters only (`imaging/synthetic.py`). Sources are split TUNE / EVAL by acquisition hash.

## Quality stage

QUALITY_V1 (frozen): 0 % false alarms on the 609 real images but blind to blur (0 % at every level) and weak on
exposure (29 % obvious) and small missing regions. QUALITY_V2 (dev-tuned; thresholds from untouched real images, blur
percentile chosen on the TUNE half), EVAL-half recall (n ≈ 11–18 per cell):

| family | OBVIOUS | MODERATE | SUBTLE | NEAR-NOISE |
|---|---|---|---|---|
| blur | 1.00 | 1.00 | 0.93 | 0.38 |
| exposure | 1.00 | 0.45 | 0.33 | 0.06 |
| missing region | 1.00 | 1.00 | 1.00 | 1.00 |
| striping | 1.00 | 1.00 | 1.00 | 1.00 |
| frame dropout | 1.00 | 1.00 | 1.00 | 1.00 |

False alarms on real images: **3.6 % (in-sample**, 22/609: brightness range 14, low sharpness 9, saturation 3) — to be
re-measured out of sample on validation. Cross-talk: V2 flags 17 % of the VISUAL NOVELTY controls, mostly because the
generator clips dark perturbations to 0 DN, which V2 reads as missing data (a generator artifact to fix).

## Redundancy (separate concepts — never one "duplicate" flag)

PIXEL-SIMILAR 668 pairs · SCENE-SIMILAR 170 · SEQUENCE-REDUNDANT 168 · STEREO-RELATED 550 acquisitions · SEQUENCE-RELATED
12,639 pairs (context only). **510 of 668 pixel-similar pairs are different scenes.**

| grouping | synthetic-duplicate retrieval | false-merge rate (different scene) | traverse compression | rover-stop loss (1 rep/group) |
|---|---|---|---|---|
| pHash only | 1.00 | **0.85** | 1.27× | 1.3 % |
| pHash + time (≤120 s) | 1.00 | 0.00 | 1.00× | 0 % |
| pHash + site/drive/pose | 1.00 | 0.00 | 1.00× | 0 % |
| metadata scene | 1.00 (by construction) | 0.00 (by construction) | 1.02× | 0 % |

The near-duplicate control is easy (σ = 5 DN noise + 1-px shift). Constrained pHash is safe but compresses nothing on
traverses; unconstrained pHash compresses traverses by merging different rover stops.

## Embeddings (MobileNetV2, unchanged)

* **Stereo:** left/right cosine distance median 0.029 (p90 0.27) vs consecutive sequence frames 0.13 vs random pairs
  0.34 — embeddings order these relations; pHash does not (Hamming medians 26 / 28 / 28), and only 1.6 % of stereo pairs
  fall within the pHash threshold (so pHash never merges a stereo pair). STEREO_PAIR is an explicit relationship; the
  acquisition unit keeps both eyes together in FULL.
* **Resolution:** full frame vs a 4×4-averaged (D-like) copy: embedding and pHash identical (the pipeline works at 256 px);
  vs a 64-px copy: embedding cosine distance 0.26, pHash 0 bits; vs the rover's real thumbnail: 0.51 / 2 bits. Sharpness
  changes 99 % at 64 px — resolution-sensitive; brightness invariant; contrast/entropy change 5–11 %.
* **The novelty ↔ product-size link is not a resolution artefact:** novelty rank is stable when every image is
  equalised to 64 px (Spearman 0.85), and its correlation with FULL bytes stays 0.57 (pHash novelty: 0.47). It follows
  sequence type: median novelty TRAV 0.041, NCAM 0.072, SAPP 0.36 — targeted frames are larger and genuinely more novel.
* **Synthetic-change sensitivity** (change = distance > median stereo distance): embeddings detect blur, exposure,
  striping, missing regions and texture at OBVIOUS–MODERATE (0.93–1.00) and localized structure 0.80 / 0.30 / 0.10 /
  0.00; pHash detects almost none (≤ 0.5) — it is invariant to exactly the changes a novelty signal needs.
* **Visual-control retention (V2):** replacing a source by its visual control lifts its retention under EMBEDDING
  NOVELTY at 1 % from 0.05 to 0.63 (OBVIOUS) and 0.03 to 0.22 (MODERATE); pHash representatives +0.02; FIFO / size-aware
  / telemetry 0 by construction.

## Sequence representation (10 traverse sequences, 423 frames)

At equal bytes (same fraction of frames at FULL, the rest as thumbnails):

| keep | method | positions represented | max spatial gap (mean / worst) |
|---|---|---|---|
| 1/2 | METADATA_POSITION_SAMPLE | **0.89** | 15.7 / 19.5 m |
| 1/2 | UNIFORM_TEMPORAL | 0.76 | 16.3 / 22.1 m |
| 1/2 | HYBRID position + visual change | 0.77 | 15.9 / 20.0 m |
| 1/2 | PHASH_REPRESENTATIVES | 0.75 | 18.6 / **39.4 m** |
| 1/4 | METADATA_POSITION_SAMPLE | 0.59 | 16.1 / 20.4 m |
| 1/4 | PHASH_REPRESENTATIVES | 0.47 | 25.3 / **75.2 m** |

SEND_ALL spacing is 15.7 m mean / 19.5 m worst. Position sampling keeps ≈ 0.59 of stops with 1/4 of the frames (≈ 0.63 is
the ceiling at 2.5 frames per stop) without widening gaps; pHash representatives open gaps of 40–78 m.

## Human review

Data model + blinded API (`/api/review/*`) + internal page `/review`. 77 disagreement pairs (`data/review/pairs_v1.json`):
size vs novelty 25, telemetry vs image 25, sequence methods 25, pHash vs embedding 2 (the declared criteria found few
strong disagreements — pHash-similar pairs are also embedding-similar). **0 annotations collected.**

## Telemetry

No measurable contribution: TELEMETRY-PRIORITY does not depend on image content, so it cannot respond to controlled
visual changes (retention lift 0 by construction and as measured), and it retains the fewest scene clusters.
