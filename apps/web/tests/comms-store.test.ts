// Editorial workflow (pure state transitions), export/import, X intent, recommendation logic.
import assert from "node:assert/strict";
import { test } from "node:test";
import { IDEA_BY_ID, IDEAS } from "../lib/comms/library.ts";
import { planWeek, recommend, reviewWeek, weekStart } from "../lib/comms/recommend.ts";
import {
  approve, createFromIdea, editContent, emptyState, exportState, importState, markPosted, markScheduled, reject, setMetrics, setXUrl, upsert,
} from "../lib/comms/store.ts";
import { postIdFromUrl, xIntentUrl } from "../lib/comms/xintent.ts";

const NOW = new Date("2026-09-28T10:00:00");
const idea = IDEA_BY_ID["neg-embeddings"];

test("draft → approve → scheduled → posted", () => {
  let it = createFromIdea(idea, { now: NOW });
  assert.equal(it.status, "DRAFT");
  assert.ok(it.claims.includes("embedding_gain"));
  it = approve(it, NOW);
  assert.equal(it.status, "APPROVED");
  assert.throws(() => markPosted(it, { xUrl: "not a url" }), /X post URL/);
  it = markScheduled(it, "2026-09-29", "09:30", NOW);
  assert.equal(it.status, "SCHEDULED_ON_X");
  assert.equal(it.scheduled_at, "2026-09-29T09:30");
  it = markPosted(it, { xUrl: "https://x.com/nassimb/status/1840000000000000000", date: "2026-09-29", time: "09:31", notes: "went fine" }, NOW);
  assert.equal(it.status, "POSTED");
  assert.equal(it.x_url, "https://x.com/nassimb/status/1840000000000000000");
  assert.equal(it.posted_at, "2026-09-29T09:31");
  assert.equal(it.notes, "went fine");
  assert.deepEqual(it.log.map((l) => l.status), ["DRAFT", "APPROVED", "SCHEDULED_ON_X", "POSTED"]);
  assert.throws(() => editContent(it, { text: "x" }), /posted/);
  it = setMetrics(it, { views: 120, likes: 4, replies: -1 as number });
  assert.deepEqual(it.metrics, { views: 120, likes: 4 });
});

test("approval is refused when the claim check fails; editing an approved post returns it to DRAFT", () => {
  let it = createFromIdea(idea, { now: NOW });
  it = editContent(it, { text: "DEEPSIFT reduced Curiosity bandwidth by 74%." }, NOW);
  assert.throws(() => approve(it), /CLAIM CHECK FAIL/);
  it = editContent(it, { text: idea.hooks.TECHNICAL + "\n\n" + idea.body }, NOW);
  it = approve(it, NOW);
  it = editContent(it, { text: it.text + " " }, NOW);
  assert.equal(it.status, "DRAFT");
  assert.equal(it.revisions.length, 4);
});

test("mark posted: every field optional, stored as entered; URL can be added later", () => {
  let it = approve(createFromIdea(idea, { now: NOW }), NOW);
  const bare = markPosted(it, {}, NOW);
  assert.equal(bare.status, "POSTED");
  assert.equal(bare.x_url, null);
  assert.equal(bare.posted_at, NOW.toISOString());
  assert.throws(() => markPosted(it, { time: "09:00" }), /date/);
  assert.throws(() => markPosted(createFromIdea(idea, { now: NOW }), {}), /approved or scheduled/);
  it = setXUrl(bare, "https://x.com/nassimb/status/1840000000000000009", NOW);
  assert.equal(it.x_url, "https://x.com/nassimb/status/1840000000000000009");
  assert.throws(() => setXUrl(bare, "https://example.com/x"), /X post URL/);
});

test("scheduling requires approval; reject works", () => {
  const it = createFromIdea(idea, { now: NOW });
  assert.throws(() => markScheduled(it, "2026-09-29", "09:00"), /Approve/);
  assert.equal(reject(it, "not now").status, "REJECTED");
});

test("export → import round-trips; merge keeps the newer copy; junk is rejected", () => {
  const a = createFromIdea(idea, { now: NOW });
  const s = upsert(emptyState(), a);
  const json = exportState(s, NOW);
  const back = importState(json, emptyState(), "replace");
  assert.deepEqual(back.state.items, s.items);
  const newer = { ...a, notes: "newer", updated_at: "2099-01-01T00:00:00.000Z" };
  const merged = importState(exportState(upsert(emptyState(), newer)), s, "merge");
  assert.equal(merged.state.items[0].notes, "newer");
  assert.throws(() => importState("{}", s), /schema/);
  assert.throws(() => importState("nope", s), /JSON/);
  const partial = importState(JSON.stringify({ schema: "deepsift-comms", version: 1, items: [{ id: 1 }, a] }), emptyState(), "replace");
  assert.equal(partial.imported, 1);
  assert.equal(partial.skipped, 1);
});

test("X web intent: official composer URL, text prefilled, no credentials", () => {
  const u = new URL(xIntentUrl("Line 1\n\n26.1% & more #x"));
  assert.equal(u.origin + u.pathname, "https://x.com/intent/tweet");
  assert.equal(u.searchParams.get("text"), "Line 1\n\n26.1% & more #x");
  assert.deepEqual([...u.searchParams.keys()], ["text"]);
  assert.equal(new URL(xIntentUrl("reply", "1840000000000000000")).searchParams.get("in_reply_to"), "1840000000000000000");
  assert.equal(new URL(xIntentUrl("reply", "javascript:alert(1)")).searchParams.get("in_reply_to"), null);
  assert.equal(postIdFromUrl("https://x.com/nassimb/status/1840000000000000000?s=20"), "1840000000000000000");
  assert.equal(postIdFromUrl("https://evil.com/nassimb/status/1"), null);
});

test("recommendation: one primary + 3 alternatives, follows the weekday cadence", () => {
  const monday = new Date("2026-09-28T09:00:00"); // a Monday
  const r = recommend(emptyState(), monday);
  assert.ok(r.primary);
  assert.equal(r.alternatives.length, 3);
  assert.equal(r.primary!.idea.pillar, "FINAL_RESULT");
  assert.ok(r.primary!.reasons.length > 0);
  const tue = recommend(emptyState(), new Date("2026-09-29T09:00:00"));
  assert.equal(tue.primary!.idea.pillar, "NEGATIVE_RESULT");
  const fri = recommend(emptyState(), new Date("2026-10-02T09:00:00"));
  assert.equal(fri.primary!.idea.pillar, "QUESTION");
});

test("recommendation avoids recently posted categories and claims, and queued ideas", () => {
  const monday = new Date("2026-09-28T09:00:00");
  let s = emptyState();
  const first = recommend(s, monday).primary!.idea;
  let it = approve(createFromIdea(first, { now: monday }), monday);
  s = upsert(s, it);
  assert.notEqual(recommend(s, monday).primary!.idea.id, first.id, "queued idea is not recommended again");
  it = markPosted(it, { xUrl: "https://x.com/nassimb/status/1840000000000000001" }, monday);
  s = upsert(s, it);
  const second = recommend(s, monday).primary!;
  assert.notEqual(second.idea.id, first.id);
  const r2 = recommend(s, monday).ranked.find((r) => r.idea.pillar === first.pillar)!;
  assert.ok(r2.reasons.some((x) => /last 7 days/.test(x)));
});

test("research mode prefers research pillars; fan mode prefers visuals", () => {
  const sat = new Date("2026-10-03T09:00:00");
  const res = recommend(emptyState(), sat, "RESEARCH").ranked.slice(0, 5).map((r) => r.idea.pillar);
  assert.ok(!res.includes("MARS_VISUAL") || res.filter((p) => p === "MARS_VISUAL").length < 3);
  const fan = recommend(emptyState(), new Date("2026-09-30T09:00:00"), "FAN").primary!; // Wednesday
  assert.ok(["MISSION_CONTROL", "MARS_VISUAL"].includes(fan.idea.pillar));
  assert.ok(["SPACE_FAN", "GENERAL"].includes(fan.idea.audience));
});

test("weekly plan: 5 distinct ideas Mon–Fri on cadence; review flags a repeated 26.1% claim", () => {
  const monday = weekStart(new Date("2026-10-01T12:00:00"));
  const plan = planWeek(emptyState(), monday);
  assert.equal(plan.length, 5);
  assert.equal(new Set(plan.map((p) => p.idea!.id)).size, 5);
  assert.deepEqual(plan.map((p) => p.idea!.pillar).slice(0, 3), ["FINAL_RESULT", "NEGATIVE_RESULT", plan[2].idea!.pillar]);
  let s = emptyState();
  for (const [id, day] of [["result-headline", 28], ["mc-send-all-vs-position", 30]] as const) {
    const d = new Date(`2026-09-${day}T10:00:00`);
    s = upsert(s, markPosted(approve(createFromIdea(IDEA_BY_ID[id], { now: d, planned_at: `2026-09-${day}` }), d), { xUrl: `https://x.com/nassimb/status/18400000000000000${day}` }, d));
  }
  const rv = reviewWeek(s, weekStart(new Date("2026-09-30T12:00:00")));
  assert.equal(rv.completed, 2);
  assert.ok(rv.suggestions.some((x) => x.includes("26.1% result twice")), JSON.stringify(rv.suggestions));
  assert.ok(IDEAS.length - rv.unusedIdeas === 2);
});
