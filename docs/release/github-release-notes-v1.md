# DEEPSIFT v1 — research release (`deepsift-v1-research`)

This release contains no new science version. It packages the completed Phase 3 study: final test config commit
`96e0694`, final result commit `fdc2122`, release tag on commit `0b5d6ff`.

## What DEEPSIFT studies

When a rover has more imagery than bandwidth, which signals actually help decide what is transmitted? DEEPSIFT replays
archived Mars Science Laboratory (Curiosity) data from the NASA Planetary Data System under simulated bandwidth limits.
Each candidate signal is tested on data it was not tuned on, against rules committed in advance.

**Protocol:**

| stage | sols |
|---|---|
| development | 412–430 |
| validation 1 | 779–820 |
| validation 2 | 1100–1129 |
| final held-out test | 950–979 |

The final test config was committed before the first test image was downloaded, and the test was analysed once.

## Final held-out result

Curiosity Navcam, sols 950–979; 12 traverses, 679 archived frames. Scheduler V3 + rover-position sampling at 1/4
traverse-frame retention:

| metric | result | pre-registered criterion |
|---|---|---|
| full-quality traverse bytes | **26.1 %** | ≤ 35 % |
| 5 m spatial coverage | **100 %** | ≥ 90 % |
| max distance from any archived frame to a retained frame | **2.05 m** | ≤ 10 m |
| broken stereo pairs | **0** | 0 |
| Scheduler V3 monotonicity violations | **0** | 0 |

**Primary criterion: PASS.**

## What generalized

- **Rover-position sampling:** farthest-point selection on PLACES positions. 5 m coverage 1.000 in all four periods.
- **Scheduler V3:** stereo-safe and progressive. It sends thumbnail pairs, then compressed pairs, then full pairs, and
  never one eye alone. Coverage is monotonic in budget.

## Negative results

- **Jev semantic ranking:** AUROC vs deterministic rules +0.006 (95 % CI −0.020 to +0.037); stopped by a pre-registered
  rule.
- **Telemetry image ranking:** image-independent; the weakest coverage of six strategies.
- **pHash representative selection:** constrained false-merge rate 0.15–0.19 on validation; at most 1.03× compression.
- **QUALITY_V2:** false-positive rate 3.6 % in development and 10.6 % on validation. Diagnostic flag only.
- **Embedding-assisted selection:** gain over position +0.044 in development, then +0.004, +0.001 and +0.005, against a
  +0.020 threshold. No measurable added value.

## Reproducibility

- **Frozen configs:** `config/phase3_3_validation_config.json`, `config/phase3_4_validation_config.json`,
  `config/phase3_final_test_config.json` (hash `6f35d7fc…`).
- **Integrity:** `uv run python scripts/release_integrity.py --verify` checks the SHA-256 of 70 scientific artifacts.
- **Public numbers:** `uv run python scripts/check_public_claims.py` checks every public number against its frozen
  source.
- **Datasets:** manifests with PDS URLs and SHA-256 are in `data/manifests/`. Raw products are re-downloadable and not
  committed.

## Limitations

- **Retrospective.** The PDS holds only downlinked observations, so this is re-prioritization of archived data, not
  onboard-stream reconstruction.
- **Simulated compressed tier.** The compressed stereo tier is a simulated product tier.
- **Interpolated positions.** Positions are PLACES interpolations.
- **Narrow scope.** One rover and one camera; traverse sequences only; four sol windows.
- **Proxy metrics.** Visual-change coverage is an embedding proxy, and spatial coverage is geometric, not
  science-value preservation.
- **Not flight software.** Not affiliated with, reviewed, used or validated by NASA or JPL.

## Links

| | |
|---|---|
| Demo | {{DEMO_URL}} (historical replay at `/final-test`) |
| Paper | `docs/deepsift-paper.md` · attach `artifacts/public/deepsift-v1-paper.pdf` |
| One-pager | attach `artifacts/public/deepsift-one-pager.pdf` |
| Reproducibility | {{DEMO_URL}}/reproducibility |
| Limitations | {{DEMO_URL}}/limitations |
