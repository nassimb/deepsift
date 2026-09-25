# Jev evaluation — Phase 2 report

**Status: Jev has not been evaluated yet (no API key).** No `TYPESAFE_API_KEY` was available during Phase 2, so every Jev
strategy and ablation is reported UNAVAILABLE and no Jev number appears in this report. The harness,
the call logging, the smoke test and all five ablation variants are implemented and tested (through the
official SDK with a mock HTTP transport); one command runs the evaluation once a key exists (see the end).

What Phase 2 *did* measure — on held-out data, with a frozen configuration — is how the deterministic
baselines, a local edge model and a mock decision engine behave. Those results define the bar Jev will
have to clear, and several of them change what the Jev question should be.

> **Onboard vs cloud.** DEEPSIFT evaluates an onboard-autonomy architecture. The current Jev
> implementation is API-hosted and therefore does not establish deployability on spacecraft hardware.

## Phase 2b — real-Jev protocol (status 2026-09-25)

**No live Jev call has been made.** The baseline is frozen at tag `phase2-pre-jev` (`3142727`). The live
experiment is prepared so that it is cheap, cached, budget-guarded and pre-registered:

* **Question being tested:** *under extreme bandwidth constraints, does semantic judgment improve the ordering
  of already-detected candidate events?* Focus budgets: 0.1, 0.25, 0.5, 1 % of generated raw bytes.
* **Staged, validation-first:** smoke (~30 events) → pilot (~300 events × 5 variants) → validation ablation →
  selection by a rule declared before any call (`docs/jev-model-selection.md`) → TEST once with the frozen
  primary configuration (and its gated RULES+JEV form, which reuses the same answers).
* **Call audit:** the Phase-2 estimate of ~142,000 calls was 28,387 test candidates × 5 variants with no cache.
  With a request-level cache and ablations restricted to validation: validation 22,222 unique calls
  (61,120 without cache), test 7,499 unique calls for one frozen variant. Requests per event = 1; the five
  bounded judgments share one request (Jev evaluates all questions against one state in parallel).
* **Cost preflight** (official price $0.042 per million input tokens, output free; token count *assumed* at
  4 chars/token until the smoke test measures it): smoke ≈ $0.001, pilot ≈ $0.04, validation ≈ $0.72,
  test ≈ $0.28. Rate limit 1,200 requests/min → validation ≥ 18.5 min, test ≥ 6.2 min.
* **Guards:** `JEV_MAX_CALLS` (default 1,000) and `JEV_MAX_COST_USD` (default $1.00); larger runs need an explicit
  `--allow-calls/--allow-cost`; the engine hard-stops at the limit; bulk runs are refused until the smoke test
  has measured real token usage.
* **Every call** is cached (key: exact state + question schema + variant + pinned model `jev-1.13.0` + SDK
  version) and logged per run in `jev_calls.jsonl` with payload hash, request id, latency, retries, tokens.
* **Objective reuse:** only JEV_FULL_CONTEXT puts the mission objective's name/description in Jev's context;
  for every other variant the objective acts purely in deterministic scoring, so changing objective weights,
  budgets, storage or priority weights needs no new call.
* **Detection vs ranking** is now separated in every result: DETECTION recall (frozen candidate filter, the
  same for every strategy) × RETENTION given detection = END-TO-END recall. Jev is judged on retention given
  detection; it cannot recover events the detector never surfaced.
* **Significance:** exact paired McNemar tests on high-severity labels per budget (Jev vs RULES,
  RULES_PLUS_STATISTICAL, LOCAL_EDGE).

Funnel (validation, real data, measured): 7,832,769 raw channel samples → 11,646 instrument windows →
1,534 candidate windows → 458 candidate events → 458 Jev evaluations per variant. Jev never sees raw samples.

### The twelve Phase-2b questions — pending the live run

1. Did real Jev improve ranking under tight bandwidth? — *pending*
2. At what bandwidth regimes? — *pending*
3. Statistically meaningful? — *pending (McNemar, per budget)*
4. Did Jev beat RULES + STATISTICAL? — *pending*
5. Did Jev beat the 1.6 KB local model? — *pending*
6. Important events Jev saved that rules lost? — *pending (A-only counts)*
7. Important events Jev wrongly deprioritized? — *pending (B-only counts)*
8. API cost? — *pending (measured from reported tokens)*
9. p50 / p95 / p99 latency? — *pending*
10. Confidence calibrated? — *pending (ECE, reliability diagram)*
11. Gain large enough to justify remote semantic inference? — *pending*
12. Does this justify Phase 3? — *pending; Phase 3 will not start automatically*

## Documented limitations kept as results

* **Forbush decreases.** The generic candidate detector (5-min windows, |z| vs a 7-sol trailing baseline,
  thresholds calibrated to a 2 % false-flag rate) is poorly matched to slowly evolving heliophysical events:
  a 5 % multi-day dose drop is ≈ 2σ of hourly RAD scatter and is rarely surfaced as a candidate. On test,
  practical strategies cover ≈ 2 % of Forbush-decrease data (random 7 %). This is not changed using test
  knowledge; a dedicated temporal detector is future work and would need a new untouched test split.
* **Protected-tier storage rule.** v0.1 intuition: after watching the sol 242 SEP degraded in a blackout,
  protect high-utility products. Validation (not used to choose storage policy — the rule stayed the v0.1
  default): already worse at 0.5–2 MiB (mock engine, 1 MiB: 7/23 vs 11/23 high-severity synthetic events
  preserved). Held-out test: same direction (1 MiB: 18/56 vs 27/56). Evidence that intuitive triage rules
  need evaluation; it is kept, not "fixed", against this test set.

## Runs and provenance

| run | split | role | code | config | data |
|---|---|---|---|---|---|
| `20260924T203948-validation-91b4` | validation | sweeps, frozen choice | `7ae93ca`¹ | `7c2806f1c14d` | 224 PDS files, digest `75160808a8dc` |
| `20260924T204836-test-c6f9` | **test** | the reported result, run once | `7ae93ca` | `d59227d52476` (frozen) | 394 PDS files, digest `735fd675fcab` |
| `20260924T211615-calibration-4924` | calibration | sol 242 development event only | `7ae93ca` | `d59227d52476` | 80 PDS files |

¹ The validation run executed code committed unchanged as `7ae93ca` immediately afterwards; its manifest
shows `dirty` because those edits were not yet committed. The test and calibration manifests show `dirty`
only because of an untracked log file and UI/API edits that the study process does not import. From
now on the runner records the git state and dirty paths at *start* time.

Full tables: `artifacts/runs/<run>/tables.md`. Figures: `artifacts/figures/<run>/`. Manifests:
`artifacts/runs/<run>/manifest.json`. All numbers below are copied from the test run's `tables.md`
unless marked *validation*.

Test contents: 14 documented events (2 surface SEPs dated to the day, 10 Forbush decreases from Guo et al.
2018, 2 MY34 dust-storm phases) and 1,852 synthetic injections (25 batches × 3 segments, fixed seeds).
The engine rows use the **MOCK heuristic** — hand-written, not a model, and written by the author of
the injection generator. They are a stand-in, not evidence about Jev.

## The questions

### Does Jev improve event triage?
**Not measured.** No Jev call was made.

What the data says about the question itself:

* **The detector, not the decision layer, bounds recall.** On the synthetic test set every
  candidate-event strategy plateaus once the budget exceeds ~1 % of generated raw bytes: RULES 68 %,
  LOCAL_EDGE 63 %, MOCK·RULES_PLUS_ENGINE 68 %, MOCK·ENGINE_ONLY 65 % high-severity recall — the share of
  injections that produce a candidate at all. No decision layer placed after the candidate filter,
  Jev included, can exceed that ceiling; it can only reorder what the filter surfaces.
* **Therefore Jev can only matter at tight budgets** — below ~1 % — where ordering decides what fits.
  That is where the mock's advantage appears (60 % vs RULES 50 % at 0.5 %), and where a real Jev
  comparison should focus.

### Under which byte budgets?
Measured for the baselines (synthetic, high-severity tolerant recall, test):

| budget (% raw) | 0.1 | 0.25 | 0.5 | 1 | 2 | 5 | 10 |
|---|---|---|---|---|---|---|---|
| RANDOM (30 seeds) | 11 % | 22 % | 36 % | 54 % | 73 % | 95 % | 100 % |
| STATISTICAL | 19 % | 34 % | 46 % | 61 % | 80 % | 100 % | 100 % |
| RULES | 8 % | 23 % | 50 % | 67 % | 68 % | 68 % | 68 % |
| RULES_PLUS_STATISTICAL (no AI) | 8 % | 23 % | 51 % | 73 % | 85 % | 100 % | 100 % |
| LOCAL_EDGE | 14 % | 35 % | 53 % | 63 % | 63 % | 63 % | 63 % |
| MOCK · RULES_PLUS_ENGINE | 13 % | 27 % | 60 % | 68 % | 68 % | 68 % | 68 % |
| ORACLE — NOT DEPLOYABLE | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % |

* At 0.1 %: STATISTICAL (window-level) leads (19 %); at 0.25 % LOCAL_EDGE (35 %) and STATISTICAL (34 %) lead.
* 0.5 %: the mock engine leads; LOCAL_EDGE and the rules are within a few points.
* ≥ 1 %: **the no-AI RULES_PLUS_STATISTICAL hybrid leads everything practical** (73 → 85 → 100 %), because it
  spends leftover budget outside the candidate filter's reach.

### For which kinds of events?
Synthetic, reference budget 0.5 %, tolerant recall by difficulty (σ of the local background):

| | NEAR-NOISE (<2σ) | WEAK (2–4σ) | MODERATE (4–8σ) | OBVIOUS (≥8σ) | QUALITY FAULT |
|---|---|---|---|---|---|
| RULES | 37 % | 41 % | 42 % | 60 % | 52 % |
| LOCAL_EDGE | 34 % | 37 % | 44 % | 70 % | 62 % |
| MOCK · RULES_PLUS_ENGINE | 43 % | 48 % | 51 % | 77 % | 71 % |
| STATISTICAL | 29 % | 37 % | 37 % | 53 % | 26 % |

(RANDOM is not bucketed per seed; its overall synthetic tolerant recall at 0.5 % is 30 %.)

Below 4σ every strategy is close to chance: the calibrated level threshold is ~9σ (REMS) / ~8.6σ (RAD)
at a 2 % false-flag target, so weak anomalies rarely become candidates. This confirms the Phase-1
observation that weak correlated REMS anomalies sit inside Gale's natural variability; the detector was
**not** tuned to catch them.

**Documented events.** Hit recall is saturated and uninformative: RANDOM reaches 100 % because Forbush
decreases last days and any retained window overlaps them. The informative metric is coverage of the
event's data: at 0.5 % every practical strategy covers ~2 % of the Forbush-decrease data (RANDOM 7 %).
The calibrated detector does not isolate Forbush decreases at hourly resolution (a 5 % drop ≈ 2σ of hourly
RAD scatter). SEPs are covered better by event-based strategies (≈ 33–36 % coverage vs STATISTICAL 23 %),
and the dust-storm phases 15–26 %. With n = 14 these are descriptive, not statistically separable.

### Where does it fail?
For Jev: not measured. The failure-analysis page (`/study`, run `20260924T204836-test-c6f9`) collects,
for the mock engine, examples of: rules-right/engine-wrong, engine-right/rules-wrong, both wrong, both
right, high-confidence type errors, low-confidence correct answers, events lost to detection, to budget,
and (in the storage sweep) to blackout storage. Every example opens in the Event Inspector. One
instructive mock error: the documented 2013-10-10 SEP (validation) was typed `instrument_anomaly` at
0.99 confidence — the kind of error a semantic model is meant to avoid and should be checked for first.

### How calibrated is its confidence?
Jev: not measured. The mock heuristic is badly miscalibrated (test): event-type ECE 0.33 (mean
confidence 79 %, agreement with the injected type 46 %); "importance" ECE 0.69 on synthetic data
(76 % confidence vs 6.5 % overlap with an injection — a lower bound on accuracy, since unlabeled real
phenomena exist). This is exactly why gating thresholds were chosen on validation rather than trusted.

### What is its latency?
Jev: not measured. Measured locally (test run, development laptop, per event):

| stage | p50 | p99 | max |
|---|---|---|---|
| local preprocessing (amortized per candidate) | 4.35 ms | 11.5 ms | 11.5 ms |
| priority computation | 0.057 ms | 0.108 ms | 130 ms |
| mock engine call | 0.013 ms | 0.033 ms | 159 ms |
| complete routing, RULES | 20 ms | 33.6 ms | 151 ms |
| complete routing, LOCAL_EDGE | 19.9 ms | 33.5 ms | 37.6 ms |

A real Jev call adds a network round-trip; TypeSafe states 70–500 ms, which would dominate routing time.
That figure is the vendor's, not a DEEPSIFT measurement.

### What does it cost?
Jev: not measured (`jev_usage.calls = 0`). The runner records reported input tokens × the configured
price per call and computes cost per 1,000 events and per retained important event once calls exist.
No cost figure is estimated here.

### How much does it improve over threshold rules?
Not measured for Jev. For calibration of expectations: the mock engine improves high-severity recall over
RULES by +10 points at 0.5 % on test (60 % vs 50 %; *validation*: 60 % vs 52 %) and 0 points at ≥ 1 %.
The mock was written with knowledge of the injection kinds, so this is an upper-bound-flavoured stand-in,
not a prediction of Jev's gain.

### How much does it improve over a local lightweight model?
Not measured for Jev. LOCAL_EDGE — 15-parameter logistic regression, 1.6 KB of JSON, ≈14 µs per event on
CPU, trained only on the calibration split — reaches 53 % high-severity recall at 0.5 % (RULES 50 %) and
the best precision lower bound of any practical strategy (8.5 % synthetic). Its largest coefficients are on
local-time features (sin/cos LMST), which may reflect when REMS samples rather than physics; it still
generalized from calibration to test. **Any remote model has to beat this network-free baseline by
enough to justify a network dependency.**

### Does Jev reduce the amount of expensive deep reasoning required?
Not measurable yet: deep analysis is disabled (no Anthropic spend in Phase 2), and there are no Jev
confidences to gate. With the mock engine the frozen gating point (auto ≥ 0.8, uncertain ≥ 0.3) would
escalate 0 of 1,073 real and 0 of 5,446 synthetic candidates — because the mock is overconfident, not
because escalation is unnecessary.

## Other findings

* **Protected-tier storage policy does not generalize.** In v0.1 I added a "protect high-utility
  products" rule after seeing the sol 242 event degraded in a blackout. On held-out synthetic data it
  preserves *fewer* high-severity events at 1–4 MiB than plain value-per-byte (1 MiB, mock engine:
  18/56 vs 27/56; rules: 25/56 vs 29/56), because it keeps a few large full products instead of many small
  ones. On documented test events both policies preserve 9/9 high-severity events from 64 KiB up with the mock engine and from 128 KiB up with RULES.
  For sol 242 (development event) it is never lost at any capacity; protection upgrades it to FULL at
  256 KiB (mock engine) at the cost of discarding 71 products instead of 27. VALUE_PER_BYTE_ONLY is the
  better default on this evidence; the protected tier is a mission-policy choice, not an efficiency gain.
* **Gating choice is stable but uninformative for the mock.** Validation and test Pareto sets agree on
  uncertain ≥ 0.3; with an overconfident engine, gating hardly ever fires.
* **Leakage was real.** v0.1 thresholds, injection magnitudes and one policy were tuned on the evaluation
  sols (`docs/leakage-audit.md`). Calibrated thresholds are much stricter (|z| 9.3 vs 4.0 REMS).

## Conclusion (Phase 2, without Jev)

Of the allowed conclusions, the evidence supports only this one so far: **simple, network-free methods
set a strong bar, and the decision layer can only matter in a narrow regime.** Candidate detection caps
every event-based strategy at 63–68 % high-severity recall on this test set; above ~1 % budget a no-AI
rules + statistical hybrid dominates; below ~0.5 % a 1.6 KB local model is within a few points of the
best practical strategy. Whether Jev materially helps in the tight-budget regime, and at what latency
and cost, remains open and is the next measurement.

## How to run the Jev evaluation

1. `cp .env.example .env` and set `TYPESAFE_API_KEY=` (never paste the key in chat).
2. `uv run python scripts/jev_smoke.py` — one call on a calibration event; must print `SMOKE TEST PASSED`.
3. `uv run python scripts/run_study.py --split validation` — Jev variants run alongside every baseline;
   every call is logged to `artifacts/runs/<run>/jev_calls.jsonl`.
4. `uv run python scripts/run_study.py --freeze <validation_run>` — applies the same pre-declared rule and
   records per-engine gating choices (the mock's choice is kept separately).
5. `uv run python scripts/run_study.py --split test` — once. Then `scripts/report_tables.py` and
   `scripts/make_figures.py` for that run, and replace the "not measured" answers above with the numbers.

Scale at the default settings: the test run scored ≈ 28,400 candidate events (1,073 on real data + 27,314 across
75 synthetic batches), so 5 variants ≈ 142,000 calls, plus validation. `--batches` reduces this linearly.
Cost is not estimated here; the runner will measure it from reported tokens.
