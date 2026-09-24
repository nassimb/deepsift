# Research methodology

DEEPSIFT v0.1 is a prototype and a simulation. This document states what it measures, how, and what the
measurements cannot support.

## Research question

Under a fixed downlink budget, does inserting a fast, bounded-output decision model (TypeSafe's Jev)
between deterministic candidate detection and a deterministic priority engine retain more scientifically
important events per downlinked byte than simple baselines? And what fraction of candidates would still
require an expensive deep model?

## Hypotheses

* **H1 (effectiveness).** Jev-informed triage achieves higher high-severity recall than threshold rules at
  equal downlinked bytes. **H0:** no improvement.
* **H2 (cost).** Confidence gating lets Jev resolve most candidates, so that fewer than a stated fraction
  require deep analysis, at a measured cost per decision.

Both outcomes are acceptable results. The harness is deliberately built so that the model can lose: the
rules strategy is the *same* pipeline with the engine replaced by deterministic rules, so any difference
is attributable to the engine.

## Experimental setup

| element | value |
|---|---|
| Data | MSL REMS MODRDR + RAD RDR, sols 232–251 (PDS; SHA-256 in `data/raw/manifest.json`) |
| Channels | pressure, ambient air T, ground brightness T, UV-ABC, relative humidity, RAD dose B/E |
| Candidate detection | identical for every event-based strategy (`config/default.yaml → detection`) |
| Budget | `passes_per_sol × pass_bytes × n_sols` (default 2 × 32 KiB × 21 = 1.38 MB) |
| Allocation | common greedy allocator: descending utility, degrade one product level until it fits |
| Trials | N injection seeds (`benchmark.injection_seed + k`); results reported as mean ± sd |
| Objective | Balanced Science unless stated |

### Strategies

1. **Random sampling** — instrument windows in seeded random order, FULL products.
2. **Threshold rules** — candidate events; rule-based type and value (`rules_decision`); same priority
   engine. This is exactly the pipeline's fallback path.
3. **Statistical anomaly detection** — every window (not just candidates) ranked by root-mean-square robust
   z across channels plus a dip term; FULL products.
4. **Decision engine** — candidates → engine → gating → priority. Jev when `TYPESAFE_API_KEY` is set,
   otherwise the labelled mock heuristic.
5. **Engine + deep analysis** — as (4) with a `DeepAnalysisProvider`; reported **UNAVAILABLE** when none is
   configured. No numbers are fabricated for unavailable strategies.

## Metrics

| metric | definition | notes |
|---|---|---|
| event recall | recovered labels / labels | a label is recovered if any retained unit of the same instrument overlaps its time span |
| high-severity recall | as above, labels with severity `high` | |
| recall by source | separately for DOCUMENTED_EVENT, SYNTHETIC_ANOMALY, HUMAN_LABEL | sources never pooled silently |
| retained-but-unlabeled rate | retained units overlapping no label / retained units | **upper bound** on false-positive rate — unlabeled real phenomena exist |
| data reduction | 1 − downlinked / raw PDS bytes | raw bytes are real record bytes |
| downlink / retained bytes | measured zlib sizes of the selected products | |
| decision latency | measured wall time (engine call, per event; strategy total) | the mock's latency is Python time, not inference |
| cost | Σ input tokens × configured price, when the API reports usage | `n/a` for the mock |
| deep-model calls, % expensive | escalations / candidates | |
| **science value per downlinked MB (proxy)** | Σ over recovered labels of severity weight (1/2/3) × assumed product fidelity (FULL 1.0, COMPRESS 0.5, SUMMARY 0.15), divided by downlinked MB | **Proxy.** Depends on assumed fidelities and on which labels exist. It does not measure scientific value. |

The Mission Control KPI "Science value / byte" is a different, *self-estimated* proxy (Σ engine-informed
utility per MB) and is labelled as such; it is not used for evaluation because it is circular.

## The ground-truth problem

We cannot know automatically what is scientifically important. DEEPSIFT therefore keeps label sources
separate and never lets a prediction become a label:

| source | how it enters | status in v0.1 |
|---|---|---|
| `DOCUMENTED_EVENT` | `data/labels/documented_events.yaml`, each with a citation | one event: 2013-04-11 SEP (sol 242), time bounds set generously by the maintainers, `needs_verification` |
| `SYNTHETIC_ANOMALY` | `evaluation/injection.py`, seeded, tagged on samples/events/labels | 9 kinds: short/long radiation, pressure drop, temperature discontinuity, stuck, dropout, noise, drift, multi-sensor |
| `HUMAN_LABEL` | Event Inspector → `labels` table | none yet |
| `RULE_GENERATED` | reserved; excluded from benchmarks by default because it is circular for the rules strategy | — |
| model prediction | `decisions` table | never used as a label |

Consequences: recall is dominated by synthetic injections whose kinds and magnitudes we chose, and a
strategy that happens to match our injection design will look good. Documented-event recall rests on a
single event.

## Limitations

* **Mock ≠ Jev.** In the absence of an API key, "engine" rows come from a heuristic written by the same
  authors as the injection generator. They demonstrate the pipeline; they are not evidence about Jev.
* **Detectability ceiling.** Candidate detection bounds every event-based strategy. Weak correlated
  anomalies (≈3 Pa / 3 K over 5 min) sit within natural sol-to-sol variability at Gale and are usually not
  detected; stuck/dropout injections are detected only when they cover a large part of a window.
* **Byte model.** zlib on PDS ASCII records; flight encodings, CCSDS packetization, relay scheduling and
  real storage allocations differ. Budgets are simulation parameters.
* **Scope.** 20 sols, one season, one site, two instruments; seven-sol baselines; no imagery.
* **Timing.** Wall-clock on a laptop; no flight-processor, power or radiation-tolerance modelling.
* **Label bounds.** The documented SEP label spans a generous window; recall for it is insensitive to
  exact onset timing.

## Risk of model misclassification

A decision model can be confidently wrong. Mitigations in DEEPSIFT: (1) the model never executes an
action — deterministic code maps answers to actions; (2) confidence gating routes low-confidence answers
to rules or escalation; (3) floors keep uncertain and likely-instrument-failure events from being silently
discarded; (4) the model can raise an action by at most one level and only when gated AUTO; (5) every
decision is stored with the exact state the model saw and can be reproduced and inspected. None of these
make a wrong classification right; they bound its consequences and make it visible.

## Why type-safe output ≠ factual correctness

A bounded answer guarantees *shape*: the output is one of the allowed options, with probabilities that
sum to one. It guarantees nothing about *truth*. A perfectly valid `event_type = radiation, confidence
0.97` can be wrong. Calibration (confidence tracking accuracy) must be measured, not assumed; with real
Jev decisions, the stored probabilities and labels allow reliability curves per question. Until that is
done, DEEPSIFT treats every answer as evidence to be gated, not as a fact.

## Reproducibility

* Data: PDS URLs, byte counts and SHA-256 per file (`data/raw/manifest.json`, `data/fixtures/.../MANIFEST.json`).
* Config: content-hashed versions; every change recorded with a path-level diff and note.
* Decisions: event, engine answers, gate, objective, config version, priority breakdown, actions — all in
  DuckDB; the Audit page recomputes each decision and reports exact match.
* Experiments: seeds, injections, labels, per-label outcomes, config snapshot stored as JSON.
* Commands: `npm run fetch-data`, `npm run pipeline`, `npm run benchmark -- --trials 5`, `npm test`.
* Non-determinism: re-querying a real model may give different answers. Stored answers are the record.

## v0.1 result (mock engine — not a result about Jev)

5 seeds, sols 232–251, budget 1,376,256 B, Balanced Science (experiment id in `README.md`):

| strategy | recall | high recall | documented | synthetic | retained-unlabeled | value/MB proxy |
|---|---|---|---|---|---|---|
| random | 20.9 % | 25.0 % | 60 % | 19.0 % | 95.5 % | 8.6 |
| rules | 51.8 % | 73.3 % | 100 % | 49.5 % | 69.7 % | 18.1 |
| statistical | 15.5 % | 11.7 % | 0 % | 16.2 % | 92.3 % | 5.8 |
| engine (mock) | 45.5 % | 68.3 % | 100 % | 42.9 % | 71.3 % | 18.8 |
| engine + deep | unavailable | | | | | |

Reading: the candidate filter plus a priority engine is doing most of the work; the heuristic engine does
not improve recall over rules and slightly improves the proxy. H1 remains untested for Jev.
