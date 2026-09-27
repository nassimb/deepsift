# DEEPSIFT
**Measured downlink autonomy for bandwidth-constrained missions** · independent research prototype · v1 (`deepsift-v1-research`)

**PROBLEM.** Rover imagery competes for limited onboard storage and relay downlink. Something has to decide what is sent
at full quality, what goes down as a thumbnail, and what waits.

**QUESTION.** How far can archived rover traverse imagery be reduced while preserving spatial mission coverage and stereo
integrity?

**DATA.** Public NASA PDS archives: Curiosity Navcam raw EDR (stereo, all product tiers, ICER/LOCO label metadata) and
PLACES rover localizations. Downlink cost comes from label estimates (lines × samples × compression rate / 8).

**EXPERIMENT.**

| stage | sols | purpose |
|---|---|---|
| Development | 412–430 | method design and tuning |
| Validation 1 | 779–820 | first out-of-sample check |
| Validation 2 | 1100–1129 | fresh check after simplification |
| Final held-out test | 950–979 | one run |

Every configuration and pass/fail rule was committed to git before the data that tested it was downloaded. The four
periods are never pooled.

**FINAL HELD-OUT RESULT** — Curiosity Navcam sols 950–979: 12 traverses, 679 archived frames. Method: Scheduler V3 +
rover-position sampling at **1/4 traverse-frame retention**. Pre-registered criterion: **PASS**.

| full-quality traverse bytes | 5 m spatial coverage | max distance, archived frame → retained frame | broken stereo pairs |
|:---:|:---:|:---:|:---:|
| **26.1 %** | **100 %** | **2.05 m** | **0** |

**WHAT GENERALIZED**
- **Rover-position sampling:** farthest-point selection on PLACES positions. 5 m coverage was 1.000 in all four periods.
- **Scheduler V3:** stereo-safe and progressive. It sends thumbnail pairs, then compressed pairs, then full pairs, and
  never one eye alone. It had 0 monotonicity violations in all four periods.

**WHAT DID NOT EARN A PRIMARY ROLE**
- **Jev semantic ranking:** AUROC vs rules +0.006 (95 % CI −0.020 to +0.037); stopped by a pre-registered rule.
- **Telemetry image ranking:** image-independent by construction; weakest coverage of six strategies.
- **pHash representative selection:** constrained false-merge rate 0.15–0.19 on validation; at most 1.03×
  compression.
- **QUALITY_V2:** false-positive rate 3.6 % in development and 10.6 % on validation.
- **Embedding-assisted selection:** visual-change gain over position +0.044 in development, then +0.004, +0.001 and
  +0.005, against a +0.020 threshold. No measurable added value.

**LIMITATIONS**
- **Retrospective.** The PDS contains only observations that were actually downlinked, so this is re-prioritization of
  archived data, not reconstruction of the onboard stream.
- **Simulated compressed tier.** The compressed stereo tier is simulated.
- **Interpolated positions.** Positions come from PLACES, mostly the nearest pose within a drive.
- **Narrow scope.** One rover, one camera, traverse sequences only.
- **Proxy metrics.** Coverage is geometric, not a measure of science value.
- **Not flight-ready, and not reviewed, used or validated by NASA/JPL.**

**LINKS**

| | |
|---|---|
| Demo | https://deepsift.space (`/final-test`) |
| GitHub | https://github.com/nassimb/deepsift |
| Paper | `docs/deepsift-paper.md` · `artifacts/public/deepsift-v1-paper.pdf` |
| Reproducibility | https://deepsift.space/reproducibility · `scripts/release_integrity.py --verify` |
