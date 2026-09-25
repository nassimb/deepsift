# Jev model selection (VALIDATION only)

**Status: PRE-REGISTERED.** Live calls so far: 1 probe + the 30-event smoke only (operational checks, no selection input). This file fixes the procedure before any
Jev output exists. The "Selection record" section is filled in by `scripts/run_study.py --freeze-jev`
output after the validation ablation; nothing here may be chosen or changed using test results.

## Frozen before this step

Tag `phase2-pre-jev` (commit `3142727`): detector thresholds, event extraction, storage policy, ground
truth and splits are frozen. Any later change to them requires a new untouched test split. The Jev
layer (state representation, questions, gating) may still change — on validation only.

Pinned model: `typesafe/jev-1.13` (never `jev-latest`). Transport: OpenRouter System One API
(`POST https://openrouter.ai/api/v1/systemone`, TypeSafe SDK with `base_url=https://openrouter.ai/api`,
key `OPENROUTER_API_KEY`; `TYPESAFE_API_KEY` is not read). Provider behind OpenRouter: TypeSafe.
Served snapshot on 2026-09-25: `typesafe/jev-1.13-20260917` (every response logs it). SDK: `typesafe-sdk` 0.7.1.
The cache key includes the transport, so answers obtained through different transports are never mixed.
Price: $0.042 / Mtok input, output free (OpenRouter endpoint listing, 2026-09-25); each response's
`usage.cost` is recorded and used by the run budget.

## Staged protocol

| stage | data | variants | purpose | guard |
|---|---|---|---|---|
| 1 smoke | ~30 stratified validation events | NO_MISSION_OBJECTIVE | API, schema, parsing, cache, logging, retries; `--repeat 3` measures run-to-run variability | stops at first malformed answer |
| 2 pilot | ~300 stratified validation events | all 5 | find broken/redundant variants, schema problems, latency, confidence behaviour | preflight + JEV_MAX_CALLS / JEV_MAX_COST_USD |
| 3 ablation | all validation candidates (real + synthetic batches) | all 5 (or those surviving the pilot) | selection metrics below | preflight + explicit `--allow-calls` |
| 4 freeze | — | — | apply the rule below; write the record | — |
| 5 test | all test candidates | the frozen primary only (+ its gated RULES+JEV form, no extra calls) | the reported result, run once | refuses anything else |

Pilot findings may change the Jev *representation or questions* (validation is development data); every
such change is recorded below with the pilot run id. A changed representation invalidates earlier cache
keys automatically (the key includes the exact state and question schema).

## Selection rule (declared 2026-09-25, before any live call)

1. **Eligibility:** ≥ 99 % of validation requests parse-valid; < 2 % errors.
2. **Primary metric:** mean VALIDATION synthetic high-severity tolerant recall over budgets 0.1, 0.25, 0.5
   and 1 % of generated raw bytes — the regime where ordering of already-detected candidates matters
   (Phase 2 showed every candidate-based strategy saturates at its detection ceiling above ~1 %).
   ENGINE_ONLY form; ENGINE_SINGLE_DECISION for the single-decision variant.
3. **Ties** (within 1 point): fewer input tokens per request, then lower p95 latency.
4. **Not used for selection:** validation documented events (n = 6, too few); ECE (reported).
5. **RULES_PLUS_JEV** (secondary configuration, answers a different question — does confidence gating to
   rules help?): the chosen variant's gated form, with (auto, uncertain) chosen by the gating rule already
   declared in `docs/research-methodology.md`. It reuses the primary's answers: zero extra calls.

## Call and cost budget (preflight, 2026-09-25, no live calls)

Counts from `scripts/jev_call_audit.py` / `scripts/jev_preflight.py`. Cost uses the official price
($0.042 per million input tokens, output free) and an **assumed** 4 characters per token until the smoke
test measures real usage (treat as ±50 %).

| stage | candidate events | requests without cache | unique live calls | est. cost | est. time |
|---|---|---|---|---|---|
| smoke | 30 | 30 | 30 (+9 repeat) | $0.0012 | < 1 min |
| pilot | 300 | 1,500 | 1,297 | $0.040 | ≥ 1.1 min |
| validation ablation (5 variants, 25 batches) | 12,224 | 61,120 | 22,222 | $0.72 | ≥ 18.5 min |
| test (1 frozen variant) | 28,387 | 28,387 | 7,499 | $0.28 | ≥ 6.2 min |

The Phase-2 figure of ~142,000 calls was 28,387 test candidates × 5 variants with no cache. Its main
redundancy: each of the 25 synthetic batches per segment re-detects the same natural events, so identical
requests repeat up to 25×. Budget, storage, gating and random-seed sweeps never trigger calls (they reuse
stored answers); the UI/API runs on the mock engine. `numeric_only` alone is 11,571 of the 22,222
validation calls because raw floats (e.g. rarity) differ slightly between batches; the pilot will show
whether it deserves the full ablation.

## Operational record (not selection input)

| stage | run | live requests | result |
|---|---|---|---|
| TypeSafe-direct smoke | `20260925T083440-jev-smoke-fe7c` | 30 (before fail-fast existed) | all HTTP 401, key rejected — transport abandoned |
| OpenRouter probe | `20260925T090044-jev-probe-6ded` | 1 | all 8 probe checks passed |
| OpenRouter smoke (30 events, `--repeat 3`) | `20260925T090119-jev-smoke-b935` | 29 + 9 repeats | 0 errors, 0 malformed, 0 retries; cache determinism confirmed |
| Pilot (300 stratified validation events × 5 variants, 20-event repeat subset × 2, objective check 2 × 50) | `20260925T091126-jev-pilot-7351` | 1,565 ($0.0815) | 0 errors / 0 malformed / 0 retries; **semantically pathological** (below) |
| Wording experiment q1 → q2 (150 of the pilot events, NO_MISSION_OBJECTIVE) | `20260925T092458-jev-wording-q2-d559` | 130 ($0.0084) | mixed; no ground-truth gain; q2 NOT adopted |

Pilot sampler (changed before the pilot, validation only): strata = (label status, synthetic severity, instrument,
detector-score tier relative to the frozen level threshold, rules type); sampling manifest in the run folder.
Pilot analysis: `scripts/jev_pilot_report.py` (cache only, zero-call budget). Ranking on the sample uses the declared
approximation in that script's docstring (budget scaled by sampled/all candidate bytes; labels detected by a sampled
candidate); with only 10 synthetic + 4 documented high-severity labels detected in the sample it is underpowered.

## Representation changes (validation only)

**q2 question schema** (`decision/questions.py` `QUESTIONS_V2`, variant `no_mission_objective@q2`, kept out of the
five pre-registered variants). Why: the q1 pilot returned `instrument_failure = yes` on 92–100 % of candidates in every
variant, including documented Forbush decreases/SEPs and synthetic physical offsets with no quality flag, and never used
`uncertain`. q2 rewrites only `instrument_failure` ("does the evidence specifically suggest malfunction or degradation
… rather than a natural phenomenon? The size of a deviation, on its own, does not distinguish the two") and the
`instrument_anomaly` criterion of `event_type`; answer keys unchanged (the frozen priority formula reads them unchanged).
Cache: keys contain the exact question schema, so q1 entries can never be served for q2; q1 entries and results kept.
Outcome on the same 150 events: REMS unflagged candidates `failure = yes` 81/95 → 53/95 and `uncertain` used twice,
but RAD `event_type = instrument_anomaly` 60 % → 84 % (documented Forbush decreases flipped to instrument anomaly);
ground-truth accuracy unchanged within noise (n = 37: event type 0.41 → 0.35, instrument failure 0.32 → 0.35).
**Not adopted.** No further wording iterations were run.

## JEV_SCHEMA_V3 — final redesign pilot (declared before any V3 answer existed)

Jev answers only scientific questions about an already-detected candidate; instrument failure, downlink action and
deep-analysis routing are system decisions and are no longer asked. Code: `decision/questions.py`
(`QUESTIONS_V3_SCIENCE`, `QUESTIONS_V3_RELEVANCE`), `decision/state.py` (`build_state_v3`, `data_quality_state`),
`evaluation/v3_adapter.py`, `scripts/jev_v3_pilot.py`. q1/q2 runs and cache entries are kept.

* Requests: V3_SCIENCE (objective-free state) → `scientific_interest` (none…exceptional) + `phenomenon_class`
  (atmospheric / radiation / thermal / other_physical / uncertain; no instrument class). V3_RELEVANCE (same state +
  objective) → `mission_relevance` only. The objective therefore cannot reach the phenomenon class. Diagnostic only:
  the science questions re-asked with the objective in the state (2 objectives × 100 events) + an uncached repeat baseline.
* `data_quality_state` CLEAN / SUSPECT / BAD from the frozen detector flags and sample counts only (no new threshold).
* State wording: qualitative buckets, no raw rows, none of failure / important / critical / valuable / interesting.
* Adapter (not tuned): ordinal map 0 / .25 / .5 / .75 / 1 on the CHOSEN category; QC factor 1 / 0.5 / 0; frozen
  objective weights for {science, relevance, anomaly strength, novelty}; no confidence penalty; no instrument-failure
  floor; frozen action thresholds. `phenomenon_class` not used in priority. RULES+JEV_V3 = RULES unchanged + 0.10 ×
  (Jev signal − 0.5), actions = RULES actions. Control V3_ADAPTER_NO_JEV = the adapter with every Jev value = 0.5.
* Health gates checked before ranking: any category > 90 %; relevance nearly constant; phenomenon class moving with the
  objective beyond the repeat baseline; confidence not separating correct from incorrect.
* Sample (validation, seed 20260925): 15 synthetic batches (first B reaching ≥ 100 medium and ≥ 100 high), all medium,
  high subsampled to ≈ 150, ≤ 2 low and 5 unlabelled distractors per group; all documented-overlap real candidates +
  60 unlabelled per real segment. Preflight: 598 events, 1,500 live calls, est. $0.046.
* Outcome rule (stop rule): PROCEED / MARGINAL / STOP JEV after this pilot; no fourth redesign.

### V3 outcome — run `20260925T094903-jev-v3-pilot-84af` (1,500 live calls, $0.0499, 0 errors)

* Health: passed the declared gates (top category ≤ 60 %; phenomenon class accuracy 0.83 on 269 physical labels vs
  0.33 for rules, but it is almost a sensor-family lookup; phenomenon class moves 0–3 % when the objective is put in the
  state vs 1 % repeat baseline). Caveats: mission relevance is 100/100 `very_high` under `engineering_health`;
  scientific interest largely echoes the magnitude bucket (raw AUROC 0.60 vs detector tier 0.59, local edge 0.61).
* Ordering-only, synthetic high severity (100 labels): no gain. AUROC Jev V3 − rules −0.001 [−0.026, 0.027] (no
  objective), +0.006 [−0.020, 0.037] (with); − no-Jev control +0.006 / +0.012 (CIs include 0). At 0.25/0.5/1 % JEV_V3
  (no objective) selects exactly the same high-severity labels as the no-Jev control. Best nominal: WITH_OBJECTIVE vs
  rules at 0.25 %, 12 vs 4 labels (p = 0.077 uncorrected, ~60 comparisons); full fidelity 12 vs 8 (p = 0.50).
* As configured, the V3 adapter (with or without Jev) sends less full-fidelity data than RULES; not a Jev effect.
* Documented real events: 5 high-severity labels (21 candidates) — UNDERPOWERED; the AUROC gain there is reproduced
  by the no-Jev control (QC factor), not by Jev.
* **Outcome: C — STOP JEV** for the ranking role (fails to improve candidate ordering). No fourth redesign.

## Selection record

*Empty until the validation ablation has run.* To be filled from `--freeze-jev` output: chosen variant,
rejected alternatives with their metrics, pilot findings and representation changes, validation run id,
commit hash, config hash.
