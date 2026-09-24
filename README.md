# DEEPSIFT — Deep Space Intelligent Filtering & Triage

> *Not every bit deserves the trip to Earth.*

DEEPSIFT is a **research prototype** of an onboard science-triage system for bandwidth-constrained
spacecraft. It ingests real Mars Science Laboratory (Curiosity) environmental and radiation data from
the NASA Planetary Data System, finds candidate events with deterministic statistics, asks a fast
decision model a handful of **bounded** questions about each candidate, and lets deterministic code
decide what is downlinked in full, compressed, summarised or discarded — under a simulated storage and
relay budget, including a communication blackout.

It is built to be **measured, inspected and reproduced**, not to impress. It is not flight software, it
is not validated by NASA/JPL, and it does not produce scientific findings.

> **Onboard vs cloud — read this first.** DEEPSIFT evaluates an *onboard-autonomy architecture*.
> ONBOARD-SIMULATED: preprocessing, feature extraction, candidate detection, priority, storage,
> bandwidth and routing. REMOTE: Jev inference, which runs on TypeSafe's hosted API over the network.
> The current Jev implementation is API-hosted and therefore does not establish deployability on
> spacecraft hardware. Jev latency and cost figures are for a ground-based API call, not an onboard
> processor. The LOCAL EDGE BASELINE is the only decision model in DEEPSIFT that runs without a network.

---

## Why onboard science triage matters

Instruments can generate far more data than relay passes can carry, and link availability is not
guaranteed. When the spacecraft must choose what to keep, the choice has to be (1) fast and cheap,
(2) aligned with what scientists currently care about, and (3) explainable after the fact. DEEPSIFT
explores one architecture for that: cheap deterministic filtering first, a small bounded-output model
second, and a code-owned priority/scheduling layer last — with every decision logged.

## Architecture

```
/apps/web                 Next.js 16 · TypeScript · Tailwind v4 — Mission Control UI
/services/pipeline
  deepsift/core           typed event model (pydantic), versioned config
  deepsift/adapters       MissionAdapter interface + CuriosityAdapter (REMS MODRDR, RAD RDR)
  deepsift/features       windowing, diurnal baselines, robust z, dips, quality flags, novelty, detection
  deepsift/decision       DecisionEngine (Mock, Jev), bounded questions, state builder, gating, DeepAnalysisProvider
  deepsift/objectives     mission objectives as structured config
  deepsift/priority       deterministic utility, action policy, explanations, counterfactuals
  deepsift/simulation     storage + downlink scheduler + blackout (discrete-event)
  deepsift/evaluation     anomaly injection, labels, 5 strategies, metrics, benchmark harness
  deepsift/audit          DuckDB audit log (decisions, runs, config versions, labels)
  deepsift/api            FastAPI service
  tests/                  58 pytest tests
/config                   default.yaml (all thresholds/weights/budgets), objectives.yaml
/data/raw                 PDS download cache + manifest.json (URLs, sizes, sha256) — git-ignored
/data/fixtures            real PDS sample, sols 238–243 (gzip) — offline fallback, LOCAL NASA SAMPLE
/data/labels              documented_events.yaml
/scripts                  fetch_nasa.py, run_pipeline.py, run_benchmark.py, demo.sh
/docs                     architecture.md, research-methodology.md, leakage-audit.md, ground-truth.md, jev-evaluation.md
```

The requested `packages/{core,mission-adapters,decision-engine,simulation,evaluation}` split is kept
as sub-packages of one Python package (`deepsift.*`) — same boundaries, no multi-package build overhead.

### Pipeline

```mermaid
flowchart LR
  A[PDS products<br/>REMS · RAD] --> B[MissionAdapter<br/>normalize]
  B --> C[Windows<br/>5-min LMST · per RAD obs]
  C --> D[Features<br/>robust z vs nearest-LMST baseline<br/>dip · stuck · dropout · noise · rarity]
  D --> E{Candidate<br/>filter}
  E -- most windows --> S[per-sol summary]
  E -- candidates --> F[Decision engine<br/>5 bounded questions]
  F --> G{Confidence<br/>gate}
  G -- auto / uncertain --> P[Priority engine<br/>deterministic utility]
  G -- low confidence --> R[Rules fallback]
  G -- escalate --> X[Deep analysis<br/>optional]
  R --> P
  X --> P
  P --> Q[Storage + downlink<br/>scheduler · blackout]
  Q --> L[(Audit log)]
```

## Dataset

| | |
|---|---|
| Mission | Mars Science Laboratory / Curiosity, Gale Crater |
| Segment | sols 232–251 (2013-04-01 → 2013-04-21) |
| REMS | `MSL-M-REMS-5-MODRDR-V1.0`, PDS Atmospheres Node — pressure, ambient air temperature, ground brightness temperature, UV-ABC, relative humidity (≈1 Hz bursts, 372-byte ASCII records) |
| RAD | `MSL-M-RAD-3-RDR-V1.0`, PDS PPI Node — total dose rate B and E (µGy/h), one value per ~1 h integration |
| Volume | 20 REMS + 20 RAD products, 294 MB raw, 1.43 M channel samples |
| Documented event | 2013-04-11 solar particle event (sol 242) — dose B rises from ~9.1 to 12.13 µGy/h in the RDR |

Timing: REMS UTC comes from each label's spacecraft-clock/UTC pair. RAD local time is derived from
`START_OBS_UTC` via a linear fit to the REMS UTC↔LMST relation, because the RAD `START_OBS_MARS` field
does not advance per observation in these products. The fit recovers a sol length of 88,775.244 s
(known value 88,775.244 s) with < 0.5 s residual.

**Data provenance is always visible**: `NASA PDS · REAL DATA` (downloaded), `LOCAL NASA SAMPLE`
(bundled real bytes), or `SYNTHETIC TEST DATA`. Real data is never silently replaced. Synthetic
anomalies are injected only in benchmark copies and are tagged on every sample, event and label.

## How Jev is used

[Jev](https://docs.typesafe.ai/) is TypeSafe AI's "System One" decision model. DEEPSIFT uses it only
through `deepsift/decision/jev.py`, via the official `typesafe-sdk` (0.7.1, wire schema generated from
`api.typesafe.ai/openapi.json`):

```python
client.system_one(state=<compact event state>, questions={...}, model="jev-latest")
# ChoiceAnswer(choice, confidence, probabilities) · NoulAnswer(noul) · usage.input_tokens
```

Five bounded questions per candidate (`deepsift/decision/questions.py`):

| question | type | options |
|---|---|---|
| `science_value` | choice | none · low · medium · high · critical |
| `event_type` | choice | nominal · atmospheric · radiation · thermal · instrument_anomaly · unknown |
| `downlink_action` | choice | discard · summary_only · compress · full_data |
| `needs_deep_analysis` | noul | P(yes) |
| `instrument_failure` | choice | yes · no · uncertain |

Design choices driven by TypeSafe's own guidance:

* **State, not raw rows.** The engine sees aggregated features; every number is paired with a
  deterministic qualitative descriptor ("+14.0 sigma — extremely far above normal") because Jev is
  documented as weak with raw numbers and dates.
* **Objective-independent questions.** The mission objective is applied in code to the returned
  probabilities, so switching objectives re-scores stored decisions with **zero** new engine calls.
* **Probabilities are persisted** exactly as returned, with latency, token usage and cost.

### Why Jev is NOT used for generation

Decisions here must be comparable, gateable and reproducible. Bounded answers with probabilities can be
thresholded, audited and re-scored; prose cannot. Explanations ("Why was this selected?") are assembled
from features, config and decision metadata. The only model-generated text in the system is the optional
deep-analysis rationale, which is always labelled `MODEL-GENERATED TEXT`.

### Mock mode

With `decision_engine.kind: auto` (default) and no `TYPESAFE_API_KEY`, the pipeline uses `MockDecisionEngine` — a transparent, deterministic
heuristic that returns the same answer shapes. Every UI surface and benchmark row that depends on it is
labelled `ENGINE MOCK · HEURISTIC` / "(mock)". **Mock results are not evidence about Jev.**

### Code owns the action

```
utility = (1 − λ(1 − confidence)) × Σ w_k · term_k
          terms: science_value (E[value] under the engine distribution) · mission_relevance
                 (objective weights × P(type)) · anomaly_strength (1 − e^(−dev/6)) · novelty
action  = thresholds(utility) → floors (uncertain gate ⇒ ≥ SUMMARY; P(instrument failure) ≥ 0.6 ⇒ ≥ SUMMARY)
          → engine may raise the action by one level only when gated AUTO
storage = degrade lowest utility-per-byte first; products with utility ≥ FULL threshold degraded last
```

Confidence gating: `≥ 0.90` automatic · `0.70–0.90` kept but flagged uncertain · `< 0.70` deterministic
rules (or deep analysis if a provider is configured). All values live in `config/default.yaml`.

## Benchmark methodology (summary)

Five strategies run on the same 20 sols with the same byte budget (2 passes/sol × 32 KiB × sols) and the
same greedy allocator: **random sampling**, **threshold rules**, **statistical anomaly detection**,
**decision engine**, **engine + deep analysis** (reported UNAVAILABLE without a provider). Labels are one
documented event plus nine kinds of synthetic injections per trial, placed with a seed. Full details and
caveats: [`docs/research-methodology.md`](docs/research-methodology.md).

> **Superseded.** The v0.1 benchmark below leaked: thresholds, injection magnitudes and one storage
> policy were tuned on the same sols it evaluates (`docs/leakage-audit.md`). It is kept as a development
> record. The Phase-2 held-out evaluation is summarised in the next section.

**v0.1 development result (2026-09-24, Apple M5, 5 seeds, engine = mock heuristic, NOT Jev)** —
experiment `20260924T190246-8a4f1b`:

| strategy | recall | high-severity recall | retained-but-unlabeled¹ | value/MB (proxy)² |
|---|---|---|---|---|
| random sampling | 20.9 % | 25.0 % | 95.5 % | 8.6 |
| threshold rules | **51.8 %** | **73.3 %** | 69.7 % | 18.1 |
| statistical anomaly | 15.5 % | 11.7 % | 92.3 % | 5.8 |
| decision engine (mock) | 45.5 % | 68.3 % | 71.3 % | **18.8** |
| engine + deep | unavailable | | | |

¹ upper bound on the false-positive rate (unlabeled real phenomena exist). ² Σ severity × assumed
fidelity per downlinked MB — a proxy, not a measure of scientific value.

In this configuration **simple rules beat the heuristic engine on recall**. Whether Jev beats the rules is
exactly what the harness is for; it has not been measured here because no API key was available.

Measured pipeline performance on the same machine (`npm run pipeline`): 1.43 M samples preprocessed in
≈4.3 s (≈330 k samples/s, of which ≈3.9 s is ASCII parsing); windowing + features + detection ≈ 290 ms;
126 candidates from 1,922 instrument windows; mock-engine decisions ≈ 0.015 ms each (Python function
time, not model inference); 99.5 % data reduction under the default budget.

## Phase 2: held-out evaluation (current)

* Temporal splits: calibration (sols 232–251) → validation (412–430, 779–820) → **test** (732–750,
  871–930, 2068–2105), each held-out segment with a never-scored baseline warm-up (`data/splits/splits.json`).
* Thresholds derived label-free from calibration only (`scripts/calibrate.py`); gating thresholds frozen
  on validation by a pre-declared rule; test run once.
* Ground truth: 121 Forbush decreases (Guo et al. 2018), 16 surface SEP dates (Löwe et al. 2025), MY34
  dust-storm phases (Viúdez-Moreiras et al. 2019); sol 242 verification record (`docs/ground-truth.md`).
* 1,852 synthetic injections on test in declared difficulty buckets; strict / tolerant / coverage metrics;
  RANDOM over 30 seeds; ORACLE — NOT DEPLOYABLE; LOCAL EDGE BASELINE (1.6 KB logistic model, no network).
* **Jev was not evaluated — no API key was available.** The harness, call log, smoke test and five
  ablations are ready (`docs/jev-evaluation.md` → "How to run").

Held-out findings (mock engine, not Jev): candidate detection caps every event-based strategy at 63–68 %
high-severity synthetic recall; above ~1 % of raw bytes a no-AI rules + statistical hybrid leads (73 → 100 %);
at 0.5 % the mock engine reaches 60 % vs rules 50 % and the local edge model 53 %; documented Forbush
decreases are not isolated by the detector (≈2 % data coverage, random 7 %); the v0.1 protected-tier storage
policy preserves *fewer* high-severity synthetic events at 1–4 MiB. Full report: `docs/jev-evaluation.md`;
UI: `/study`; artifacts: `artifacts/runs/`, `artifacts/figures/`.

## How to reproduce

```bash
uv run python scripts/fetch_nasa.py --sols 232-251   # real PDS products + manifest (sha256)
npm run pipeline                                      # one run → audit log + stage timings
npm run benchmark -- --trials 5                       # stored in data/processed/experiments/
npm test                                              # 58 tests (run offline on the bundled sample)
```

Every run records the config version (content hash), pipeline version, engine, objective and each
decision's inputs; the Audit page recomputes utility and action from those inputs and reports whether
they match exactly.

## Running locally

Requirements: Python 3.12 via [uv](https://docs.astral.sh/uv/), Node.js ≥ 20.

```bash
npm run demo
```

This installs dependencies, downloads the 20-sol segment from the PDS on first run (≈290 MB; falls back
to the bundled sample if the download fails), starts the API on `:8787` and the UI on `:3000`, and
opens Mission Control. Then: **PLAY** → change the **Objective** → **Trigger blackout** → click any
event → **Experiments → Run benchmark**.

Individual services: `npm run api`, `npm run web`.

## Environment variables

| variable | purpose |
|---|---|
| `TYPESAFE_API_KEY` | enables `JevDecisionEngine` automatically (`decision_engine.kind: auto`; set `mock` to force the heuristic) |
| `TYPESAFE_BASE_URL`, `TYPESAFE_DEFAULT_MODEL` | optional SDK overrides |
| `ANTHROPIC_API_KEY` | enables `ClaudeDeepAnalysis` (also set `deep_analysis.provider: claude`) |
| `NEXT_PUBLIC_DEEPSIFT_API` | UI → API base URL (default `http://localhost:8787`) |
| `DEEPSIFT_SOLS`, `DEEPSIFT_API_PORT`, `DEEPSIFT_WEB_PORT`, `DEEPSIFT_SKIP_FETCH` | demo script options |

Copy `.env.example` to `.env`; keys are never hard-coded or logged.

## Limitations

* One documented event; recall is dominated by synthetic injections whose kinds and magnitudes we chose.
* The mock engine and the injection generator share authors — mock rows say nothing about Jev.
* Byte costs are zlib sizes of PDS ASCII records; storage/relay budgets are simulation parameters, not
  Curiosity's allocations.
* 20 sols, one season, one site; seven-sol trailing baselines.
* Weak multi-sensor anomalies (a few Pa / K over minutes) fall inside natural sol-to-sol variability at
  Gale and are usually missed by the candidate filter.
* No flight-processor timing, power or radiation-tolerance modelling.

## Future work

Real Jev evaluation and calibration curves · more documented events (e.g. Sept 2017 SEP, 2018 dust storm)
and human labels · Perseverance MEDA adapter · imagery and multi-instrument fusion · learned baselines ·
onboard-realistic encodings and CCSDS packetization · hardware-in-the-loop timing.

## Research disclaimer

DEEPSIFT is a prototype and a simulation. It makes no claim of NASA validation, flight readiness,
scientific discovery or operational superiority. Metrics labelled *proxy* do not measure true scientific
value. NASA data courtesy of the Planetary Data System (Atmospheres and PPI nodes); REMS data produced by
Centro de Astrobiología, RAD data by the MSL RAD team.
