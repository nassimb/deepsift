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
