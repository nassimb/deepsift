# Phase 3 dataset assessment (read-only, 2026-09-25)

**Status: proposal, awaiting approval. No image product has been downloaded; nothing is implemented.**

Sources inspected: PDS Imaging Node MSL archive (`https://planetarydata.jpl.nasa.gov/img/data/msl/`) — directory
listings, a handful of PDS3 label files, PDS4 XML labels of the PLACES bundle — plus telemetry already on disk.
Reproduce: `scripts/phase3_image_survey.py` (listings → `artifacts/phase3_assessment/listing_survey.json`),
`scripts/phase3_alignment_check.py` (→ `alignment.json`); `structure.json` = movement / sequence summary.
Sizes are Apache-listing sizes (rounded to K/M, ±5 %). Phase-2 TEST sols (732–750, 871–930, 2068–2105) were never listed.

## Archive facts

| | Navcam (engineering, `MSLNAV_0XXX` EDR) | Mastcam (`MSLMST_*`) | MAHLI (`MSLMHL_*`) |
|---|---|---|---|
| Layout | `DATA/SOLnnnnn/`, one directory for the whole mission | volumes of ~90 sols, `DATA/EDR|RDR/SURFACE/<sol>/` | same as Mastcam |
| Index | `INDEX/INDEX.TAB` cumulative, 539 MB (not needed: per-sol listings suffice) | per-volume `EDRINDEX.TAB` 17.6 MB, `RDRINDEX.TAB` 75 MB | per-volume, 8–11 MB |
| Pixel format | PDS3 `.IMG` + detached `.LBL`; 1024×1024 frame, 12-bit in 16-bit; grayscale; stereo L/R | EDR `.DAT` = JPEG (q 65) in MSSS container (needs MSSS decoder); RDR `.IMG` 8/16-bit colour 1344×1200 (4.9–9.6 MB) | as Mastcam (1600×1200 colour) |
| Product tiers present | every acquisition: one primary (F full / D downsampled 256² / S subframe / M) **plus its rover thumbnail T** | E full, I thumbnail 160×144, C, D | E, I, C + focus-merge products (R, S, T, U) |
| Onboard compression recorded | `INST_CMPRS_NAME` / `INST_CMPRS_RATE` (ICER 2–4 bpp full/sub-frames, LOCO lossless downsampled) | JPEG quality in label | JPEG quality in label |
| Time | `START_TIME` ms; SCLK with ms fraction | `START_TIME` ms; SCLK whole seconds | as Mastcam |
| Position | `ROVER_MOTION_COUNTER` in label; site + drive also in file name | `ROVER_MOTION_COUNTER` | `ROVER_MOTION_COUNTER` |
| Checksums | none in labels sampled (we would record sha256 at download) | none seen | none seen |
| Browse | `EXTRAS/FULL` JPEG (e.g. 23 kB D, 1.5 kB T) — archive re-encodings, not rover products | — | — |

## Measured per segment (listings)

| segment (Phase 2 role) | Navcam acquisitions (sols active) | Navcam EDR size | Mastcam EDR / all RDR | MAHLI EDR / all RDR |
|---|---|---|---|---|
| 232–251 (calibration) | 32 thumbnails + 32 others on 2/20 sols — solar conjunction (Apr 2013) | 0.03 GB | EDR on 3 sols | 1 sol |
| **412–430 (validation SEP)** | **1,159 on 13/19 sols** (median 92 / active sol, max 256); 50 sequences (median 10 images, max 214); 4 sites, 226 site/drive positions; 550/609 stereo pairs | **0.78 GB** (+≈56 MB labels) | 1,039 EDR (0.20 GB) / 14.2 GB | 19 EDR on 9 sols (0.32 GB RDR) |
| 779–820 (validation FD) | 1,623 on 35/42 sols (median 14 / active sol); 139 sequences; 2 sites, 340 positions | 1.89 GB | 3,050 EDR (0.43 GB) / 29.9 GB | 1,676 EDR (Pahrump Hills contact science) / 9.4 GB |

Tier mix (412–430): 846 D+T, 261 F+T, 40 M+T, 12 S+T acquisitions — only 23 % have a full frame in the archive.

## Temporal alignment (measured, Navcam, both validation segments, 2,782 non-thumbnail products)

* Image instant: SCLK → UTC linear fit reproduces label `START_TIME` within 0.01–0.8 s; labels give ms.
* REMS (pressure) nearest sample: median 238 s, p90 24 min; 46 % within ±150 s (same 5-min window),
  74 % within 15 min, 100 % within 60 min (REMS runs hourly 5-min blocks).
* RAD observations every ~1,021 s (≈17 min); 91 % of images within 15 min of one.
* Therefore: image time is sub-second; **telemetry context is minutes-level** (REMS block / RAD integration), never
  an instantaneous co-measurement. The honest unit is "image + telemetry context window", with the gap recorded.

## Location

PLACES bundle (`msl_places/data_localizations/localized_interp.csv`, 11 MB; `localized_pos.csv`, 341 KB): per
site/drive/pose — landing-frame x/y/z (m), planetocentric lat/lon, elevation, roll/pitch/yaw, earliest SCLK, sol.
Match method: exact join on the label's `ROVER_MOTION_COUNTER` (site, drive, pose) — no time interpolation.
Uncertainty: defined in the PLACES SIS (not quantified here); positions are per rover stop/pose, so all images at one
stop share a position.
