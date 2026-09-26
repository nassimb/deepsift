# Outreach note (≤ 150 words)

**Subject:** Feedback on a retrospective study of rover imagery downlink prioritization

Hi {{NAME}},

I built an independent research prototype on bandwidth-constrained rover downlink, using public Curiosity Navcam and
PLACES data from the PDS. I froze a development / validation / held-out test protocol before each download.

On the held-out interval (sols 950–979), position-based sampling with a stereo-safe progressive scheduler kept 1/4 of
traverse frames at 26.1% of full-quality bytes. Every archived frame stayed within 5 m of a kept frame (at most
2.05 m), and no stereo pair was broken. Several AI approaches added no value, including a semantic ranker, a quality
detector and image embeddings.

It is retrospective (only downlinked data exist) and not flight work. I would value your view on whether the
assumptions and the problem framing map to real mission operations, and where they don't.

Paper: https://github.com/nassimb/deepsift/blob/main/docs/deepsift-paper.md · Replay: {{DEMO_URL}}/final-test

Thanks,
{{SENDER}}
