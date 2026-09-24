# Ground truth

DEEPSIFT does not know what is scientifically important. It evaluates against **documented events**
taken from primary sources, and — separately — against **synthetic anomalies** it injects itself.
The two are never pooled into one metric.

Machine-readable file: `data/ground_truth/documented_events.json`, built reproducibly by
`scripts/build_ground_truth.py` (parses the source PDFs, records their sha256).

## Sources

| key | source | type | what it gives | events |
|---|---|---|---|---|
| `guo2018` | Guo et al. (2018), *A&A* 611, A79 — Appendix table (arXiv:1712.06885v1) | peer-reviewed paper | Forbush decreases (FDs) in MSL/RAD dose rate, 2014-10 → 2016-09: onset time, nadir time, dose rate at onset/nadir, drop % | 121 |
| `lowe2025` | Löwe et al. (2025), submitted to *Space Weather* (arXiv:2502.02469v1), Tables 1–3 | mission-team publication (preprint) | Surface SEP events detected by RAD, calendar date only; shelter duration and time-to-peak for some | 16 |
| `hassler2014` | Hassler et al. (2014), *Science* 343, 1244797 | peer-reviewed paper | the sol 242 SEP | 1 |
| `viudez2019` | Viúdez-Moreiras et al. (2019), *JGR Planets* 124, 1899–1912 | peer-reviewed paper | MY34 global dust storm phases at Gale in sol numbers (REMS) | 2 phases |

No REMS-observable event with sub-sol timing (e.g. an individual convective vortex from a published
catalogue) was located in an accessible primary source during Phase 2. This is a known gap.

## Fields

`event_id, event_type, event_subtype, start_time, end_time, time_uncertainty, confidence_in_time_bounds,
affected_instruments, severity, magnitude, source, source_type, citation, notes`.

`confidence_in_time_bounds`:

| value | meaning | used for |
|---|---|---|
| `documented_uncertainty` | the source states the timing uncertainty (Guo: δonset = 0.68 d, δnadir = 0.55 d) | strict and tolerant recall |
| `sol_resolution` | the source gives sol numbers only | tolerant recall |
| `NEEDS_VERIFICATION` | date-only or conflicting statements | tolerant recall only, reported separately |

## Temporal matching

* **Strict**: a retained unit overlaps `[start_time, end_time]`.
* **Tolerant**: a retained unit overlaps `[start_time − δstart, end_time + δend]` where δ comes from
  `time_uncertainty` — i.e. from the source (Guo Table 1) or from the stated resolution (1 sol, 1 day).

The tolerance is taken from the sources, not tuned. It is recorded in every run manifest.

## Severity convention (fixed before Phase-2 evaluation)

Not a scientific ranking — a declared evaluation convention so that "high-severity recall" is defined:

* Forbush decrease: **high** if drop ≥ 5 %, **medium** 3–5 %, **low** < 3 %. Rationale: the source's
  manual-identification uncertainty on the drop is 1.38 %, and hourly RAD dose-rate scatter is a few
  percent, so < 3 % drops are near the noise floor of a single-instrument, hour-scale detector.
* Surface SEP event: **high**. Dust-storm phase: **high**.

## Coverage and splits

Recall can only be computed where a catalogue claims coverage. The FD catalogue covers
2014-10-17 → 2016-09-28 only; the SEP list covers the whole mission but with date resolution.
Events are assigned to a split by `data/splits/splits.json`:

| split | segments | documented events expected inside |
|---|---|---|
| calibration | sols 232–251 | sol 242 SEP (development event — never test evidence) |
| validation | 412–430; 779–820 | 2013-10-10 SEP; FD #1–#4 region |
| test | 732–750; 871–930; 2068–2105 | 2014-09-02 and 2014-09-10 SEPs; FDs ≈ #10–#22; dust-storm onset and peak |

PDS gaps (no product exists): REMS and RAD sols 874–879; RAD sol 782; RAD sols 2081–2083. Events
falling inside a gap are reported as `no_data`, not as misses.

## Sol 242 verification record

| | |
|---|---|
| old bounds (v0.1) | 2013-04-11T06:00Z → 2013-04-12T12:00Z — set by the maintainers from the same RDR data it was evaluated on |
| new bounds | 2013-04-11T00:00Z → 2013-04-12T23:59:59Z (day resolution) |
| status | **NEEDS_VERIFICATION** (sub-day timing not established by an independent source) |

Statements found:

1. Hassler et al. 2014, main text and Fig. 1 caption: *"one hard SEP event on sol 242 (12 to 13 April 2013)"*.
2. Hassler et al. 2014, Materials and Methods: *"the SEP event enhancement seen on 11 to 12 April 2013 resulting from an M-class flare"*.
3. Löwe et al. 2025, Tables 1–3: surface SEP event dated *2013-04-10*.
4. PDS RAD RDR (DEEPSIFT reading): dose B 9.13 µGy/h at 2013-04-11T06:01Z, 10.73 at 12:09Z, peak 12.13 at 14:12Z, ≈9.2 by 2013-04-12T04:32Z.

Reason: the primary paper is internally inconsistent. Sol 242 spans ≈ 2013-04-11T05:30Z → 2013-04-12T06:10Z
(REMS clock relation; checked against the sol 2075 product label to within 1 minute), which is consistent
only with statement 2. The new bounds adopt statement 2 at its stated day resolution. The event sits in the
calibration split and is reported only as a development event.

## What is not ground truth

* Model predictions (engine answers, deep-model verdicts) — stored in the audit log, never used as labels.
* `RULE_GENERATED` labels — circular for the rules strategy; excluded from benchmarks.
* Synthetic injections — ground truth only for the synthetic stress test, reported separately.
