# DEEPSIFT — media package (v1 research release)

All images are captures of the built web app (`next build` at the `deepsift-v1-research` release, served locally) or the
release figures. Every number in them comes from `apps/web/data/release.json`, which is built from frozen artifacts; see
`docs/public-claims-checklist.md`.

There is no mock data, no NASA logo, and no implied endorsement. Files are in `artifacts/public/media/`.

| # | file | what it shows | recommended caption |
|---|---|---|---|
| 1 | `01_homepage_final_result.png` (1440×685) | Homepage hero with the held-out result panel | *DEEPSIFT held-out test (Curiosity Navcam, sols 950–979): keeping 1/4 of traverse frames used 26.1 % of full-quality bytes, with 100 % 5 m coverage, at most 2.05 m to a retained frame, and 0 broken stereo pairs. Retrospective replay of archived PDS data.* |
| 2 | `02_final_test_replay_overview.png` (1440×1080) | `/final-test` historical replay, traverse 967:trav00327, POSITION at 1/4, fully shown | *Historical replay of a held-out Curiosity Navcam traverse. Filled squares are frames kept at full quality; everything else goes down as a thumbnail pair. Stereo pairs are never split.* |
| 3 | `03_retained_vs_all_positions.png` (1243×827, figure 5) | All archived frame positions vs retained positions, 5 m discs, nearest-kept distances | *Example held-out traverse (longest path; not claimed statistically representative). Why the metric works: every archived frame (hollow) lies within 5 m of a retained frame (filled). The largest distance on this traverse is 2.05 m. Positions are PLACES interpolations.* |
| 4 | `04_four_period_generalization.png` (1440×1004) | Four-period small multiples plus the embedding-gain panel | *One result, four separate periods: development, two validations and a held-out test, never pooled. The embedding's development gain (+0.044) did not persist (+0.004, +0.001, +0.005).* |
| 5 | `05_what_survived.png` (1440×843) | "What didn't work" vs "What generalized" | *Most of what we tried did not earn a place: semantic ranking, telemetry ranking, pHash, a learned quality check and embedding-assisted selection. Rover position and a stereo-safe scheduler generalized.* |

**Also available**
- **Figures:** `docs/figures/fig1…fig5` as PNG and SVG, suited to print or slides.
- **Documents:** `artifacts/public/deepsift-v1-paper.pdf` and `artifacts/public/deepsift-one-pager.pdf`.

**Recapture**
1. Run `cd apps/web && npx next build && npx next start -p 3399`.
2. Capture with Chrome headless at a 1440 px viewport. Images 1, 4 and 5 are crops of the homepage at its section borders.

**Before publishing:**
- links are final: site https://deepsift.space, repository https://github.com/nassimb/deepsift;
- run `uv run python scripts/check_public_claims.py`.
