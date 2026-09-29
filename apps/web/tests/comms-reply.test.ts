// Reply Lab: relevance, no forced project mentions, no links/hashtags/mentions, claim checker, value check, repetition.
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  ANGLES, REPLY_STYLES, STANCES, TOPICS, analyzePost, checkReply, draftStyle, expertQuestion, linkRecommendation, pickAngles,
  primaryOptions, promoRisk, repetition, valueCheck, type Analysis,
} from "../lib/comms/reply.ts";
import { FACT_BY_ID } from "../lib/comms/facts.ts";
import type { ReplyRecord } from "../lib/comms/store.ts";

const run = (text: string, extra: { context?: string; authorName?: string } = {}) => {
  const a = analyzePost({ text, ...extra });
  const angle = pickAngles(a, repetition([]))[0] ?? null;
  const opts = primaryOptions(a, angle);
  return { a, angle, opts, value: valueCheck(a, opts[0]) };
};

const SCENARIOS: [string, string, string[]][] = [
  ["Mars rover bandwidth", "Bandwidth remains one of the hardest constraints for Mars rover missions. Relay passes limit how much imagery comes home each sol.", ["STRONG"]],
  ["autonomous science", "Onboard autonomy becomes essential as spacecraft operate farther from Earth.", ["STRONG"]],
  ["robotics", "Our new robot arm learned to grasp unseen objects after only 200 demonstrations.", ["MODERATE"]],
  ["AI validation", "Most ML papers never test on out-of-distribution data. Generalization claims should require held-out evaluation.", ["MODERATE"]],
  ["Curiosity imagery", "New raw images from Curiosity's Navcam show the rover climbing toward Mount Sharp.", ["STRONG"]],
  ["spacecraft communications", "The Deep Space Network is oversubscribed; data rates from Mars relay orbiters are a real bottleneck.", ["STRONG"]],
  ["astrophysics", "JWST just imaged a galaxy cluster 10 billion light-years away, revealing new dark matter structure.", ["NONE"]],
  ["science journalism", "NASA announced today a new mission to study Mars' atmosphere.", ["WEAK"]],
  ["unrelated", "Best sourdough recipe I've tried: 75% hydration, 18 hour cold proof.", ["NONE"]],
];

for (const [name, text, rel] of SCENARIOS) {
  test(`scenario: ${name} → ${rel.join("/")}`, () => {
    const { a, opts } = run(text);
    assert.ok(rel.includes(a.relevance), `${name}: ${a.relevance}`);
    for (const o of opts.filter((o) => o.available)) {
      const c = checkReply(o.text);
      assert.equal(c.status, "PASS", `${name}/${o.key}: ${JSON.stringify(c.issues)}`);
      assert.ok(!c.hasLink, "no automatic link");
      assert.ok(!/#\w/.test(o.text) && !/(^|\s)@\w/.test(o.text), "no hashtags / mentions");
    }
    const natural = opts[0];
    assert.ok(!/DEEPSIFT/i.test(natural.text), "NATURAL (default) never names DEEPSIFT");
  });
}

test("unrelated and astrophysics posts: NO NATURAL DEEPSIFT CONNECTION + DON'T REPLY, nothing generated", () => {
  for (const text of [SCENARIOS[6][1], SCENARIOS[8][1]]) {
    const { a, opts, value } = run(text);
    assert.equal(a.relevance, "NONE");
    assert.ok(a.noConnection);
    assert.equal(value.value, "NOTHING");
    assert.equal(value.reply, false);
    assert.ok(opts.every((o) => !o.available && o.text === ""), "no forced reply");
    assert.ok(opts.some((o) => o.unavailableReason?.includes("NO NATURAL DEEPSIFT CONNECTION")));
    assert.equal(expertQuestion(a), null);
    assert.equal(linkRecommendation(a).link, "NONE");
  }
});

test("generic space journalism (WEAK): DEEPSIFT never named, default is DON'T REPLY", () => {
  const { a, opts, value } = run(SCENARIOS[7][1]);
  assert.equal(a.relevance, "WEAK");
  assert.equal(value.reply, false);
  assert.equal(opts[2].available, false);
  for (const s of REPLY_STYLES) {
    const d = draftStyle(s, a, pickAngles(a, repetition([]))[0]);
    if (d.available) assert.ok(!/DEEPSIFT/i.test(d.text), s);
  }
});

test("'AI will transform Mars exploration' → measured pushback, not 'DEEPSIFT proves this'", () => {
  const { a, opts } = run("AI will transform Mars exploration within a decade.");
  assert.equal(a.stance?.id, "ai-will-transform");
  assert.match(opts[0].text, /more cautious/);
  assert.match(opts[0].text, /\?$/);
  assert.ok(!/prove/i.test(opts[0].text));
  assert.equal(checkReply(opts[0].text).status, "PASS");
  assert.equal(expertQuestion(a), a.stance!.question, "the expert question belongs to the point being discussed");
  assert.deepEqual(opts[0].facts, ["jev_ranking", "embedding_gain"]);
});

test("constructive disagreement only when a real conflict exists", () => {
  const { a, angle } = run(SCENARIOS[0][1]);
  const d = draftStyle("CONSTRUCTIVE_DISAGREEMENT", a, angle);
  assert.equal(d.available, false);
  assert.match(d.unavailableReason!, /manufactured/);
});

test("context 'don't mention DEEPSIFT' suppresses the project everywhere", () => {
  const { a, opts } = run(SCENARIOS[0][1], { context: "I don't want to mention DEEPSIFT directly" });
  assert.ok(a.suppressProject);
  assert.equal(opts[2].available, false);
  for (const o of opts.filter((x) => x.available)) assert.ok(!/DEEPSIFT/i.test(o.text));
});

test("DEEPSIFT connection only for STRONG/MODERATE, named exactly once, facts are verified", () => {
  const { opts } = run(SCENARIOS[0][1]);
  const c = opts[2];
  assert.ok(c.available);
  assert.equal((c.text.match(/DEEPSIFT/g) ?? []).length, 1);
  assert.ok(c.facts.length > 0 && c.facts.every((f) => FACT_BY_ID[f]));
});

test("every talking point, question and stance passes the claim checker and fits one X post", () => {
  for (const g of ANGLES) {
    for (const k of ["short", "natural", "technical", "deepsift", "plain"] as const) assert.equal(checkReply(g[k]).status, "PASS", `${g.id}.${k}: ${JSON.stringify(checkReply(g[k]).issues)}`);
    for (const k of ["short", "natural", "technical", "plain"] as const) assert.ok(!/DEEPSIFT/i.test(g[k]), `${g.id}.${k} names the project`);
    assert.ok(g.facts.every((f) => FACT_BY_ID[f]), g.id);
  }
  for (const q of new Set(TOPICS.flatMap((t) => t.questions))) assert.equal(checkReply(q).status, "PASS", q);
  for (const s of STANCES) assert.equal(checkReply(`${s.acknowledge}\n\n${s.evidence}\n\n${s.question}`).status, "PASS", s.id);
});

const REJECT: [string, string][] = [
  ["NASA uses DEEPSIFT for Curiosity downlink now.", "AFFILIATION"],
  ["JPL is testing DEEPSIFT on the rover.", "OVERCLAIM"],
  ["DEEPSIFT improves real Curiosity operations.", "OVERCLAIM"],
  ["DEEPSIFT preserves scientific value.", "SCIENTIFIC_VALUE"],
  ["DEEPSIFT solved spacecraft bandwidth.", "CAUSAL"],
  ["DEEPSIFT is flight-ready.", "FLIGHT_READINESS"],
  ["With DEEPSIFT you can control the rover.", "LIVE_DATA"],
  ["DEEPSIFT processes live Mars data.", "OVERCLAIM"],
  ["My results show AI is useless.", "OVERCLAIM"],
  ["Rover position is the universally optimal signal.", "OVERCLAIM"],
  ["This generalizes to all planetary missions.", "OVERCLAIM"],
  ["Check out my project!", "OVERCLAIM"],
  ["As a NASA engineer, I think so.", "OVERCLAIM"],
  ["Great point #Mars #AI", "HASHTAG"],
  ["Agree @NASA @JPL", "MENTION"],
  ["More at deepsift.space", "LINK"],
];
for (const [text, rule] of REJECT) {
  test(`reply check rejects: ${text}`, () => {
    const r = checkReply(text);
    assert.equal(r.status, "FAIL");
    assert.ok(r.issues.some((i) => i.rule === rule), `${rule} not in ${JSON.stringify(r.issues)}`);
  });
}

test("links only on COPY + LINK", () => {
  assert.equal(checkReply("Replay: deepsift.space/mission-control", { allowLink: true }).issues.some((i) => i.rule === "LINK"), false);
});

test("promotional risk: LOW without the name, MEDIUM named once, HIGH when forced or repeated", () => {
  const strong = analyzePost({ text: SCENARIOS[0][1] });
  const weak = analyzePost({ text: SCENARIOS[7][1] });
  assert.equal(promoRisk("I found that geometry held up.", strong).risk, "LOW");
  assert.equal(promoRisk("In DEEPSIFT I found that geometry held up.", strong).risk, "MEDIUM");
  assert.equal(promoRisk("DEEPSIFT! DEEPSIFT again.", strong).risk, "HIGH");
  assert.equal(promoRisk("In DEEPSIFT I found that.", weak).risk, "HIGH");
  assert.equal(promoRisk("Check out my project", strong).risk, "HIGH");
});

test("link recommendation: default NONE; GITHUB when asked what you built; RESEARCH when asked for evidence", () => {
  assert.equal(linkRecommendation(analyzePost({ text: SCENARIOS[0][1] })).link, "NONE");
  assert.equal(linkRecommendation(analyzePost({ text: "Rover downlink prioritization is hard. What did you build? Link?" })).link, "GITHUB");
  assert.equal(linkRecommendation(analyzePost({ text: "Is there any evidence that onboard prioritization of downlink helps?" })).link, "RESEARCH");
});

test("expert question for qualified authors never claims an answer", () => {
  const a = analyzePost({ text: SCENARIOS[1][1], authorName: "Dr. Jane Roe, JPL" });
  assert.ok(a.qualifiedAuthor);
  const q = expertQuestion(a)!;
  assert.match(q, /\?$/);
  assert.equal(checkReply(q).status, "PASS");
});

test("repetition protection: 26.1% used in recent replies → warning and a different angle", () => {
  const now = new Date("2026-09-29T12:00:00Z");
  const rec = (i: number): ReplyRecord => ({
    id: `r${i}`, created_at: new Date(now.getTime() - i * 86_400_000).toISOString(), updated_at: now.toISOString(), post_text: "x", post_url: null,
    author_name: "", author_handle: "", context: "", reply: "…", style: "TECHNICAL", angle: "held-out-result", facts: ["held_out_bytes", "held_out_coverage"],
    relevance: "STRONG", promo_risk: "LOW", value: "NEW EVIDENCE", link: null, posted: true, reply_url: null,
  });
  const rep = repetition([1, 2, 3, 4].map(rec), now);
  assert.ok(rep.warnings.some((w) => w.includes("26.1% held-out result in 4 recent replies")));
  const a: Analysis = analyzePost({ text: "Rover image downlink bandwidth is the bottleneck: which images to send first?" });
  const angles = pickAngles(a, rep).map((x) => x.id);
  assert.ok(angles.indexOf("held-out-result") > 0, "the repeated angle is not first");
});
