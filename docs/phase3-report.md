# DEEPSIFT Phase 3 — multimodal (imagery + telemetry) triage: baseline report

> **Survivorship bias — read first.** The PDS archive contains only observations that were actually downlinked.
> Phase 3 does **not** reproduce the rover's complete onboard image stream. It tests *retrospective
> bandwidth-constrained prioritization of archived rover observations*, not reconstruction of every image the rover
> could have captured onboard. Anything never downlinked is invisible to every strategy and metric here.

**Status: development baseline (M1–M12). No multimodal fusion, no VLM, no Jev, no UI. Validation and test imagery not
downloaded.**

## Splits (frozen before any image download — `data/splits/phase3_splits.json`, commit `0aeb663`)

| split | sols | how chosen |
|---|---|---|
| development | 412–430 | approved (Phase 2 validation SEP segment) |
| validation | 779–820 | approved (Phase 2 validation FD segment) |
| **test** | **950–979** | first 30-sol window from sol 950 satisfying the pre-declared rule (listings + telemetry availability only): 25 active Navcam sols, 1,194 acquisitions, REMS 29/30, RAD 30/30 sols; outside all Phase 2 sols and the 2013 / 2015 conjunction moratoria (sols 235–262, 1008–1022) |

## Data

Navcam raw EDR (`MSLNAV_0XXX`, PDS Imaging Node): every `.IMG` + `.LBL` of every tier (full F, downsampled D,
subframe S, mono-downsampled M, thumbnail T) for sols 412–430, stored in the archive's own directory structure
(`data/raw/navcam/…`, git-ignored). Manifest with URL, product ID, sol, UTC, SCLK, eye, site/drive/pose, sequence,
tier, compression method/rate/ratio, archive bytes, estimated downlink bytes and SHA-256 of both files:
`data/manifests/navcam_development.json`. PLACES `localized_interp.csv` with its SHA-256 in `data/raw/places/manifest.json`.

## Experimental unit

IMAGE ACQUISITION = all products with the same sol and capture clock (`MSL-NAV-<sol>-<sclk>`). A stereo left/right
pair and each eye's rover thumbnail are ONE acquisition. Features use the primary product (full > subframe > mono-
downsampled > downsampled, left eye first).

## Byte accounting (declared; M11)

* The archive `.IMG` stores **decompressed** pixels (12-bit data in 16-bit words) — archive size is NOT a downlink cost.
* Estimated onboard downlink bytes per product = `LINES × LINE_SAMPLES × INST_CMPRS_RATE / 8`, from the label's
  `COMPRESSION_PARMS` group (the compression actually applied onboard):
  LOCO (lossless) → measured bits/pixel, exact; ICER (lossy) → the byte budget the encoder stops at, an upper bound.
  CCSDS/packet framing and the label itself are not included. Missing fields → **UNKNOWN** (never invented).
* Acquisition tiers: **FULL** = all primary products (both eyes) at their onboard compression; **COMPRESSED** =
  DEEPSIFT ground re-encoding of the primary (8-bit JPEG q50, measured size — *not an onboard product*); **THUMBNAIL**
  = the rover's own thumbnail product (label bytes); **METADATA** = compact JSON record (measured); **NONE**.
* Budget = fraction × Σ FULL bytes (what the mission spent at primary quality).

## Declared parameters (before results)

pHash near-duplicate: same sol and Hamming ≤ 10/64 · SCENE cluster (evaluation, metadata only): same site/drive/pose
and pointing within 15° · telemetry context window ±30 min (frozen Phase 2 detector + RULES utility) · embedding
novelty: 1 − max cosine to earlier acquisitions within 3 sols (causal) · JPEG q50 · budgets 0.1, 0.25, 0.5, 1, 2, 5,
10 % · RANDOM 20 seeds · quality thresholds in `deepsift/imaging/features.py` · vision-model rule in
`scripts/phase3_select_vision_model.py` (development only).

## Development baseline results — run `20260925T132323-phase3-dev-baseline-ff13`

Full tables: `artifacts/phase3/20260925T132323-phase3-dev-baseline-ff13/tables.md` (rendered from `benchmark.json` by
`scripts/phase3_report_tables.py`); figures in the same folder. DEVELOPMENT data only — not an evaluation result.

**Data.** 2,318 products (0.853 GB archive) → **609 acquisitions** (550 stereo, 59 mono; primary tiers D 423, F 134,
M 40, S 12). 13 listed products are excluded by the declared file-name rule (9 engineering column-sum / histogram /
reference-pixel products, 4 "EID" products of one acquisition). Estimated onboard downlink Σ FULL = **161.4 MB** vs
852.8 MB archive (label-derived; 0 UNKNOWN). Per-tier archive/downlink ratio: F 5.3, S 4.2, D 2.2, M 8.6.

**Quality.** 609/609 CLEAN under the declared thresholds — consistent with survivorship (the archive holds frames the
team chose to downlink); the quality stage is untested on real defects until synthetic controls exist.

**Redundancy depends on its definition.** pHash (same sol, ≤10/64 bits): 17 duplicate groups covering 150
acquisitions, largest 33, 17.5 MB (10.9 %) "redundant". But the large pHash groups are drive-imaging sequences
(e.g. `trav00113`, sol 424: 33 downsampled frames at 33 different rover stops); the metadata scene clusters count
them as distinct scenes (25 duplicate clusters, 86 acquisitions, 9.6 MB). Only the 8-frame `ncam00505` group (one
stop, one pointing) is a repeat under both definitions. Sequence id alone is not a duplicate signal (50 sequences, 133 MB).

**Local vision baseline.** MobileNetV2 (ONNX zoo, 14.0 MB, 1,280-d), CPU p50/p95 2.3/2.5 ms, 126 MB peak RSS — picked
on development by the declared rule; stereo-pair retrieval@1 0.64 (ResNet-18 0.63, DINOv2-S 0.62).

**Telemetry context.** REMS gap median 75 s / p90 23 min; RAD gap median 262 s / p90 8.3 min; 306/609 acquisitions
have a frozen-Phase-2 candidate event within ±30 min. PLACES: 59 exact site/drive/pose, 550 drive-level fallback.

**Baselines** (budget = % of Σ FULL). Key rows, unique SCENE CLUSTERS retained at ≥ COMPRESSED (of 548):

| strategy (mode) | 0.1 % | 0.25 % | 0.5 % | 1 % | 2 % | 5 % | 10 % |
|---|---|---|---|---|---|---|---|
| FIFO (policy) | 2 | 16 | 11 | 23 | 26 | 55 | 77 |
| RANDOM (policy, 20 seeds) | 5.9 | 8.7 | 10.2 | 13.4 | 18.4 | 36.4 | 65.8 |
| SIZE-AWARE (policy) | 4 | 4 | 4 | 5 | 19 | 46 | 111 |
| THUMBNAIL-EVERYTHING | 0 | 14 | 9 | 21 | 25 | 56 | 64 |
| PHASH-REPRESENTATIVES | 0 | 14 | 9 | 21 | 23 | 50 | 82 |
| EMBEDDING-NOVELTY (policy) | 2 | 5 | 5 | 13 | 15 | 26 | 37 |
| TELEMETRY-PRIORITY (policy) | 3 | 6 | 2 | 14 | 11 | 15 | 29 |

* **Thumbnails dominate coverage per byte.** A rover thumbnail of every acquisition costs 0.31 MB (0.19 % of Σ FULL):
  every thumbnail-first policy delivers an image of all 609 acquisitions / 548 scene clusters from 0.25 % upward
  (315 at 0.1 %); FULL-first policies deliver 3–85.
* **pHash representatives vs thumbnails-then-FIFO:** equal ≤ 1 %, slightly lower at 2–5 %, higher at 10 % (82 vs 64
  scene clusters, 84 vs 54 pHash groups — the latter circular).
* **Embedding novelty adds no measurable value over pHash** on the non-circular metrics (scene clusters, acquisitions);
  it is confounded with product size (Spearman ρ = 0.58 between novelty and FULL bytes; its top-50 are 41 full frames,
  mean 532 kB vs 265 kB overall), possibly a resolution artefact (full frames are resized from 1024 px, downsampled
  frames are native 256 px). On its own (circular) embedding-coverage proxy it is not better than RANDOM.
* **Telemetry priority adds nothing measurable** on these image-diversity metrics (lowest scene-cluster retention);
  there are no documented image events or human labels yet, so its possible value cannot be assessed.
* **Greedy FULL-first allocation is non-monotonic** (e.g. FIFO 16 usable at 0.25 % but 11 at 0.5 %): a larger budget
  buys a few expensive full frames instead of many cheap re-encodings.
