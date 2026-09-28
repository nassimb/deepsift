/** Seed content library for the private comms console — curated, deterministic templates (no LLM).
 *  Every post is built only from VERIFIED_FACTS wording and must pass the claim checker (tests/comms-claims.test.ts checks
 *  every hook variant and every thread post). To add an idea: append to IDEAS with a unique id, list the facts it uses, and
 *  run `npm test`. */

export type Pillar =
  | "FINAL_RESULT"
  | "NEGATIVE_RESULT"
  | "MISSION_CONTROL"
  | "ENGINEERING"
  | "METHODOLOGY"
  | "REPRODUCIBILITY"
  | "QUESTION"
  | "BUILD_STORY"
  | "MARS_VISUAL";

export const PILLARS: Pillar[] = ["FINAL_RESULT", "NEGATIVE_RESULT", "MISSION_CONTROL", "ENGINEERING", "METHODOLOGY", "REPRODUCIBILITY", "QUESTION", "BUILD_STORY", "MARS_VISUAL"];

export const PILLAR_LABEL: Record<Pillar, string> = {
  FINAL_RESULT: "Final result",
  NEGATIVE_RESULT: "Negative result",
  MISSION_CONTROL: "Mission Control",
  ENGINEERING: "Engineering lesson",
  METHODOLOGY: "Methodology",
  REPRODUCIBILITY: "Reproducibility",
  QUESTION: "Research question",
  BUILD_STORY: "Build story",
  MARS_VISUAL: "Data / Mars visual",
};

export type Audience = "SCIENTIST" | "SPACECRAFT_ENGINEER" | "ROBOTICS_AUTONOMY" | "SPACE_FAN" | "TECHNICAL_GENERAL" | "GENERAL";
export const AUDIENCES: Audience[] = ["SCIENTIST", "SPACECRAFT_ENGINEER", "ROBOTICS_AUTONOMY", "SPACE_FAN", "TECHNICAL_GENERAL", "GENERAL"];
export const AUDIENCE_LABEL: Record<Audience, string> = {
  SCIENTIST: "Scientist",
  SPACECRAFT_ENGINEER: "Spacecraft engineer",
  ROBOTICS_AUTONOMY: "Robotics / autonomy",
  SPACE_FAN: "Space fan",
  TECHNICAL_GENERAL: "Technical general",
  GENERAL: "General",
};

export type HookStyle = "TECHNICAL" | "SURPRISING" | "ACCESSIBLE";
export const HOOK_STYLES: HookStyle[] = ["TECHNICAL", "SURPRISING", "ACCESSIBLE"];

export type Mode = "ALL" | "RESEARCH" | "FAN";

export interface VideoIdea {
  start: string;
  steps: string[];
  show: string[];
  duration: string;
}

export interface ContentIdea {
  id: string;
  pillar: Pillar;
  audience: Audience;
  /** The angle, in one line (shown on the card, not posted). */
  title: string;
  hooks: Record<HookStyle, string>;
  defaultHook: HookStyle;
  /** Text after the hook. */
  body: string;
  facts: string[];
  visual: string | null;
  video?: VideoIdea;
  /** Thread blocks to leave out when this idea is expanded to a thread (its own post already covers them). */
  threadSkip?: ThreadBlock[];
}

export type ThreadBlock = "problem" | "experiment" | "result" | "negative" | "limitation" | "demo";

/** Standard thread structure after the hook post: problem → experiment → result → negative result → limitation → demo. */
export const THREAD_BLOCKS: Record<ThreadBlock, string> = {
  problem:
    "The problem: a Mars rover can collect more data than its relay passes carry. Something has to decide what goes down at full quality, what goes as a thumbnail, and what waits.",
  experiment:
    "The experiment: replay archived Curiosity Navcam data from NASA's public PDS under simulated bandwidth limits. Tune on one period, validate on two more, test once on a fourth, with every rule committed before the data was downloaded.",
  result:
    "Held-out result (Curiosity Navcam, sols 950–979, archived data), keeping 1/4 of traverse frames at full quality:\n• 26.1% of SEND ALL full-quality bytes\n• 100% of frames within 5 m of a kept frame\n• max 2.05 m to the nearest kept frame\n• 0 broken stereo pairs",
  negative:
    "What didn't earn a place: a semantic model ranker, telemetry ranking, perceptual hashing, a learned quality check, and image embeddings (+0.044 in development, then +0.004 / +0.001 / +0.005 against a +0.020 bar).",
  limitation:
    "Caveats: the PDS only holds what was already downlinked, so this is retrospective re-prioritization, not the onboard stream. One rover, one camera. Geometric coverage is not scientific value. Not flight software; not NASA/JPL-reviewed.",
  demo: "Replay it frame by frame: deepsift.space/mission-control\n\nPaper, code, configs and hashes: github.com/nassimb/deepsift",
};
export const THREAD_ORDER: ThreadBlock[] = ["problem", "experiment", "result", "negative", "limitation", "demo"];

const MC_VIDEO: VideoIdea = {
  start: "Open deepsift.space/mission-control on the example traverse 967:trav00327, policy SEND ALL, press Reset.",
  steps: ["Play SEND ALL until the bandwidth bar is full.", "Switch policy to POSITION · retention 1/4, press Reset, then play.", "Click one deprioritized frame so its decision reason and nearest retained frame show."],
  show: ["26.1% of SEND ALL full-quality bytes", "100% 5 m coverage", "0 broken stereo pairs", "HISTORICAL REPLAY badge visible the whole time"],
  duration: "15–25 seconds",
};

export const IDEAS: ContentIdea[] = [
  // ───────────── FINAL RESULT ─────────────
  {
    id: "result-headline", pillar: "FINAL_RESULT", audience: "TECHNICAL_GENERAL",
    title: "What survived the held-out test",
    hooks: {
      TECHNICAL: "Held-out result: position-based frame selection for rover downlink.",
      SURPRISING: "I tested whether more AI improved rover downlink. It mostly didn't.",
      ACCESSIBLE: "Which quarter of a Mars rover's drive pictures should go home first?",
    },
    defaultHook: "SURPRISING",
    body: "Held-out Curiosity Navcam test, 1/4 of drive frames at full quality:\n• 26.1% of SEND ALL full-quality bytes\n• 100% 5 m coverage\n• 0 broken stereo pairs\n\nReplay of archived PDS data.\ndeepsift.space",
    facts: ["held_out_bytes", "held_out_coverage", "held_out_stereo", "held_out_retention", "held_out_dataset"],
    visual: "media_headline", threadSkip: ["result"],
  },
  {
    id: "result-worst-case", pillar: "FINAL_RESULT", audience: "SPACECRAFT_ENGINEER",
    title: "The worst case, not the average: 2.05 m",
    hooks: {
      TECHNICAL: "Worst case over every archived traverse frame: 2.05 m to the nearest kept frame.",
      SURPRISING: "Averages hide dropped rover stops. So the pass/fail rule used the worst case.",
      ACCESSIBLE: "Keep a quarter of the pictures; every other one still sits near a kept one.",
    },
    defaultHook: "SURPRISING",
    body: "Held-out Curiosity Navcam test, 1/4 retention: no archived drive frame was more than 2.05 m from a full-quality frame (pre-registered limit: 10 m).\n\nInterpolated positions.",
    facts: ["held_out_max_distance", "held_out_retention", "lim_positions"],
    visual: "fig1", threadSkip: ["result"],
  },
  {
    id: "result-every-nth", pillar: "FINAL_RESULT", audience: "ROBOTICS_AUTONOMY",
    title: "Every-Nth vs position sampling at equal bytes",
    hooks: {
      TECHNICAL: "Farthest-point sampling on position vs every-Nth, at about the same bytes.",
      SURPRISING: "Keeping every 4th frame sounds fine. It left one frame 20.04 m from anything kept.",
      ACCESSIBLE: "Same byte budget, two ways to choose rover pictures. One left a 20.04 m gap.",
    },
    defaultHook: "SURPRISING",
    body: "Held-out Curiosity Navcam replay, 1/4 retention:\n• every Nth frame: worst 20.04 m to a kept frame\n• rover-position sampling: 2.05 m\n\nEvery-Nth drops whole rover stops.\ndeepsift.space",
    facts: ["method_comparison", "held_out_max_distance"],
    visual: "fig1", threadSkip: ["result"],
  },
  {
    id: "result-stereo", pillar: "FINAL_RESULT", audience: "SPACE_FAN",
    title: "0 broken stereo pairs",
    hooks: {
      TECHNICAL: "Stereo integrity as a hard scheduling constraint.",
      SURPRISING: "0 broken stereo pairs. It took three schedulers to get there.",
      ACCESSIBLE: "Curiosity's Navcam shoots in stereo. A pair is only usable with both eyes.",
    },
    defaultHook: "ACCESSIBLE",
    body: "In DEEPSIFT's held-out replay of archived Curiosity Navcam data, 174 stereo pairs were kept whole at full quality and 0 were split. The scheduler never sends one eye alone.\n\ndeepsift.space",
    facts: ["held_out_stereo", "scheduler_v3"],
    visual: "navcam_pair",
  },
  {
    id: "result-pass-criteria", pillar: "FINAL_RESULT", audience: "SCIENTIST",
    title: "A binary, pre-registered pass/fail",
    hooks: {
      TECHNICAL: "The final test was binary, pre-registered, and run once.",
      SURPRISING: "I wrote the pass/fail rule before downloading the test data. It passed.",
      ACCESSIBLE: "Before looking at the final test data, I wrote down what success meant.",
    },
    defaultHook: "TECHNICAL",
    body: "Held-out Curiosity Navcam test, archived PDS data, 1/4 retention:\nbytes ≤ 0.35 → 0.261\n5 m coverage ≥ 0.90 → 1.000\nworst distance ≤ 10 m → 2.05 m\nbroken stereo pairs = 0 → 0\n\nPASS.",
    facts: ["held_out_pass", "held_out_bytes", "held_out_coverage", "held_out_max_distance", "held_out_stereo"],
    visual: "media_headline", threadSkip: ["result"],
  },
  {
    id: "result-four-periods", pillar: "FINAL_RESULT", audience: "SCIENTIST",
    title: "Same method, four separate periods",
    hooks: {
      TECHNICAL: "One claim, four separate periods, never pooled.",
      SURPRISING: "Four stretches of Curiosity's drive. Nearly the same numbers.",
      ACCESSIBLE: "One result, checked on four stretches of Curiosity's drive.",
    },
    defaultHook: "TECHNICAL",
    body: "Position sampling at 1/4, archived Curiosity Navcam data:\nbytes 0.266 / 0.265 / 0.270 / 0.261\n5 m coverage 1.000 in all four\nworst 2.64 / 2.78 / 1.94 / 2.05 m\n\nDev, 2 validations, 1 held-out test.",
    facts: ["four_periods", "four_period_bytes", "four_period_coverage", "four_period_distance"],
    visual: "fig2",
  },

  // ───────────── NEGATIVE RESULTS ─────────────
  {
    id: "neg-more-ai", pillar: "NEGATIVE_RESULT", audience: "TECHNICAL_GENERAL",
    title: "More AI mostly didn't help",
    hooks: {
      TECHNICAL: "Negative results from a pre-registered downlink-prioritization study.",
      SURPRISING: "I tested whether more AI improved rover downlink ranking. It mostly didn't.",
      ACCESSIBLE: "I tried five clever ways to pick which Mars pictures go first. None stuck.",
    },
    defaultHook: "SURPRISING",
    body: "Didn't earn a place:\n• semantic model ranking\n• telemetry ranking\n• perceptual hashing\n• a learned quality check\n• image embeddings\n\nWhat generalized: rover position + a stereo-safe scheduler.",
    facts: ["jev_ranking", "telemetry_ranking", "phash_failed", "quality_v2_failed", "embedding_gain", "ctx_what_worked"],
    visual: "fig4", threadSkip: ["negative"],
  },
  {
    id: "neg-embeddings", pillar: "NEGATIVE_RESULT", audience: "ROBOTICS_AUTONOMY",
    title: "Embeddings: a development-only gain",
    hooks: {
      TECHNICAL: "Embedding-assisted selection vs position-only sampling, across four periods.",
      SURPRISING: "Image embeddings looked great in development. Then they met new data.",
      ACCESSIBLE: "A neural network helped on the data I tuned it on. Then barely at all.",
    },
    defaultHook: "SURPRISING",
    body: "Visual-change gain over position-only sampling:\ndevelopment +0.044\nvalidation 1 +0.004\nvalidation 2 +0.001\nheld-out test +0.005\n\nPre-registered bar: +0.020. (A proxy metric, not science value.)",
    facts: ["embedding_gain", "embedding_final", "lim_geometry_not_science"],
    visual: "fig3", threadSkip: ["negative"],
  },
  {
    id: "neg-quality-detector", pillar: "NEGATIVE_RESULT", audience: "SCIENTIST",
    title: "A quality detector that tripled its false positives",
    hooks: {
      TECHNICAL: "QUALITY_V2 false-positive rate: 3.6% in development, 10.6% on validation 1.",
      SURPRISING: "My image-quality detector tripled its false positives out of sample.",
      ACCESSIBLE: "An automatic 'is this photo bad?' check failed on new data.",
    },
    defaultHook: "SURPRISING",
    body: "False positives rose from 3.6% (development) to 10.6% (validation 1), concentrated on upward-pointing, low-texture frames: 43% flagged above the horizon vs 2.2% at or below.\n\nNow only a diagnostic flag.",
    facts: ["quality_v2_failed"],
    visual: "fig4", threadSkip: ["negative"],
  },
  {
    id: "neg-phash", pillar: "NEGATIVE_RESULT", audience: "SPACECRAFT_ENGINEER",
    title: "Image fingerprints merged different scenes",
    hooks: {
      TECHNICAL: "Constrained pHash failed its safety rule on validation 1.",
      SURPRISING: "Image fingerprints merged different scenes and saved almost nothing.",
      ACCESSIBLE: "I tried spotting duplicate Mars pictures with image fingerprints. It confused different places.",
    },
    defaultHook: "SURPRISING",
    body: "Constrained pHash merged different scenes at a rate of 0.15–0.19 (limit: 0.05) and compressed traverses by at most 1.03×.\n\nUnsafe and near-useless for this task, so it was dropped.",
    facts: ["phash_failed"],
    visual: "fig4", threadSkip: ["negative"],
  },
  {
    id: "neg-jev", pillar: "NEGATIVE_RESULT", audience: "SCIENTIST",
    title: "A semantic model re-ranking events: no measurable gain",
    hooks: {
      TECHNICAL: "Semantic ranking vs rules: AUROC +0.006 (95% CI −0.020 to +0.037).",
      SURPRISING: "1,500 live calls to a semantic model. No measurable ranking gain.",
      ACCESSIBLE: "I asked an AI model which rover events mattered most. Rules did as well.",
    },
    defaultHook: "SURPRISING",
    body: "Re-ranking REMS/RAD events a frozen detector had already found, the model (Jev) did not beat deterministic rules. A pre-registered stop rule ended it.\n\nRole-specific, not a verdict on the model.",
    facts: ["jev_ranking"],
    visual: "fig4", threadSkip: ["negative"],
  },
  {
    id: "neg-telemetry", pillar: "NEGATIVE_RESULT", audience: "ROBOTICS_AUTONOMY",
    title: "Telemetry ranking ignores the images",
    hooks: {
      TECHNICAL: "Telemetry-priority image ranking, 1% budget.",
      SURPRISING: "Ranking rover images by telemetry ignores the images.",
      ACCESSIBLE: "Can weather and radiation readings pick the pictures to send? No.",
    },
    defaultHook: "SURPRISING",
    body: "Environmental telemetry is image-independent by construction. At a 1% budget it made 7 acquisitions usable at 1 rover position, the fewest of 6 strategies tested in development.\n\nDropped for image selection.",
    facts: ["telemetry_ranking"],
    visual: "fig4", threadSkip: ["negative"],
  },
  {
    id: "neg-own-rule-failed", pillar: "NEGATIVE_RESULT", audience: "SCIENTIST",
    title: "One of my own validation rules failed",
    hooks: {
      TECHNICAL: "A density-relative worst-gap rule failed on validation 1.",
      SURPRISING: "One of my own validation rules failed. It's still in the record.",
      ACCESSIBLE: "Sometimes the test itself is the problem. You still write that down.",
    },
    defaultHook: "SURPRISING",
    body: "Validation traverses were about ten times denser, so a limit set relative to frame spacing shrank from about 39 m to 3.8 m.\n\nVerdict: PARTIALLY GENERALIZES. Never rewritten; a new metric came before new data.",
    facts: ["validation1_partial", "distance_metric"],
    visual: null,
  },

  // ───────────── MISSION CONTROL ─────────────
  {
    id: "mc-send-all-vs-position", pillar: "MISSION_CONTROL", audience: "SPACE_FAN",
    title: "SEND ALL → POSITION · 1/4 (video)",
    hooks: {
      TECHNICAL: "Mission Control replays the held-out test: SEND ALL vs position sampling at 1/4.",
      SURPRISING: "Same Curiosity drive. A quarter of the frames at full quality.",
      ACCESSIBLE: "A Curiosity drive, replayed frame by frame, twice.",
    },
    defaultHook: "ACCESSIBLE",
    body: "Historical replay of archived Curiosity Navcam data, held-out test:\n• 26.1% of SEND ALL full-quality bytes\n• 100% 5 m coverage\n• 0 broken stereo pairs\n\nNot live. A replay.\ndeepsift.space/mission-control",
    facts: ["held_out_bytes", "held_out_coverage", "held_out_stereo", "ctx_mission_control"],
    visual: "mc_recording", video: MC_VIDEO, threadSkip: ["result", "demo"],
  },
  {
    id: "mc-example-traverse", pillar: "MISSION_CONTROL", audience: "SPACE_FAN",
    title: "One drive: 105 frames over 89 m",
    hooks: {
      TECHNICAL: "Example held-out traverse 967:trav00327, the longest path (not claimed representative).",
      SURPRISING: "Filled squares: full quality. Everything else: thumbnails.",
      ACCESSIBLE: "One Curiosity drive: 105 archived Navcam frames over 89 m.",
    },
    defaultHook: "ACCESSIBLE",
    body: "In the replay, position sampling keeps frames that spread out along the path, and every other frame still goes down as a thumbnail pair.\n\nArchived PDS data, replayed.\ndeepsift.space/mission-control",
    facts: ["example_traverse", "thumbnails_sent", "ctx_mission_control"],
    visual: "fig5",
    video: {
      start: "Open deepsift.space/mission-control, traverse 967:trav00327, POSITION · 1/4, press Reset.",
      steps: ["Play the replay at normal speed.", "Let the retained squares and 5 m discs accumulate along the route.", "End on the full route in FINAL STATE."],
      show: ["105 archived frames", "retained frames spreading along the path", "HISTORICAL REPLAY badge"],
      duration: "15–20 seconds",
    },
    threadSkip: ["demo"],
  },
  {
    id: "mc-tradeoff", pillar: "MISSION_CONTROL", audience: "TECHNICAL_GENERAL",
    title: "Retention sweep: 1/2, 1/4, 1/8",
    hooks: {
      TECHNICAL: "Retention sweep on the held-out test: 1/2, 1/4, 1/8.",
      SURPRISING: "Halve the frames again and the trade-off shows up.",
      ACCESSIBLE: "Send fewer pictures and, at some point, gaps appear. Here's where.",
    },
    defaultHook: "SURPRISING",
    body: "Held-out Curiosity Navcam replay:\n1/2 → 51.4% of bytes, worst 1.00 m\n1/4 → 26.1% of full-quality bytes, worst 2.05 m\n1/8 → 13.8% of bytes, 98.3% 5 m coverage, worst 6.53 m\n\nOnly 1/4 was pre-registered.",
    facts: ["operating_points", "held_out_bytes", "held_out_max_distance"],
    visual: "mc_screenshot",
    video: {
      start: "Open deepsift.space/mission-control, POSITION, retention 1/2.",
      steps: ["Switch retention 1/2 → 1/4 → 1/8, pausing on each KPI strip.", "At 1/8, click the frame farthest from a retained one."],
      show: ["bytes and worst-distance KPIs changing", "coverage dropping below 100% only at 1/8"],
      duration: "20–25 seconds",
    },
    threadSkip: ["result"],
  },
  {
    id: "mc-explainable", pillar: "MISSION_CONTROL", audience: "ROBOTICS_AUTONOMY",
    title: "Every decision has a written reason",
    hooks: {
      TECHNICAL: "Explainable selection, one frame at a time.",
      SURPRISING: "Every frame in the replay says why it was kept.",
      ACCESSIBLE: "Click any frame in the replay and it tells you why it was chosen.",
    },
    defaultHook: "ACCESSIBLE",
    body: "Farthest-point sampling on position is easy to explain: kept because it adds the most coverage, or thumbnail because a kept frame is within 5 m.\n\nHistorical replay of archived data.\ndeepsift.space/mission-control",
    facts: ["ctx_what_worked", "ctx_mission_control"],
    visual: "mc_screenshot",
    video: {
      start: "Open deepsift.space/mission-control, POSITION · 1/4, FINAL STATE.",
      steps: ["Click a retained frame; hold on its decision reason.", "Click a thumbnail-only frame; use 'Inspect nearest retained frame'."],
      show: ["the decision trace text", "the nearest retained frame and its distance"],
      duration: "15–20 seconds",
    },
    threadSkip: ["demo"],
  },

  // ───────────── ENGINEERING ─────────────
  {
    id: "eng-monotonicity", pillar: "ENGINEERING", audience: "SPACECRAFT_ENGINEER",
    title: "More budget, less coverage: the V1 bug",
    hooks: {
      TECHNICAL: "Scheduler monotonicity: coverage must never fall as budget grows.",
      SURPRISING: "My first scheduler had a bug: more bandwidth could mean less coverage.",
      ACCESSIBLE: "More bandwidth, worse result. That happened.",
    },
    defaultHook: "SURPRISING",
    body: "The greedy V1 was non-monotonic. V2 fixed that, but its compressed tier carried one eye and broke stereo.\n\nV3 fills tiers in order (thumbnails, compressed, full pairs), so coverage can't drop.",
    facts: ["scheduler_history", "scheduler_v3"],
    visual: null,
  },
  {
    id: "eng-stereo-tiers", pillar: "ENGINEERING", audience: "SPACECRAFT_ENGINEER",
    title: "Every tier carries both eyes",
    hooks: {
      TECHNICAL: "Stereo-safe scheduling: every tier carries both eyes.",
      SURPRISING: "The scheduler tier that broke stereo was one eye short.",
      ACCESSIBLE: "Never send half a stereo pair.",
    },
    defaultHook: "TECHNICAL",
    body: "Order: metadata → thumbnail pair for every acquisition → compressed pair → full pair; stop at the first that doesn't fit.\n\nHeld-out test: 0 monotonicity violations, 0 single-eye pairs. (Compressed tier: simulated.)",
    facts: ["scheduler_v3", "lim_simulated_tier"],
    visual: "navcam_pair",
  },
  {
    id: "eng-why-geometry", pillar: "ENGINEERING", audience: "ROBOTICS_AUTONOMY",
    title: "Why simple geometry may have generalized",
    hooks: {
      TECHNICAL: "Why position may have transferred when learned signals didn't.",
      SURPRISING: "The signal that generalized wasn't in the images.",
      ACCESSIBLE: "The best clue for which pictures to send was where the rover stood.",
    },
    defaultHook: "SURPRISING",
    body: "It was the rover's position. Position sampling needs no training, so there's nothing to overfit, and in all four periods every archived frame stayed within a few metres of a kept one.\n\nA hypothesis, not a proof.",
    facts: ["ctx_what_worked", "four_period_distance", "embedding_gain"],
    visual: "fig2",
  },
  {
    id: "eng-metric-choice", pillar: "ENGINEERING", audience: "SCIENTIST",
    title: "Choosing the right ruler",
    hooks: {
      TECHNICAL: "Why 'largest distance to a kept frame' replaced gap metrics.",
      SURPRISING: "My first metric measured how the rover drove, not what I picked.",
      ACCESSIBLE: "Sometimes the hard part is choosing the right ruler.",
    },
    defaultHook: "SURPRISING",
    body: "Frames cluster at rover stops about 19.5 m apart, so gap metrics tracked the drive step. Distance to the nearest kept frame is 0 m for SEND ALL and jumps to about 20 m if a method drops a stop.",
    facts: ["distance_metric"],
    visual: "fig5",
  },
  {
    id: "eng-thumbnails", pillar: "ENGINEERING", audience: "SPACE_FAN",
    title: "Nothing is thrown away",
    hooks: {
      TECHNICAL: "Byte accounting: frames that are not kept are sent as thumbnail pairs, and counted.",
      SURPRISING: "Keeping a quarter of the frames doesn't mean dropping the rest.",
      ACCESSIBLE: "When a frame isn't picked here, it isn't deleted.",
    },
    defaultHook: "SURPRISING",
    body: "In DEEPSIFT's replay, frames not kept at full quality still go down as small thumbnail pairs, and those bytes count in the total.\n\nThe real question is which frames deserve full quality first.",
    facts: ["thumbnails_sent", "held_out_retention"],
    visual: "final_test_replay",
  },

  // ───────────── METHODOLOGY ─────────────
  {
    id: "method-frozen", pillar: "METHODOLOGY", audience: "SCIENTIST",
    title: "Config committed before the first test image",
    hooks: {
      TECHNICAL: "Pre-registration via git: final test config committed before any test data was on disk.",
      SURPRISING: "The final test config was committed less than 25 seconds before the first test image hit the disk.",
      ACCESSIBLE: "Before seeing the final test data, I locked the rules in git.",
    },
    defaultHook: "SURPRISING",
    body: "Config and pass/fail rule committed: 17:03:26 UTC.\nFirst test image written: 17:03:50 UTC.\nThe analysis ran once; nothing changed afterwards.\n\ndeepsift.space/reproducibility",
    facts: ["frozen_before_download", "preregistration", "test_used_once"],
    visual: "reproducibility_page",
  },
  {
    id: "method-used-once", pillar: "METHODOLOGY", audience: "SCIENTIST",
    title: "A test only works once",
    hooks: {
      TECHNICAL: "Single-use held-out test: analysed once, not reusable.",
      SURPRISING: "The held-out test is now used up. That's the point.",
      ACCESSIBLE: "A real test only works once. After you've looked, it's no longer a test.",
    },
    defaultHook: "SURPRISING",
    body: "DEEPSIFT's final interval (Curiosity Navcam sols 950–979) was analysed once. Any change to the method now needs new, untouched data, not another look at the same sols.\n\ndeepsift.space/reproducibility",
    facts: ["test_used_once", "held_out_dataset"],
    visual: "reproducibility_page",
  },
  {
    id: "method-listings", pillar: "METHODOLOGY", audience: "SCIENTIST",
    title: "Picking validation data without looking",
    hooks: {
      TECHNICAL: "Validation 2 (sols 1100–1129) was selected from PDS listings only.",
      SURPRISING: "I picked a validation interval without looking at a single image in it.",
      ACCESSIBLE: "How do you choose test data without fooling yourself?",
    },
    defaultHook: "SURPRISING",
    body: "The interval was chosen by a rule applied to archive listings alone, before any image content was read.\n\nListing-only selection limits selection bias. It doesn't remove it.",
    facts: ["validation2_listings"],
    visual: "fig2",
  },
  {
    id: "method-staged", pillar: "METHODOLOGY", audience: "TECHNICAL_GENERAL",
    title: "Develop → validate → validate → test once",
    hooks: {
      TECHNICAL: "Develop → validate → validate → test once.",
      SURPRISING: "Most ideas died in validation. That's what validation is for.",
      ACCESSIBLE: "Here's how I tried not to fool myself.",
    },
    defaultHook: "ACCESSIBLE",
    body: "1. Tune on one period.\n2. Check on a second.\n3. Simplify, re-register, check on a third.\n4. Test once on a fourth, config committed before download.\n\nEach failed verdict stays in the record.\ndeepsift.space/research",
    facts: ["four_periods", "preregistration", "test_used_once"],
    visual: "fig4",
  },

  // ───────────── REPRODUCIBILITY ─────────────
  {
    id: "repro-integrity", pillar: "REPRODUCIBILITY", audience: "SCIENTIST",
    title: "70 hash-locked artifacts",
    hooks: {
      TECHNICAL: "70 scientific artifacts, one aggregate SHA-256, one verify command.",
      SURPRISING: "You can check that none of the result files changed after the fact.",
      ACCESSIBLE: "Every result file is fingerprinted, so anyone can check nothing was edited.",
    },
    defaultHook: "TECHNICAL",
    body: "uv run python scripts/release_integrity.py --verify\n→ INTACT\n\nConfigs, manifests, run artifacts and reports for all four periods.\ngithub.com/nassimb/deepsift",
    facts: ["integrity_manifest"],
    visual: "reproducibility_page",
  },
  {
    id: "repro-claims-script", pillar: "REPRODUCIBILITY", audience: "TECHNICAL_GENERAL",
    title: "Every public number is recomputed by a script",
    hooks: {
      TECHNICAL: "52 public claims, each checked against a frozen JSON path.",
      SURPRISING: "Every number I publish about DEEPSIFT is recomputed by a script first.",
      ACCESSIBLE: "Before I post a number, a script checks it against the original results.",
    },
    defaultHook: "SURPRISING",
    body: "scripts/check_public_claims.py recomputes all 52 from the frozen artifacts and fails on any mismatch. The numbers in these posts come from the same list.\n\ngithub.com/nassimb/deepsift",
    facts: ["public_claims"],
    visual: null,
  },
  {
    id: "repro-open", pillar: "REPRODUCIBILITY", audience: "ROBOTICS_AUTONOMY",
    title: "All of it is public, failures included",
    hooks: {
      TECHNICAL: "DEEPSIFT v1 research release: Apache-2.0, tag deepsift-v1-research.",
      SURPRISING: "All of it is public, including the parts that didn't work.",
      ACCESSIBLE: "Code, configs, data manifests, results and the paper: all public.",
    },
    defaultHook: "SURPRISING",
    body: "Git tags mark every stage, from v0.1-baseline to phase3-final-test-complete. Raw PDS products are re-downloadable and checked by SHA-256.\n\ngithub.com/nassimb/deepsift",
    facts: ["open_code", "integrity_manifest"],
    visual: "paper",
  },

  // ───────────── QUESTIONS ─────────────
  {
    id: "q-metric", pillar: "QUESTION", audience: "SCIENTIST",
    title: "Which metric would operators trust?",
    hooks: {
      TECHNICAL: "Operators: geometric coverage, sequence coverage, or stereo retention?",
      SURPRISING: "Which of my metrics would you trust first?",
      ACCESSIBLE: "When a rover can't send every picture, what should 'good enough' mean?",
    },
    defaultHook: "TECHNICAL",
    body: "DEEPSIFT reports 5 m spatial coverage, distance to the nearest kept frame, and stereo integrity. None of them measures scientific value.\n\nIf you've worked rover ops or downlink planning: what's missing?",
    facts: ["lim_geometry_not_science"],
    visual: "one_pager",
  },
  {
    id: "q-flight-constraint", pillar: "QUESTION", audience: "SPACECRAFT_ENGINEER",
    title: "What breaks first on flight hardware?",
    hooks: {
      TECHNICAL: "On flight hardware, what dominates first: CPU, memory, power, or scheduling?",
      SURPRISING: "Everything in this study ran on a laptop. Where would it break first on a rover?",
      ACCESSIBLE: "Something that works on a laptop may not work on a Mars rover. What changes first?",
    },
    defaultHook: "TECHNICAL",
    body: "Position sampling is simple arithmetic on positions, but I have no flight processor, power, thermal or memory model.\n\nIf you've built flight software: which constraint would you check first?",
    facts: ["lim_no_flight_hw"],
    visual: null,
  },
  {
    id: "q-traverse-vs-targeted", pillar: "QUESTION", audience: "SCIENTIST",
    title: "Traverse coverage vs targeted science imagery",
    hooks: {
      TECHNICAL: "How should traverse coverage be valued relative to targeted science imagery?",
      SURPRISING: "Spatial coverage says nothing about which images scientists actually need.",
      ACCESSIBLE: "Drive pictures vs science pictures: how would you share one downlink budget?",
    },
    defaultHook: "TECHNICAL",
    body: "DEEPSIFT only studied Navcam traverse sequences. Targeted science imaging is a different decision, and geometric coverage says nothing about its value.\n\nHow would you weigh the two in one budget?",
    facts: ["lim_one_rover_camera", "lim_geometry_not_science"],
    visual: null,
  },
  {
    id: "q-thumbnails-enough", pillar: "QUESTION", audience: "SPACECRAFT_ENGINEER",
    title: "When do thumbnails stop being enough?",
    hooks: {
      TECHNICAL: "Is a thumbnail of every frame plus 1/4 at full quality the right shape for traverse imagery?",
      SURPRISING: "A thumbnail of everything, full quality for a quarter. Is that the right shape?",
      ACCESSIBLE: "If you could only see small previews of most rover pictures, what would you miss?",
    },
    defaultHook: "TECHNICAL",
    body: "That's the operating point DEEPSIFT tested, in a held-out replay of archived data.\n\nIf you've used thumbnails in real planning: when do they stop being enough?",
    facts: ["thumbnails_sent", "held_out_retention"],
    visual: "final_test_replay",
  },
  {
    id: "q-next-test", pillar: "QUESTION", audience: "ROBOTICS_AUTONOMY",
    title: "What should the next test be?",
    hooks: {
      TECHNICAL: "The held-out test is used up. What would be the most informative next test?",
      SURPRISING: "My test set is spent. Where should the next one come from?",
      ACCESSIBLE: "If you could test this idea on any other rover or camera, which would you pick?",
    },
    defaultHook: "TECHNICAL",
    body: "Any extension of DEEPSIFT needs new, untouched data: another rover's navigation cameras, Mastcam, orbiter imagery?\n\nAnd what should the pass/fail rule be, written before the download?",
    facts: ["test_used_once", "lim_one_rover_camera"],
    visual: null,
  },

  // ───────────── BUILD STORY ─────────────
  {
    id: "build-clever-parts", pillar: "BUILD_STORY", audience: "TECHNICAL_GENERAL",
    title: "The clever parts came back out",
    hooks: {
      TECHNICAL: "Build log: added, validated, removed.",
      SURPRISING: "The biggest surprise: how little the clever parts mattered.",
      ACCESSIBLE: "I built a lot of AI into this project. Most of it came back out.",
    },
    defaultHook: "ACCESSIBLE",
    body: "Semantic ranking, telemetry, pHash, a quality detector and embeddings all went in. What's left: position sampling plus a stereo-safe scheduler.\n\nA unit test checks the rest can't change a decision.",
    facts: ["ctx_what_worked", "jev_ranking", "embedding_gain"],
    visual: "media_survived",
  },
  {
    id: "build-publish-failures", pillar: "BUILD_STORY", audience: "SCIENTIST",
    title: "Why the failures are public",
    hooks: {
      TECHNICAL: "Negative results are findings, not footnotes.",
      SURPRISING: "Most of DEEPSIFT's results are things that didn't work. I published them anyway.",
      ACCESSIBLE: "Most of what I tried failed. That's the useful part.",
    },
    defaultHook: "SURPRISING",
    body: "A development-only gain that disappears on new data is exactly what a staged test should catch. Every failed verdict is kept as recorded.\n\nThe full list: deepsift.space/research",
    facts: ["embedding_gain", "validation1_partial"],
    visual: "fig4",
  },
  {
    id: "build-smaller-claim", pillar: "BUILD_STORY", audience: "SCIENTIST",
    title: "The claim got smaller before the test",
    hooks: {
      TECHNICAL: "Post-validation simplification before the test.",
      SURPRISING: "Before the final test, I made the claim smaller.",
      ACCESSIBLE: "Right before the final exam, I cut the part I wasn't sure about.",
    },
    defaultHook: "SURPRISING",
    body: "Embeddings added +0.004 and +0.001 on the two validations, so the primary claim became position sampling + scheduler, embeddings a secondary question.\n\nHeld-out test: +0.005, no measurable added value.",
    facts: ["embedding_gain", "embedding_final"],
    visual: "fig3",
  },

  // ───────────── DATA / MARS VISUAL ─────────────
  {
    id: "vis-navcam-frame", pillar: "MARS_VISUAL", audience: "SPACE_FAN",
    title: "A real Navcam frame, sol 967",
    hooks: {
      TECHNICAL: "Curiosity Navcam frame, sol 967, from traverse 967:trav00327 (display preview).",
      SURPRISING: "One of 679 archived frames in DEEPSIFT's held-out test.",
      ACCESSIBLE: "A real Curiosity Navcam frame from sol 967, from NASA's public archive.",
    },
    defaultHook: "ACCESSIBLE",
    body: "Navcam is the rover's navigation stereo camera. DEEPSIFT replays its archived drive imagery to study which frames to send at full quality first.\n\nImage: NASA/JPL-Caltech (contrast-stretched preview).",
    facts: ["ctx_public_data", "example_traverse", "held_out_dataset"],
    visual: "navcam_left",
  },
  {
    id: "vis-stereo-pair", pillar: "MARS_VISUAL", audience: "SPACE_FAN",
    title: "Left eye, right eye",
    hooks: {
      TECHNICAL: "One archived Navcam stereo acquisition: left and right eyes, sol 967.",
      SURPRISING: "Two pictures, one moment: Curiosity's Navcam shoots in stereo.",
      ACCESSIBLE: "Left eye, right eye: Curiosity's navigation camera shoots in stereo.",
    },
    defaultHook: "ACCESSIBLE",
    body: "That's why DEEPSIFT's scheduler never sends one eye without the other. In the held-out replay of archived data, 174 pairs were kept whole and 0 were split.\n\nImages: NASA/JPL-Caltech (display previews).",
    facts: ["held_out_stereo", "ctx_public_data"],
    visual: "navcam_pair",
  },
  {
    id: "vis-bandwidth", pillar: "MARS_VISUAL", audience: "GENERAL",
    title: "The bandwidth challenge",
    hooks: {
      TECHNICAL: "Downlink prioritization: full quality, thumbnail, later, or never.",
      SURPRISING: "Not every bit deserves the trip to Earth.",
      ACCESSIBLE: "A Mars rover can collect more data than it can send home.",
    },
    defaultHook: "ACCESSIBLE",
    body: "Something has to decide what goes first. DEEPSIFT is independent research that replays archived Curiosity data to measure which signals actually help.\n\nNot affiliated with NASA or JPL.\ndeepsift.space",
    facts: ["ctx_bandwidth_problem", "lim_no_nasa", "ctx_public_data"],
    visual: "navcam_left", threadSkip: ["problem"],
  },
  {
    id: "vis-route-map", pillar: "MARS_VISUAL", audience: "SPACE_FAN",
    title: "89 metres of Curiosity's drive",
    hooks: {
      TECHNICAL: "Example held-out traverse: kept frames, thumbnails, 5 m discs.",
      SURPRISING: "Filled squares: full quality. Hollow circles: thumbnails only.",
      ACCESSIBLE: "89 metres of Curiosity's drive, and which frames went down at full quality.",
    },
    defaultHook: "ACCESSIBLE",
    body: "Each shaded disc is 5 m around a kept frame. On this example traverse (the longest), every archived frame sits inside a disc.\n\nArchived PDS data; not claimed representative.",
    facts: ["example_traverse", "held_out_coverage"],
    visual: "fig5",
  },
];

export const IDEA_BY_ID: Record<string, ContentIdea> = Object.fromEntries(IDEAS.map((i) => [i.id, i]));

/** Hook + body, exactly as it would be posted. */
export function composePost(idea: ContentIdea, style: HookStyle = idea.defaultHook): string {
  return `${idea.hooks[style]}\n\n${idea.body}`;
}

/** Deterministic thread: the composed post, then the standard blocks it doesn't already cover (4–7 posts). */
export function composeThread(idea: ContentIdea, style: HookStyle = idea.defaultHook): string[] {
  const skip = new Set(idea.threadSkip ?? []);
  return [composePost(idea, style), ...THREAD_ORDER.filter((b) => !skip.has(b)).map((b) => THREAD_BLOCKS[b])];
}
