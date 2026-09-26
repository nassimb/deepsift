# Launch post — LinkedIn

**I started by testing whether more AI improved autonomous downlink decisions. It mostly didn't.**

DEEPSIFT is an independent research prototype. It asks a narrow question that matters for bandwidth-constrained
missions: when a rover has more imagery than its relay passes can carry, which signals actually help decide what is
transmitted?

**The data.** I used public NASA Planetary Data System archives:
- Curiosity Navcam raw images, with their compression metadata;
- PLACES rover localizations;
- earlier in the project, REMS weather and RAD radiation telemetry.

Everything was replayed as if it were waiting onboard, under simulated bandwidth limits.

**The method.** The design goal was to make it hard to fool myself:
- one development period for building and tuning;
- two separate validation periods;
- one held-out test interval, used exactly once;
- every configuration and pass/fail rule committed to git before the data that tested it was downloaded, and every
  scientific artifact hash-locked.

**The held-out result** (Curiosity Navcam, sols 950–979; 12 traverses, 679 archived frames). Keeping one quarter of
traverse frames at full quality, rover-position sampling with a stereo-safe progressive scheduler:
- used 26.1% of full-quality traverse bytes;
- kept 100% of archived frames within 5 m of a retained frame;
- left no frame more than 2.05 m from a retained one;
- broke 0 stereo pairs.

**What did not earn a place:**
- **A semantic model (Jev) ranking candidate events:** no measurable improvement over deterministic rules, and stopped
  by a pre-registered rule.
- **Telemetry-driven image ranking:** it cannot respond to image content, and it gave the weakest coverage.
- **Perceptual hashing:** unsafe scene merges on validation, with almost no compression.
- **A learned image-quality check:** false positives went from 3.6% to 10.6% out of sample.
- **Image embeddings:** a +0.044 visual-change gain in development that fell to +0.004, +0.001 and +0.005 afterwards,
  below the +0.020 threshold I had set in advance.

**The lesson for me:** the simplest signal, where the rover was, generalized better than every more complex one. Just
as important, a scheduler that never lets more bandwidth reduce coverage and never splits a stereo pair.

**Limits:**
- The PDS holds only what the mission actually downlinked, so this is retrospective re-prioritization, not the
  rover's onboard stream.
- One rover, one camera; a simulated compressed tier; interpolated positions.
- Not flight software, and not reviewed or validated by NASA/JPL.

I would value criticism from people who work on mission operations or onboard autonomy, especially on whether this
framing matches how downlink decisions are actually made.

Paper, interactive replay, and every config and hash: https://github.com/nassimb/deepsift · {{DEMO_URL}}
