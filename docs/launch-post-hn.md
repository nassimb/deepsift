# Show HN: DEEPSIFT – pre-registered test of downlink prioritization on Curiosity rover data

I started by testing whether more AI improved autonomous downlink decisions for a rover. It mostly didn't. What
survived was rover geometry plus a correct scheduler. The negative results are the interesting part, so they are
reported in full.

**Setup**

- **Data.** Public NASA PDS archives: Curiosity Navcam raw EDR (stereo pairs, full/downsampled/thumbnail tiers,
  ICER/LOCO label metadata) and PLACES localizations. Phase 2 also used REMS/RAD telemetry. Each product is recorded
  with its URL and SHA-256.
- **Replay.** Archived products are treated as if they were waiting onboard. Downlink cost is estimated from each
  label as lines × samples × compression rate / 8.
- **Protocol.** Development (sols 412–430), validation 1 (779–820), validation 2 (1100–1129), and a held-out test
  (950–979) chosen by a deterministic rule from directory listings only. Configs, pass/fail rules and "meaningful
  effect" thresholds were committed before each download. Runners refuse to start if the config hash or any listed
  source-file hash changed. The test config was committed 24 s before the first test image landed on disk, and the test
  was analysed once.

**Architecture that survived**

1. **Grouping.** Acquisitions are grouped by spacecraft-clock instant; a stereo pair plus its thumbnails is one unit.
2. **POSITION.** Farthest-point sampling on PLACES (x, y) within each traverse, keeping ⌈f·n⌉ frames.
3. **Scheduler V3.** Progressive prefix fill: every THUMBNAIL_PAIR, then COMPRESSED_STEREO_PAIR, then FULL_STEREO_PAIR,
   stopping at the first misfit. Coverage is therefore monotonic in budget, which is property-tested and checked on an
   80-point grid. A stereo pair is never usable with one eye.
   - V1 (greedy) was non-monotonic: more budget could lose coverage.
   - V2 fixed that but carried only one eye in the compressed tier.

**Held-out result** (12 traverses, 679 frames, 1/4 retention): 26.1% of full-quality bytes, 5 m coverage 1.000, max
distance from any archived frame to a kept frame 2.05 m, 0 broken stereo pairs, 0 monotonicity violations. The
pre-registered criterion passed.

**What didn't work**

- **Jev (bounded-output semantic model) ranking REMS/RAD candidates:** AUROC vs rules +0.006, 95% CI −0.020 to +0.037,
  over 1,500 live calls. Stopped by rule.
- **Telemetry-driven image ranking:** image-independent by construction; worst coverage (7 usable acquisitions at 1
  rover position at a 1% budget).
- **Constrained pHash dedup:** false-merge rate 0.15–0.19 on validation against a 0.05 limit; at most 1.03×
  compression.
- **Learned quality detector:** false-positive rate 3.6% in development and 10.6% on validation, mostly upward-pointing,
  low-texture frames. I did not fix it on validation data.
- **MobileNetV2 embedding-assisted selection:** visual-change gain over POSITION +0.044 in development, then +0.004,
  +0.001 and +0.005, against a pre-registered +0.020 threshold. The embedding is a fine change detector; it just didn't
  improve selection.

**A metric lesson.** I first bounded the worst gap between kept frames relative to native frame spacing. Validation 1
traverses were about 10× denser than development, so that rule failed for reasons unrelated to selection quality. The
failure is recorded and was not rewritten. For later periods I used a density-invariant metric, "max distance from any
archived frame to its nearest kept frame", chosen on development data only.

**Caveats**
- PDS survivorship bias: only downlinked data exist.
- Simulated compressed tier.
- Interpolated positions.
- One rover and one camera.
- No flight hardware or power model.
- Not affiliated with or validated by NASA/JPL.

Code, paper, figures, replay and a 70-file hash manifest: https://github.com/nassimb/deepsift · https://deepsift.space
