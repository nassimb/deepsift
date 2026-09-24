### Run 20260924T203948-validation-91b4 — split VALIDATION — git v0.1-baseline-2-g52996bb-dirty — config 7c2806f1c14d — Jev: UNAVAILABLE: TYPESAFE_API_KEY not set

#### Documented events — reference budget 0.5 %

| strategy | labels | strict recall | tolerant recall | high-sev recall | coverage | precision (lb) | unlabelled kept | downlinked MB | value/MB (proxy) |
|---|---|---|---|---|---|---|---|---|---|
| ORACLE — NOT DEPLOYABLE | 6 | 80% | 100% | 100% | 43.4% | 100.0% | 0 | 11.29 | 1.5 |
| RANDOM | 6 | 98% [96–100] | 100% [100–100] | 100% [100–100] | 6.9% | 13.9% | 736 | 11.29 | 1.5 |
| STATISTICAL | 6 | 100% | 100% | 100% | 3.0% | 6.4% | 1009 | 11.29 | 1.5 |
| RULES | 6 | 100% | 100% | 100% | 2.7% | 7.1% | 340 | 10.58 | 1.6 |
| RULES_PLUS_STATISTICAL | 6 | 100% | 100% | 100% | 2.7% | 5.9% | 418 | 11.29 | 1.5 |
| LOCAL_EDGE | 6 | 100% | 100% | 100% | 2.1% | 8.5% | 195 | 9.72 | 1.7 |
| MOCK/ENGINE_ONLY | 6 | 100% | 100% | 100% | 2.7% | 6.8% | 359 | 7.65 | 2.2 |
| MOCK/RULES_PLUS_ENGINE | 6 | 100% | 100% | 100% | 2.7% | 5.7% | 432 | 9.81 | 1.7 |

#### Synthetic stress test — reference budget 0.5 %

| strategy | labels | strict recall | tolerant recall | high-sev recall | coverage | precision (lb) | unlabelled kept | downlinked MB | value/MB (proxy) |
|---|---|---|---|---|---|---|---|---|---|
| ORACLE — NOT DEPLOYABLE | 971 | 100% | 100% | 100% | 100.0% | 95.5% | 310 | 104.40 | 21.0 |
| RANDOM | 971 | 30% [29–30] | 31% [31–32] | 38% [37–39] | 7.4% | 2.3% | 20875 | 282.36 | 2.6 |
| STATISTICAL | 971 | 38% | 39% | 42% | 21.8% | 4.7% | 25469 | 282.36 | 3.1 |
| RULES | 971 | 48% | 48% | 52% | 36.6% | 5.7% | 8495 | 269.27 | 3.6 |
| RULES_PLUS_STATISTICAL | 971 | 48% | 49% | 52% | 37.2% | 5.1% | 9948 | 282.36 | 3.5 |
| LOCAL_EDGE | 971 | 51% | 51% | 48% | 42.7% | 10.1% | 4657 | 249.29 | 4.0 |
| MOCK/ENGINE_ONLY | 971 | 60% | 61% | 61% | 48.0% | 6.4% | 9268 | 206.72 | 4.2 |
| MOCK/RULES_PLUS_ENGINE | 971 | 61% | 62% | 60% | 48.9% | 6.1% | 10007 | 255.84 | 3.8 |

#### high_tolerant_recall vs budget — real

| strategy | 0.1% | 0.25% | 0.5% | 1% | 2% | 5% | 10% | 25% |
|---|---|---|---|---|---|---|---|---|
| ORACLE — NOT DEPLOYABLE | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| RANDOM | 92% | 99% | 100% | 100% | 100% | 100% | 100% | 100% |
| STATISTICAL | 80% | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| RULES | 80% | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| RULES_PLUS_STATISTICAL | 80% | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| LOCAL_EDGE | 80% | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| MOCK/ENGINE_ONLY | 80% | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| MOCK/RULES_PLUS_ENGINE | 60% | 80% | 100% | 100% | 100% | 100% | 100% | 100% |

#### coverage vs budget — real

| strategy | 0.1% | 0.25% | 0.5% | 1% | 2% | 5% | 10% | 25% |
|---|---|---|---|---|---|---|---|---|
| ORACLE — NOT DEPLOYABLE | 11% | 27% | 43% | 63% | 95% | 100% | 100% | 100% |
| RANDOM | 1% | 3% | 7% | 14% | 28% | 71% | 100% | 100% |
| STATISTICAL | 1% | 2% | 3% | 4% | 17% | 57% | 100% | 100% |
| RULES | 2% | 2% | 3% | 3% | 3% | 3% | 3% | 3% |
| RULES_PLUS_STATISTICAL | 2% | 2% | 3% | 4% | 19% | 59% | 97% | 97% |
| LOCAL_EDGE | 1% | 1% | 2% | 3% | 3% | 3% | 3% | 3% |
| MOCK/ENGINE_ONLY | 2% | 3% | 3% | 3% | 3% | 3% | 3% | 3% |
| MOCK/RULES_PLUS_ENGINE | 2% | 2% | 3% | 3% | 3% | 3% | 3% | 3% |

#### high_tolerant_recall vs budget — synthetic

| strategy | 0.1% | 0.25% | 0.5% | 1% | 2% | 5% | 10% | 25% |
|---|---|---|---|---|---|---|---|---|
| ORACLE — NOT DEPLOYABLE | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| RANDOM | 12% | 24% | 38% | 55% | 74% | 95% | 100% | 100% |
| STATISTICAL | 17% | 31% | 42% | 60% | 80% | 100% | 100% | 100% |
| RULES | 10% | 29% | 52% | 66% | 66% | 66% | 66% | 66% |
| RULES_PLUS_STATISTICAL | 10% | 29% | 52% | 76% | 85% | 100% | 100% | 100% |
| LOCAL_EDGE | 20% | 33% | 48% | 60% | 60% | 60% | 60% | 60% |
| MOCK/ENGINE_ONLY | 16% | 31% | 61% | 61% | 61% | 61% | 61% | 61% |
| MOCK/RULES_PLUS_ENGINE | 10% | 26% | 60% | 66% | 66% | 66% | 66% | 66% |

#### coverage vs budget — synthetic

| strategy | 0.1% | 0.25% | 0.5% | 1% | 2% | 5% | 10% | 25% |
|---|---|---|---|---|---|---|---|---|
| ORACLE — NOT DEPLOYABLE | 79% | 97% | 100% | 100% | 100% | 100% | 100% | 100% |
| RANDOM | 2% | 4% | 7% | 15% | 29% | 73% | 100% | 100% |
| STATISTICAL | 5% | 13% | 22% | 38% | 64% | 96% | 100% | 100% |
| RULES | 3% | 15% | 37% | 56% | 56% | 56% | 56% | 56% |
| RULES_PLUS_STATISTICAL | 3% | 15% | 37% | 63% | 77% | 95% | 98% | 98% |
| LOCAL_EDGE | 14% | 28% | 43% | 52% | 52% | 52% | 52% | 52% |
| MOCK/ENGINE_ONLY | 6% | 18% | 48% | 48% | 48% | 48% | 48% | 48% |
| MOCK/RULES_PLUS_ENGINE | 3% | 12% | 49% | 56% | 56% | 56% | 56% | 56% |

#### Synthetic tolerant recall by difficulty bucket (reference budget)

| strategy | NEAR_NOISE_FLOOR | WEAK | MODERATE | OBVIOUS | QUALITY_FAULT |
|---|---|---|---|---|---|
| ORACLE — NOT DEPLOYABLE | 100% (n=90) | 100% (n=196) | 100% (n=199) | 100% (n=303) | 100% (n=183) |
| STATISTICAL | 30% (n=90) | 31% (n=196) | 31% (n=199) | 55% (n=303) | 35% (n=183) |
| RULES | 29% (n=90) | 33% (n=196) | 36% (n=199) | 74% (n=303) | 46% (n=183) |
| RULES_PLUS_STATISTICAL | 31% (n=90) | 35% (n=196) | 36% (n=199) | 74% (n=303) | 46% (n=183) |
| LOCAL_EDGE | 34% (n=90) | 35% (n=196) | 37% (n=199) | 70% (n=303) | 61% (n=183) |
| MOCK/ENGINE_ONLY | 37% (n=90) | 42% (n=196) | 50% (n=199) | 86% (n=303) | 62% (n=183) |
| MOCK/RULES_PLUS_ENGINE | 37% (n=90) | 46% (n=196) | 48% (n=199) | 84% (n=303) | 70% (n=183) |

#### Documented events by subtype (reference budget): tolerant recall / coverage

| strategy | forbush_decrease | solar_energetic_particle_event |
|---|---|---|
| ORACLE — NOT DEPLOYABLE | 100% / 36.5% (n=5) | 100% / 77.8% (n=1) |
| STATISTICAL | 100% / 2.5% (n=5) | 100% / 5.2% (n=1) |
| RULES | 100% / 2.1% (n=5) | 100% / 5.6% (n=1) |
| RULES_PLUS_STATISTICAL | 100% / 2.1% (n=5) | 100% / 5.6% (n=1) |
| LOCAL_EDGE | 100% / 1.4% (n=5) | 100% / 5.6% (n=1) |
| MOCK/ENGINE_ONLY | 100% / 2.1% (n=5) | 100% / 5.6% (n=1) |
| MOCK/RULES_PLUS_ENGINE | 100% / 2.1% (n=5) | 100% / 5.6% (n=1) |

#### Storage sweep (whole scored segment in blackout): high-severity events preserved / products


real:

| strategy · policy | 16 KiB | 32 KiB | 64 KiB | 128 KiB | 256 KiB | 512 KiB | 1024 KiB | 2048 KiB | 4096 KiB | 8192 KiB |
|---|---|---|---|---|---|---|---|---|---|---|
| MOCK/RULES_PLUS_ENGINE · PROTECTED_HIGH_VALUE_TIER | 3/5 · F0 S16 | 4/5 · F0 S30 | 5/5 · F2 S61 | 5/5 · F10 S87 | 5/5 · F16 S106 | 5/5 · F40 S66 | 5/5 · F110 S21 | 5/5 · F210 S12 | 5/5 · F272 S42 | 5/5 · F292 S131 |
| MOCK/RULES_PLUS_ENGINE · VALUE_PER_BYTE_ONLY | 3/5 · F0 S15 | 4/5 · F0 S30 | 5/5 · F2 S61 | 5/5 · F10 S87 | 5/5 · F16 S118 | 5/5 · F36 S95 | 5/5 · F91 S100 | 5/5 · F194 S144 | 5/5 · F265 S134 | 5/5 · F292 S131 |
| RULES · PROTECTED_HIGH_VALUE_TIER | 2/5 · F0 S18 | 4/5 · F0 S32 | 5/5 · F2 S65 | 5/5 · F10 S87 | 5/5 · F18 S111 | 5/5 · F36 S98 | 5/5 · F101 S32 | 5/5 · F208 S19 | 5/5 · F283 S36 | 5/5 · F322 S104 |
| RULES · VALUE_PER_BYTE_ONLY | 2/5 · F0 S17 | 4/5 · F0 S32 | 5/5 · F2 S64 | 5/5 · F10 S87 | 5/5 · F18 S114 | 5/5 · F33 S109 | 5/5 · F90 S97 | 5/5 · F198 S119 | 5/5 · F279 S123 | 5/5 · F321 S118 |

synthetic:

| strategy · policy | 16 KiB | 32 KiB | 64 KiB | 128 KiB | 256 KiB | 512 KiB | 1024 KiB | 2048 KiB | 4096 KiB | 8192 KiB |
|---|---|---|---|---|---|---|---|---|---|---|
| MOCK/RULES_PLUS_ENGINE · PROTECTED_HIGH_VALUE_TIER | 1/23 · F0 S16 | 3/23 · F0 S31 | 4/23 · F2 S61 | 5/23 · F10 S86 | 7/23 · F16 S110 | 7/23 · F40 S74 | 7/23 · F106 S23 | 7/23 · F207 S14 | 9/23 · F272 S46 | 12/23 · F297 S137 |
| MOCK/RULES_PLUS_ENGINE · VALUE_PER_BYTE_ONLY | 1/23 · F0 S16 | 3/23 · F0 S31 | 4/23 · F2 S62 | 5/23 · F10 S86 | 7/23 · F16 S121 | 8/23 · F34 S101 | 11/23 · F88 S109 | 11/23 · F193 S150 | 12/23 · F265 S143 | 12/23 · F297 S137 |
| RULES · PROTECTED_HIGH_VALUE_TIER | 1/23 · F0 S19 | 3/23 · F0 S33 | 3/23 · F2 S66 | 6/23 · F9 S88 | 7/23 · F18 S114 | 7/23 · F36 S104 | 8/23 · F101 S39 | 8/23 · F205 S21 | 10/23 · F284 S41 | 10/23 · F325 S38 |
| RULES · VALUE_PER_BYTE_ONLY | 1/23 · F0 S18 | 3/23 · F0 S33 | 3/23 · F2 S65 | 6/23 · F9 S88 | 7/23 · F18 S118 | 9/23 · F32 S115 | 11/23 · F88 S109 | 11/23 · F194 S125 | 12/23 · F279 S132 | 12/23 · F324 S124 |

#### Gating sweep real:MOCK: Pareto-optimal points (8/24)

| auto ≥ | uncertain ≥ | high-sev recall | precision (lb) | would escalate | downlinked MB |
|---|---|---|---|---|---|
| 0.5 | 0.3 | 100% | 5.3% | 0/458 | 8.54 |
| 0.6 | 0.3 | 100% | 4.9% | 0/458 | 7.65 |
| 0.8 | 0.3 | 100% | 4.7% | 0/458 | 6.49 |
| 0.8 | 0.8 | 100% | 5.9% | 333/458 | 10.47 |
| 0.9 | 0.3 | 100% | 4.7% | 0/458 | 6.49 |
| 0.9 | 0.8 | 100% | 5.9% | 333/458 | 10.47 |
| 0.95 | 0.3 | 100% | 4.7% | 0/458 | 6.49 |
| 0.95 | 0.8 | 100% | 5.9% | 333/458 | 10.47 |

#### Gating sweep synthetic:MOCK: Pareto-optimal points (4/24)

| auto ≥ | uncertain ≥ | high-sev recall | precision (lb) | would escalate | downlinked MB |
|---|---|---|---|---|---|
| 0.5 | 0.3 | 60% | 6.7% | 0/2353 | 45.21 |
| 0.8 | 0.3 | 65% | 6.7% | 0/2353 | 34.66 |
| 0.9 | 0.3 | 65% | 6.7% | 0/2353 | 34.66 |
| 0.95 | 0.3 | 65% | 6.7% | 0/2353 | 34.66 |

#### Confidence calibration (MODEL CONFIDENCE, not probability of scientific truth)

| series | n | ECE | mean confidence | observed agreement |
|---|---|---|---|---|
| real:MOCK:importance | 458 | 0.628 | 73.3% | 5.7% |
| synthetic:MOCK:event_type | 884 | 0.311 | 78.6% | 48.8% |
| synthetic:MOCK:importance | 11766 | 0.642 | 72.8% | 7.5% |

#### Latency (ms, measured on the development laptop)

| series | n | p50 | p90 | p95 | p99 | max |
|---|---|---|---|---|---|---|
| engine_call_ms:MOCK | 12224 | 0.0127 | 0.0141 | 0.0165 | 0.0306 | 75.6 |
| preprocessing_ms_per_event | 458 | 9.05 | 9.05 | 9.05 | 9.05 | 9.05 |
| priority_ms_per_event | 12224 | 0.0538 | 0.0596 | 0.0774 | 0.101 | 101 |
| routing_ms_per_event:LOCAL_EDGE | 12224 | 22 | 22.7 | 23 | 23.1 | 23.1 |
| routing_ms_per_event:MOCK | 12224 | 22.1 | 22.8 | 23.1 | 23.1 | 123 |
| routing_ms_per_event:RULES | 12224 | 22.1 | 22.8 | 23.1 | 23.1 | 123 |

Jev usage: {'calls': 0, 'errors': 0, 'cost_usd': 0.0, 'input_tokens': 0}
