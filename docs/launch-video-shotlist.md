# DEEPSIFT — 60-second launch video (no narration)

**Format:** 16:9, 1920×1080, dark background matching the web app (#07080a), IBM Plex Sans/Mono, no music required.

**Source of every visual:** the web app, recorded from `/final-test` and `/`, or the figures in `docs/figures/`. No
mock-ups, no generated imagery.

**Visual rules:**
- No NASA logo or insignia, and nothing that suggests NASA/JPL endorsement.
- No sci-fi graphics.

**Recording setup:** in `/final-test`, select traverse **967:trav00327** (the representative traverse: 105 frames, 89 m).
Use the **reset → play** controls for the animations.

| time | picture | on-screen text |
|---|---|---|
| 0–5 s | Black. Wordmark fades in. | **DEEPSIFT** · *Not every bit deserves the trip to Earth.* |
| 5–12 s | `/final-test`, mode **SEND ALL**, press **show all**: the full route with every archived frame as a filled square. Slow push-in on the route. | **HISTORICAL REPLAY** · Curiosity Navcam · sols 950–979 · 105 archived frames on one traverse. Small, persistent footer from here: *Retrospective replay of archived PDS data* |
| 12–22 s | Bandwidth meter: SEND ALL fills to 100 %. Cut to the mode switch **POSITION · 1/4** (click visible). | **SEND ALL → 25 % FRAME RETENTION** |
| 22–38 s | **reset → play** in POSITION: blue squares appear along the path, other frames stay hollow (thumbnail only), 5 m discs accumulate, thin lines join each hollow frame to its nearest kept frame. Right panel: "stereo pairs sent whole" counting up, "stereo pairs broken 0". | 22 s: **POSITION keeps frames that spread along the rover’s path** · 30 s: **Stereo pairs stay intact — never one eye alone** |
| 38–52 s | Homepage hero KPI panel, numbers revealed one at a time (≈3 s each), with the **HELD-OUT TEST** chip visible. | **26.1 %** FULL-QUALITY BYTES · **100 %** 5 M SPATIAL COVERAGE · **2.05 M** MAX NEAREST-KEPT DISTANCE · **0** BROKEN STEREO PAIRS · small line: *held-out interval, frozen before download* |
| 52–57 s | Homepage "What we tested" section, or figure 3 (embedding gain by period). | **MORE COMPLEX DID NOT MEAN BETTER.** · Jev ranking — no measurable gain · Embeddings — no measurable added selection value · Rover position — generalized |
| 57–60 s | Black. Wordmark. | **DEEPSIFT** · *Measured autonomy for bandwidth-constrained missions.* · small: independent research prototype · {{GITHUB_URL}} |

Before export, run `uv run python scripts/check_public_claims.py`. Every number above is in
`docs/public-claims-checklist.md`.
