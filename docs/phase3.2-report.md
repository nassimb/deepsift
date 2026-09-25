# DEEPSIFT Phase 3.2 — corrective and diagnostic evaluation (development only)

> **Survivorship bias.** The PDS archive holds only observations that were actually downlinked. Phase 3 therefore tests
> retrospective bandwidth-constrained prioritization of archived rover observations, not the complete onboard stream.
>
> **Synthetic data.** Every perturbed image here is a SYNTHETIC CONTROL: a modified copy of a NASA PDS OBSERVATION. None
> is a Mars anomaly or a scientific event.
>
> **Jev.** JEV PAIRWISE PREFERENCE is an experimental, text-only reviewer. Jev receives structured metadata/features
> only. It does not see the images. It is not human review, expert review, scientific ground truth, NASA-like review or
> telemetry validation.

**Runs**
- Corrective run: `artifacts/phase3_2/20260925T135920-phase3.2-dev-corrective-ceb8/results.json` (`scripts/run_phase3_2.py`).
- Jev run: `artifacts/phase3_2/20260925T140308-jev-pairwise-ee35/` (`scripts/jev_pairwise_review.py`); copy at
  `data/review/jev_pairwise_v1.json`.

**Scope.** Development sols 412–430 only. Validation and test imagery were not downloaded (on disk: sols 412–429 only).
No fusion, no VLM, no vision or captioning model.

**Phase 3.1 is frozen.** Tag `phase3.1-complete` → `af661c6`. SHA-256 values below were re-verified unchanged after this run:

| file | SHA-256 |
|---|---|
| Phase 3.1 `results.json` | `9b0a4c37…` |
| `synthetic_controls_v1.json` | `548c58a1…` |
| `pairs_v1.json` | `a786e8a1…` |
| `phase3.1-report.md` | `36d7c878…` |
| baseline `benchmark.json` | `26c48a47…` |

## Scheduler V3 — `SCHEDULER_V3_STEREO_SAFE`

`SCHEDULER_V3_STEREO_SAFE` uses the same progressive prefix allocator as V2, with pair costs. For a stereo acquisition,
each tier carries both eyes:

| tier | contents | byte source |
|---|---|---|
| THUMBNAIL_PAIR | L + R rover thumbnails | NASA label estimate |
| COMPRESSED_STEREO_PAIR | L + R JPEG q50 | **SIMULATED PRODUCT TIER** — not a NASA downlink product |
| FULL_STEREO_PAIR | L + R primaries | NASA label estimate |

Per-eye bytes are in `byte_accounting_per_eye.json`. Totals for the 550 stereo acquisitions, left / right:

| tier | left | right |
|---|---|---|
| thumbnail | 0.281 MB | 0.282 MB |
| compressed | 12.95 MB | 12.97 MB |
| full | 76.2 MB | 75.8 MB |

V1 and V2 are unchanged.

**Monotonicity: 0 violations for V3 and for V2.** The grid is 80 log-spaced budgets × 6 strategies × 5 metrics:
acquisitions, scene clusters, rover positions, stereo present and stereo usable. V1 has 21–33 decreases per policy
strategy. The property test runs 150 random cost tables × 42 budgets.

**Stereo-safe.** A stereo acquisition is counted *usable* only when both eyes have been sent at COMPRESSED or better.

The table shows FIFO. Each cell gives acquisitions represented / usable · scene clusters · rover positions ·
stereo present / usable / full · bytes.

| budget | V1 greedy | V2 progressive | V3 stereo-safe |
|---|---|---|---|
| 0.1 % | 3/2 · 3 · 3 · 1/1/1 · 0.16 MB | 61/0 · 61 · 26 · 0/0/0 · 0.16 | 21/0 · 21 · 14 · 21/0/0 · 0.16 |
| 0.25 % | 16/16 · 16 · 12 · 2/2/2 · 0.40 | 609/14 · 548 · 226 · 0/0/0 · 0.40 | 346/0 · 314 · 135 · 320/0/0 · 0.40 |
| 0.5 % | 17/11 · 17 · 13 · 5/5/5 · 0.81 | 609/48 · 548 · 226 · 0/0/0 · 0.73 | 609/16 · 548 · 226 · 550/16/0 · 0.80 |
| 1 % | 27/23 · 27 · 16 · 10/10/10 · 1.61 | 609/85 · 548 · 226 · 0/0/0 · 1.61 | 609/49 · 548 · 226 · 550/48/0 · 1.59 |
| 2 % | 26/26 · 26 · 16 · 21/21/21 · 3.23 | 609/149 · 548 · 226 · 0/0/0 · 3.23 | 609/89 · 548 · 226 · 550/88/0 · 3.22 |
| 5 % | 66/55 · 66 · 31 · 46/46/46 · 8.07 | 609/438 · 548 · 226 · 0/0/0 · 8.07 | 609/218 · 548 · 226 · 550/205/0 · 8.04 |
| 10 % | 85/78 · 84 · 37 · 59/59/59 · 16.14 | 609/609 · 548 · 226 · 17/17/17 · 16.00 | 609/461 · 548 · 226 · 550/435/0 · 16.13 |

The rows for all 6 strategies are in `results.json`.

**Trade-off.** Two eyes cost twice as much, so at 1 % FIFO, V3 makes fewer acquisitions usable than V2 (49 vs 85). In
exchange it makes 48 stereo pairs usable, where V2 makes 0.

**No FULL_STEREO_PAIR at or below 10 %.** V3 is breadth-first: every compressed pair (≈ 26 MB) is sent before any full
pair. Full fidelity starts at about 17 % of Σ FULL.

## Synthetic Generator V2 — `SYNTH_V2`, `imaging/synthetic_v2.py`

- **Contracts.** Each family has allowed changes and forbidden side effects, checked programmatically by `check_contract`.
  The tests are in `tests/test_synthetic_contracts.py` (58).
- **Controls.** 960 development controls, paired with V1: same sources, seeds and TUNE/EVAL halves.
  - Manifest: `data/manifests/synthetic_controls_v2.json`.
  - Images: `data/synthetic/phase3_2/controls_v2` (git-ignored).
- **Contract violations.** V2: **0**. V1 checked against the same contracts: 78.
  - LOCALIZED_STRUCTURE: 21 new zero pixels, 1 new saturation.
  - TEXTURE_CHANGE: 45 new zero pixels, 8 new saturation.
  - NEAR_DUPLICATE: 2 new zero pixels, 1 new saturation.
- **How V2 avoids clipping.** It never clips a visual perturbation; it scales it down and records the factor.
  - OBVIOUS: 68 % of controls scaled down (median scale 0.68).
  - MODERATE: 28 %.
  - SUBTLE: 12 %.
  - NEAR_NOISE: 3 %.
  - Difficulty levels are still defined by the nominal parameters, so V2's OBVIOUS visual controls are weaker in effect
    than V1's.

**QUALITY_V2 (frozen Phase 3.1 thresholds, not retuned).** Engineering families are identical in V1 and V2, so recall is
identical. EVAL-half recall (OBVIOUS / MODERATE / SUBTLE / NEAR-NOISE):

| family | recall |
|---|---|
| blur | 1.00 / 1.00 / 0.93 / 0.38 |
| exposure | 1.00 / 0.45 / 0.33 / 0.06 |
| missing region | 1.00 at every level |
| striping | 1.00 at every level |
| frame dropout | 1.00 at every level |

**Cross-talk.** Share of VISUAL NOVELTY controls flagged by QUALITY_V2:
- Generator V1: 16.7 % (zero_pixels 34, brightness_out_of_range 8, saturation 2).
- Generator V2: **3.3 %** (brightness_out_of_range 8, saturation 1).

The zero-pixel artefact is gone. The residual 3.3 % comes from large bright or dark regions shifting the brightness range.

**DEVELOPMENT FALSE-POSITIVE RATE: 3.6 %** (22/609). The thresholds were derived from these same acquisitions, so this is
not a validated rate.

## pHash safety

Grouping is within a sol; 120 synthetic near-duplicates are injected.

| variant | duplicate retrieval | false merge (different scene) | traverse compression | unique-position loss |
|---|---|---|---|---|
| pHash only | 1.00 | **0.85** | 1.27× | 1.3 % |
| + temporal (≤ 120 s) | 1.00 | 0.00 | 1.00× | 0 |
| + same rover stop (site, drive) | 1.00 | 0.00 | 1.00× | 0 |
| + site / drive / pose | 1.00 | 0.00 | 1.00× | 0 |
| metadata scene grouping | 1.00 | 0.00 (by construction) | 1.02× | 0 |

**Stereo effects.** Grouping is per acquisition, so a group never splits the eyes. Only 1.6 % of L/R pairs fall within
10 bits.

**Taxonomy (kept separate):**

| relationship | count |
|---|---|
| PIXEL_SIMILAR | 668 pairs |
| SCENE_SIMILAR | 170 |
| SEQUENCE_RELATED | 12,639 (context) |
| STEREO_RELATED | 550 acquisitions |
| **POTENTIALLY_REDUNDANT** (pixel- and scene-similar) | **158** |

510 of the 668 pixel-similar pairs are *not* scene-similar.

## Embeddings (MobileNetV2, unchanged)

**Relationship distances** (cosine, p50):

| pair type | p50 | p90 |
|---|---|---|
| stereo L/R | 0.029 | 0.27 |
| consecutive frames | 0.13 | 0.48 |
| random pairs | 0.34 | — |

pHash Hamming medians for the same three pair types are 26 / 28 / 28: pHash does not separate them.

**Change sensitivity on V2 controls** (share above the median stereo distance):

| family | embedding (OBVIOUS → NEAR-NOISE) | pHash |
|---|---|---|
| blur | 1.00 / 0.93 / 0.97 / 0.03 | 0 |
| exposure | 1.00 / 1.00 / 0.03 / 0 | 0 |
| striping | ≥ 0.97 at every level | 0 |
| missing region | 1.00 → 0.77 | ≤ 0.5 |
| texture | 0.93 / 0.73 / 0.10 / 0 | 0 |
| localized structure | 0.50 / 0.27 / 0.10 / 0 | 0 |

Localized structure was 0.80 at OBVIOUS on V1 controls. The drop reflects V2's attenuated amplitude, not a change in the
embedding.

**Resolution** (134 full frames):

| comparison | embedding cosine distance | pHash |
|---|---|---|
| vs D-like 256 px | 0.000 | 0 bits |
| vs 64 px | 0.26 | 0 bits |
| vs the rover's real thumbnail | 0.51 | 2 bits |

- **Quality-feature change at 64 px:** sharpness changes 99 %, contrast 11 %, entropy 7 %, brightness 0.
- **Novelty rank:** full frame vs 64 px, Spearman 0.85.
- **Novelty vs FULL bytes:** Spearman 0.58 at full resolution, 0.57 at 64 px.
- **Implication:** embeddings are comparable only within one tier.

## Traverse experiment

**Research question** (now in `docs/research-methodology.md`): *For rover traverse imaging, how much downlink can be
removed while preserving spatial coverage and meaningful visual change?*

**Setup**
- 10 traverse sequences, 423 frames, all stereo.
- Kept frames are sent as FULL_STEREO_PAIR, the rest as THUMBNAIL_PAIR.
- Bytes are given as a fraction of SEND_ALL.
- Max gap is the mean over sequences / the worst sequence.
- Visual-change coverage is the mean best cosine similarity of every frame to a kept frame.
- Stereo preservation: all kept pairs are complete (0 broken, by construction).

| keep | method | bytes | positions retained | cov. ≤ 5 m | mean gap | max gap | visual cov. |
|---|---|---|---|---|---|---|---|
| all | SEND_ALL | 1.00 | 1.00 | 1.00 | 1.6 m | 15.7 / 19.5 m | 1.000 |
| 1/2 | EVERY_NTH | 0.51 | 0.76 | 1.00 | 3.2 | 16.1 / 20.0 | 0.958 |
| 1/2 | UNIFORM_DISTANCE | 0.51 | 0.75 | 1.00 | 3.2 | 15.7 / 19.5 | 0.967 |
| 1/2 | POSITION | 0.51 | **0.89** | 1.00 | 3.2 | 15.7 / 19.5 | 0.968 |
| 1/2 | EMBEDDING_CHANGE | 0.51 | 0.73 | 1.00 | 3.2 | 16.2 / 20.4 | **0.982** |
| 1/2 | POSITION + EMBEDDING | 0.51 | 0.74 | 1.00 | 3.2 | 16.2 / 20.4 | 0.981 |
| 1/4 | EVERY_NTH | 0.27 | 0.59 | 0.95 | 6.4 | 28.6 / 39.9 | 0.931 |
| 1/4 | UNIFORM_DISTANCE | 0.27 | 0.56 | 1.00 | 6.4 | 15.7 / 19.6 | 0.922 |
| 1/4 | POSITION | 0.27 | **0.59** | 1.00 | 6.4 | 16.1 / 20.4 | 0.917 |
| 1/4 | EMBEDDING_CHANGE | 0.27 | 0.44 | 0.98 | 6.3 | 21.6 / 43.4 | 0.961 |
| 1/4 | POSITION + EMBEDDING | 0.27 | 0.51 | **1.00** | 6.3 | 16.4 / 20.4 | **0.961** |
| 1/8 | EVERY_NTH | 0.14 | 0.30 | 0.93 | 14.7 | 40.8 / 75.7 | 0.905 |
| 1/8 | UNIFORM_DISTANCE | 0.14 | 0.30 | 0.85 | 15.2 | 19.7 / 45.7 | 0.904 |
| 1/8 | POSITION | 0.14 | 0.30 | 0.87 | 15.2 | 20.1 / 45.7 | 0.903 |
| 1/8 | EMBEDDING_CHANGE | 0.14 | 0.28 | 0.93 | 14.6 | 35.2 / 74.4 | **0.936** |
| 1/8 | POSITION + EMBEDDING | 0.14 | 0.30 | **0.93** | 15.0 | 25.6 / 43.4 | 0.932 |

**Development answer.** About 73 % of traverse bytes can be removed (keep 1/4 at FULL, the rest as thumbnails) with
POSITION + EMBEDDING and still:
- keep every frame within 5 m of a kept frame;
- keep the SEND_ALL maximum gap (≈ 16 m);
- reach a visual-change proxy of 0.96.

At 1/8, every method opens gaps of more than 40 m on its worst sequence.

## JEV PAIRWISE REVIEW — label: **JEV PAIRWISE PREFERENCE**

**Input.** Jev received a text-only structured state.
- Per side: camera, stereo, resolution, sequence type code, sol, site/drive/pose, number of acquisitions at that position,
  full-quality kB, QUALITY_V2 check, brightness / contrast / entropy / sharpness / saturated / missing, embedding
  difference from the previous frame, and whether a telemetry event occurred within 30 min.
- For the pair: time gap, distance, same stop / scene / sequence, and embedding and pHash difference between A and B.

**Withheld.** No image, URL, caption, strategy name, rank, score, category or ground truth. `assert_clean` enforces this
on every state.

**Disclosed overlaps with strategy inputs.**
- Downlink size (SIZE-AWARE) and same-position count (POSITION) are visible to Jev.
- The previous-frame difference equals the EMBEDDING-NOVELTY input for 27 of 126 sides.

**Run facts**
- Schema `JEV_PAIRWISE_V1`. Requested `typesafe/jev-1.13`; every call returned `typesafe/jev-1.13-20260917`.
- OpenRouter → provider TypeSafe.
- The cache key includes schema, order, state, questions, model, expected snapshot, SDK and transport.
- Preflight projected $0.0146 (1.5× margin) against the $0.05 cap.

| | |
|---|---|
| pairs | 77 (all of `pairs_v1.json`; ids listed in the summary) |
| live calls | 178 = 77 AB + 77 BA + 12 pairs × 2 uncached repeats · 0 errors |
| cache hits | 0 in the live run; 77/77 identical on the cache re-read (determinism) |
| cost | **$0.0101** (usage.cost) · 240 k input tokens · p50 latency 294 ms |

**Choices, AB order:** A 42 · B 34 · EQUAL 1 · UNSURE 0. Over AB + BA: A 76 · B 77 · EQUAL 1.
Choice confidence p10 / p50 / p90: 0.35 / 0.65 / 0.84. Reason confidence p50: 0.40.

**Reasons (AB):**

| reason | count |
|---|---|
| SPATIAL_COVERAGE | 15 |
| VISUAL_CHANGE | 53 |
| IMAGE_QUALITY | 3 |
| BANDWIDTH_EFFICIENCY | 0 |
| STEREO_VALUE | 6 |
| NO_CLEAR_ADVANTAGE | 0 |

**Agreement (preference alignment, not accuracy).** Decisive AB pairs, with Wilson 95 % intervals:

| strategy | agreement | 95 % CI | n |
|---|---|---|---|
| FIFO | 0.47 | 0.37–0.58 | 76 |
| size-aware | 0.47 | 0.37–0.58 | 76 |
| position sampling | 0.35 | 0.23–0.49 | 49 |
| pHash representatives | 0.34 | 0.25–0.45 | 76 |
| embedding novelty | 0.54 | 0.43–0.65 | 76 |
| telemetry | 0.47 | 0.33–0.61 | 47 |

**Post-hoc feature rules** (`feature_rule_alignment.json`, main calls). Jev's choices follow features it was given:

| rule | agreement |
|---|---|
| stereo over single eye | 0.86 |
| higher entropy | 0.80 |
| larger previous-frame difference | 0.76 |
| full frame over downsampled | 0.76 |
| larger bytes | 0.53 |
| telemetry event nearby | 0.43 |

**Repeatability** (12 stratified pairs, 3 draws each): choice identical in 11/12, reason identical in 10/12. The one
choice flip was P31-001, a low-confidence EQUAL→B. Cache determinism is separate: 77/77.

**A/B positional consistency.**
- 69/77 (0.90) pairs give the same underlying acquisition after swapping.
- Position-A share 0.497 (95 % CI 0.42–0.58): no positional bias detected.

**Answers**
- **Does Jev mostly agree with one simple heuristic?** It does not agree with any of the six strategies (0.34–0.54). It
  does closely follow simple rules over its own input: stereo, entropy, previous-frame change, full resolution.
- **Does it add a distinct preference signal?** It is distinct from the strategies. It leans *against* pHash
  representatives and rare-position sampling, with intervals below 0.5. It is largely explained by a "visually
  richer / more changed / stereo / full-res" rule, so it adds little independent information.
- **Is its preference stable across repeats?** Yes: 11/12 choices and 10/12 reasons.
- **Does it show A/B positional bias?** No detectable bias; 0.90 swap consistency.
- **Is it useful enough to keep as an auxiliary reviewer?** Yes, as a cheap, stable, unbiased *auxiliary diagnostic*.
  It is not a ranking input, not a tuning target and not a substitute for human review. Jev is not ground truth.

The `/review` page now has two modes: HUMAN REVIEW (future; 0 annotations, none fabricated) and **AI REVIEW — JEV 1.13**
(read-only, `GET /api/review/jev`, with the required notice).

## Telemetry — **DROP** (as a prioritization signal)

- **Coverage.** Under V3 at 1 %, TELEMETRY-PRIORITY makes 7 acquisitions usable at **1** rover position, the fewest of the
  6 strategies (FIFO 49 / 24; size-aware 124 / 56).
- **Visual change.** It cannot respond to controlled visual change: it is image-independent by construction, and the
  measured lift is 0.
- **No label supports it.** Its intended value, coincidence with environmental events, is untestable without labels.
  There are 0 human annotations.
- The telemetry context stays in each observation as descriptive metadata. JEV PAIRWISE IS NOT TELEMETRY VALIDATION: its
  0.47 agreement is not used as evidence.
