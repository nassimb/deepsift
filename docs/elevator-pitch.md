# DEEPSIFT in 30 seconds

**What is it?** DEEPSIFT is a research project that asks which information should decide what a Mars rover sends home
when it has more pictures than bandwidth.

**Why does it exist?** Every rover relay pass carries a limited number of bytes. Someone, or eventually something
onboard, has to choose what goes first. I wanted to measure which signals actually help make that choice, instead of
assuming smarter models would.

**What did it find?** I replayed real Curiosity camera data from NASA's public archive and tested each idea on data it
had never seen, with the rules fixed in advance. The AI-heavy ideas mostly didn't help: a language-model ranker, image
fingerprints, a learned quality check and image embeddings. What worked was simple: choose frames by where the rover
was, and never split a stereo pair. On the final held-out test that kept a quarter of the frames, used 26.1% of the
bytes, and left no frame more than about 2 metres from a kept one.

**Why should a spacecraft engineer care?** It suggests that cheap, explainable geometry can go a long way before you
need a model, and it shows a way to test that claim honestly. The caveat: it uses only archived, already-downlinked
data, so it is evidence for a direction, not flight readiness.
