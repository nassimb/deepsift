/** REPLY LAB — deterministic reply assistant for other people's X posts. No model, no API.
 *
 *  Order of work (topic first, project second):
 *  1. classify the ORIGINAL post's domain (planetary geology, astrophysics, communications, autonomy…);
 *  2. decide DEEPSIFT relevance — DIRECT / ADJACENT / WEAK / NONE. Mission or agency names (Mars, NASA, JPL, rover,
 *     Curiosity, Perseverance, space, science, AI) never create a connection on their own, and a science subject
 *     DEEPSIFT has no evidence about caps relevance;
 *  3. write an INDEPENDENT reply about the post's own subject, never using DEEPSIFT and never inventing article content;
 *  4. only then consider a DEEPSIFT-related reply, and recommend it only when it materially improves the contribution.
 *  Every reply passes the claim checker + reply rules (no hashtags, @mentions, automatic links, overclaims, project
 *  insertion under unrelated posts). Limitation: this matches topics, not arguments (SEMANTIC_LIMITATION). Pure logic. */
import { checkPost, type ClaimCheck } from "./claims.ts";
import { FACT_BY_ID } from "./facts.ts";
import type { PromoRisk, Relevance, ReplyRecord } from "./store.ts";

export const SEMANTIC_LIMITATION =
  "Keyword-based, deterministic analysis: it classifies the post's subject and suggests questions or verified DEEPSIFT points, but it does not understand the author's specific argument or the article behind a headline. Read the post and edit the reply so it answers what they actually said.";

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

export type Value = "NEW EVIDENCE" | "PERSONAL EXPERIMENT" | "TECHNICAL QUESTION" | "QUESTION ABOUT THE SUBJECT" | "METHODOLOGICAL POINT" | "USEFUL LIMITATION" | "CONSTRUCTIVE DISAGREEMENT" | "NOTHING";
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
  /** False for "here's what I built" points (no finding or limitation): never recommended on ADJACENT posts. */
  finding?: boolean;
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
    id: "mission-control-replay", label: "Historical replay you can inspect", finding: false, types: ["MISSION CONTROL", "DATASET / CURIOSITY"],
    facts: ["ctx_mission_control", "example_traverse", "thumbnails_sent"], value: "PERSONAL EXPERIMENT",
    short: "I built a historical replay of archived Curiosity Navcam traverses that shows, frame by frame, which frames go down at full quality and why.",
    natural: "I've been replaying archived Curiosity Navcam traverses frame by frame. Seeing which frames go down at full quality, and which only as thumbnails, made the downlink trade-offs much easier to reason about.",
    technical: "Replaying archived Curiosity Navcam traverses frame by frame helped me: each kept frame is the position farthest from everything already kept, and every other frame still goes down as a thumbnail pair. It's a historical replay, not live data.",
    deepsift: "I built DEEPSIFT's Mission Control for exactly this: a frame-by-frame historical replay of archived Curiosity Navcam traverses showing which frames go down at full quality and why. Not live data; a replay.",
    plain: "Is there a replay or visualization of how frames are chosen on a real traverse? It makes these trade-offs much easier to reason about.",
  },
  {
    id: "reproducibility", label: "Hash-locked, checkable results", finding: false, types: ["REPRODUCIBILITY", "METHODOLOGY"],
    facts: ["integrity_manifest", "public_claims"], value: "METHODOLOGICAL POINT",
    short: "Something that helped my own work: hash-locking the result files and recomputing every public number from them by script.",
    natural: "What helped me most with reproducibility: hash-locking the 70 files behind the result, and having a script recompute every public number from them before anything is published.",
    technical: "Reproducibility setup that worked for me: 70 artifacts under an integrity manifest with an aggregate SHA-256, plus a script that recomputes all 52 public numbers from the frozen artifacts and fails on any mismatch.",
    deepsift: "In DEEPSIFT the 70 files behind the result are hash-locked, and a script recomputes all 52 public numbers from them before anything is published. It caught more mistakes than I expected.",
    plain: "Are the result files hash-locked or versioned so others can check nothing changed after the fact?",
  },
];
export const ANGLE_BY_ID: Record<string, Angle> = Object.fromEntries(ANGLES.map((a) => [a.id, a]));

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


// ─── 1. TOPIC FIRST: what is the original post about? ─────────────────────
export type Domain =
  | "PLANETARY GEOLOGY" | "ASTROBIOLOGY" | "ASTROPHYSICS" | "METEOROLOGY" | "ROCKETS / LAUNCH" | "SPACE POLICY"
  | "INSTRUMENTATION" | "ROVER ENGINEERING" | "SPACECRAFT OPERATIONS" | "COMMUNICATIONS" | "AUTONOMY" | "AI / ML" | "ROBOTICS"
  | "SCIENCE NEWS";

interface DomainDef {
  domain: Domain;
  re: RegExp;
  /** A science subject DEEPSIFT has no evidence about: caps relevance at WEAK. */
  science: boolean;
  /** Independent replies (no project): {Q} = quoted word from the post, {M} = mission/instrument named in the post. */
  natural: string;
  naturalQuoted?: string;
  curious: string[];
}

const DOMAINS: DomainDef[] = [
  { domain: "PLANETARY GEOLOGY", science: true,
    re: /\b(volcan\w*|lava|magma|basalt\w*|mineral\w*|clays?|sediment\w*|sulfates?|carbonates?|rocks?|outcrops?|crater (floor|rim|lake)|delta|river|lake ?beds?|ancient water|water (on|record|history)|geolog\w*|stratigraph\w*|erosion|hydrothermal|groundwater|ice deposits?|regolith)\b/gi,
    natural: "Interesting result. What in the {M} data points to this interpretation, and how confident are the researchers so far?",
    naturalQuoted: "The ‘{Q}’ part is what caught my attention. What evidence in the {M} data makes this different from what researchers expected?",
    curious: ["Is this from a single site or seen across several locations? That would change how I read it.", "Which observations does this rest on: rover instruments, orbital data, or both?"] },
  { domain: "ASTROBIOLOGY", science: true,
    re: /\b(life|biosignatures?|organics?|organic molecules|habitab\w*|microb\w*|biolog\w*|astrobiolog\w*|potential signs of)\b/gi,
    natural: "Interesting. How strong is the evidence so far, and what would the next measurement need to show?",
    naturalQuoted: "The ‘{Q}’ framing is interesting. What would it take to rule out a non-biological explanation here?",
    curious: ["What would it take to rule out a non-biological explanation here?", "Is this something the samples returned to Earth could confirm?"] },
  { domain: "ASTROPHYSICS", science: true,
    re: /\b(black holes?|galax\w*|exoplanets?|stars?|stellar|supernova\w*|cosmolog\w*|dark (matter|energy)|big bang|neutron stars?|gravitational waves?|nebula\w*|quasars?|astrophysic\w*|light-years?|redshift|telescopes?|JWST|Webb|Hubble)\b/gi,
    natural: "Remarkable observation. What's the key measurement that makes this stand out from earlier results?",
    naturalQuoted: "The ‘{Q}’ part stands out. What made this different from what models predicted?",
    curious: ["How sensitive is this to the modeling assumptions?", "What follow-up observation would confirm it?"] },
  { domain: "METEOROLOGY", science: true,
    re: /\b(dust (storms?|devils?)|weather|atmospher\w*|clouds?|wind|seasonal|methane|temperature|climate)\b/gi,
    natural: "Interesting. How does this compare with what earlier missions recorded in the same season?",
    curious: ["Is this a seasonal pattern or a one-off event?"] },
  { domain: "ROCKETS / LAUNCH", science: true,
    re: /\b(launch\w*|lift-?off|rockets?|boosters?|Starship|Falcon|SLS|landing burn|static fire|countdown)\b/gi,
    natural: "Congratulations to the team. What's the next milestone you're watching for?",
    curious: ["What was the biggest open question going into this one?"] },
  { domain: "SPACE POLICY", science: true,
    re: /\b(budget|funding|Congress|policy|cancel\w*|appropriation\w*|administrator|workforce|contract\w*)\b/gi,
    natural: "What would this change in practice for missions already in development?",
    curious: ["Which missions are most exposed to this?"] },
  { domain: "INSTRUMENTATION", science: false,
    re: /\b(spectrometer\w*|instruments?|sensors?|cameras?|lasers?|SuperCam|PIXL|SHERLOC|ChemCam|MOXIE|radar|detector\w*|calibrat\w*)\b/gi,
    natural: "What was the hardest part of getting the {M} instrument to deliver this?",
    curious: ["How is the instrument calibrated in the field?"] },
  { domain: "ROVER ENGINEERING", science: false,
    re: /\b(wheels?|drill\w*|robotic arm|arm|hardware|mobility|suspension|actuators?|power system|RTG|batter(y|ies)|engineering team)\b/gi,
    natural: "What was the main engineering constraint behind this?",
    curious: ["How much margin does the team keep for this kind of issue?"] },
  { domain: "SPACECRAFT OPERATIONS", science: false,
    re: /\b(operations|ops|planning|sol \d+|commands?|sequenc\w*|uplink|tactical|drive plan\w*|traverse\w*|navigat\w*)\b/gi,
    natural: "How much of this is planned on the ground versus decided onboard?",
    curious: ["What usually limits how much gets done in one planning cycle?"] },
  { domain: "COMMUNICATIONS", science: false,
    re: /\b(down[- ]?link\w*|bandwidth|relay\w*|DSN|Deep Space Network|data rates?|antenna\w*|comms?|communications?|signal delay|light[- ]time)\b/gi,
    natural: "What ends up being the binding constraint in practice: data volume, pass timing, or ground-station time?",
    curious: ["How is the data volume split between science and engineering data?"] },
  { domain: "AUTONOMY", science: false,
    re: /\b(autonom\w*|onboard decision\w*|self-driving|AEGIS|AutoNav)\b/gi,
    natural: "Which decisions would you trust onboard first, and how would you validate them before flight?",
    curious: ["How do you test an onboard decision before trusting it in flight?"] },
  { domain: "AI / ML", science: false,
    re: /\b(AI|artificial intelligence|machine learning|ML|deep learning|neural net\w*|LLMs?|models?|GPT)\b/g,
    natural: "How was it evaluated out of sample? That's usually where the story changes.",
    curious: ["What does it get wrong most often?"] },
  { domain: "ROBOTICS", science: false,
    re: /\b(robot\w*|manipulat\w*|grasp\w*|SLAM|drones?|UAVs?)\b/gi,
    natural: "How did it do on objects or conditions outside the training set?",
    curious: ["What was the main failure mode during testing?"] },
  { domain: "SCIENCE NEWS", science: true,
    re: /\b(NASA|JPL|ESA|Mars|Moon|lunar|rover|Perseverance|Curiosity|mission|spacecraft|scientists?|researchers?|study|discover\w*|finds?|reveals?|uncovers?|evidence)\b/gi,
    natural: "Interesting. What's the key evidence behind this?",
    naturalQuoted: "The ‘{Q}’ part caught my attention. What evidence makes this different from what was expected?",
    curious: ["What would the next measurement need to show to confirm it?"] },
];

const MISSION = /\b(Perseverance|Curiosity|Opportunity|Zhurong|InSight|Ingenuity|JWST|Webb|Hubble|Europa Clipper|Juno|MRO|MAVEN|Artemis|Starship|Mars 2020|SuperCam|PIXL|SHERLOC|ChemCam|MOXIE)\b/;
const QUOTED = /(?:^|\s)[‘“"']([^‘’“”"']{3,40})[’”"'](?=[\s.,!?:;)]|$)/;

// ─── 2. DEEPSIFT connection (only what DEEPSIFT actually studied) ─────────
export interface Connection {
  id: string;
  label: string;
  level: "DIRECT" | "ADJACENT";
  re: RegExp;
  angles: string[];
  questions: string[];
  types: ConnectionType[];
}

/** Mission/agency/generic words (Mars, NASA, JPL, rover, Curiosity, Perseverance, space, science, AI) never create a connection on their own. */
export const CONNECTIONS: Connection[] = [
  { id: "autonomous-science", label: "onboard autonomy / autonomous science", level: "DIRECT",
    re: /\b(autonomous science|science autonomy|onboard autonomy|on-board autonomy|more autonomy|autonomous (rovers?|spacecraft|operations?|targeting)|AEGIS|onboard decision\w*)\b/gi,
    angles: ["complexity-didnt-generalize", "validation-protocol", "laptop-only"], questions: [Q.learned, Q.triage, Q.constraint], types: ["AUTONOMY", "NEGATIVE RESULT"] },
  { id: "downlink", label: "downlink / bandwidth", level: "DIRECT",
    re: /\b(down[- ]?link\w*|bandwidth|data volume|relay (pass|passes|capacity|bandwidth)|data rates?|megabits?|mbps|kbps|limited (link|bandwidth)|data budget)\b/gi,
    angles: ["what-is-preserved", "held-out-result", "monotonic-scheduler", "complexity-didnt-generalize"], questions: [Q.constraint, Q.metric, Q.thumbnails], types: ["DOWNLINK CONSTRAINT", "RESULT"] },
  { id: "prioritization", label: "onboard data prioritization / image selection", level: "DIRECT",
    re: /\b(prioriti[sz]\w* (data|images?|downlink|what)|data prioriti[sz]\w*|triage|image selection|data selection|which (images?|data|frames?) to send|onboard (selection|summari[sz]ation|data reduction)|science data management)\b/gi,
    angles: ["complexity-didnt-generalize", "held-out-result", "what-is-preserved", "dev-only-gain"], questions: [Q.triage, Q.proxy, Q.learned], types: ["AUTONOMY", "RESULT"] },
  { id: "onboard-compute", label: "onboard / edge computation", level: "DIRECT",
    re: /\b(onboard (comput\w*|processing|inference|AI|ML)|edge (inference|computing|AI)|flight (processors?|computers?)|radiation[- ](hardened|tolerant) (processors?|computers?|chips?)|HPSC|RAD750)\b/gi,
    angles: ["laptop-only", "complexity-didnt-generalize"], questions: [Q.constraint, Q.learned], types: ["AUTONOMY", "LIMITATION"] },
  { id: "stereo", label: "stereo image handling", level: "DIRECT",
    re: /\b(stereo (pairs?|images?|imagery|cameras?)|stereoscopic|depth maps?)\b/gi,
    angles: ["stereo-constraint"], questions: [Q.metric], types: ["STEREO PRESERVATION"] },
  { id: "compression", label: "compression / telemetry constraints", level: "DIRECT",
    re: /\b(image compression|data compression|compress(ed|ing)? (images?|data)|ICER|lossy|lossless|telemetry (budget|constraints?|limits?))\b/gi,
    angles: ["what-is-preserved", "stereo-constraint", "monotonic-scheduler"], questions: [Q.metric, Q.constraint], types: ["DOWNLINK CONSTRAINT", "STEREO PRESERVATION"] },
  { id: "rover-imagery-triage", label: "rover image data (raw imagery, navigation cameras)", level: "ADJACENT",
    re: /\b(raw images?|Navcam|Hazcam|navigation cameras?|rover (images|imagery|image data)|image pipeline)\b/gi,
    angles: ["mission-control-replay", "survivorship", "stereo-constraint"], questions: [Q.thumbnails, Q.replay], types: ["DATASET / CURIOSITY", "MISSION CONTROL"] },
  { id: "rover-ops", label: "rover operations / traverse planning", level: "ADJACENT",
    re: /\b(rover (operations|ops|planners?|drivers?)|mission operations|tactical planning|sol planning|traverse planning|drive planning|ops team)\b/gi,
    angles: ["what-is-preserved", "mission-control-replay", "metric-choice"], questions: [Q.metric, Q.thumbnails, Q.replay], types: ["MISSION CONTROL", "OPEN RESEARCH QUESTION"] },
  { id: "autonomy-validation", label: "validation of autonomous systems", level: "ADJACENT",
    re: /\b(validat\w* (autonom\w*|onboard|flight|AI|models?)|verification and validation|V&V|test(ing)? autonom\w*|trust(ing)? autonom\w*|certif\w* (AI|autonom\w*))\b/gi,
    angles: ["validation-protocol", "dev-only-gain", "complexity-didnt-generalize"], questions: [Q.validation, Q.learned], types: ["VALIDATION / GENERALIZATION", "METHODOLOGY"] },
  { id: "ml-generalization", label: "scientific ML generalization", level: "ADJACENT",
    re: /\b(generali[sz]\w*|overfit\w*|out[- ]of[- ](sample|distribution)|distribution shift|held[- ]out|benchmark overfitting|pre-?regist\w*)\b/gi,
    angles: ["dev-only-gain", "quality-detector-ood", "validation-protocol"], questions: [Q.validation], types: ["VALIDATION / GENERALIZATION", "NEGATIVE RESULT"] },
  { id: "mission-data", label: "mission data pipelines / archives", level: "ADJACENT",
    re: /\b(PDS|Planetary Data System|data archive|archived data|data pipelines?|raw data release)\b/gi,
    angles: ["survivorship", "reproducibility", "mission-control-replay"], questions: [Q.archive], types: ["DATASET / CURIOSITY", "REPRODUCIBILITY"] },
];

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

// ─── 3. analysis ───────────────────────────────────────────────────────────
export interface ReplyInput {
  text: string;
  url?: string;
  authorName?: string;
  authorHandle?: string;
  context?: string;
}

export interface Hit<T> { def: T; matches: string[] }

export interface Analysis {
  domain: Domain | null;
  domainTerms: string[];
  domains: Hit<DomainDef>[];
  about: string;
  postType: "QUESTION" | "PREDICTION / OPINION" | "ANNOUNCEMENT" | "RESULT / DATA" | "STATEMENT";
  connections: Hit<Connection>[];
  relevance: Relevance;
  relevanceWhy: string;
  noConnection: boolean;
  connectionTypes: ConnectionType[];
  mission: string | null;
  quoted: string | null;
  technicalSubstance: boolean;
  qualifiedAuthor: boolean;
  suppressProject: boolean;
  wantsQuestion: boolean;
  stance: Stance | null;
  asksForEvidence: boolean;
  asksWhatBuilt: boolean;
}

const QUALIFIED = /\b(NASA|JPL|ESA|JAXA|Caltech|MIT|professor|prof\.?|PhD|Dr\.?|postdoc|researcher|scientist|engineer|lab|university|institute|rover (team|driver|planner|operator)|roboticist)\b/i;
const uniq = (xs: string[]) => [...new Set(xs.map((x) => x.trim()))];

export function analyzePost(input: ReplyInput): Analysis {
  const text = input.text ?? "";
  const domains: Hit<DomainDef>[] = DOMAINS.map((d) => ({ def: d, matches: uniq([...text.matchAll(d.re)].map((m) => m[0])) })).filter((h) => h.matches.length);
  // the generic SCIENCE NEWS bucket (Mars, NASA, rover…) only wins when nothing more specific matched
  const specific = domains.filter((h) => h.def.domain !== "SCIENCE NEWS").sort((x, y) => y.matches.length - x.matches.length || DOMAINS.indexOf(x.def) - DOMAINS.indexOf(y.def));
  const primary = specific[0] ?? domains[0] ?? null;
  const connections: Hit<Connection>[] = CONNECTIONS.map((c) => ({ def: c, matches: uniq([...text.matchAll(c.re)].map((m) => m[0])) })).filter((h) => h.matches.length);
  // DIRECT before ADJACENT, then list order (the thesis-level subjects — autonomy, prioritization — come first)
  connections.sort((x, y) => (x.def.level === y.def.level ? CONNECTIONS.indexOf(x.def) - CONNECTIONS.indexOf(y.def) : x.def.level === "DIRECT" ? -1 : 1));
  const stance = STANCES.find((s) => s.re.test(text)) ?? null;

  let relevance: Relevance = connections[0] ? connections[0].def.level : stance ? "ADJACENT" : primary ? "WEAK" : "NONE";
  // a science subject DEEPSIFT has no evidence about caps the connection: the post is about the science, not the data handling
  const connectionWeight = connections.reduce((n, h) => n + h.matches.length, 0);
  const sciencePrimary = !!primary && primary.def.science && primary.def.domain !== "SCIENCE NEWS" && primary.matches.length >= connectionWeight;
  if (sciencePrimary && relevance === "DIRECT") relevance = "ADJACENT";
  else if (sciencePrimary && relevance === "ADJACENT" && !stance) relevance = "WEAK";

  const ctx = (input.context ?? "").toLowerCase();
  const postType: Analysis["postType"] = /\?\s*$|\?\s/.test(text) ? "QUESTION"
    : /\b(will|should|must|going to|need to|I think|I believe|future)\b/i.test(text) ? "PREDICTION / OPINION"
    : /\b(announc\w*|launch\w*|today|new|introducing|released?|uncovers?|reveals?|finds?|discover\w*)\b/i.test(text) ? "ANNOUNCEMENT"
    : /\d/.test(text) ? "RESULT / DATA" : "STATEMENT";
  const domainTerms = primary?.matches ?? [];
  const about = !text.trim() ? "" : primary
    ? `${primary.def.domain} — ${postType === "QUESTION" ? "a question" : postType === "PREDICTION / OPINION" ? "an opinion / prediction" : postType === "ANNOUNCEMENT" ? "a news / announcement post" : postType === "RESULT / DATA" ? "a post with data" : "a statement"} (detected: ${uniq([...domainTerms, ...connections.flatMap((c) => c.matches)]).slice(0, 8).join(", ")}).`
    : "No space, science or engineering subject detected (keyword-based).";
  const relevanceWhy =
    relevance === "DIRECT" ? `The post is substantively about ${connections.filter((c) => c.def.level === "DIRECT").map((c) => c.def.label).slice(0, 2).join(" and ")} — something DEEPSIFT actually studied.`
    : relevance === "ADJACENT" ? (connections[0] ? `Legitimate methodological/engineering overlap (${connections[0].def.label})${sciencePrimary ? `, but the post is mainly ${primary!.def.domain.toLowerCase()}` : ""}.` : "The post makes a claim that DEEPSIFT evidence speaks to directly.")
    : relevance === "WEAK" ? `Same broad domain (${primary!.def.domain.toLowerCase()}), but DEEPSIFT adds little to this specific conversation. Mission or agency names alone are not a connection.`
    : "No meaningful connection.";
  const connectionTypes = uniq(connections.flatMap((c) => c.def.types)) as ConnectionType[];
  return {
    domain: primary?.def.domain ?? null, domainTerms, domains, about, postType, connections, relevance, relevanceWhy, noConnection: relevance === "NONE",
    connectionTypes, mission: text.match(MISSION)?.[0] ?? null, quoted: text.match(QUOTED)?.[1]?.trim() ?? null,
    technicalSubstance: /\d/.test(text) || connectionWeight >= 2 || /\b(algorithm|architecture|latency|throughput|compute|processor|protocol|validation|dataset|metric)\b/i.test(text),
    qualifiedAuthor: QUALIFIED.test(`${input.authorName ?? ""} ${input.authorHandle ?? ""} ${input.context ?? ""}`) || /\bworks? on\b/.test(ctx),
    suppressProject: /\b(don'?t|do not|no|without|never)\b[^.]{0,30}\b(mention|name|plug|promote|reference)\b|\bno (project|deepsift) mention\b/.test(ctx),
    wantsQuestion: /\bquestion|\bask\b/.test(ctx), stance,
    asksForEvidence: /\b(evidence|source|data (on|for|behind)|paper|citation|show me|any (studies|results|numbers))\b/i.test(text),
    asksWhatBuilt: /\b(what (did|have) you (build|built|make|made)|link\??|repo|code\?|where can I (see|find))\b/i.test(text),
  };
}

// ─── 4. self-promotion tracking ───────────────────────────────────────────
/** True when a reply mentions DEEPSIFT or the builder's own experiment. */
export function mentionsProject(text: string): boolean {
  return /\bDEEPSIFT\b|\bI had exactly this happen\b|\bmy own (tests?|experiments?|scheduler)\b|\bthe data I tuned\b|\bI found\b|\bI've been (experimenting|replaying|testing)\b|\bmy (project|experiments?|tests?|replay|scheduler)\b|\bI (built|tested|ran into)\b|\bI'?ve been (experimenting|replaying|testing)\b|\bin my (own )?(tests|experiments?|rover-image experiments)\b|\barchived Curiosity\b|\bNavcam\b|\bMission Control\b/i.test(text);
}

export interface Repetition {
  angleCounts: Record<string, number>;
  factCounts: Record<string, number>;
  recentMentions: number;
  recentCount: number;
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
  const last10 = [...history].sort((x, y) => y.created_at.localeCompare(x.created_at)).slice(0, 10);
  const recentMentions = last10.filter((r) => r.mentions_project ?? mentionsProject(r.reply)).length;
  const warnings: string[] = [];
  if ((factCounts.held_out_bytes ?? 0) >= 2) warnings.push(`You have mentioned the 26.1% held-out result in ${factCounts.held_out_bytes} recent replies. Try a negative result, the scheduler lesson, the validation method, a limitation or a question.`);
  for (const [a, n] of Object.entries(angleCounts)) if (n >= 3 && a !== "held-out-result") warnings.push(`“${ANGLE_BY_ID[a]?.label ?? a}” used in ${n} recent replies — pick another angle.`);
  if (last10.length >= 3 && recentMentions / last10.length > 0.3) warnings.push(`${recentMentions} of your last ${last10.length} replies mentioned DEEPSIFT (target: roughly 15–30%). Keep the next ones project-free unless the connection is direct.`);
  return { angleCounts, factCounts, recentMentions, recentCount: last10.length, warnings };
}

/** Talking points for this post, least-recently-used first (empty unless DIRECT/ADJACENT). */
export function pickAngles(a: Analysis, rep: Repetition, override = false): Angle[] {
  if (a.relevance === "NONE" || (a.relevance === "WEAK" && !override)) return [];
  const ids: string[] = a.stance ? [a.stance.angle] : [];
  for (const h of a.connections) for (const id of h.def.angles) if (!ids.includes(id)) ids.push(id);
  if (!ids.length && override) ids.push("what-is-preserved", "complexity-didnt-generalize");
  const penalty = (id: string) => (rep.angleCounts[id] ?? 0) * 2 + ANGLE_BY_ID[id].facts.reduce((s, f) => s + (rep.factCounts[f] ?? 0) * (f === "held_out_bytes" ? 2 : 0.5), 0);
  return ids.map((id, i) => ({ id, i, p: penalty(id) })).sort((x, y) => x.p - y.p || x.i - y.i).map((x) => ANGLE_BY_ID[x.id]);
}

// ─── 5. should DEEPSIFT be mentioned? ──────────────────────────────────────
export function shouldMention(a: Analysis, rep: Repetition, override = false, angle: Angle | null = null): { mention: boolean; why: string } {
  if (a.suppressProject) return { mention: false, why: "Your context says not to mention DEEPSIFT." };
  if (a.relevance === "NONE") return { mention: false, why: "No meaningful connection — never mention DEEPSIFT here." };
  if (a.relevance === "WEAK")
    return override ? { mention: true, why: "Override selected. The connection is only the broad domain, so this reads as self-promotion — use with care." }
      : { mention: false, why: `The post is about ${a.domain?.toLowerCase()}; DEEPSIFT has no evidence on that. Mars/NASA/rover words alone are not a reason to bring it up.` };
  const ratioHigh = rep.recentCount >= 3 && rep.recentMentions / rep.recentCount > 0.3;
  if (a.relevance === "ADJACENT") {
    if (ratioHigh) return { mention: false, why: `Adjacent topic, and ${rep.recentMentions} of your last ${rep.recentCount} replies already mentioned DEEPSIFT. Contribute without it this time.` };
    if (angle && angle.finding === false) return { mention: false, why: `Adjacent topic, but the matching DEEPSIFT point (“${angle.label}”) is about what you built, not a finding or limitation. Contribute without it.` };
    return { mention: true, why: "Adjacent topic where a concrete DEEPSIFT finding or limitation adds something. Mention it once, only as evidence." };
  }
  return { mention: true, why: ratioHigh ? `Direct connection — but ${rep.recentMentions} of your last ${rep.recentCount} replies mentioned DEEPSIFT; the project-free reply is still a good choice.` : "Direct connection: DEEPSIFT has evidence on exactly this subject, so it can materially improve the reply." };
}

// ─── 6. reply drafts ───────────────────────────────────────────────────────
export interface ReplyDraft {
  key: string;
  label: string;
  style: ReplyStyle;
  text: string;
  angle: string | null;
  facts: string[];
  value: Value;
  project: boolean;
  available: boolean;
  unavailableReason?: string;
}

const fit = (parts: string[], max = 280) => {
  let out = parts[0];
  for (const p of parts.slice(1)) if (`${out}\n\n${p}`.length <= max) out = `${out}\n\n${p}`;
  return out;
};

function fill(t: string, a: Analysis): string {
  return t.replace("{Q}", a.quoted ?? "").replace(/the \{M\} data/g, a.mission ? `the ${a.mission} data` : "the data").replace(/the \{M\} instrument/g, a.mission ? a.mission : "the instrument").replace("{M}", a.mission ?? "");
}

const domainDef = (a: Analysis) => DOMAINS.find((d) => d.domain === a.domain) ?? null;

/** A — independent reply: reacts to the post's own subject, never uses DEEPSIFT, never invents article content. */
export function naturalReply(a: Analysis): string | null {
  const d = domainDef(a);
  if (!d) return null;
  return fill(a.quoted && d.naturalQuoted ? d.naturalQuoted : d.natural, a);
}

/** B — a curious question about the original subject. */
export function curiousQuestion(a: Analysis): string | null {
  const d = domainDef(a);
  return d ? fill(d.curious[0], a) : null;
}

/** Expert question: exposes a real DEEPSIFT limitation (DIRECT/ADJACENT) — otherwise a question about the subject. */
export function expertQuestion(a: Analysis): string | null {
  if (a.noConnection) return null;
  if (a.stance) return a.stance.question;
  if (a.relevance === "DIRECT" || a.relevance === "ADJACENT") return a.connections.flatMap((h) => h.def.questions)[0] ?? null;
  const d = domainDef(a);
  return d ? fill(d.curious[1] ?? d.curious[0], a) : null;
}

export function draftStyle(style: ReplyStyle, a: Analysis, angle: Angle | null, override = false): ReplyDraft {
  const base = { key: style, label: STYLE_LABEL[style], style, angle: angle?.id ?? null, project: false };
  const none = (reason: string): ReplyDraft => ({ ...base, text: "", facts: [], value: "NOTHING", available: false, unavailableReason: reason });
  const projectOk = (a.relevance === "DIRECT" || a.relevance === "ADJACENT" || override) && !a.suppressProject && !!angle;
  const indep = naturalReply(a);
  if (a.noConnection) return none("NO NATURAL DEEPSIFT CONNECTION — and no recognisable subject to respond to. Don't reply, or write your own.");
  switch (style) {
    case "NO_PROJECT_MENTION":
      return indep ? { ...base, angle: null, text: indep, facts: [], value: "QUESTION ABOUT THE SUBJECT", available: true } : none("No recognisable subject.");
    case "CURIOUS": {
      const q = curiousQuestion(a);
      return q ? { ...base, angle: null, text: q, facts: [], value: "QUESTION ABOUT THE SUBJECT", available: true } : none("No recognisable subject.");
    }
    case "QUESTION": {
      const q = expertQuestion(a);
      return q ? { ...base, angle: null, text: q, facts: [], value: "TECHNICAL QUESTION", available: true } : none("No question matches this post.");
    }
    case "SHORT":
      if (projectOk && angle) return { ...base, text: angle.short, facts: angle.facts, value: angle.value, project: true, available: true };
      return indep ? { ...base, angle: null, text: indep, facts: [], value: "QUESTION ABOUT THE SUBJECT", available: true } : none("No recognisable subject.");
    case "TECHNICAL":
      if (!projectOk || !angle) return none(a.relevance === "WEAK" ? "A technical reply here would need the article's content (or a model). Don't invent details from a headline." : "Your context says not to mention DEEPSIFT.");
      if (!a.technicalSubstance) return none("Not enough technical substance in the pasted text for a technical reply.");
      return { ...base, text: angle.technical, facts: angle.facts, value: angle.value === "PERSONAL EXPERIMENT" ? "NEW EVIDENCE" : angle.value, project: true, available: true };
    case "DEEPSIFT_CONNECTION":
      if (a.suppressProject) return none("Your context says not to mention DEEPSIFT.");
      if (!projectOk || !angle) return none("DEEPSIFT is only named when relevance is DIRECT or ADJACENT (or you tick the override).");
      return { ...base, text: angle.deepsift, facts: angle.facts, value: angle.value, project: true, available: true };
    case "CONSTRUCTIVE_DISAGREEMENT": {
      if (!a.stance) return none("No genuine conflict with DEEPSIFT evidence detected — disagreement would be manufactured.");
      if (a.suppressProject) return none("Your context says not to mention DEEPSIFT (the evidence is from your experiment).");
      const text = fit([a.stance.acknowledge, a.stance.evidence, a.stance.question]);
      return { ...base, angle: a.stance.angle, text, facts: a.stance.facts, value: "CONSTRUCTIVE DISAGREEMENT", project: true, available: true };
    }
  }
}

/** A natural (no project) · B curious question · C technical · D DEEPSIFT-related (DIRECT/ADJACENT or override only). */
export function primaryOptions(a: Analysis, angle: Angle | null, override = false): ReplyDraft[] {
  const A = { ...draftStyle("NO_PROJECT_MENTION", a, null), key: "NATURAL", label: "A · Natural (no project)" };
  const B = { ...draftStyle("CURIOUS", a, null), key: "CURIOUS", label: "B · Curious question" };
  const C = { ...draftStyle("TECHNICAL", a, angle, override), key: "TECHNICAL", label: "C · Technical" };
  let D: ReplyDraft;
  const projectOk = (a.relevance === "DIRECT" || a.relevance === "ADJACENT" || override) && !a.suppressProject;
  if (!projectOk || !angle) D = { ...draftStyle("DEEPSIFT_CONNECTION", a, angle, override), key: "DEEPSIFT", label: "D · DEEPSIFT-related" };
  else if (a.stance) D = { ...draftStyle("CONSTRUCTIVE_DISAGREEMENT", a, angle), key: "DEEPSIFT", label: "D · DEEPSIFT-related" };
  else D = { key: "DEEPSIFT", label: "D · DEEPSIFT-related", style: "SHORT", text: angle.natural, angle: angle.id, facts: angle.facts, value: angle.value, project: true, available: true };
  if (!projectOk && a.relevance === "WEAK" && !a.suppressProject) D = { ...D, available: false, text: "", unavailableReason: "Not generated: relevance is WEAK. Tick the project-connection override only if you really want it." };
  return [A, B, C, D];
}

/** Recommended = the best contribution: D only when DEEPSIFT should be mentioned AND it adds evidence; otherwise A. */
export function recommend(a: Analysis, options: ReplyDraft[], mention: { mention: boolean }): ReplyDraft | null {
  const [A, B, , D] = options;
  if (a.noConnection) return null;
  if (mention.mention && D.available && D.facts.length) return D;
  if (A.available) return A;
  if (B.available) return B;
  return null;
}

// ─── 7. checks on a (possibly edited) reply ────────────────────────────────
export interface ReplyIssue { rule: string; message: string; match?: string }

const OVERCLAIM: [RegExp, string][] = [
  [/\b(NASA|JPL)\b[^.\n]{0,20}\b(uses?|using|is testing|tests|adopted|evaluat\w*|runs?)\b[^.\n]{0,20}\bDEEPSIFT\b/i, "Implies NASA/JPL uses or tests DEEPSIFT."],
  [/\bDEEPSIFT\b[^.\n]{0,40}\b(improv\w*|help\w*|optimi[sz]\w*)\b[^.\n]{0,25}\b(real |actual )?(Curiosity|rover|mission) (operations?|ops|team)\b/i, "Implies DEEPSIFT improves real mission operations."],
  [/\b(rover )?position\b[^.\n]{0,25}\b(is|are)\b[^.\n]{0,12}\b(universally|always|the) (optimal|best)\b/i, "Implies rover position is universally optimal."],
  [/\bgenerali[sz]\w*\b[^.\n]{0,20}\b(to )?(all|every|any)\b[^.\n]{0,20}\b(missions?|rovers?|cameras?)\b/i, "Implies the experiment generalizes to all missions."],
  [/\b(AI|machine learning|ML|learned models?|models?)\b[^.\n]{0,20}\b(is|are|was|were|proven)\b[^.\n]{0,12}\b(useless|worthless|pointless)\b/i, "Implies AI was proven useless."],
  [/\bprocess\w*\b[^.\n]{0,15}\blive\b[^.\n]{0,15}\b(Mars )?data\b/i, "Implies DEEPSIFT processes live Mars data."],
  [/\b(check (it )?out|my project|try it|link in bio|follow me|shameless plug|sign up|this reminds me of DEEPSIFT)\b/i, "Promotional phrasing."],
  [/\b(as a|I'?m a|I am a)\s+(NASA|JPL)\b|\bat (NASA|JPL),? (we|I)\b|\b(we|I) at (NASA|JPL)\b|\bAt DEEPSIFT,? we\b/i, "Implies an institutional role you don't have."],
  [/\b(this (proves|shows|confirms|means)|the (finding|result|study) (proves|shows|confirms)|the mineral composition suggests)\b/i, "States article content you haven't pasted — ask instead of asserting."],
];

export interface ReplyCheck {
  claim: ClaimCheck;
  issues: ReplyIssue[];
  warnings: ReplyIssue[];
  status: "PASS" | "FAIL";
  chars: number;
  project: boolean;
  hasLink: boolean;
  facts: string[];
}

export function checkReply(text: string, opts: { allowLink?: boolean; relevance?: Relevance; override?: boolean } = {}): ReplyCheck {
  const claim = checkPost(text);
  const issues: ReplyIssue[] = [];
  const warnings: ReplyIssue[] = [];
  for (const m of text.matchAll(/(^|\s)#[\p{L}\d_]+/gu)) issues.push({ rule: "HASHTAG", message: "No hashtags in replies.", match: m[0].trim() });
  for (const m of text.matchAll(/(^|\s)@[A-Za-z0-9_]{1,15}/g)) issues.push({ rule: "MENTION", message: "No @mentions — the reply is already under the author's post.", match: m[0].trim() });
  const hasLink = /\bhttps?:\/\/|\b[a-z0-9-]+\.(space|com|org|io|gov|dev)\b/i.test(text);
  if (hasLink && !opts.allowLink) issues.push({ rule: "LINK", message: "Default reply has no link — use COPY + LINK only when a link materially helps." });
  for (const [re, msg] of OVERCLAIM) {
    const m = text.match(re);
    if (m) issues.push({ rule: "OVERCLAIM", message: msg, match: m[0] });
  }
  const project = mentionsProject(text);
  if (project && (opts.relevance === "WEAK" || opts.relevance === "NONE")) {
    const it = { rule: "PROJECT_INSERTION", message: "This reply only makes sense because you built DEEPSIFT, but the post isn't about anything DEEPSIFT studied. Keep the project out of it." };
    if (opts.override && opts.relevance === "WEAK") warnings.push(it);
    else issues.push(it);
  }
  const all = [...claim.issues.map((i) => ({ rule: i.rule, message: i.message, match: i.match })), ...issues];
  return { claim, issues: all, warnings, status: all.length ? "FAIL" : "PASS", chars: claim.chars, project, hasLink, facts: claim.facts };
}

export function promoRisk(text: string, a: Analysis, withLink = false): { risk: PromoRisk; why: string } {
  const named = (text.match(/\bDEEPSIFT\b/gi) ?? []).length;
  const project = mentionsProject(text);
  const promo = /\b(check (it )?out|my project|try it|link in bio|follow me|shameless plug|sign up)\b/i.test(text);
  if (promo || named > 1 || (project && (a.relevance === "WEAK" || a.relevance === "NONE")) || (withLink && project && a.relevance !== "DIRECT"))
    return { risk: "HIGH", why: promo ? "Promotional phrasing." : named > 1 ? "Names DEEPSIFT more than once." : withLink ? "Mentions your project and adds a link on a post that isn't directly about it." : "Brings your project into a post it isn't really connected to." };
  if (project || withLink) return { risk: "MEDIUM", why: withLink && !project ? "Adds a link." : "Mentions your project/experiment once, on a relevant post." };
  return { risk: "LOW", why: "Contributes to the conversation without mentioning your project." };
}

/** WOULD THIS REPLY MAKE SENSE IF I HAD NEVER BUILT DEEPSIFT? */
export function wouldMakeSenseWithoutDeepsift(text: string): boolean {
  return !mentionsProject(text);
}

export function linkRecommendation(a: Analysis): { link: LinkRec; why: string } {
  if (a.relevance === "NONE" || a.relevance === "WEAK") return { link: "NONE", why: "Not a DEEPSIFT conversation — no link." };
  if (a.asksWhatBuilt) return { link: "GITHUB", why: "They asked what you built or for the code." };
  if (a.asksForEvidence && a.relevance === "DIRECT") return { link: "RESEARCH", why: "They asked for evidence; the research page has results and negative results." };
  if (a.postType === "QUESTION" && a.relevance === "DIRECT" && a.connections.some((h) => h.def.id === "prioritization" || h.def.id === "downlink"))
    return { link: "MISSION CONTROL", why: "Their question is about which rover frames get sent — the replay answers it visually." };
  return { link: "NONE", why: "Default: no link. The reply should stand on its own." };
}

// ─── 8. conversation-value test ────────────────────────────────────────────
export interface ValueTest {
  checks: { key: string; label: string; ok: boolean }[];
  reply: boolean;
  what: string;
}

const STOP = new Set("this that with from what about have been were their there which would could should into than then them they your youre just also more most much very some such only over under after before because while where when these those being does make made like said says".split(" "));
const words = (s: string) => new Set((s.toLowerCase().match(/[a-z][a-z'-]{3,}/g) ?? []).filter((w) => !STOP.has(w)));

export function conversationValue(a: Analysis, text: string, draft: ReplyDraft | null): ValueTest {
  const t = text.trim();
  const postWords = words([...a.domainTerms, ...a.connections.flatMap((c) => c.matches), a.quoted ?? "", a.mission ?? ""].join(" "));
  const replyWords = words(t);
  const reacts = !!t && ([...replyWords].some((w) => postWords.has(w)) || (!!a.mission && t.includes(a.mission)) || (!!a.quoted && t.toLowerCase().includes(a.quoted.toLowerCase())) || (!!draft && ["NATURAL", "CURIOUS"].includes(draft.key) && !!a.domain));
  const question = /\?/.test(t);
  const checks = [
    { key: "subject", label: "Reacts to the actual subject", ok: reacts },
    { key: "information", label: "Adds information", ok: checkPost(t).facts.length > 0 || (!!draft && draft.facts.length > 0 && draft.text === t) },
    { key: "question", label: "Asks a meaningful question", ok: question && reacts },
    { key: "clarifies", label: "Clarifies something", ok: /\b(caveat|limitation|not the same as|isn't|is not|to be clear|only)\b/i.test(t) && reacts },
    { key: "experience", label: "Contributes relevant experience", ok: mentionsProject(t) && (a.relevance === "DIRECT" || a.relevance === "ADJACENT") },
    { key: "discussion", label: "Invites useful discussion", ok: question || /\b(curious|interested|I'd like to hear|would love to hear)\b/i.test(t) },
  ];
  const reply = !a.noConnection && !!t && checks.some((c) => c.ok);
  const what = !reply ? "Nothing useful to add." : draft?.project && draft.facts.length ? `Relevant experience — ${ANGLE_BY_ID[draft.angle ?? ""]?.label ?? "DEEPSIFT evidence"}.` : question ? "A genuine question about the subject." : "An observation on the subject.";
  return { checks, reply, what };
}

export const factLabel = (id: string) => FACT_BY_ID[id]?.short_claim ?? id;
