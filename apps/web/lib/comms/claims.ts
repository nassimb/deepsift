/** Claim checker — deterministic rules, no model. A post can only be APPROVED when this returns PASS.
 *  Checks: every number is licensed by a VERIFIED_FACT; headline numbers carry scope + archived-data context; and no wording
 *  implies NASA/JPL endorsement, flight readiness, deployment, live data, preserved scientific value, onboard-stream
 *  reconstruction, discovery, AI superiority, mission gains beyond the replay, or hype. Negated mentions ("not NASA-reviewed")
 *  are allowed. Pure logic (tests/comms-claims.test.ts). */
import { FACT_BY_ID, HEADLINE_FACT_IDS, VERIFIED_FACTS } from "./facts.ts";

export type Rule =
  | "NUMBER"
  | "SCOPE"
  | "CAUSAL"
  | "AFFILIATION"
  | "FLIGHT_READINESS"
  | "SCIENTIFIC_VALUE"
  | "LIVE_DATA"
  | "RECONSTRUCTION"
  | "DISCOVERY"
  | "AI_SUPERIORITY"
  | "MISSION_GAIN"
  | "HYPE"
  | "FORBIDDEN_WORDING"
  | "LENGTH";

export interface ClaimIssue {
  rule: Rule;
  message: string;
  match?: string;
}

export interface ClaimCheck {
  status: "PASS" | "FAIL";
  issues: ClaimIssue[];
  /** Facts whose numbers or wording appear in the text (shown as SOURCES). */
  facts: string[];
  chars: number;
}

export const X_LIMIT = 280;
const URL_WEIGHT = 23; // X counts every link as 23 characters (t.co)
const URL_RE = /\bhttps?:\/\/\S+|\b(?:[a-z0-9-]+\.)+(?:space|com|org|gov|io|dev|net)(?:\/[^\s)]*)?/gi;

/** Character count as X weighs it: links count 23; everything else by code point. */
export function xLength(text: string): number {
  let n = 0;
  const rest = text.replace(URL_RE, () => {
    n += URL_WEIGHT;
    return "";
  });
  return n + [...rest].length;
}

// ─── numbers ──────────────────────────────────────────────────────────────
type Tok = { key: string; raw: string };
const NUM_RE = /(?<![\w./:])([+\-−]?)(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(?:\s*(%|×|x\b|m\b|metres\b|meters\b|seconds\b|s\b)|\/(\d+))?/g;

function tokens(text: string): Tok[] {
  const out: Tok[] = [];
  const clean = text
    .replace(URL_RE, " ")
    .replace(/\b\d{1,2}:\d{2}(?::\d{2})?\b/g, (m) => ` T${m.replace(/:/g, "")} `) // clock times
    .replace(/\b(\d{3,4})[–-](\d{3,4})\b/g, "$1 $2"); // sol ranges
  for (const m of clean.matchAll(NUM_RE)) {
    const [raw, sign, num, unit, denom] = m;
    const v = num.replace(/,/g, "");
    let u = unit ? unit.toLowerCase() : "";
    if (u === "metres" || u === "meters") u = "m";
    if (u === "x") u = "×";
    if (u === "seconds") u = "s";
    const key = denom ? `${v}/${denom}` : `${sign === "−" ? "-" : sign}${v}${u ? "|" + u : ""}`;
    out.push({ key, raw: raw.trim() });
  }
  for (const m of clean.matchAll(/\bT(\d{4,6})\b/g)) out.push({ key: `T${m[1]}`, raw: m[1] });
  return out;
}

const keyOf = (s: string) => tokens(s).map((t) => t.key);
const unsigned = (k: string) => k.replace(/^[+-]/, "");

/** Number tokens licensed by each fact. */
export const FACT_NUMBERS: Record<string, string[]> = Object.fromEntries(VERIFIED_FACTS.map((f) => [f.id, f.numbers.flatMap(keyOf)]));
const ALLOWED = new Set(Object.values(FACT_NUMBERS).flat().flatMap((k) => [k, unsigned(k)]));
// Context numbers that are not results: retention fractions, the 5 m radius, small counts written as digits.
["1/2", "1/4", "1/8", "5|m", "10|m"].forEach((k) => ALLOWED.add(k));
for (let i = 0; i <= 10; i++) ALLOWED.add(String(i));

// ─── wording rules ────────────────────────────────────────────────────────
const NEG = /\b(not|no|never|nor|without|isn['’]t|aren['’]t|wasn['’]t|doesn['’]t|don['’]t|didn['’]t|neither|nothing|none)\b|≠/i;

/** True when the match sits in a clause that negates it ("not reviewed or validated by NASA"). */
function negated(text: string, index: number): boolean {
  const start = Math.max(text.lastIndexOf(".", index), text.lastIndexOf("\n", index), text.lastIndexOf("!", index), text.lastIndexOf("?", index), text.lastIndexOf(";", index));
  const clause = text.slice(start + 1, index);
  return NEG.test(clause.slice(-70));
}

type Pattern = { rule: Rule; re: RegExp; message: string; negatable: boolean };
const P = (rule: Rule, re: RegExp, message: string, negatable = true): Pattern => ({ rule, re, message, negatable });

const PATTERNS: Pattern[] = [
  // NASA / JPL affiliation
  P("AFFILIATION", /\b(NASA|JPL)[- ]?(approved|endorsed|validated|backed|certified|grade|reviewed|funded|sponsored|verified)\b/gi, "Implies NASA/JPL endorsement or validation."),
  P("AFFILIATION", /\b(approved|endorsed|validated|reviewed|used|adopted|funded|backed|sponsored|certified|recognized|verified)\s+by\s+(NASA|JPL|the MSL (mission )?team)\b/gi, "Implies NASA/JPL endorsement, use or validation."),
  P("AFFILIATION", /\b(partner(ship|ed)?|working|collaborat\w*)\s+with\s+(NASA|JPL)\b/gi, "Implies a NASA/JPL affiliation."),
  P("AFFILIATION", /\b(built|made|designed|developed)\s+for\s+(NASA|JPL)\b/gi, "Implies DEEPSIFT was made for NASA/JPL."),
  P("AFFILIATION", /\b(NASA|JPL)\s+(uses|is using|adopted|needs|should|could use|will use|approved|endorses|validated)\b/gi, "Speaks for NASA/JPL."),
  // flight readiness / deployment
  P("FLIGHT_READINESS", /\bflight[- ](ready|proven|qualified|tested|software ready)\b|\bready for flight\b|\bmission[- ]ready\b|\bproduction[- ]ready\b|\bspace[- ]ready\b/gi, "Implies flight readiness."),
  P("FLIGHT_READINESS", /\b(deployed|deployment|runs|running|operational|in operation|installed|flying)\b[^.\n]{0,30}\b(onboard|on board|on Curiosity|on the rover|on Mars|in flight)\b/gi, "Implies operational deployment."),
  P("FLIGHT_READINESS", /\b(onboard|on board|on Curiosity|on the rover)\b[^.\n]{0,20}\b(today|now|already)\b/gi, "Implies operational deployment."),
  // live data / live control
  P("LIVE_DATA", /\blive\s+(feed|data|rover|stream|telemetry|images?|imagery|view|from Mars|NASA|mission)\b|\breal[- ]time\b|\bstreaming from Mars\b/gi, "Implies live data — Mission Control is a historical replay."),
  P("LIVE_DATA", /\b(controls?|controlling|drive|driving|command(s|ing)?)\s+(the\s+)?(Curiosity|rover)\b/gi, "Implies live rover control."),
  // scientific value
  P("SCIENTIFIC_VALUE", /\b(preserv\w*|keeps?|kept|retain\w*|protect\w*|maintain\w*)\b[^.\n]{0,30}\bscien(ce|tific)\b[^.\n]{0,12}\b(value|content|information|return)?/gi, "Claims preserved scientific value — geometric coverage is not scientific value."),
  P("SCIENTIFIC_VALUE", /\bno (science|scientific \w+) (was |is )?lost\b|\bwithout losing (any )?science\b|\bnothing (important|of value) (was |is )?lost\b/gi, "Claims no science was lost.", false),
  P("SCIENTIFIC_VALUE", /\bscien(ce|tific)[- ](value|return|content)\b/gi, "Mentions scientific value without negation — only say what the metric is NOT."),
  // reconstruction
  P("RECONSTRUCTION", /\breconstruct\w*\b/gi, "Implies onboard-stream reconstruction."),
  P("RECONSTRUCTION", /\b(every|all (the )?)(image|photo|picture|frame)s? (Curiosity|the rover) (took|captured|acquired)\b/gi, "Implies access to the full onboard stream."),
  // discovery
  P("DISCOVERY", /\bdiscover(y|ies|ed)\b|\bnew (science|finding|result) about Mars\b|\bscientific breakthrough\b/gi, "Implies a scientific discovery."),
  // AI superiority
  P("AI_SUPERIORITY", /\b(AI|model|algorithm|DEEPSIFT)\s+(beats|outperforms|outperformed|is better than|replaces?|surpass\w*)\s+(humans?|operators?|scientists?|engineers?|NASA|JPL|the team)\b/gi, "Implies AI superiority over people."),
  P("AI_SUPERIORITY", /\bsmarter than\b|\bsuperhuman\b|\bbetter than (NASA|JPL|humans?|operators?)\b/gi, "Implies AI superiority.", false),
  // mission gains beyond the replay / causal wording
  P("MISSION_GAIN", /\b(NASA|JPL|Curiosity|the rover|rovers?|missions?|Mars missions?)\s+(could|would|will|can|might)\s+(save|send|downlink|return|get|cut|reduce|free up)\b/gi, "Projects mission gains beyond the tested replay."),
  P("MISSION_GAIN", /\b(sav\w*|cut\w*|reduc\w*|slash\w*|free\w* up)\b[^.\n]{0,25}\b(bandwidth|downlink|data volume)\b/gi, "Frames the replay result as a bandwidth saving. Say what fraction of the SEND ALL baseline was used, on the held-out test."),
  P("MISSION_GAIN", /\b\d+(\.\d+)?\s?%\s+(less|fewer|lower|smaller|saving|savings|reduction|cheaper)\b/gi, "Frames the result as a reduction percentage."),
  P("CAUSAL", /\b(proves?|proven|guarantees?|guaranteed|always works|will work)\b/gi, "Over-strong causal/certainty wording — say what happened on this test."),
  P("CAUSAL", /\b(solv(e|es|ed|ing))\b[^.\n]{0,25}\b(bandwidth|downlink|Mars|problem)\b/gi, "Claims the problem is solved."),
  // hype
  P("HYPE", /\b(revolutionary|revolutioni[sz]\w*|game[- ]chang\w*|breakthrough|unprecedented|world[- ]first|first[- ]ever|mind[- ]blowing|insane|you won['’]t believe|NASA[- ]grade|cutting[- ]edge|disrupt\w*)\b/gi, "Hype wording.", false),
];

const HEADLINE_KEYS = new Set(HEADLINE_FACT_IDS.flatMap((id) => FACT_NUMBERS[id]).filter((k) => !["0", "5|m", "10|m", "1.000"].includes(k)));
HEADLINE_KEYS.add("100|%");

/** Check one post (one X post; for a thread, call per post). */
export function checkPost(text: string, opts: { maxChars?: number } = {}): ClaimCheck {
  const issues: ClaimIssue[] = [];
  const toks = tokens(text);

  for (const t of toks) {
    if (!ALLOWED.has(t.key) && !ALLOWED.has(unsigned(t.key))) issues.push({ rule: "NUMBER", message: `Number "${t.raw}" is not in VERIFIED_FACTS.`, match: t.raw });
  }

  const headline = toks.filter((t) => HEADLINE_KEYS.has(t.key));
  if (headline.length) {
    if (!/held[- ]out|\btest\b/i.test(text)) issues.push({ rule: "SCOPE", message: `Headline number "${headline[0].raw}" needs its scope: say it is the held-out test.`, match: headline[0].raw });
    if (!/Curiosity|Navcam/i.test(text)) issues.push({ rule: "SCOPE", message: `Headline number "${headline[0].raw}" needs its scope: Curiosity Navcam.`, match: headline[0].raw });
    if (!/archiv|retrospective|replay|\bPDS\b|already[- ]downlinked|already sent/i.test(text))
      issues.push({ rule: "SCOPE", message: "Headline result without archived/retrospective context (PDS survivorship caveat): add “archived”, “replay” or “retrospective”.", match: headline[0].raw });
  }
  for (const m of text.matchAll(/26\.1\s?%/g)) {
    const after = text.slice(m.index!, m.index! + 70);
    if (!/full[- ]quality|SEND ALL|bytes|baseline/i.test(after))
      issues.push({ rule: "SCOPE", message: "“26.1%” must name its baseline (of the SEND ALL / full-quality traverse bytes).", match: m[0] });
  }

  for (const p of PATTERNS) {
    for (const m of text.matchAll(p.re)) {
      if (p.negatable && negated(text, m.index!)) continue;
      issues.push({ rule: p.rule, message: p.message, match: m[0].trim() });
    }
  }

  const lower = text.toLowerCase();
  for (const f of VERIFIED_FACTS)
    for (const w of f.forbidden_wording) {
      const i = lower.indexOf(w.toLowerCase());
      if (i >= 0 && !negated(text, i)) issues.push({ rule: "FORBIDDEN_WORDING", message: `Forbidden wording for ${f.id}.`, match: w });
    }

  const chars = xLength(text);
  const max = opts.maxChars ?? X_LIMIT;
  if (chars > max) issues.push({ rule: "LENGTH", message: `${chars} characters — over the ${max}-character X limit.` });
  if (!text.trim()) issues.push({ rule: "LENGTH", message: "Empty post." });

  // de-duplicate identical rule+match pairs
  const seen = new Set<string>();
  const uniq = issues.filter((i) => {
    const k = `${i.rule}|${i.match ?? ""}|${i.message}`;
    return seen.has(k) ? false : (seen.add(k), true);
  });
  return { status: uniq.length ? "FAIL" : "PASS", issues: uniq, facts: factsIn(text), chars };
}

/** Facts whose distinctive numbers appear in the text. */
export function factsIn(text: string): string[] {
  const keys = new Set(tokens(text).map((t) => t.key));
  const generic = new Set(["0", "1", "5|m", "10|m", "1/4", "1/2", "1/8", "1.000", "100|%"]);
  return VERIFIED_FACTS.filter((f) => FACT_NUMBERS[f.id].some((k) => keys.has(k) && !generic.has(k)) || (f.id === "held_out_coverage" && keys.has("100|%")))
    .map((f) => f.id);
}

/** Check a thread: every post independently. */
export function checkThread(posts: string[]): { status: "PASS" | "FAIL"; posts: ClaimCheck[] } {
  const res = posts.map((p) => checkPost(p));
  return { status: res.every((r) => r.status === "PASS") && posts.length > 0 ? "PASS" : "FAIL", posts: res };
}

export { FACT_BY_ID };
