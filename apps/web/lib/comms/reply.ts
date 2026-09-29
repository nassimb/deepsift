/** REPLY LAB — deterministic reply assistant for other people's X posts. No model, no API.
 *
 *  What is deterministic (and honest about it):
 *  - topic + relevance detection from a transparent keyword lexicon (the matched words are shown);
 *  - DEEPSIFT talking points ("angles") written ONLY from VERIFIED_FACTS wording, in the builder's own voice;
 *  - reply styles assembled from those angles and a bank of expert questions;
 *  - constructive disagreement only when the post matches a stance pattern that DEEPSIFT evidence actually contradicts;
 *  - claim check (lib/comms/claims.ts) + reply rules (no hashtags, no @mentions, no automatic link), promotional risk,
 *    value check (NOTHING → DON'T REPLY), link recommendation and repetition protection.
 *  What it cannot do: understand the specific argument of an arbitrary post. Replies react to the detected TOPIC, not to
 *  the author's exact claim — that part needs a language model or your own edit (see SEMANTIC_LIMITATION). Pure logic. */
import { checkPost, type ClaimCheck } from "./claims.ts";
import { FACT_BY_ID } from "./facts.ts";
import type { PromoRisk, Relevance, ReplyRecord } from "./store.ts";

export const SEMANTIC_LIMITATION =
  "Keyword-based, deterministic analysis: it detects the topic and matches verified DEEPSIFT talking points, but it does not understand the author's specific argument. Read the post yourself and edit the reply so it answers what they actually said.";

export type ConnectionType =
  | "RESULT" | "NEGATIVE RESULT" | "ENGINEERING LESSON" | "METHODOLOGY" | "MISSION CONTROL" | "DATASET / CURIOSITY" | "AUTONOMY"
  | "DOWNLINK CONSTRAINT" | "STEREO PRESERVATION" | "SPATIAL COVERAGE" | "VALIDATION / GENERALIZATION" | "REPRODUCIBILITY"
  | "LIMITATION" | "OPEN RESEARCH QUESTION";

export type ReplyStyle = "SHORT" | "TECHNICAL" | "CURIOUS" | "CONSTRUCTIVE_DISAGREEMENT" | "QUESTION" | "DEEPSIFT_CONNECTION" | "NO_PROJECT_MENTION";
export const REPLY_STYLES: ReplyStyle[] = ["SHORT", "TECHNICAL", "CURIOUS", "CONSTRUCTIVE_DISAGREEMENT", "QUESTION", "DEEPSIFT_CONNECTION", "NO_PROJECT_MENTION"];
export const STYLE_LABEL: Record<ReplyStyle, string> = {
  SHORT: "Short", TECHNICAL: "Technical", CURIOUS: "Curious", CONSTRUCTIVE_DISAGREEMENT: "Constructive disagreement",
  QUESTION: "Question", DEEPSIFT_CONNECTION: "DEEPSIFT connection", NO_PROJECT_MENTION: "No project mention",
};

export type Value = "NEW EVIDENCE" | "PERSONAL EXPERIMENT" | "TECHNICAL QUESTION" | "METHODOLOGICAL POINT" | "USEFUL LIMITATION" | "CONSTRUCTIVE DISAGREEMENT" | "NOTHING";
export type LinkRec = "NONE" | "MISSION CONTROL" | "FINAL TEST" | "RESEARCH" | "GITHUB" | "HOMEPAGE";
export const LINK_URL: Record<Exclude<LinkRec, "NONE">, string> = {
  "MISSION CONTROL": "deepsift.space/mission-control",
  "FINAL TEST": "deepsift.space/final-test",
  RESEARCH: "deepsift.space/research",
  GITHUB: "github.com/nassimb/deepsift",
  HOMEPAGE: "deepsift.space",
};

// ─── talking points (only VERIFIED_FACTS wording) ──────────────────────────
export interface Angle {
  id: string;
  label: string;
  types: ConnectionType[];
  facts: string[];
  value: Value;
  /** Short, no project name. */
  short: string;
  /** Personal voice, no project name (the default NATURAL reply). */
  natural: string;
  /** Precise, numbers + scope, no project name. */
  technical: string;
  /** Names DEEPSIFT once. */
  deepsift: string;
  /** No project and no personal experiment — an observation or question only. */
  plain: string;
}

export const ANGLES: Angle[] = [
  {
    id: "complexity-didnt-generalize", label: "More complex signals didn't generalize", types: ["NEGATIVE RESULT", "VALIDATION / GENERALIZATION", "AUTONOMY"],
    facts: ["embedding_gain", "jev_ranking", "ctx_what_worked"], value: "PERSONAL EXPERIMENT",
    short: "In my tests on archived Curiosity data, the more complex selection signals didn't hold up out of sample. Rover position did.",
    natural: "One thing I found testing this on archived Curiosity Navcam data: the more complex decision signals didn't generalize better. A simple geometry-based signal held up best in the held-out replay.\n\nIt made me more cautious about equating onboard intelligence with model complexity.",
    technical: "In a pre-registered replay of archived Curiosity Navcam data, image embeddings added +0.044 visual-change coverage in development, then +0.004 / +0.001 / +0.005 on later periods (bar: +0.020). Farthest-point sampling on rover position was what held up.",
    deepsift: "This is something I ran into while testing DEEPSIFT on archived Curiosity Navcam data: the semantic, telemetry and embedding signals didn't add measurable value after validation. What generalized was rover position plus a stereo-safe scheduler.",
    plain: "How often do the more complex decision signals still help once you test them on data from a different period? That's the part I'd want to see before trusting them onboard.",
  },
  {
    id: "what-is-preserved", label: "Defining what is preserved under a byte budget", types: ["DOWNLINK CONSTRAINT", "SPATIAL COVERAGE", "LIMITATION"],
    facts: ["lim_geometry_not_science", "held_out_coverage", "held_out_stereo"], value: "USEFUL LIMITATION",
    short: "The hard part for me wasn't cutting bytes, it was defining what I could honestly claim stayed intact. I limited it to geometric coverage and stereo integrity, not science value.",
    natural: "I've been experimenting with this constraint on archived Curiosity Navcam data. The interesting part wasn't reducing bytes, it was defining what could honestly be claimed to stay preserved.\n\nI limited that claim to geometric coverage and stereo integrity, not scientific value.",
    technical: "Working on this with archived Curiosity Navcam data, I ended up reporting only what the metrics measure: 5 m spatial coverage, distance to the nearest kept frame and stereo integrity. Geometric coverage is not scientific value, and only mission scientists could judge that.",
    deepsift: "This is the constraint I've been working on in DEEPSIFT, using archived Curiosity Navcam data. The interesting part wasn't reducing bytes, it was defining what could honestly be claimed to remain preserved: geometric coverage and stereo integrity, not scientific value.",
    plain: "When a downlink budget forces a cut, what should count as preserved? Geometric coverage is easy to measure, but it isn't scientific value. I'm curious how mission teams define it.",
  },
  {
    id: "held-out-result", label: "Held-out result (1/4 retention)", types: ["RESULT", "DOWNLINK CONSTRAINT", "DATASET / CURIOSITY"],
    facts: ["held_out_bytes", "held_out_coverage", "held_out_stereo", "held_out_retention"], value: "NEW EVIDENCE",
    short: "On a held-out replay of archived Curiosity Navcam traverses, keeping 1/4 of frames at full quality used 26.1% of the full-quality bytes, with 100% 5 m coverage.",
    natural: "I tested a small version of this on archived Curiosity Navcam traverses. In a held-out replay, keeping 1/4 of frames at full quality (the rest as thumbnails) used 26.1% of the full-quality bytes, with every frame within 5 m of a kept one.",
    technical: "Held-out replay, archived Curiosity Navcam (sols 950–979): position sampling at 1/4 retention used 26.1% of SEND ALL full-quality bytes, 100% 5 m coverage, max 2.05 m to a kept frame, 0 broken stereo pairs. Archived data only; not the onboard stream.",
    deepsift: "Related data point from DEEPSIFT, my replay of archived Curiosity Navcam data: on a held-out test, keeping 1/4 of traverse frames at full quality used 26.1% of the full-quality bytes, with 100% 5 m coverage and 0 broken stereo pairs.",
    plain: "Has anyone measured how much spatial coverage survives when only a fraction of traverse frames go down at full quality? That trade-off seems under-discussed.",
  },
  {
    id: "stereo-constraint", label: "Never split a stereo pair", types: ["STEREO PRESERVATION", "ENGINEERING LESSON"],
    facts: ["scheduler_v3", "scheduler_history"], value: "PERSONAL EXPERIMENT",
    short: "One lesson from my own scheduler experiments: a compressed tier that carried only one eye silently broke stereo pairs. Every tier has to carry both eyes.",
    natural: "I ran into this building a downlink scheduler for archived Curiosity Navcam data. An early version had a compressed tier that carried only one eye, which quietly broke stereo pairs.\n\nThe fix was making every tier carry both eyes.",
    technical: "A scheduling detail that bit me: a progressive tier carrying one eye breaks stereo. The version that held up fills metadata, then a thumbnail pair for every acquisition, then compressed pairs, then full pairs, never one eye alone (0 single-eye pairs in the held-out replay).",
    deepsift: "Stereo was one of the harder constraints in DEEPSIFT: an early scheduler's compressed tier carried one eye and broke pairs. The final one makes every tier carry both eyes, and had 0 single-eye pairs in the held-out replay of archived Curiosity data.",
    plain: "For stereo cameras, do downlink schedulers treat the pair as one unit at every quality tier? Sending one eye alone seems like an easy failure mode.",
  },
  {
    id: "monotonic-scheduler", label: "More budget reduced coverage (V1 bug)", types: ["ENGINEERING LESSON", "DOWNLINK CONSTRAINT"],
    facts: ["scheduler_history"], value: "PERSONAL EXPERIMENT",
    short: "My first downlink scheduler had a bug where more bandwidth could mean less coverage. Worth testing monotonicity explicitly.",
    natural: "Something I learned the hard way: my first greedy downlink scheduler was non-monotonic, so giving it more budget could reduce coverage.\n\nI now test that property explicitly before looking at anything else.",
    technical: "A property worth testing in any downlink scheduler: monotonicity. My first greedy version wasn't; more budget could reduce coverage. Filling tiers in a fixed order (thumbnails, then compressed, then full) makes coverage a prefix, so it can't drop.",
    deepsift: "In DEEPSIFT my first greedy scheduler was non-monotonic: more budget could reduce coverage. Filling tiers in a fixed order fixed it. Since then I test monotonicity before anything else.",
    plain: "Do downlink schedulers get tested for monotonicity, so that more budget never means less coverage? It's an easy property to break with greedy logic.",
  },
  {
    id: "validation-protocol", label: "Pre-registered, single-use held-out test", types: ["METHODOLOGY", "VALIDATION / GENERALIZATION", "REPRODUCIBILITY"],
    facts: ["preregistration", "frozen_before_download", "test_used_once"], value: "METHODOLOGICAL POINT",
    short: "What helped me most was committing the pass/fail rule before downloading the test data, then running the test once.",
    natural: "What changed my results most wasn't a model, it was the protocol: write the pass/fail rule, commit it, and only then download the data that tests it. The final test ran once.\n\nSeveral ideas that looked good in development didn't survive that.",
    technical: "Method that kept me honest: tune on one period, validate on two others, then one held-out test. Each config and pass/fail rule was committed to git before the test data was downloaded, and the analysis ran once.",
    deepsift: "In DEEPSIFT I committed every config and pass/fail rule to git before downloading the data that tested it, and ran the final test once. It removed a development-only gain I'd otherwise have reported.",
    plain: "Was the evaluation rule fixed before the test data was seen? For autonomy results, that single detail changes how much I trust the numbers.",
  },
  {
    id: "dev-only-gain", label: "A development-only gain", types: ["VALIDATION / GENERALIZATION", "NEGATIVE RESULT"],
    facts: ["embedding_gain", "embedding_final"], value: "NEW EVIDENCE",
    short: "In my rover-image experiments, a signal looked useful in development (+0.044) and fell to +0.001 to +0.005 on new periods. Held-out checks changed my conclusions.",
    natural: "I had exactly this happen: image embeddings looked useful on the data I tuned on, then added almost nothing on three later periods.\n\nIf I hadn't fixed the threshold in advance, I'd probably have reported the development number.",
    technical: "Concrete case: embedding-assisted selection gained +0.044 visual-change coverage in development, then +0.004, +0.001 and +0.005 on validation and held-out periods, against a pre-registered +0.020 bar. The metric is a proxy, not science value.",
    deepsift: "DEEPSIFT had a textbook case: embeddings gained +0.044 in development, then +0.004 / +0.001 / +0.005 on new periods, below a pre-registered +0.020 bar. So they stayed a comparator, not part of the method.",
    plain: "How big is the gap between development and held-out performance here? In my experience that gap is where most of the story is.",
  },
  {
    id: "quality-detector-ood", label: "Quality detector failed out of sample", types: ["NEGATIVE RESULT", "VALIDATION / GENERALIZATION"],
    facts: ["quality_v2_failed"], value: "NEW EVIDENCE",
    short: "A learned image-quality check I built went from 3.6% to 10.6% false positives on a new period, mostly on upward-pointing frames.",
    natural: "Similar experience here: a learned image-quality check I built looked fine in development (3.6% false positives) and tripled on a new stretch of archived Curiosity data (10.6%), mostly on upward-pointing, low-texture frames.",
    technical: "Data point: a learned Navcam quality detector had a 3.6% false-positive rate in development and 10.6% on validation, with 43% flagged above the horizon vs 2.2% at or below. It was kept only as a diagnostic flag.",
    deepsift: "In DEEPSIFT a learned quality detector went from 3.6% false positives in development to 10.6% on a new period of archived Curiosity data, so it was demoted to a diagnostic flag.",
    plain: "How does the detector behave on frames pointing up at the sky or at low-texture terrain? That's where I'd expect false positives to jump.",
  },
  {
    id: "survivorship", label: "Archive survivorship bias", types: ["LIMITATION", "DATASET / CURIOSITY"],
    facts: ["lim_survivorship", "lim_no_onboard_stream"], value: "USEFUL LIMITATION",
    short: "One caveat with archive-based studies: the public archive only holds what was already sent home, so you can't see what was never downlinked.",
    natural: "A limitation I keep running into with archive-based work: the public archive only contains what the mission already sent home. Any replay re-prioritizes those archived observations; it can't see images that were never sent.",
    technical: "Caveat for anyone replaying PDS data: it's survivorship-biased. The archive holds downlinked products only, so a replay re-prioritizes archived observations and does not reconstruct what the rover actually held onboard.",
    deepsift: "It's the main caveat on DEEPSIFT too: the PDS only holds what Curiosity already downlinked, so my replay re-prioritizes archived observations. It can't see what was never sent.",
    plain: "How do you account for survivorship bias when the archive only contains what was already downlinked?",
  },
  {
    id: "metric-choice", label: "Choosing the right spatial metric", types: ["METHODOLOGY", "SPATIAL COVERAGE"],
    facts: ["distance_metric"], value: "METHODOLOGICAL POINT",
    short: "Gap metrics fooled me: frames cluster at rover stops, so they measured the drive, not the selection. Distance to the nearest kept frame worked better.",
    natural: "One metric lesson from my own experiments: frames cluster at rover stops about 19.5 m apart, so gap-based metrics mostly measured how the rover drove.\n\nThe distance from every frame to its nearest kept frame turned out to be the useful one.",
    technical: "Metric note: median native spacing between consecutive frames was 0 m, with stops about 19.5 m apart, so gap metrics tracked the drive step. Distance to the nearest kept frame is 0 m for SEND ALL and jumps to about 20 m when a method drops a whole stop.",
    deepsift: "A metric lesson from DEEPSIFT: rover frames cluster at stops about 19.5 m apart, so gap metrics mostly measured the drive. I switched to the distance from each archived frame to its nearest kept frame.",
    plain: "Which spatial metric do you use? Gap metrics can end up measuring the rover's drive pattern rather than the selection.",
  },
  {
    id: "laptop-only", label: "No flight hardware (open question)", types: ["LIMITATION", "OPEN RESEARCH QUESTION", "AUTONOMY"],
    facts: ["lim_no_flight_hw"], value: "USEFUL LIMITATION",
    short: "Everything I've tested so far ran on a laptop, so I have no idea yet which onboard constraint would bite first.",
    natural: "This is one of the limitations I struggled with: everything in my experiment ran on a laptop, with no flight processor, power or thermal model.\n\nSo I genuinely don't know which onboard constraint would dominate first.",
    technical: "Honest gap in my own work: all selection and scheduling ran on a laptop CPU, with no radiation-tolerant processor, flight software, power or thermal model. Byte costs are label estimates, not flight packetization.",
    deepsift: "It's the biggest open gap in DEEPSIFT: everything ran on a laptop, with no flight processor, power or thermal model. The selection logic is simple, but I haven't tested it anywhere near flight conditions.",
    plain: "For onboard selection logic, which constraint tends to dominate first: compute, memory, power, or relay scheduling?",
  },
  {
    id: "mission-control-replay", label: "Historical replay you can inspect", types: ["MISSION CONTROL", "DATASET / CURIOSITY"],
    facts: ["ctx_mission_control", "example_traverse", "thumbnails_sent"], value: "PERSONAL EXPERIMENT",
    short: "I built a historical replay of archived Curiosity Navcam traverses that shows, frame by frame, which frames go down at full quality and why.",
    natural: "I've been replaying archived Curiosity Navcam traverses frame by frame. Seeing which frames go down at full quality, and which only as thumbnails, made the downlink trade-offs much easier to reason about.",
    technical: "Replaying archived Curiosity Navcam traverses frame by frame helped me: each kept frame is the position farthest from everything already kept, and every other frame still goes down as a thumbnail pair. It's a historical replay, not live data.",
    deepsift: "I built DEEPSIFT's Mission Control for exactly this: a frame-by-frame historical replay of archived Curiosity Navcam traverses showing which frames go down at full quality and why. Not live data; a replay.",
    plain: "Is there a replay or visualization of how frames are chosen on a real traverse? It makes these trade-offs much easier to reason about.",
  },
  {
    id: "reproducibility", label: "Hash-locked, checkable results", types: ["REPRODUCIBILITY", "METHODOLOGY"],
    facts: ["integrity_manifest", "public_claims"], value: "METHODOLOGICAL POINT",
    short: "Something that helped my own work: hash-locking the result files and recomputing every public number from them by script.",
    natural: "What helped me most with reproducibility: hash-locking the 70 files behind the result, and having a script recompute every public number from them before anything is published.",
    technical: "Reproducibility setup that worked for me: 70 artifacts under an integrity manifest with an aggregate SHA-256, plus a script that recomputes all 52 public numbers from the frozen artifacts and fails on any mismatch.",
    deepsift: "In DEEPSIFT the 70 files behind the result are hash-locked, and a script recomputes all 52 public numbers from them before anything is published. It caught more mistakes than I expected.",
    plain: "Are the result files hash-locked or versioned so others can check nothing changed after the fact?",
  },
];
export const ANGLE_BY_ID: Record<string, Angle> = Object.fromEntries(ANGLES.map((a) => [a.id, a]));

// ─── topics (transparent keyword lexicon) ──────────────────────────────────
export interface Topic {
  id: string;
  label: string;
  strength: Exclude<Relevance, "NONE">;
  re: RegExp;
  angles: string[];
  questions: string[];
  types: ConnectionType[];
}

const Q = {
  proxy: "For an operational system, would you treat traverse geometry as a useful first-order proxy, or would mission teams need observation-type-specific utility functions?",
  constraint: "Which constraint do you think becomes dominant first onboard: compute, storage, power, or relay scheduling?",
  triage: "Would you evaluate image triage independently from observation planning, or only end-to-end?",
  metric: "Which metric would mission operators trust first here: geometric coverage, sequence coverage, or stereo retention?",
  learned: "Which onboard decisions do you think benefit most from learned models, and which are better left to deterministic policies?",
  validation: "How do you decide a gain is real before testing on a new period? Is a pre-declared threshold common practice in your field?",
  thumbnails: "When you plan with thumbnails, at what point do they stop being enough to decide what to request at full quality?",
  archive: "How would you correct for the fact that archives only contain what was already downlinked?",
  targeted: "How would you weigh traverse coverage against targeted science imagery within one downlink budget?",
  replay: "Would a frame-by-frame replay of the selection be useful for operators, or would they want aggregate metrics only?",
};

export const TOPICS: Topic[] = [
  { id: "downlink", label: "rover/spacecraft downlink & bandwidth", strength: "STRONG",
    re: /\b(down[- ]?link\w*|bandwidth|data volume|relay (pass|orbiter)s?|data rates?|bits? per|megabits?|mbps|kbps|deep space network|DSN|MRO relay|limited (link|bandwidth))\b/gi,
    angles: ["what-is-preserved", "held-out-result", "monotonic-scheduler", "complexity-didnt-generalize"], questions: [Q.constraint, Q.metric, Q.thumbnails], types: ["DOWNLINK CONSTRAINT", "RESULT"] },
  { id: "prioritization", label: "onboard data prioritization / image selection", strength: "STRONG",
    re: /\b(prioriti[sz]\w*|triage|image selection|data selection|select(ing)? (which|what) (images?|data)|which (images?|data|frames?) to send|onboard (selection|summari[sz]ation)|data reduction|science data management)\b/gi,
    angles: ["complexity-didnt-generalize", "held-out-result", "what-is-preserved", "dev-only-gain"], questions: [Q.triage, Q.proxy, Q.learned], types: ["AUTONOMY", "RESULT"] },
  { id: "mars-imagery", label: "Mars rover imagery / Curiosity / Navcam", strength: "STRONG",
    re: /\b(Curiosity|Navcam|Hazcam|Mastcam|Perseverance|rover (images?|imagery|cameras?|photos?|pictures?)|Gale crater|Mount Sharp|raw images?)\b/gi,
    angles: ["mission-control-replay", "survivorship", "held-out-result", "stereo-constraint"], questions: [Q.thumbnails, Q.targeted, Q.replay], types: ["DATASET / CURIOSITY", "MISSION CONTROL"] },
  { id: "navigation", label: "rover navigation / traverse", strength: "STRONG",
    re: /\b(rover navigation|auto[- ]?nav|traverse\w*|drive distance|drove \d+|path planning|localization|visual odometry)\b/gi,
    angles: ["metric-choice", "held-out-result", "stereo-constraint"], questions: [Q.proxy, Q.metric], types: ["SPATIAL COVERAGE", "AUTONOMY"] },
  { id: "stereo", label: "stereo imagery", strength: "STRONG",
    re: /\b(stereo\w*|stereoscopic|3D (terrain|mesh|reconstruction)|depth maps?|anaglyph)\b/gi,
    angles: ["stereo-constraint"], questions: [Q.metric], types: ["STEREO PRESERVATION"] },
  { id: "autonomous-science", label: "autonomous science / onboard autonomy", strength: "STRONG",
    re: /\b(autonomous science|science autonomy|onboard autonomy|on-board autonomy|autonomous (rovers?|spacecraft|operations?|targeting)|AEGIS|onboard decision\w*)\b/gi,
    angles: ["complexity-didnt-generalize", "validation-protocol", "laptop-only"], questions: [Q.learned, Q.triage, Q.constraint], types: ["AUTONOMY", "NEGATIVE RESULT"] },
  { id: "onboard-compute", label: "edge inference / onboard computing", strength: "STRONG",
    re: /\b(onboard (comput\w*|processing|inference|AI|ML)|edge (inference|computing|AI)|flight (processors?|computers?|software)|radiation[- ](hardened|tolerant)|HPSC|RAD750|FPGA)\b/gi,
    angles: ["laptop-only", "complexity-didnt-generalize"], questions: [Q.constraint, Q.learned], types: ["AUTONOMY", "LIMITATION"] },
  { id: "mission-ops", label: "mission operations / planning", strength: "STRONG",
    re: /\b(mission operations|ops team|tactical planning|sol planning|operations team|uplink|command sequenc\w*|mission planners?)\b/gi,
    angles: ["what-is-preserved", "mission-control-replay", "survivorship"], questions: [Q.metric, Q.thumbnails, Q.replay], types: ["MISSION CONTROL", "OPEN RESEARCH QUESTION"] },
  { id: "compression", label: "compression / telemetry constraints", strength: "STRONG",
    re: /\b(compress\w*|ICER|JPEG|lossy|lossless|telemetry (budget|constraints?|limits?)|data budget)\b/gi,
    angles: ["what-is-preserved", "stereo-constraint", "monotonic-scheduler"], questions: [Q.metric, Q.constraint], types: ["DOWNLINK CONSTRAINT", "STEREO PRESERVATION"] },
  { id: "autonomy-validation", label: "validation of autonomous systems", strength: "STRONG",
    re: /\b(validat\w* (autonom\w*|onboard|flight)|verification and validation|V&V|test(ing)? autonom\w*|trust(ing)? autonom\w*|certif\w* (AI|autonom\w*))\b/gi,
    angles: ["validation-protocol", "dev-only-gain", "complexity-didnt-generalize"], questions: [Q.validation, Q.learned], types: ["VALIDATION / GENERALIZATION", "METHODOLOGY"] },
  { id: "planetary-data", label: "planetary mission data systems / PDS", strength: "STRONG",
    re: /\b(PDS|Planetary Data System|data archive|archived data|open data|raw data release|data pipeline)\b/gi,
    angles: ["survivorship", "reproducibility", "mission-control-replay"], questions: [Q.archive], types: ["DATASET / CURIOSITY", "REPRODUCIBILITY"] },
  // moderate
  { id: "robotics", label: "robotics", strength: "MODERATE",
    re: /\b(robot\w*|manipulat\w*|SLAM|field robotics|autonomous vehicles?|drones?|UAVs?)\b/gi,
    angles: ["dev-only-gain", "validation-protocol", "complexity-didnt-generalize"], questions: [Q.validation, Q.learned], types: ["AUTONOMY", "VALIDATION / GENERALIZATION"] },
  { id: "ai-reliability", label: "AI reliability / generalization", strength: "MODERATE",
    re: /\b(generali[sz]\w*|overfit\w*|out[- ]of[- ](sample|distribution)|distribution shift|benchmark\w*|held[- ]out|reliab\w* (AI|ML|models?)|hallucinat\w*|robustness)\b/gi,
    angles: ["dev-only-gain", "quality-detector-ood", "validation-protocol"], questions: [Q.validation], types: ["VALIDATION / GENERALIZATION", "NEGATIVE RESULT"] },
  { id: "science-ml", label: "scientific ML validation", strength: "MODERATE",
    re: /\b(machine learning|deep learning|neural net\w*|ML models?|AI models?|LLMs?|foundation models?|embeddings?)\b.*\b(science|scientific|research|data)\b|\b(scientific|science) (ML|AI|machine learning)\b/gi,
    angles: ["dev-only-gain", "complexity-didnt-generalize", "validation-protocol"], questions: [Q.validation, Q.learned], types: ["VALIDATION / GENERALIZATION", "METHODOLOGY"] },
  { id: "autonomous-systems", label: "autonomous systems", strength: "MODERATE",
    re: /\b(autonom\w*|self[- ]driving|decision[- ]making systems?)\b/gi,
    angles: ["complexity-didnt-generalize", "validation-protocol", "laptop-only"], questions: [Q.learned, Q.constraint], types: ["AUTONOMY"] },
  { id: "edge-ai", label: "edge AI", strength: "MODERATE",
    re: /\b(edge (devices?|hardware)|tinyML|on-device|low[- ]power (AI|inference|compute))\b/gi,
    angles: ["laptop-only", "complexity-didnt-generalize"], questions: [Q.constraint], types: ["AUTONOMY", "LIMITATION"] },
  { id: "computer-vision", label: "computer vision", strength: "MODERATE",
    re: /\b(computer vision|image (classification|recognition|quality)|object detection|perceptual hash\w*|pHash|image similarity|segmentation)\b/gi,
    angles: ["quality-detector-ood", "dev-only-gain"], questions: [Q.validation], types: ["NEGATIVE RESULT", "VALIDATION / GENERALIZATION"] },
  { id: "reproducible-research", label: "reproducible research", strength: "MODERATE",
    re: /\b(reproduc\w*|replicat\w*|pre-?regist\w*|open science|negative results?|p-hacking|research integrity)\b/gi,
    angles: ["validation-protocol", "reproducibility", "dev-only-gain"], questions: [Q.validation], types: ["METHODOLOGY", "REPRODUCIBILITY"] },
  // weak
  { id: "space-general", label: "space exploration (general)", strength: "WEAK",
    re: /\b(Mars|NASA|JPL|ESA|rovers?|spacecraft|mission|space exploration|planetary|lander|orbiter|Moon|lunar|Artemis)\b/gi,
    angles: ["what-is-preserved", "survivorship"], questions: [Q.targeted, Q.metric], types: ["OPEN RESEARCH QUESTION"] },
  { id: "ai-general", label: "AI (general)", strength: "WEAK",
    re: /\b(AI|artificial intelligence|machine learning|ML|LLMs?|GPT|chatbots?)\b/g,
    angles: ["complexity-didnt-generalize", "dev-only-gain"], questions: [Q.learned, Q.validation], types: ["OPEN RESEARCH QUESTION"] },
];

/** Topics that look space-related but have no DEEPSIFT connection on their own (astronomy/astrophysics). */
const NO_CONNECTION_TOPICS = /\b(black holes?|galax\w*|exoplanets?|JWST|Webb|Hubble|telescopes?|supernova\w*|cosmolog\w*|dark (matter|energy)|big bang|neutron stars?|gravitational waves?|nebula\w*|quasars?|astrophysic\w*|launch(es|ed)? (window|pad)|rocket launch|Starship|Falcon)\b/gi;

// ─── stances DEEPSIFT evidence can respectfully push back on ──────────────
export interface Stance {
  id: string;
  re: RegExp;
  /** Acknowledge the point + name the specific disagreement. */
  acknowledge: string;
  /** Evidence from VERIFIED_FACTS, with its limitation. */
  evidence: string;
  /** Angle this evidence belongs to (for repetition tracking). */
  angle: string;
  /** Exactly the VERIFIED_FACTS the evidence sentence uses. */
  facts: string[];
  question: string;
}
export const STANCES: Stance[] = [
  { id: "ai-will-transform", re: /\b(AI|machine learning|deep learning|LLMs?)\b[^.?!]{0,40}\b(will|is going to|is about to)\b[^.?!]{0,20}\b(transform|revolutioni[sz]e|change everything|solve|replace)\b/i,
    acknowledge: "Agree models will matter. My own tests made me more cautious about how much.",
    evidence: "On archived Curiosity data, semantic and embedding signals added no measurable value after validation. One small experiment, though.",
    angle: "complexity-didnt-generalize", facts: ["jev_ranking", "embedding_gain"], question: "Which onboard decisions need learned models most?" },
  { id: "more-complex-better", re: /\b(more (data|compute|parameters|complex\w*|sophisticated)|bigger models?|smarter (models?|AI|algorithms?))\b[^.?!]{0,40}\b(better|wins?|beats?|outperforms?|always)\b/i,
    acknowledge: "Sometimes. In the one downlink problem I tested, it didn't.",
    evidence: "Embeddings gained +0.044 in development, then +0.001 to +0.005 on new periods, below a pre-registered +0.020 bar. One experiment on archived Curiosity data.",
    angle: "dev-only-gain", facts: ["embedding_gain"], question: "Where has complexity paid off out of sample for you?" },
  { id: "bandwidth-solved", re: /\b(bandwidth|downlink)\b[^.?!]{0,40}\b(solved|no longer (a|an) (problem|issue|constraint)|isn't (a|an) (problem|issue|constraint) anymore)\b/i,
    acknowledge: "Links are improving, but I doubt prioritization goes away.",
    evidence: "Someone still decides what goes first and what counts as preserved. On archived Curiosity data I could only claim geometric coverage and stereo integrity, not science value.",
    angle: "what-is-preserved", facts: ["lim_geometry_not_science", "held_out_stereo"], question: "What becomes the binding constraint next?" },
  { id: "dev-results-enough", re: /\b(state[- ]of[- ]the[- ]art|SOTA|99(\.\d+)?%|near[- ]perfect)\b[^.?!]{0,60}\b(accuracy|performance|results?)\b/i,
    acknowledge: "Impressive numbers. What I'd want next is the same metric on data from a different period.",
    evidence: "In my own tests, a learned quality detector went from 3.6% to 10.6% false positives on a new period of archived Curiosity data.",
    angle: "quality-detector-ood", facts: ["quality_v2_failed"], question: "Has it been tested on a held-out site or period?" },
];

// ─── analysis ──────────────────────────────────────────────────────────────
export interface ReplyInput {
  text: string;
  url?: string;
  authorName?: string;
  authorHandle?: string;
  context?: string;
}

export interface TopicHit {
  topic: Topic;
  matches: string[];
}

export interface Analysis {
  about: string;
  postType: "QUESTION" | "PREDICTION / OPINION" | "ANNOUNCEMENT" | "RESULT / DATA" | "STATEMENT";
  hits: TopicHit[];
  relevance: Relevance;
  relevanceWhy: string;
  noConnection: boolean;
  astronomyOnly: boolean;
  connectionTypes: ConnectionType[];
  qualifiedAuthor: boolean;
  suppressProject: boolean;
  wantsQuestion: boolean;
  stance: Stance | null;
  asksForEvidence: boolean;
  asksWhatBuilt: boolean;
}

const QUALIFIED = /\b(NASA|JPL|ESA|JAXA|Caltech|MIT|professor|prof\.?|PhD|Dr\.?|postdoc|researcher|scientist|engineer|lab|university|institute|mission|rover (team|driver|planner|operator)|roboticist)\b/i;

export function analyzePost(input: ReplyInput): Analysis {
  const text = input.text ?? "";
  const hits: TopicHit[] = [];
  for (const t of TOPICS) {
    const m = [...new Set([...text.matchAll(t.re)].map((x) => x[0].trim()))];
    if (m.length) hits.push({ topic: t, matches: m });
  }
  const order = { STRONG: 0, MODERATE: 1, WEAK: 2 };
  hits.sort((a, b) => order[a.topic.strength] - order[b.topic.strength] || b.matches.length - a.matches.length);
  const astro = [...new Set([...text.matchAll(NO_CONNECTION_TOPICS)].map((x) => x[0]))];
  const best = hits[0]?.topic.strength;
  let relevance: Relevance = best ?? "NONE";
  // astronomy/launch posts that only hit generic space words have no natural connection
  if (astro.length && relevance === "WEAK") relevance = "NONE";
  const ctx = (input.context ?? "").toLowerCase();
  const suppressProject = /\b(don'?t|do not|no|without|never)\b[^.]{0,30}\b(mention|name|plug|promote|reference)\b|\bno (project|deepsift) mention\b/.test(ctx);
  const wantsQuestion = /\bquestion|\bask\b/.test(ctx);
  const qualifiedAuthor = QUALIFIED.test(`${input.authorName ?? ""} ${input.authorHandle ?? ""} ${input.context ?? ""}`) || /\bworks? on\b/.test(ctx);
  const postType: Analysis["postType"] = /\?\s*$|\?\s/.test(text) ? "QUESTION"
    : /\b(will|should|must|going to|need to|I think|I believe|future)\b/i.test(text) ? "PREDICTION / OPINION"
    : /\b(announc\w*|launch\w*|today|new|introducing|released?|we('| a)re)\b/i.test(text) ? "ANNOUNCEMENT"
    : /\d/.test(text) ? "RESULT / DATA" : "STATEMENT";
  const stance = STANCES.find((s) => s.re.test(text)) ?? null;
  // a claim that DEEPSIFT evidence speaks to directly is a genuine (moderate) connection
  if (stance && (relevance === "WEAK" || relevance === "NONE")) relevance = "MODERATE";
  const labels = hits.map((h) => h.topic.label);
  const about = !text.trim() ? "" : hits.length
    ? `${postType === "QUESTION" ? "A question" : postType === "PREDICTION / OPINION" ? "An opinion / prediction" : postType === "ANNOUNCEMENT" ? "An announcement" : postType === "RESULT / DATA" ? "A post with data" : "A statement"} about ${labels.slice(0, 3).join(", ")}${astro.length ? ` (also: ${astro.slice(0, 3).join(", ")})` : ""}. Detected terms: ${hits.flatMap((h) => h.matches).slice(0, 8).join(", ")}.`
    : astro.length ? `An astronomy / space-science post (${astro.slice(0, 4).join(", ")}), outside rover data and downlink.` : "No DEEPSIFT-related terms detected (keyword-based).";
  const relevanceWhy =
    relevance === "STRONG" ? `Directly about ${hits.filter((h) => h.topic.strength === "STRONG").map((h) => h.topic.label).slice(0, 2).join(" and ")} — something DEEPSIFT actually tested.`
    : relevance === "MODERATE" ? (stance && !hits.some((h) => h.topic.strength !== "WEAK") ? "The post makes a claim that DEEPSIFT evidence speaks to directly (see constructive disagreement)." : `Adjacent topic (${hits[0].topic.label}): a DEEPSIFT lesson may be useful, mentioned at most once.`)
    : relevance === "WEAK" ? `Only generic terms (${hits.flatMap((h) => h.matches).slice(0, 4).join(", ")}). Contribute an observation or question; don't name DEEPSIFT.`
    : astro.length ? "Astronomy / launch topic — DEEPSIFT is about rover image downlink, so there is no natural connection."
    : "No overlap with anything DEEPSIFT tested.";
  const connectionTypes = [...new Set(hits.filter((h) => h.topic.strength !== "WEAK").flatMap((h) => h.topic.types))];
  if (relevance === "WEAK") connectionTypes.push("OPEN RESEARCH QUESTION");
  return {
    about, postType, hits, relevance, relevanceWhy, noConnection: relevance === "NONE", astronomyOnly: !!astro.length && relevance === "NONE",
    connectionTypes: [...new Set(connectionTypes)], qualifiedAuthor, suppressProject, wantsQuestion, stance,
    asksForEvidence: /\b(evidence|source|data (on|for|behind)|paper|citation|show me|any (studies|results|numbers))\b/i.test(text),
    asksWhatBuilt: /\b(what (did|have) you (build|built|make|made)|link\??|repo|code\?|where can I (see|find))\b/i.test(text),
  };
}

// ─── repetition protection ─────────────────────────────────────────────────
export interface Repetition {
  angleCounts: Record<string, number>;
  factCounts: Record<string, number>;
  warnings: string[];
}

export function repetition(history: ReplyRecord[], now = new Date(), days = 21): Repetition {
  const recent = history.filter((r) => (now.getTime() - Date.parse(r.created_at)) / 86_400_000 <= days && r.facts.length);
  const angleCounts: Record<string, number> = {};
  const factCounts: Record<string, number> = {};
  for (const r of recent) {
    if (r.angle) angleCounts[r.angle] = (angleCounts[r.angle] ?? 0) + 1;
    for (const f of r.facts) factCounts[f] = (factCounts[f] ?? 0) + 1;
  }
  const warnings: string[] = [];
  if ((factCounts.held_out_bytes ?? 0) >= 2) warnings.push(`You have mentioned the 26.1% held-out result in ${factCounts.held_out_bytes} recent replies. Try a negative result, the scheduler lesson, the validation method, a limitation or a question.`);
  for (const [a, n] of Object.entries(angleCounts)) if (n >= 3 && a !== "held-out-result") warnings.push(`“${ANGLE_BY_ID[a]?.label ?? a}” used in ${n} recent replies — pick another angle.`);
  return { angleCounts, factCounts, warnings };
}

// ─── reply assembly ────────────────────────────────────────────────────────
export interface ReplyDraft {
  key: string;
  label: string;
  style: ReplyStyle;
  text: string;
  angle: string | null;
  facts: string[];
  value: Value;
  available: boolean;
  unavailableReason?: string;
}

/** Candidate angles for this post, least-recently-used first. */
export function pickAngles(a: Analysis, rep: Repetition): Angle[] {
  const ids: string[] = a.stance ? [a.stance.angle] : [];
  for (const h of a.hits) for (const id of h.topic.angles) if (!ids.includes(id)) ids.push(id);
  const penalty = (id: string) => (rep.angleCounts[id] ?? 0) * 2 + ANGLE_BY_ID[id].facts.reduce((s, f) => s + (rep.factCounts[f] ?? 0) * (f === "held_out_bytes" ? 2 : 0.5), 0);
  return ids.map((id, i) => ({ id, i, p: penalty(id) })).sort((x, y) => x.p - y.p || x.i - y.i).map((x) => ANGLE_BY_ID[x.id]);
}

export function expertQuestion(a: Analysis): string | null {
  if (a.noConnection) return null;
  if (a.stance) return a.stance.question; // the question that belongs to the point being discussed
  return a.hits.flatMap((h) => h.topic.questions)[0] ?? null;
}

const fit = (parts: string[], max = 280) => {
  let out = parts[0];
  for (const p of parts.slice(1)) if (`${out}\n\n${p}`.length <= max) out = `${out}\n\n${p}`;
  return out;
};

export function draftStyle(style: ReplyStyle, a: Analysis, angle: Angle | null): ReplyDraft {
  const q = expertQuestion(a);
  const base = { key: style, label: STYLE_LABEL[style], style, angle: angle?.id ?? null };
  const none = (reason: string): ReplyDraft => ({ ...base, text: "", facts: [], value: "NOTHING", available: false, unavailableReason: reason });
  if (a.noConnection) {
    if (style === "QUESTION" || style === "CURIOUS")
      return none("No natural DEEPSIFT connection — a genuine question needs you to engage with the specific post (or a language model). Write your own, or don't reply.");
    return none("NO NATURAL DEEPSIFT CONNECTION.");
  }
  if (!angle) return none("No verified talking point matches this topic.");
  switch (style) {
    case "SHORT":
      return { ...base, text: a.relevance === "WEAK" ? angle.plain : angle.short, facts: a.relevance === "WEAK" ? [] : angle.facts, value: a.relevance === "WEAK" ? "TECHNICAL QUESTION" : angle.value, available: true };
    case "TECHNICAL":
      if (a.relevance === "WEAK") return none("Topic too generic for a technical DEEPSIFT data point.");
      return { ...base, text: angle.technical, facts: angle.facts, value: angle.value === "PERSONAL EXPERIMENT" ? "NEW EVIDENCE" : angle.value, available: true };
    case "CURIOUS":
      return { ...base, text: fit([a.relevance === "WEAK" ? angle.plain : angle.short, q ?? ""].filter(Boolean)), facts: a.relevance === "WEAK" ? [] : angle.facts, value: "TECHNICAL QUESTION", available: true };
    case "QUESTION":
      return q ? { ...base, angle: null, text: q, facts: [], value: "TECHNICAL QUESTION", available: true } : none("No question matches this topic.");
    case "NO_PROJECT_MENTION":
      return { ...base, text: angle.plain, facts: [], value: "TECHNICAL QUESTION", available: true };
    case "DEEPSIFT_CONNECTION":
      if (a.suppressProject) return none("Your context says not to mention DEEPSIFT.");
      if (a.relevance !== "STRONG" && a.relevance !== "MODERATE") return none("DEEPSIFT is only named when relevance is STRONG or MODERATE.");
      return { ...base, text: angle.deepsift, facts: angle.facts, value: angle.value, available: true };
    case "CONSTRUCTIVE_DISAGREEMENT": {
      if (!a.stance) return none("No genuine conflict with DEEPSIFT evidence detected — disagreement would be manufactured.");
      const ev = ANGLE_BY_ID[a.stance.angle];
      const text = fit([a.stance.acknowledge, a.stance.evidence, a.stance.question]);
      return { ...base, angle: ev.id, text, facts: a.stance.facts, value: "CONSTRUCTIVE DISAGREEMENT", available: true };
    }
  }
}

/** The three primary options: A NATURAL (default), B TECHNICAL, C DEEPSIFT CONNECTION. */
export function primaryOptions(a: Analysis, angle: Angle | null): ReplyDraft[] {
  let natural: ReplyDraft;
  if (a.noConnection || !angle) natural = draftStyle("SHORT", a, null);
  else if (a.stance) natural = draftStyle("CONSTRUCTIVE_DISAGREEMENT", a, angle); // measured pushback, no project name
  else if (a.relevance === "WEAK" || a.suppressProject) natural = draftStyle("NO_PROJECT_MENTION", a, angle);
  else if (a.relevance === "MODERATE") natural = { ...draftStyle("SHORT", a, angle) };
  else natural = { key: "NATURAL", label: "", style: "SHORT", text: angle.natural, angle: angle.id, facts: angle.facts, value: angle.value, available: true };
  return [
    { ...natural, key: "NATURAL", label: "A · Natural" },
    { ...draftStyle("TECHNICAL", a, angle), key: "TECHNICAL", label: "B · Technical" },
    { ...draftStyle("DEEPSIFT_CONNECTION", a, angle), key: "DEEPSIFT", label: "C · DEEPSIFT connection" },
  ];
}

// ─── checks on a (possibly edited) reply ───────────────────────────────────
export interface ReplyIssue { rule: string; message: string; match?: string }

const OVERCLAIM: [RegExp, string][] = [
  [/\b(NASA|JPL)\b[^.\n]{0,20}\b(uses?|using|is testing|tests|adopted|evaluat\w*|runs?)\b[^.\n]{0,20}\bDEEPSIFT\b/i, "Implies NASA/JPL uses or tests DEEPSIFT."],
  [/\bDEEPSIFT\b[^.\n]{0,40}\b(improv\w*|help\w*|optimi[sz]\w*)\b[^.\n]{0,25}\b(real |actual )?(Curiosity|rover|mission) (operations?|ops|team)\b/i, "Implies DEEPSIFT improves real mission operations."],
  [/\b(rover )?position\b[^.\n]{0,25}\b(is|are)\b[^.\n]{0,12}\b(universally|always|the) (optimal|best)\b/i, "Implies rover position is universally optimal."],
  [/\bgenerali[sz]\w*\b[^.\n]{0,20}\b(to )?(all|every|any)\b[^.\n]{0,20}\b(missions?|rovers?|cameras?)\b/i, "Implies the experiment generalizes to all missions."],
  [/\b(AI|machine learning|ML|learned models?|models?)\b[^.\n]{0,20}\b(is|are|was|were|proven)\b[^.\n]{0,12}\b(useless|worthless|pointless)\b/i, "Implies AI was proven useless."],
  [/\bprocess\w*\b[^.\n]{0,15}\blive\b[^.\n]{0,15}\b(Mars )?data\b/i, "Implies DEEPSIFT processes live Mars data."],
  [/\b(check (it )?out|my project|try it|link in bio|follow me|shameless plug|sign up)\b/i, "Promotional phrasing."],
  [/\b(as a|I'?m a|I am a)\s+(NASA|JPL)\b|\bat (NASA|JPL),? (we|I)\b|\b(we|I) at (NASA|JPL)\b|\bAt DEEPSIFT,? we\b/i, "Implies an institutional role you don't have."],
];

export interface ReplyCheck {
  claim: ClaimCheck;
  issues: ReplyIssue[];
  status: "PASS" | "FAIL";
  chars: number;
  mentionsDeepsift: number;
  hasLink: boolean;
  facts: string[];
}

export function checkReply(text: string, opts: { allowLink?: boolean } = {}): ReplyCheck {
  const claim = checkPost(text);
  const issues: ReplyIssue[] = [];
  for (const m of text.matchAll(/(^|\s)#[\p{L}\d_]+/gu)) issues.push({ rule: "HASHTAG", message: "No hashtags in replies.", match: m[0].trim() });
  for (const m of text.matchAll(/(^|\s)@[A-Za-z0-9_]{1,15}/g)) issues.push({ rule: "MENTION", message: "No @mentions — the reply is already under the author's post.", match: m[0].trim() });
  const hasLink = /\bhttps?:\/\/|\b[a-z0-9-]+\.(space|com|org|io|gov|dev)\b/i.test(text);
  if (hasLink && !opts.allowLink) issues.push({ rule: "LINK", message: "Default reply has no link — use COPY + LINK only when a link materially helps." });
  for (const [re, msg] of OVERCLAIM) {
    const m = text.match(re);
    if (m) issues.push({ rule: "OVERCLAIM", message: msg, match: m[0] });
  }
  const all = [...claim.issues.map((i) => ({ rule: i.rule, message: i.message, match: i.match })), ...issues];
  const mentionsDeepsift = (text.match(/\bDEEPSIFT\b/gi) ?? []).length;
  return { claim, issues: all, status: all.length ? "FAIL" : "PASS", chars: claim.chars, mentionsDeepsift, hasLink, facts: claim.facts };
}

export function promoRisk(text: string, a: Analysis, withLink = false): { risk: PromoRisk; why: string } {
  const n = (text.match(/\bDEEPSIFT\b/gi) ?? []).length;
  const promo = /\b(check (it )?out|my project|try it|link in bio|follow me|shameless plug|sign up)\b/i.test(text);
  if (promo || n > 1 || (n >= 1 && (a.relevance === "WEAK" || a.relevance === "NONE")) || (withLink && n >= 1 && a.relevance !== "STRONG"))
    return { risk: "HIGH", why: promo ? "Promotional phrasing." : n > 1 ? "Names DEEPSIFT more than once." : withLink ? "Names DEEPSIFT and adds a link on a post that isn't squarely about it." : "Names DEEPSIFT under a post it isn't really connected to." };
  if (n === 1 || withLink) return { risk: "MEDIUM", why: withLink && n === 0 ? "Adds a link." : "DEEPSIFT is relevant and named once." };
  return { risk: "LOW", why: "Contributes without naming the project." };
}

export function linkRecommendation(a: Analysis): { link: LinkRec; why: string } {
  if (a.noConnection) return { link: "NONE", why: "No DEEPSIFT connection — no link." };
  if (a.asksWhatBuilt) return { link: "GITHUB", why: "They asked what you built or for the code." };
  if (a.asksForEvidence && a.relevance === "STRONG") return { link: "RESEARCH", why: "They asked for evidence; the research page has results and negative results." };
  if (a.postType === "QUESTION" && a.hits.some((h) => h.topic.id === "mars-imagery" || h.topic.id === "prioritization") && a.relevance === "STRONG")
    return { link: "MISSION CONTROL", why: "Their question is about which rover frames get sent — the replay answers it visually." };
  return { link: "NONE", why: "Default: no link. The reply should stand on its own." };
}

export function valueCheck(a: Analysis, draft: ReplyDraft | null): { value: Value; reply: boolean; why: string } {
  if (a.noConnection || !draft || !draft.available || !draft.text.trim())
    return { value: "NOTHING", reply: false, why: a.noConnection ? "NO NATURAL DEEPSIFT CONNECTION — nothing verified to add. Don't reply (or write something of your own)." : "Nothing verified to add." };
  if (a.relevance === "WEAK")
    return { value: "NOTHING", reply: false, why: "Only generic terms matched, so any DEEPSIFT angle would be forced. Don't reply — unless you have your own question about the post (optional drafts below are unrelated to its specifics)." };
  return { value: draft.value, reply: true, why: `Adds: ${draft.value.toLowerCase()}.` };
}

export const factLabel = (id: string) => FACT_BY_ID[id]?.short_claim ?? id;
