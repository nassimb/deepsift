# Launch thread — X

**1/**
I started by testing whether more AI improved autonomous downlink decisions for a Mars rover.

It mostly didn't.

What survived was rover geometry plus correct scheduling. 🧵

**2/**
The problem: rovers collect more imagery than relay passes can carry. Something has to decide what goes down at full
quality, what goes as a thumbnail, and what waits.

I replayed archived Curiosity Navcam data from NASA's public PDS under simulated bandwidth limits.

**3/**
The method: develop on one period, validate on two others, then run one held-out test.

Every config and pass/fail rule was committed to git before the data that tested it was downloaded. The test ran once.

**4/**
Held-out result (Curiosity Navcam, sols 950–979), keeping 1/4 of traverse frames at full quality:

• 26.1% of full-quality bytes
• 100% of frames within 5 m of a kept frame
• max 2.05 m to the nearest kept frame
• 0 broken stereo pairs

**5/**
What did not earn a place:

• a semantic LLM-style ranker: no measurable ranking gain
• telemetry-driven image ranking
• perceptual hashing: unsafe scene merges
• a learned quality check: false positives tripled out of sample
• image embeddings: +0.044 in dev, then +0.004 / +0.001 / +0.005 (threshold 0.020)

**6/**
What worked: farthest-point sampling on the rover's position, plus a scheduler that fills thumbnails, then compressed,
then full images, and never splits a stereo pair.

**7/**
Caveats. The PDS only holds what was actually downlinked, so this is retrospective re-prioritization, not the onboard
stream. It is one rover and one camera. It is not flight software and not NASA-reviewed.

Paper, replay and hashes: https://github.com/nassimb/deepsift · https://deepsift.space
