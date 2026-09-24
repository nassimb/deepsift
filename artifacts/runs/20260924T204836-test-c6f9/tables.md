### Run 20260924T204836-test-c6f9 — split TEST — git v0.1-baseline-3-g7ae93ca-dirty — config d59227d52476 — Jev: UNAVAILABLE: TYPESAFE_API_KEY not set

#### Documented events — reference budget 0.5 %

| strategy | labels | strict recall | tolerant recall | high-sev recall | coverage | precision (lb) | unlabelled kept | downlinked MB | value/MB (proxy) |
|---|---|---|---|---|---|---|---|---|---|
| ORACLE — NOT DEPLOYABLE | 14 | 70% | 100% | 100% | 16.8% | 100.0% | 0 | 22.60 | 1.5 |
| RANDOM | 14 | 99% [97–100] | 100% [100–100] | 100% [100–100] | 6.5% | 31.4% | 1059 | 22.60 | 1.5 |
| STATISTICAL | 14 | 80% | 93% | 100% | 6.1% | 28.8% | 1382 | 22.60 | 1.4 |
| RULES | 14 | 80% | 93% | 100% | 8.7% | 22.5% | 560 | 20.62 | 1.6 |
| RULES_PLUS_STATISTICAL | 14 | 90% | 93% | 100% | 8.8% | 17.8% | 755 | 22.60 | 1.4 |
| LOCAL_EDGE | 14 | 80% | 93% | 100% | 8.5% | 27.1% | 376 | 19.12 | 1.7 |
| MOCK/ENGINE_ONLY | 14 | 80% | 93% | 100% | 8.7% | 26.3% | 484 | 19.33 | 1.7 |
| MOCK/RULES_PLUS_ENGINE | 14 | 80% | 93% | 100% | 10.2% | 31.2% | 616 | 16.78 | 1.9 |

#### Synthetic stress test — reference budget 0.5 %

| strategy | labels | strict recall | tolerant recall | high-sev recall | coverage | precision (lb) | unlabelled kept | downlinked MB | value/MB (proxy) |
|---|---|---|---|---|---|---|---|---|---|
| ORACLE — NOT DEPLOYABLE | 1852 | 100% | 100% | 100% | 100.0% | 95.3% | 642 | 225.27 | 18.5 |
| RANDOM | 1852 | 28% [28–29] | 30% [30–30] | 36% [36–37] | 6.6% | 2.2% | 37694 | 565.12 | 2.4 |
| STATISTICAL | 1852 | 37% | 39% | 46% | 18.3% | 4.2% | 45837 | 565.12 | 3.1 |
| RULES | 1852 | 47% | 49% | 50% | 36.5% | 5.3% | 17161 | 534.83 | 3.1 |
| RULES_PLUS_STATISTICAL | 1852 | 48% | 50% | 51% | 36.9% | 4.7% | 20181 | 565.12 | 3.0 |
| LOCAL_EDGE | 1852 | 52% | 53% | 53% | 42.1% | 8.5% | 11272 | 502.94 | 4.0 |
| MOCK/ENGINE_ONLY | 1852 | 44% | 45% | 49% | 33.5% | 5.5% | 15498 | 497.79 | 3.1 |
| MOCK/RULES_PLUS_ENGINE | 1852 | 60% | 61% | 60% | 47.0% | 5.4% | 21373 | 445.34 | 3.6 |

#### high_tolerant_recall vs budget — real

| strategy | 0.1% | 0.25% | 0.5% | 1% | 2% | 5% | 10% | 25% |
|---|---|---|---|---|---|---|---|---|
| ORACLE — NOT DEPLOYABLE | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| RANDOM | 98% | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| STATISTICAL | 89% | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| RULES | 78% | 89% | 100% | 100% | 100% | 100% | 100% | 100% |
| RULES_PLUS_STATISTICAL | 78% | 89% | 100% | 100% | 100% | 100% | 100% | 100% |
| LOCAL_EDGE | 78% | 89% | 100% | 100% | 100% | 100% | 100% | 100% |
| MOCK/ENGINE_ONLY | 78% | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| MOCK/RULES_PLUS_ENGINE | 78% | 100% | 100% | 100% | 100% | 100% | 100% | 100% |

#### coverage vs budget — real

| strategy | 0.1% | 0.25% | 0.5% | 1% | 2% | 5% | 10% | 25% |
|---|---|---|---|---|---|---|---|---|
| ORACLE — NOT DEPLOYABLE | 4% | 9% | 17% | 33% | 74% | 100% | 100% | 100% |
| RANDOM | 1% | 3% | 7% | 13% | 26% | 65% | 100% | 100% |
| STATISTICAL | 1% | 3% | 6% | 10% | 18% | 63% | 100% | 100% |
| RULES | 6% | 7% | 9% | 11% | 11% | 11% | 11% | 11% |
| RULES_PLUS_STATISTICAL | 6% | 7% | 9% | 13% | 18% | 65% | 97% | 97% |
| LOCAL_EDGE | 5% | 7% | 8% | 10% | 10% | 10% | 10% | 10% |
| MOCK/ENGINE_ONLY | 6% | 7% | 9% | 11% | 11% | 11% | 11% | 11% |
| MOCK/RULES_PLUS_ENGINE | 6% | 7% | 10% | 11% | 11% | 11% | 11% | 11% |

#### high_tolerant_recall vs budget — synthetic

| strategy | 0.1% | 0.25% | 0.5% | 1% | 2% | 5% | 10% | 25% |
|---|---|---|---|---|---|---|---|---|
| ORACLE — NOT DEPLOYABLE | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| RANDOM | 11% | 22% | 36% | 54% | 73% | 95% | 100% | 100% |
| STATISTICAL | 19% | 34% | 46% | 61% | 80% | 100% | 100% | 100% |
| RULES | 8% | 23% | 50% | 67% | 68% | 68% | 68% | 68% |
| RULES_PLUS_STATISTICAL | 8% | 23% | 51% | 73% | 85% | 100% | 100% | 100% |
| LOCAL_EDGE | 14% | 35% | 53% | 63% | 63% | 63% | 63% | 63% |
| MOCK/ENGINE_ONLY | 13% | 27% | 49% | 65% | 65% | 65% | 65% | 65% |
| MOCK/RULES_PLUS_ENGINE | 13% | 27% | 60% | 68% | 68% | 68% | 68% | 68% |

#### coverage vs budget — synthetic

| strategy | 0.1% | 0.25% | 0.5% | 1% | 2% | 5% | 10% | 25% |
|---|---|---|---|---|---|---|---|---|
| ORACLE — NOT DEPLOYABLE | 74% | 95% | 100% | 100% | 100% | 100% | 100% | 100% |
| RANDOM | 1% | 3% | 7% | 13% | 26% | 65% | 100% | 100% |
| STATISTICAL | 4% | 9% | 18% | 34% | 60% | 94% | 100% | 100% |
| RULES | 3% | 10% | 37% | 53% | 55% | 55% | 55% | 55% |
| RULES_PLUS_STATISTICAL | 3% | 10% | 37% | 58% | 74% | 94% | 98% | 98% |
| LOCAL_EDGE | 10% | 27% | 42% | 51% | 51% | 51% | 51% | 51% |
| MOCK/ENGINE_ONLY | 5% | 13% | 33% | 48% | 48% | 48% | 48% | 48% |
| MOCK/RULES_PLUS_ENGINE | 5% | 13% | 47% | 55% | 55% | 55% | 55% | 55% |

#### Synthetic tolerant recall by difficulty bucket (reference budget)

| strategy | NEAR_NOISE_FLOOR | WEAK | MODERATE | OBVIOUS | QUALITY_FAULT |
|---|---|---|---|---|---|
| ORACLE — NOT DEPLOYABLE | 100% (n=184) | 100% (n=378) | 100% (n=367) | 100% (n=573) | 100% (n=350) |
| STATISTICAL | 29% (n=184) | 37% (n=378) | 37% (n=367) | 53% (n=573) | 26% (n=350) |
| RULES | 37% (n=184) | 41% (n=378) | 42% (n=367) | 60% (n=573) | 52% (n=350) |
| RULES_PLUS_STATISTICAL | 39% (n=184) | 43% (n=378) | 43% (n=367) | 60% (n=573) | 52% (n=350) |
| LOCAL_EDGE | 34% (n=184) | 37% (n=378) | 44% (n=367) | 70% (n=573) | 62% (n=350) |
| MOCK/ENGINE_ONLY | 36% (n=184) | 37% (n=378) | 39% (n=367) | 61% (n=573) | 40% (n=350) |
| MOCK/RULES_PLUS_ENGINE | 43% (n=184) | 48% (n=378) | 51% (n=367) | 77% (n=573) | 71% (n=350) |

#### Documented events by subtype (reference budget): tolerant recall / coverage

| strategy | forbush_decrease | global_dust_storm_phase | solar_energetic_particle_event |
|---|---|---|---|
| ORACLE — NOT DEPLOYABLE | 100% / 15.8% (n=10) | 100% / 20.7% (n=2) | 100% / 18.1% (n=2) |
| STATISTICAL | 90% / 1.8% (n=10) | 100% / 10.6% (n=2) | 100% / 22.8% (n=2) |
| RULES | 90% / 1.9% (n=10) | 100% / 15.4% (n=2) | 100% / 36.0% (n=2) |
| RULES_PLUS_STATISTICAL | 90% / 2.0% (n=10) | 100% / 15.4% (n=2) | 100% / 36.0% (n=2) |
| LOCAL_EDGE | 90% / 1.9% (n=10) | 100% / 16.5% (n=2) | 100% / 33.3% (n=2) |
| MOCK/ENGINE_ONLY | 90% / 1.9% (n=10) | 100% / 15.7% (n=2) | 100% / 35.6% (n=2) |
| MOCK/RULES_PLUS_ENGINE | 90% / 1.9% (n=10) | 100% / 26.1% (n=2) | 100% / 35.6% (n=2) |

#### Storage sweep (whole scored segment in blackout): high-severity events preserved / products


real:

| strategy · policy | 16 KiB | 32 KiB | 64 KiB | 128 KiB | 256 KiB | 512 KiB | 1024 KiB | 2048 KiB | 4096 KiB | 8192 KiB |
|---|---|---|---|---|---|---|---|---|---|---|
| MOCK/RULES_PLUS_ENGINE · PROTECTED_HIGH_VALUE_TIER | 6/9 · F0 S38 | 6/9 · F1 S77 | 9/9 · F2 S144 | 9/9 · F6 S203 | 9/9 · F12 S227 | 9/9 · F38 S137 | 9/9 · F121 S25 | 9/9 · F289 S9 | 9/9 · F446 S33 | 9/9 · F476 S277 |
| MOCK/RULES_PLUS_ENGINE · VALUE_PER_BYTE_ONLY | 6/9 · F0 S30 | 6/9 · F0 S73 | 9/9 · F2 S140 | 9/9 · F6 S213 | 9/9 · F11 S264 | 9/9 · F20 S229 | 9/9 · F57 S183 | 9/9 · F234 S166 | 9/9 · F416 S191 | 9/9 · F476 S277 |
| RULES · PROTECTED_HIGH_VALUE_TIER | 6/9 · F0 S29 | 7/9 · F0 S72 | 8/9 · F0 S133 | 9/9 · F8 S220 | 9/9 · F17 S271 | 9/9 · F45 S342 | 9/9 · F110 S128 | 9/9 · F339 S60 | 9/9 · F596 S17 | 9/9 · F774 S31 |
| RULES · VALUE_PER_BYTE_ONLY | 6/9 · F0 S28 | 7/9 · F0 S72 | 8/9 · F0 S131 | 9/9 · F8 S220 | 9/9 · F17 S272 | 9/9 · F40 S356 | 9/9 · F100 S175 | 9/9 · F317 S146 | 9/9 · F570 S247 | 9/9 · F766 S220 |

synthetic:

| strategy · policy | 16 KiB | 32 KiB | 64 KiB | 128 KiB | 256 KiB | 512 KiB | 1024 KiB | 2048 KiB | 4096 KiB | 8192 KiB |
|---|---|---|---|---|---|---|---|---|---|---|
| MOCK/RULES_PLUS_ENGINE · PROTECTED_HIGH_VALUE_TIER | 3/56 · F0 S37 | 4/56 · F2 S76 | 8/56 · F3 S141 | 12/56 · F7 S198 | 15/56 · F13 S222 | 18/56 · F39 S132 | 18/56 · F124 S29 | 18/56 · F290 S13 | 18/56 · F443 S21 | 36/56 · F474 S286 |
| MOCK/RULES_PLUS_ENGINE · VALUE_PER_BYTE_ONLY | 4/56 · F0 S28 | 5/56 · F0 S73 | 9/56 · F2 S137 | 12/56 · F7 S208 | 16/56 · F13 S258 | 19/56 · F20 S231 | 27/56 · F59 S188 | 32/56 · F235 S177 | 34/56 · F412 S195 | 36/56 · F474 S286 |
| RULES · PROTECTED_HIGH_VALUE_TIER | 3/56 · F0 S27 | 4/56 · F0 S71 | 6/56 · F0 S131 | 11/56 · F9 S212 | 14/56 · F20 S266 | 18/56 · F46 S338 | 25/56 · F110 S132 | 25/56 · F342 S67 | 25/56 · F597 S19 | 25/56 · F774 S6 |
| RULES · VALUE_PER_BYTE_ONLY | 3/56 · F0 S27 | 4/56 · F0 S70 | 6/56 · F0 S130 | 11/56 · F9 S212 | 14/56 · F20 S265 | 20/56 · F42 S351 | 29/56 · F99 S186 | 32/56 · F319 S158 | 36/56 · F569 S258 | 36/56 · F765 S228 |

#### Gating sweep real:MOCK: Pareto-optimal points (3/24)

| auto ≥ | uncertain ≥ | high-sev recall | precision (lb) | would escalate | downlinked MB |
|---|---|---|---|---|---|
| 0.8 | 0.3 | 100% | 36.3% | 0/1073 | 16.78 |
| 0.9 | 0.3 | 100% | 36.3% | 0/1073 | 16.78 |
| 0.95 | 0.3 | 100% | 36.3% | 0/1073 | 16.78 |

#### Gating sweep synthetic:MOCK: Pareto-optimal points (2/24)

| auto ≥ | uncertain ≥ | high-sev recall | precision (lb) | would escalate | downlinked MB |
|---|---|---|---|---|---|
| 0.9 | 0.3 | 47% | 5.1% | 0/5446 | 90.83 |
| 0.95 | 0.3 | 47% | 5.1% | 0/5446 | 90.83 |

#### Confidence calibration (MODEL CONFIDENCE, not probability of scientific truth)

| series | n | ECE | mean confidence | observed agreement |
|---|---|---|---|---|
| real:MOCK:importance | 1073 | 0.559 | 77.1% | 27.6% |
| synthetic:MOCK:event_type | 1769 | 0.331 | 79.1% | 46.0% |
| synthetic:MOCK:importance | 27314 | 0.685 | 76.5% | 6.5% |

#### Latency (ms, measured on the development laptop)

| series | n | p50 | p90 | p95 | p99 | max |
|---|---|---|---|---|---|---|
| engine_call_ms:MOCK | 28387 | 0.0132 | 0.0162 | 0.0187 | 0.0334 | 159 |
| preprocessing_ms_per_event | 1073 | 4.35 | 11.5 | 11.5 | 11.5 | 11.5 |
| priority_ms_per_event | 28387 | 0.0567 | 0.0683 | 0.0818 | 0.108 | 130 |
| routing_ms_per_event:LOCAL_EDGE | 28387 | 19.9 | 32.4 | 32.9 | 33.5 | 37.6 |
| routing_ms_per_event:MOCK | 28387 | 20 | 32.5 | 33 | 33.6 | 179 |
| routing_ms_per_event:RULES | 28387 | 20 | 32.5 | 33 | 33.6 | 151 |

Jev usage: {'calls': 0, 'errors': 0, 'cost_usd': 0.0, 'input_tokens': 0}
