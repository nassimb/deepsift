# Evaluation leakage audit (Phase 2)

Audit of the v0.1 benchmark (tag `v0.1-baseline`), written before any Phase-2 validation or test
result was computed. Verdict: **v0.1 leaked.** Its numbers are development results, not evidence.

## Questions and answers

**1. Which data was used to establish thresholds?**
Sols 232–251 — the same sols the benchmark evaluated on. Concretely: `dip_threshold_pa = 0.75` was
chosen as ≈ p99.8 of pressure dips over all 20 sols; `noise_ratio_threshold` was raised 1.6 → 3.0 → 4.0
after inspecting how many windows it flagged on those sols; `rad_z_threshold = 3.5` and per-channel
`min_sigma` floors were hand-set while looking at the same data; the baseline method (nearest-LMST
matching, LMST-aligned windows) was redesigned after inspecting z-score distributions on those sols.

**2. Which data is used for evaluation?**
v0.1: sols 232–251 with synthetic injections, plus the sol 242 SEP. Same data as (1).

**3. Are synthetic anomaly parameters influenced by detector thresholds?**
Yes. Injection magnitudes (2.5 Pa drop, +25 % dose, 6 K step, …) were chosen by the same author,
knowing the thresholds. Dropout detection was fixed (complete window × channel grid) after the benchmark
showed dropouts being missed — a detector change made in response to evaluation outcomes.

**4. Are any labels visible to the decision engine?**
No direct path. `build_state` sends features only; `synthetic_injection_ids` is stored on the event but
never read by the state builder, mock engine, priority engine or scheduler (verified by code search).
Indirect: the mock engine's rules were written with knowledge of the injection kinds (e.g. quality-flag →
instrument-anomaly logic). That is design leakage for the mock; it does not apply to Jev.

**5. Can any strategy indirectly infer ground truth?**
Not through data paths. Two metric-level biases exist: (a) the "any retained unit overlaps the label"
recall is lenient for long events and rewards random sampling of long intervals; (b) the mock engine
gives a bonus to RAD events longer than 3 h — a rule written after seeing the 17-h sol 242 event.

**6. Is the documented sol 242 event in development/tuning AND evaluation?**
Yes. Its data motivated the choice of the sol window, the RAD threshold, the mock's long-RAD bonus and,
in the blackout work, the protected-tier storage rule. It was also the only documented label in the
benchmark.

**7. Are mission-objective weights tuned using evaluation outcomes?**
The objective presets and priority weights were written a priori and not changed after benchmark runs.
The priority/action thresholds (0.55 / 0.42 / 0.22) and the protected-tier rule were set while viewing
outcomes on the development sols (the latter explicitly after the sol 242 blackout result).

## Corrections

| leak | correction |
|---|---|
| thresholds set on evaluation data | `scripts/calibrate.py` derives every detector threshold from the **calibration** split only, from declared target flag rates (`config/calibration_targets.yaml`), label-free, no injections → `config/phase2.yaml` with provenance |
| duplicated threshold literals in state builder, mock, rules, novelty | replaced by the detector's own per-channel `flags`, so recalibration cannot desynchronise them |
| single contaminated segment | temporal splits in `data/splits/splits.json`: calibration (232–251), validation (412–430, 779–820), test (732–750, 871–930, 2068–2105), each with a 7-sol baseline warm-up that is never scored |
| sol 242 in dev and eval | sol 242 is a **development event** in the calibration split; never reported as test evidence |
| one documented event | 121 Forbush decreases (Guo et al. 2018), 16 SEP dates (Löwe et al. 2025), 2 dust-storm phases (Viúdez-Moreiras et al. 2019) — `data/ground_truth/documented_events.json` |
| injection magnitudes chosen near thresholds | synthetic stress test uses systematic sweeps in units of the channel's calibration-derived sensor noise σ, crossing the thresholds on both sides; results by difficulty bucket |
| real and synthetic pooled | reported separately, always |
| lenient overlap recall | strict + tolerant (tolerance from sources) recall, plus event **coverage** and the analytic chance level of random selection |
| action thresholds / policy chosen on eval data | chosen on **validation** via sweeps, frozen, then applied once to test |
| LOCAL EDGE model training | trained only on calibration-split data with calibration-seed injections |

## Residual risks (not removable)

* The author designed the pipeline knowing the *kinds* of documented events (SEP, Forbush decrease,
  dust storm) that the test set contains. Detector design was frozen before test data was inspected,
  but prior knowledge of event classes cannot be undone.
* The mock engine remains author-designed. Mock results are never evidence about Jev.
* Calibration uses one season (Ls ≈ 5–15°, MY 31). Thresholds are in σ units of a trailing baseline,
  which transfers across seasons only to the extent that noise and weather variability scale similarly.
