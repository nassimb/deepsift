# DEEPSIFT — 60-second demo script

Target length: 45–60 seconds. Screen: the web app. Start at `/final-test` with traverse `967:trav00327` (the
example held-out traverse, chosen as the longest path — not claimed statistically representative), mode SEND ALL, then press **reset**.

Every on-screen number comes from `apps/web/data/release.json`, which is built from the frozen final-test artifacts.

| time | on screen | voice-over |
|---|---|---|
| 0–8 s | Homepage hero: "Not every bit deserves the trip to Earth." | "A Mars rover takes more pictures than it can send home. Every relay pass has a fixed number of bytes." |
| 8–18 s | `/final-test` · chip **HISTORICAL REPLAY · Curiosity Navcam · sols 950–979** · press **play** in SEND ALL | "This is a real Curiosity traverse from the public archive, replayed frame by frame: 105 Navcam stereo frames over 89 metres." |
| 18–30 s | SEND ALL finishes; the bandwidth meter is full (100 % of SEND ALL). Switch to **POSITION · 1/4** and press **reset**. | "Sending everything at full quality fills the link. What if we could send only a quarter?" |
| 30–42 s | Press **play** in POSITION: blue squares appear along the path, grey frames become thumbnails, 5 m discs cover the route. | "DEEPSIFT keeps the frames that spread out along the rover's path. Everything else still goes down as a small thumbnail, and stereo pairs are never split." |
| 42–52 s | Homepage hero KPIs: **26.1 %** · **100 %** · **2.05 m** · **0** | "On a held-out test interval, frozen before download: 26.1 percent of the bytes, every frame within five metres of a kept one, at most 2.05 metres away, and zero broken stereo pairs." |
| 52–60 s | Homepage "What we tested" funnel → then the DEEPSIFT wordmark | "We also tried a semantic model, telemetry, image hashing, a quality detector and image embeddings. The simplest signal that generalized was rover position." End card: **DEEPSIFT — Measured autonomy for bandwidth-constrained missions.** |

**Say:**
- "retrospective replay of archived data";
- "held-out test";
- "pre-registered".

**Do not say:**
- that NASA or JPL uses, approves or validated DEEPSIFT;
- "flight-ready";
- "preserves science value";
- "reconstructs the rover's onboard images".

The PDS archive contains only what was downlinked.
