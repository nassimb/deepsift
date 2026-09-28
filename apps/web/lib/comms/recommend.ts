/** "What should I post today?" — transparent, deterministic scoring over the seed library and the local history.
 *  No engagement prediction, no virality model: only cadence, repetition, unused facts, audience variety and visuals.
 *  Every point added or removed comes with a plain-language reason. Pure logic. */
import { FACT_BY_ID, HEADLINE_FACT_IDS } from "./facts.ts";
import { IDEAS, PILLAR_LABEL, type ContentIdea, type Mode, type Pillar } from "./library.ts";
import type { CommsState, EditorialItem } from "./store.ts";

/** Default cadence: 5 original posts a week; weekends optional. getDay(): 0 = Sunday. */
export const CADENCE: Record<number, { pillars: Pillar[]; label: string; optional?: boolean }> = {
  1: { pillars: ["FINAL_RESULT"], label: "Result / finding" },
  2: { pillars: ["NEGATIVE_RESULT"], label: "Negative result" },
  3: { pillars: ["MISSION_CONTROL", "MARS_VISUAL"], label: "Mission Control visual / demo" },
  4: { pillars: ["ENGINEERING", "METHODOLOGY", "REPRODUCIBILITY", "BUILD_STORY"], label: "Engineering or methodology lesson" },
  5: { pillars: ["QUESTION"], label: "Technical question to researchers" },
  6: { pillars: ["MARS_VISUAL", "BUILD_STORY"], label: "Optional: visual / recap / no post", optional: true },
  0: { pillars: ["MARS_VISUAL", "BUILD_STORY"], label: "Optional: visual / recap / no post", optional: true },
};

const RESEARCH_PILLARS: Pillar[] = ["NEGATIVE_RESULT", "METHODOLOGY", "REPRODUCIBILITY", "ENGINEERING", "QUESTION"];
const FAN_PILLARS: Pillar[] = ["MISSION_CONTROL", "MARS_VISUAL", "FINAL_RESULT"];

export interface Recommendation {
  idea: ContentIdea;
  score: number;
  reasons: string[];
}

export const ymd = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const daysAgo = (iso: string | null, today: Date) => (iso ? (today.getTime() - new Date(iso).getTime()) / 86_400_000 : Infinity);
const when = (it: EditorialItem) => it.posted_at ?? (it.scheduled_at ? `${it.scheduled_at}:00` : null);
/** Posts that are out (posted) or committed (scheduled on X). */
const outgoing = (s: CommsState) => s.items.filter((i) => i.status === "POSTED" || i.status === "SCHEDULED_ON_X");

function hash(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return (h >>> 0) / 2 ** 32;
}

export function scoreIdea(idea: ContentIdea, state: CommsState, today: Date, mode: Mode, dayOverride?: number): Recommendation | null {
  const reasons: string[] = [];
  let score = 0;
  const day = dayOverride ?? today.getDay();
  const cad = CADENCE[day];

  const mine = state.items.filter((i) => i.idea_id === idea.id);
  if (mine.some((i) => ["IDEA", "DRAFT", "APPROVED", "SCHEDULED_ON_X"].includes(i.status))) return null; // already in the queue
  if (mine.some((i) => i.status === "POSTED")) { score -= 20; reasons.push("Already posted — only if you want a follow-up."); }
  if (mine.some((i) => i.status === "REJECTED")) { score -= 6; reasons.push("You rejected this idea before."); }

  const ci = cad.pillars.indexOf(idea.pillar);
  if (ci === 0) { score += 4; reasons.push(`Fits ${["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"][day]}'s slot: ${cad.label}.`); }
  else if (ci > 0) { score += 3; reasons.push(`Fits today's slot: ${cad.label}.`); }

  if (mode === "RESEARCH") {
    if (RESEARCH_PILLARS.includes(idea.pillar)) { score += 2; reasons.push("Technical / research mode prefers this category."); }
    if (idea.pillar === "MARS_VISUAL") score -= 2;
    if (["SCIENTIST", "SPACECRAFT_ENGINEER", "ROBOTICS_AUTONOMY"].includes(idea.audience)) score += 1;
  } else if (mode === "FAN") {
    if (FAN_PILLARS.includes(idea.pillar)) { score += 2; reasons.push("Space-fan mode prefers visuals and Mission Control."); }
    if (["SPACE_FAN", "GENERAL"].includes(idea.audience)) score += 2;
    if (idea.audience === "SCIENTIST") score -= 1;
  }

  const out = outgoing(state);
  const recent7 = out.filter((i) => daysAgo(when(i), today) <= 7);
  const samePillar = recent7.filter((i) => i.pillar === idea.pillar).length;
  if (samePillar) { score -= 3 * samePillar; reasons.push(`${samePillar} ${PILLAR_LABEL[idea.pillar].toLowerCase()} post(s) in the last 7 days.`); }

  const recent14 = out.filter((i) => daysAgo(when(i), today) <= 14);
  const recentClaims = new Set(recent14.flatMap((i) => i.claims));
  const repeated = idea.facts.filter((f) => recentClaims.has(f));
  if (repeated.length) {
    const heavy = repeated.filter((f) => HEADLINE_FACT_IDS.includes(f)).length;
    score -= 1.5 * repeated.length + 1.5 * heavy;
    reasons.push(`Repeats ${repeated.length} claim(s) used in the last 14 days (${repeated.map((f) => FACT_BY_ID[f]?.exact_value ?? f).slice(0, 2).join("; ")}).`);
  }
  const everUsed = new Set(state.items.filter((i) => i.status === "POSTED").flatMap((i) => i.claims));
  const fresh = idea.facts.filter((f) => !everUsed.has(f)).length;
  if (fresh) { score += 0.5 * Math.min(fresh, 4); reasons.push(`Uses ${fresh} verified fact(s) you haven't posted yet.`); }

  const lastAud = out.slice().sort((a, b) => String(when(b)).localeCompare(String(when(a)))).slice(0, 3).map((i) => i.audience);
  if (!lastAud.includes(idea.audience)) { score += 1; reasons.push("Different audience from your last 3 posts."); }

  if (idea.visual) { score += 1; reasons.push("Has an existing visual."); } else { score -= 1; reasons.push("No visual — text-only."); }

  score += hash(`${ymd(today)}|${idea.id}`) * 0.5; // deterministic daily rotation between equal ideas
  return { idea, score: Math.round(score * 100) / 100, reasons };
}

export function recommend(state: CommsState, today: Date, mode: Mode = "ALL", dayOverride?: number): { primary: Recommendation | null; alternatives: Recommendation[]; ranked: Recommendation[] } {
  const ranked = IDEAS.map((i) => scoreIdea(i, state, today, mode, dayOverride)).filter((r): r is Recommendation => !!r).sort((a, b) => b.score - a.score);
  const primary = ranked[0] ?? null;
  // alternatives: best of other categories first, for variety
  const alts: Recommendation[] = [];
  const pillars = new Set(primary ? [primary.idea.pillar] : []);
  for (const r of ranked.slice(1)) if (!pillars.has(r.idea.pillar) && alts.length < 3) { alts.push(r); pillars.add(r.idea.pillar); }
  for (const r of ranked.slice(1)) if (alts.length < 3 && !alts.includes(r)) alts.push(r);
  return { primary, alternatives: alts, ranked };
}

/** Monday of the week containing d (local time). */
export function weekStart(d: Date): Date {
  const x = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  x.setDate(x.getDate() - ((x.getDay() + 6) % 7));
  return x;
}

/** Suggested ideas for Mon–Fri of a week, following the cadence and never repeating an idea. */
export function planWeek(state: CommsState, monday: Date, mode: Mode = "ALL"): { date: string; day: number; idea: ContentIdea | null }[] {
  const chosen = new Set<string>();
  const out: { date: string; day: number; idea: ContentIdea | null }[] = [];
  for (let k = 0; k < 5; k++) {
    const d = new Date(monday.getFullYear(), monday.getMonth(), monday.getDate() + k);
    const ranked = recommend(state, d, mode).ranked.filter((r) => !chosen.has(r.idea.id) && CADENCE[d.getDay()].pillars.includes(r.idea.pillar));
    const pick = ranked[0]?.idea ?? null;
    if (pick) chosen.add(pick.id);
    out.push({ date: ymd(d), day: d.getDay(), idea: pick });
  }
  return out;
}

// ─── weekly review & performance (observations only — nothing is optimized from them) ─────
export interface WeekReview {
  planned: number;
  completed: number;
  scheduled: number;
  pillars: Record<string, number>;
  audiences: Record<string, number>;
  repeatedClaims: { fact: string; count: number }[];
  unusedIdeas: number;
  suggestions: string[];
}

export function reviewWeek(state: CommsState, monday: Date): WeekReview {
  const start = ymd(monday);
  const end = ymd(new Date(monday.getFullYear(), monday.getMonth(), monday.getDate() + 7));
  const inWeek = (d: string | null) => !!d && d.slice(0, 10) >= start && d.slice(0, 10) < end;
  const items = state.items.filter((i) => i.status !== "REJECTED" && (inWeek(i.planned_at) || inWeek(i.scheduled_at) || inWeek(i.posted_at)));
  const done = items.filter((i) => i.status === "POSTED");
  const pillars: Record<string, number> = {};
  const audiences: Record<string, number> = {};
  const claimCount: Record<string, number> = {};
  for (const i of items) {
    pillars[i.pillar] = (pillars[i.pillar] ?? 0) + 1;
    audiences[i.audience] = (audiences[i.audience] ?? 0) + 1;
  }
  for (const i of items.filter((x) => x.status === "POSTED" || x.status === "SCHEDULED_ON_X")) for (const c of i.claims) claimCount[c] = (claimCount[c] ?? 0) + 1;
  const repeatedClaims = Object.entries(claimCount).filter(([, n]) => n > 1).map(([fact, count]) => ({ fact, count })).sort((a, b) => b.count - a.count);
  const usedIdeas = new Set(state.items.map((i) => i.idea_id));
  const unusedIdeas = IDEAS.filter((i) => !usedIdeas.has(i.id)).length;

  const suggestions: string[] = [];
  const bytes = claimCount["held_out_bytes"] ?? 0;
  if (bytes >= 2) suggestions.push(`You have posted the final 26.1% result ${bytes === 2 ? "twice" : `${bytes} times`} this week. Use an engineering failure story next.`);
  for (const r of repeatedClaims.filter((r) => r.fact !== "held_out_bytes").slice(0, 2)) suggestions.push(`“${FACT_BY_ID[r.fact]?.short_claim ?? r.fact}” appears in ${r.count} posts this week — pick a different fact next.`);
  const missing = (["NEGATIVE_RESULT", "QUESTION", "MISSION_CONTROL"] as Pillar[]).filter((p) => !pillars[p]);
  if (missing.length) suggestions.push(`No ${missing.map((p) => PILLAR_LABEL[p].toLowerCase()).join(" / ")} post this week yet.`);
  if (Object.keys(audiences).length === 1 && items.length >= 3) suggestions.push("Every post this week targets the same audience — vary it.");
  if (!items.length) suggestions.push("Nothing planned this week — use PLAN THIS WEEK on the calendar.");
  return { planned: items.length, completed: done.length, scheduled: items.filter((i) => i.status === "SCHEDULED_ON_X").length, pillars, audiences, repeatedClaims, unusedIdeas, suggestions };
}

export interface PillarPerformance {
  pillar: Pillar;
  posts: number;
  withMetrics: number;
  views: number;
  likes: number;
  replies: number;
  reposts: number;
  qualified: number;
}

export function performanceByPillar(state: CommsState): PillarPerformance[] {
  const out = new Map<Pillar, PillarPerformance>();
  for (const i of state.items.filter((x) => x.status === "POSTED")) {
    const p = out.get(i.pillar) ?? { pillar: i.pillar, posts: 0, withMetrics: 0, views: 0, likes: 0, replies: 0, reposts: 0, qualified: 0 };
    p.posts++;
    if (Object.keys(i.metrics).length) p.withMetrics++;
    p.views += i.metrics.views ?? 0;
    p.likes += i.metrics.likes ?? 0;
    p.replies += i.metrics.replies ?? 0;
    p.reposts += i.metrics.reposts ?? 0;
    p.qualified += i.qualified_replies.length;
    out.set(i.pillar, p);
  }
  return [...out.values()].sort((a, b) => b.qualified - a.qualified || b.posts - a.posts);
}
