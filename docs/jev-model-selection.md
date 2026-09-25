# Jev model selection (VALIDATION only)

**Status: PRE-REGISTERED — no live Jev call has been made.** This file fixes the procedure before any
Jev output exists. The "Selection record" section is filled in by `scripts/run_study.py --freeze-jev`
output after the validation ablation; nothing here may be chosen or changed using test results.

## Frozen before this step

Tag `phase2-pre-jev` (commit `3142727`): detector thresholds, event extraction, storage policy, ground
truth and splits are frozen. Any later change to them requires a new untouched test split. The Jev
layer (state representation, questions, gating) may still change — on validation only.

Pinned model: `jev-1.13.0` (the alias `jev-latest` resolved to it on 2026-09-25 per
https://docs.typesafe.ai/models.md). SDK: `typesafe-sdk` 0.7.1.

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

## Selection record

*Empty until the validation ablation has run.* To be filled from `--freeze-jev` output: chosen variant,
rejected alternatives with their metrics, pilot findings and representation changes, validation run id,
commit hash, config hash.
