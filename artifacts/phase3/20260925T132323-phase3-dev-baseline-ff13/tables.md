# Phase 3 baseline tables — 20260925T132323-phase3-dev-baseline-ff13

Budget base: 161.37 MB (Σ FULL onboard-compressed bytes); acquisitions with UNKNOWN full cost: 0.

## Mode: policy

*policy* = each strategy's own action policy; *ordering* = common thumbnails-for-all first pass, then FULL upgrades in strategy order (THUMBNAIL-EVERYTHING and PHASH-REPRESENTATIVES are identical in both modes).

### UNIQUE SCENE CLUSTERS retained at ≥ COMPRESSED (of 548)

| strategy | 0.1% | 0.25% | 0.5% | 1% | 2% | 5% | 10% |
|---|---|---|---|---|---|---|---|
| FIFO | 2 | 16 | 11 | 23 | 26 | 55 | 77 |
| RANDOM | 5.9 | 8.7 | 10.2 | 13.4 | 18.4 | 36.4 | 65.8 |
| SIZE-AWARE | 4 | 4 | 4 | 5 | 19 | 46 | 111 |
| THUMBNAIL-EVERYTHING | 0 | 14 | 9 | 21 | 25 | 56 | 64 |
| PHASH-REPRESENTATIVES | 0 | 14 | 9 | 21 | 23 | 50 | 82 |
| EMBEDDING-NOVELTY | 2 | 5 | 5 | 13 | 15 | 26 | 37 |
| TELEMETRY-PRIORITY | 3 | 6 | 2 | 14 | 11 | 15 | 29 |

### SCENE CLUSTERS with any image (≥ THUMBNAIL)

| strategy | 0.1% | 0.25% | 0.5% | 1% | 2% | 5% | 10% |
|---|---|---|---|---|---|---|---|
| FIFO | 3 | 16 | 17 | 27 | 26 | 66 | 84 |
| RANDOM | 13.1 | 15 | 17.5 | 19.3 | 24.6 | 42.4 | 72.3 |
| SIZE-AWARE | 4 | 4 | 4 | 5 | 27 | 49 | 119 |
| THUMBNAIL-EVERYTHING | 287 | 548 | 548 | 548 | 548 | 548 | 548 |
| PHASH-REPRESENTATIVES | 287 | 548 | 548 | 548 | 548 | 548 | 548 |
| EMBEDDING-NOVELTY | 11 | 28 | 12 | 31 | 28 | 44 | 69 |
| TELEMETRY-PRIORITY | 31 | 31 | 27 | 31 | 19 | 32 | 32 |

### UNIQUE ACQUISITIONS retained at ≥ COMPRESSED

| strategy | 0.1% | 0.25% | 0.5% | 1% | 2% | 5% | 10% |
|---|---|---|---|---|---|---|---|
| FIFO | 2 | 16 | 11 | 23 | 26 | 55 | 78 |
| RANDOM | 6 | 8.8 | 10.4 | 13.6 | 18.8 | 37.1 | 68.5 |
| SIZE-AWARE | 9 | 9 | 17 | 35 | 54 | 81 | 146 |
| THUMBNAIL-EVERYTHING | 0 | 14 | 9 | 21 | 25 | 56 | 64 |
| PHASH-REPRESENTATIVES | 0 | 14 | 9 | 21 | 23 | 50 | 84 |
| EMBEDDING-NOVELTY | 2 | 5 | 5 | 13 | 15 | 26 | 37 |
| TELEMETRY-PRIORITY | 3 | 6 | 2 | 16 | 11 | 22 | 37 |

### UNIQUE ACQUISITIONS with any image (≥ THUMBNAIL)

| strategy | 0.1% | 0.25% | 0.5% | 1% | 2% | 5% | 10% |
|---|---|---|---|---|---|---|---|
| FIFO | 3 | 16 | 17 | 27 | 26 | 66 | 85 |
| RANDOM | 13.2 | 15.2 | 17.8 | 19.6 | 25.1 | 43.4 | 75.2 |
| SIZE-AWARE | 15 | 9 | 23 | 40 | 62 | 84 | 154 |
| THUMBNAIL-EVERYTHING | 315 | 609 | 609 | 609 | 609 | 609 | 609 |
| PHASH-REPRESENTATIVES | 315 | 609 | 609 | 609 | 609 | 609 | 609 |
| EMBEDDING-NOVELTY | 11 | 28 | 12 | 31 | 28 | 44 | 69 |
| TELEMETRY-PRIORITY | 33 | 37 | 27 | 36 | 19 | 41 | 45 |

### pHash GROUPS retained at ≥ COMPRESSED (secondary; circular for pHash strategy)

| strategy | 0.1% | 0.25% | 0.5% | 1% | 2% | 5% | 10% |
|---|---|---|---|---|---|---|---|
| FIFO | 2 | 15 | 11 | 19 | 21 | 45 | 65 |
| RANDOM | 5.9 | 8.4 | 9.9 | 13.1 | 17.9 | 34.4 | 60.5 |
| SIZE-AWARE | 4 | 4 | 4 | 5 | 10 | 17 | 61 |
| THUMBNAIL-EVERYTHING | 0 | 13 | 9 | 18 | 21 | 46 | 54 |
| PHASH-REPRESENTATIVES | 0 | 14 | 9 | 21 | 23 | 50 | 84 |
| EMBEDDING-NOVELTY | 2 | 5 | 5 | 13 | 15 | 26 | 37 |
| TELEMETRY-PRIORITY | 3 | 6 | 2 | 14 | 11 | 15 | 29 |

### NEAR-DUPLICATE SHARE of FULL bytes (same scene cluster; lower = less redundancy)

| strategy | 0.1% | 0.25% | 0.5% | 1% | 2% | 5% | 10% |
|---|---|---|---|---|---|---|---|
| FIFO | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| RANDOM | — | 0.000 | 0.000 | 0.000 | 0.003 | 0.005 | 0.012 |
| SIZE-AWARE | 0.500 | 0.333 | 0.667 | 0.833 | 0.723 | 0.284 | 0.142 |
| THUMBNAIL-EVERYTHING | — | — | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| PHASH-REPRESENTATIVES | — | — | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| EMBEDDING-NOVELTY | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| TELEMETRY-PRIORITY | — | — | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |

### OBSERVATION DIVERSITY PROXY — embedding coverage (circular for novelty strategy)

| strategy | 0.1% | 0.25% | 0.5% | 1% | 2% | 5% | 10% |
|---|---|---|---|---|---|---|---|
| FIFO | 0.755 | 0.853 | 0.848 | 0.858 | 0.859 | 0.883 | 0.900 |
| RANDOM | 0.832 | 0.858 | 0.870 | 0.884 | 0.897 | 0.919 | 0.936 |
| SIZE-AWARE | 0.516 | 0.516 | 0.516 | 0.525 | 0.852 | 0.863 | 0.907 |
| THUMBNAIL-EVERYTHING | 0.000 | 0.852 | 0.771 | 0.857 | 0.859 | 0.878 | 0.911 |
| PHASH-REPRESENTATIVES | 0.000 | 0.849 | 0.771 | 0.853 | 0.854 | 0.885 | 0.924 |
| EMBEDDING-NOVELTY | 0.781 | 0.867 | 0.867 | 0.891 | 0.896 | 0.906 | 0.916 |
| TELEMETRY-PRIORITY | 0.803 | 0.825 | 0.727 | 0.863 | 0.833 | 0.863 | 0.884 |

### BYTES TRANSMITTED (kB)

| strategy | 0.1% | 0.25% | 0.5% | 1% | 2% | 5% | 10% |
|---|---|---|---|---|---|---|---|
| FIFO | 161 | 403 | 807 | 1614 | 3227 | 8068 | 16137 |
| RANDOM | 161 | 403 | 807 | 1614 | 3227 | 8068 | 16137 |
| SIZE-AWARE | 161 | 403 | 807 | 1614 | 3227 | 8068 | 16137 |
| THUMBNAIL-EVERYTHING | 161 | 403 | 806 | 1612 | 3227 | 8066 | 16136 |
| PHASH-REPRESENTATIVES | 161 | 402 | 806 | 1611 | 3225 | 8067 | 16136 |
| EMBEDDING-NOVELTY | 161 | 403 | 807 | 1614 | 3227 | 8068 | 16137 |
| TELEMETRY-PRIORITY | 161 | 403 | 807 | 1614 | 3227 | 8068 | 16137 |

### PRODUCT COUNTS (FULL / COMPRESSED / THUMBNAIL / METADATA-ONLY / none)

| strategy | 0.1% | 0.25% | 0.5% | 1% | 2% | 5% | 10% |
|---|---|---|---|---|---|---|---|
| FIFO | 1 / 1 / 1 / 0 / 606 | 2 / 14 / 0 / 0 / 593 | 5 / 6 / 6 / 0 / 592 | 10 / 13 / 4 / 0 / 582 | 21 / 5 / 0 / 1 / 582 | 47 / 8 / 11 / 0 / 543 | 60 / 18 / 7 / 0 / 524 |
| RANDOM | 1 / 5 / 7 / 0 / 595 | 2 / 7 / 6 / 1 / 593 | 3 / 7 / 7 / 1 / 591 | 7 / 7 / 6 / 0 / 589 | 13 / 6 / 6 / 1 / 583 | 31 / 6 / 6 / 1 / 565 | 61 / 8 / 7 / 1 / 533 |
| SIZE-AWARE | 2 / 7 / 6 / 1 / 593 | 6 / 3 / 0 / 0 / 600 | 12 / 5 / 6 / 0 / 586 | 24 / 11 / 5 / 1 / 568 | 44 / 10 / 8 / 1 / 546 | 79 / 2 / 3 / 1 / 524 | 135 / 11 / 8 / 1 / 454 |
| THUMBNAIL-EVERYTHING | 0 / 0 / 315 / 0 / 294 | 0 / 14 / 595 / 0 / 0 | 3 / 6 / 600 / 0 / 0 | 8 / 13 / 588 / 0 / 0 | 19 / 6 / 584 / 0 / 0 | 47 / 9 / 553 / 0 / 0 | 61 / 3 / 545 / 0 / 0 |
| PHASH-REPRESENTATIVES | 0 / 0 / 315 / 0 / 294 | 0 / 14 / 595 / 0 / 0 | 3 / 6 / 600 / 0 / 0 | 8 / 13 / 588 / 0 / 0 | 19 / 4 / 586 / 0 / 0 | 39 / 11 / 559 / 0 / 0 | 58 / 26 / 525 / 0 / 0 |
| EMBEDDING-NOVELTY | 1 / 1 / 9 / 0 / 598 | 3 / 2 / 23 / 1 / 580 | 3 / 2 / 7 / 0 / 597 | 6 / 7 / 18 / 1 / 577 | 9 / 6 / 13 / 1 / 580 | 20 / 6 / 18 / 0 / 565 | 33 / 4 / 32 / 0 / 540 |
| TELEMETRY-PRIORITY | 0 / 3 / 30 / 1 / 575 | 0 / 6 / 31 / 0 / 572 | 1 / 1 / 25 / 1 / 581 | 2 / 14 / 20 / 0 / 573 | 3 / 8 / 8 / 1 / 589 | 11 / 11 / 19 / 0 / 568 | 23 / 14 / 8 / 1 / 563 |

## Mode: ordering

*policy* = each strategy's own action policy; *ordering* = common thumbnails-for-all first pass, then FULL upgrades in strategy order (THUMBNAIL-EVERYTHING and PHASH-REPRESENTATIVES are identical in both modes).

### UNIQUE SCENE CLUSTERS retained at ≥ COMPRESSED (of 548)

| strategy | 0.1% | 0.25% | 0.5% | 1% | 2% | 5% | 10% |
|---|---|---|---|---|---|---|---|
| FIFO | 0 | 14 | 9 | 21 | 25 | 56 | 64 |
| RANDOM | 0 | 7.1 | 11.3 | 13.8 | 18.3 | 36.2 | 64 |
| SIZE-AWARE | 0 | 4 | 4 | 4 | 16 | 46 | 119 |
| THUMBNAIL-EVERYTHING | 0 | 14 | 9 | 21 | 25 | 56 | 64 |
| PHASH-REPRESENTATIVES | 0 | 14 | 9 | 21 | 23 | 50 | 82 |
| EMBEDDING-NOVELTY | 0 | 9 | 8 | 14 | 18 | 27 | 39 |
| TELEMETRY-PRIORITY | 0 | 3 | 8 | 11 | 5 | 16 | 31 |

### SCENE CLUSTERS with any image (≥ THUMBNAIL)

| strategy | 0.1% | 0.25% | 0.5% | 1% | 2% | 5% | 10% |
|---|---|---|---|---|---|---|---|
| FIFO | 287 | 548 | 548 | 548 | 548 | 548 | 548 |
| RANDOM | 287 | 548 | 548 | 548 | 548 | 548 | 548 |
| SIZE-AWARE | 287 | 548 | 548 | 548 | 548 | 548 | 548 |
| THUMBNAIL-EVERYTHING | 287 | 548 | 548 | 548 | 548 | 548 | 548 |
| PHASH-REPRESENTATIVES | 287 | 548 | 548 | 548 | 548 | 548 | 548 |
| EMBEDDING-NOVELTY | 287 | 548 | 548 | 548 | 548 | 548 | 548 |
| TELEMETRY-PRIORITY | 287 | 548 | 548 | 548 | 548 | 548 | 548 |

### UNIQUE ACQUISITIONS retained at ≥ COMPRESSED

| strategy | 0.1% | 0.25% | 0.5% | 1% | 2% | 5% | 10% |
|---|---|---|---|---|---|---|---|
| FIFO | 0 | 14 | 9 | 21 | 25 | 56 | 64 |
| RANDOM | 0 | 7.2 | 11.7 | 14.1 | 18.6 | 37.0 | 66.7 |
| SIZE-AWARE | 0 | 8 | 19 | 21 | 51 | 81 | 154 |
| THUMBNAIL-EVERYTHING | 0 | 14 | 9 | 21 | 25 | 56 | 64 |
| PHASH-REPRESENTATIVES | 0 | 14 | 9 | 21 | 23 | 50 | 84 |
| EMBEDDING-NOVELTY | 0 | 9 | 8 | 14 | 18 | 27 | 39 |
| TELEMETRY-PRIORITY | 0 | 6 | 8 | 18 | 11 | 16 | 42 |

### UNIQUE ACQUISITIONS with any image (≥ THUMBNAIL)

| strategy | 0.1% | 0.25% | 0.5% | 1% | 2% | 5% | 10% |
|---|---|---|---|---|---|---|---|
| FIFO | 315 | 609 | 609 | 609 | 609 | 609 | 609 |
| RANDOM | 315 | 609 | 609 | 609 | 609 | 609 | 609 |
| SIZE-AWARE | 315 | 609 | 609 | 609 | 609 | 609 | 609 |
| THUMBNAIL-EVERYTHING | 315 | 609 | 609 | 609 | 609 | 609 | 609 |
| PHASH-REPRESENTATIVES | 315 | 609 | 609 | 609 | 609 | 609 | 609 |
| EMBEDDING-NOVELTY | 315 | 609 | 609 | 609 | 609 | 609 | 609 |
| TELEMETRY-PRIORITY | 315 | 609 | 609 | 609 | 609 | 609 | 609 |

### pHash GROUPS retained at ≥ COMPRESSED (secondary; circular for pHash strategy)

| strategy | 0.1% | 0.25% | 0.5% | 1% | 2% | 5% | 10% |
|---|---|---|---|---|---|---|---|
| FIFO | 0 | 13 | 9 | 18 | 21 | 46 | 54 |
| RANDOM | 0 | 7.0 | 11.2 | 13.2 | 17.6 | 34.1 | 58.7 |
| SIZE-AWARE | 0 | 4 | 4 | 4 | 10 | 17 | 68 |
| THUMBNAIL-EVERYTHING | 0 | 13 | 9 | 18 | 21 | 46 | 54 |
| PHASH-REPRESENTATIVES | 0 | 14 | 9 | 21 | 23 | 50 | 84 |
| EMBEDDING-NOVELTY | 0 | 9 | 8 | 14 | 18 | 27 | 39 |
| TELEMETRY-PRIORITY | 0 | 3 | 8 | 11 | 5 | 16 | 31 |

### NEAR-DUPLICATE SHARE of FULL bytes (same scene cluster; lower = less redundancy)

| strategy | 0.1% | 0.25% | 0.5% | 1% | 2% | 5% | 10% |
|---|---|---|---|---|---|---|---|
| FIFO | — | — | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| RANDOM | — | — | 0.011 | 0.000 | 0.004 | 0.007 | 0.011 |
| SIZE-AWARE | — | 0.000 | 0.429 | 0.800 | 0.792 | 0.294 | 0.145 |
| THUMBNAIL-EVERYTHING | — | — | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| PHASH-REPRESENTATIVES | — | — | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| EMBEDDING-NOVELTY | — | — | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| TELEMETRY-PRIORITY | — | — | — | 0.000 | 0.000 | 0.000 | 0.000 |

### OBSERVATION DIVERSITY PROXY — embedding coverage (circular for novelty strategy)

| strategy | 0.1% | 0.25% | 0.5% | 1% | 2% | 5% | 10% |
|---|---|---|---|---|---|---|---|
| FIFO | 0.000 | 0.852 | 0.771 | 0.857 | 0.859 | 0.878 | 0.911 |
| RANDOM | 0.000 | 0.850 | 0.880 | 0.883 | 0.900 | 0.920 | 0.936 |
| SIZE-AWARE | 0.000 | 0.515 | 0.525 | 0.525 | 0.851 | 0.863 | 0.910 |
| THUMBNAIL-EVERYTHING | 0.000 | 0.852 | 0.771 | 0.857 | 0.859 | 0.878 | 0.911 |
| PHASH-REPRESENTATIVES | 0.000 | 0.849 | 0.771 | 0.853 | 0.854 | 0.885 | 0.924 |
| EMBEDDING-NOVELTY | 0.000 | 0.873 | 0.878 | 0.896 | 0.906 | 0.912 | 0.916 |
| TELEMETRY-PRIORITY | 0.000 | 0.763 | 0.807 | 0.860 | 0.850 | 0.863 | 0.885 |

### BYTES TRANSMITTED (kB)

| strategy | 0.1% | 0.25% | 0.5% | 1% | 2% | 5% | 10% |
|---|---|---|---|---|---|---|---|
| FIFO | 161 | 403 | 806 | 1612 | 3227 | 8066 | 16136 |
| RANDOM | 161 | 402 | 806 | 1612 | 3226 | 8067 | 16135 |
| SIZE-AWARE | 161 | 400 | 807 | 1610 | 3224 | 8066 | 16137 |
| THUMBNAIL-EVERYTHING | 161 | 403 | 806 | 1612 | 3227 | 8066 | 16136 |
| PHASH-REPRESENTATIVES | 161 | 402 | 806 | 1611 | 3225 | 8067 | 16136 |
| EMBEDDING-NOVELTY | 161 | 403 | 805 | 1613 | 3227 | 8068 | 16136 |
| TELEMETRY-PRIORITY | 161 | 401 | 805 | 1612 | 3225 | 8068 | 16136 |

### PRODUCT COUNTS (FULL / COMPRESSED / THUMBNAIL / METADATA-ONLY / none)

| strategy | 0.1% | 0.25% | 0.5% | 1% | 2% | 5% | 10% |
|---|---|---|---|---|---|---|---|
| FIFO | 0 / 0 / 315 / 0 / 294 | 0 / 14 / 595 / 0 / 0 | 3 / 6 / 600 / 0 / 0 | 8 / 13 / 588 / 0 / 0 | 19 / 6 / 584 / 0 / 0 | 47 / 9 / 553 / 0 / 0 | 61 / 3 / 545 / 0 / 0 |
| RANDOM | 0 / 0 / 315 / 0 / 294 | 0 / 7 / 602 / 0 / 0 | 2 / 9 / 597 / 0 / 0 | 5 / 9 / 595 / 0 / 0 | 12 / 7 / 590 / 0 / 0 | 30 / 7 / 572 / 0 / 0 | 59 / 8 / 542 / 0 / 0 |
| SIZE-AWARE | 0 / 0 / 315 / 0 / 294 | 1 / 7 / 601 / 0 / 0 | 7 / 12 / 590 / 0 / 0 | 20 / 1 / 588 / 0 / 0 | 42 / 9 / 558 / 0 / 0 | 77 / 4 / 528 / 0 / 0 | 133 / 21 / 455 / 0 / 0 |
| THUMBNAIL-EVERYTHING | 0 / 0 / 315 / 0 / 294 | 0 / 14 / 595 / 0 / 0 | 3 / 6 / 600 / 0 / 0 | 8 / 13 / 588 / 0 / 0 | 19 / 6 / 584 / 0 / 0 | 47 / 9 / 553 / 0 / 0 | 61 / 3 / 545 / 0 / 0 |
| PHASH-REPRESENTATIVES | 0 / 0 / 315 / 0 / 294 | 0 / 14 / 595 / 0 / 0 | 3 / 6 / 600 / 0 / 0 | 8 / 13 / 588 / 0 / 0 | 19 / 4 / 586 / 0 / 0 | 39 / 11 / 559 / 0 / 0 | 58 / 26 / 525 / 0 / 0 |
| EMBEDDING-NOVELTY | 0 / 0 / 315 / 0 / 294 | 0 / 9 / 600 / 0 / 0 | 4 / 4 / 601 / 0 / 0 | 5 / 9 / 595 / 0 / 0 | 8 / 10 / 591 / 0 / 0 | 19 / 8 / 582 / 0 / 0 | 32 / 7 / 570 / 0 / 0 |
| TELEMETRY-PRIORITY | 0 / 0 / 315 / 0 / 294 | 0 / 6 / 603 / 0 / 0 | 0 / 8 / 601 / 0 / 0 | 1 / 17 / 591 / 0 / 0 | 3 / 8 / 598 / 0 / 0 | 11 / 5 / 593 / 0 / 0 | 22 / 20 / 567 / 0 / 0 |
