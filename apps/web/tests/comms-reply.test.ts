// Reply Lab: topic first, project second. No forced DEEPSIFT, no invented article content, no links/hashtags/mentions.
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  ANGLES, CONNECTIONS, REPLY_STYLES, STANCES, analyzePost, checkReply, conversationValue, draftStyle, expertQuestion, linkRecommendation,
  mentionsProject, pickAngles, primaryOptions, promoRisk, recommend, repetition, shouldMention, wouldMakeSenseWithoutDeepsift,
} from "../lib/comms/reply.ts";
import { FACT_BY_ID } from "../lib/comms/facts.ts";
import type { ReplyRecord } from "../lib/comms/store.ts";

const NO_HISTORY = repetition([]);
const run = (text: string, extra: { context?: string; authorName?: string } = {}, override = false) => {
  const a = analyzePost({ text, ...extra });
  const angle = pickAngles(a, NO_HISTORY, override)[0] ?? null;
  const opts = primaryOptions(a, angle, override);
  const mention = shouldMention(a, NO_HISTORY, override, angle);
  const rec = recommend(a, opts, mention);
  return { a, angle, opts, mention, rec, value: conversationValue(a, rec?.text ?? "", rec) };
};

const PERSEVERANCE = "NASA’s Perseverance Uncovers ‘Unexpected’ Volcanic Record of Water on Mars";

test("REGRESSION: Perseverance volcanic-water headline → planetary geology, WEAK, no DEEPSIFT", () => {
  const { a, opts, mention, rec, value } = run(PERSEVERANCE);
  assert.equal(a.domain, "PLANETARY GEOLOGY");
  assert.equal(a.relevance, "WEAK");
  assert.equal(mention.mention, false);
  assert.ok(rec, "a reply about the science is recommended");
  assert.equal(rec!.key, "NATURAL");
  assert.match(rec!.text, /unexpected|evidence|volcanic|water/i, "discusses or asks about the geology claim itself");
  assert.ok(value.reply);
  const FORBIDDEN = /Curiosity|Navcam|frame|sampling|downlink|DEEPSIFT|archived|I tested|I built|my project/i;
  for (const o of opts.filter((x) => x.available)) assert.ok(!FORBIDDEN.test(o.text), `${o.key}: ${o.text}`);
  for (const s of REPLY_STYLES) {
    const d = draftStyle(s, a, null);
    if (d.available) assert.ok(!FORBIDDEN.test(d.text), `${s}: ${d.text}`);
  }
  assert.equal(opts[3].available, false, "no DEEPSIFT-related option on a WEAK post");
  assert.equal(linkRecommendation(a).link, "NONE");
  assert.ok(!/this (proves|shows)|the finding shows|mineral composition/i.test(rec!.text), "no invented article content");
  assert.equal(checkReply(rec!.text, { relevance: a.relevance }).status, "PASS");
});

test("REGRESSION: project insertion under the Perseverance post is rejected unless overridden", () => {
  const a = analyzePost({ text: PERSEVERANCE });
  const bad = "Replaying archived Curiosity Navcam traverses frame by frame helped me reason about which frames to send.";
  const c = checkReply(bad, { relevance: a.relevance });
  assert.equal(c.status, "FAIL");
  assert.ok(c.issues.some((i) => i.rule === "PROJECT_INSERTION"));
  assert.equal(promoRisk(bad, a).risk, "HIGH");
  assert.equal(wouldMakeSenseWithoutDeepsift(bad), false);
  const withOverride = checkReply(bad, { relevance: a.relevance, override: true });
  assert.ok(withOverride.warnings.some((w) => w.rule === "PROJECT_INSERTION"), "override turns it into a warning, still shown");
  const { opts } = run(PERSEVERANCE, {}, true);
  assert.equal(opts[3].available, true, "override explicitly enables the project option");
});

test("mission / agency / generic words alone never create a DEEPSIFT connection", () => {
  for (const t of ["NASA's Curiosity rover celebrates another year on Mars.", "JPL engineers share a new Perseverance selfie.", "AI and space science are exciting.", "Mars rover news today."]) {
    const { a, opts } = run(t);
    assert.ok(a.relevance === "WEAK" || a.relevance === "NONE", `${t}: ${a.relevance}`);
    assert.equal(opts[3].available, false, t);
    for (const o of opts.filter((x) => x.available)) assert.ok(!mentionsProject(o.text), `${t}: ${o.text}`);
  }
});

const WEAK_SCIENCE: [string, string][] = [
  ["Perseverance finds evidence of volcanic interaction with water.", "PLANETARY GEOLOGY"],
  ["JWST just imaged a galaxy cluster 10 billion light-years away, revealing new dark matter structure.", "ASTROPHYSICS"],
  ["Could Perseverance's samples hold signs of ancient microbial life?", "ASTROBIOLOGY"],
  ["A huge dust storm is building over Mars this season.", "METEOROLOGY"],
  ["Falcon 9 launches another batch of satellites tonight.", "ROCKETS / LAUNCH"],
  ["New exoplanet found in the habitable zone of a nearby star.", "ASTROPHYSICS"],
];
for (const [t, domain] of WEAK_SCIENCE) {
  test(`science post stays WEAK and project-free: ${domain}`, () => {
    const { a, rec, mention } = run(t);
    assert.equal(a.domain, domain);
    assert.equal(a.relevance, "WEAK");
    assert.equal(mention.mention, false);
    assert.ok(rec && !mentionsProject(rec.text));
    assert.equal(checkReply(rec!.text, { relevance: a.relevance }).status, "PASS");
  });
}

test("GOOD connection: onboard autonomy post → DIRECT, DEEPSIFT mentioned with the complexity-didn't-generalize finding", () => {
  const { a, mention, rec } = run("Future Mars missions may need more onboard autonomy because of communication delays and limited relay bandwidth.");
  assert.equal(a.relevance, "DIRECT");
  assert.equal(mention.mention, true);
  assert.equal(rec!.key, "DEEPSIFT");
  assert.equal(rec!.angle, "complexity-didnt-generalize");
  assert.match(rec!.text, /archived Curiosity Navcam/);
  assert.equal(checkReply(rec!.text, { relevance: a.relevance }).status, "PASS");
});

const DIRECT_OR_ADJACENT: [string, string, string][] = [
  ["Mars rover bandwidth", "Bandwidth remains one of the hardest constraints for Mars rover missions. Relay passes limit how much imagery comes home each sol.", "DIRECT"],
  ["autonomous science", "Onboard autonomy becomes essential as spacecraft operate farther from Earth.", "DIRECT"],
  ["spacecraft communications", "The Deep Space Network is oversubscribed; data rates from Mars relay orbiters are a real bottleneck.", "DIRECT"],
  ["AI validation", "Most ML papers never test on out-of-distribution data. Generalization claims should require held-out evaluation.", "ADJACENT"],
  ["Curiosity imagery", "New raw images from Curiosity's Navcam show the rover climbing toward Mount Sharp.", "ADJACENT"],
];
for (const [name, t, rel] of DIRECT_OR_ADJACENT) {
  test(`${name} → ${rel}; every option passes; natural option never names the project`, () => {
    const { a, opts } = run(t);
    assert.equal(a.relevance, rel);
    for (const o of opts.filter((x) => x.available)) {
      const c = checkReply(o.text, { relevance: a.relevance });
      assert.equal(c.status, "PASS", `${o.key}: ${JSON.stringify(c.issues)}`);
      assert.ok(!c.hasLink && !/#\w/.test(o.text) && !/(^|\s)@\w/.test(o.text));
    }
    assert.ok(!mentionsProject(opts[0].text), "A · Natural is independent of DEEPSIFT");
    assert.ok(!mentionsProject(opts[1].text), "B · Curious question is independent of DEEPSIFT");
  });
}

test("ADJACENT with only a 'what I built' point (Mission Control replay) → no mention, natural reply recommended", () => {
  const { a, mention, rec } = run("New raw images from Curiosity's Navcam show the rover climbing toward Mount Sharp.");
  assert.equal(a.relevance, "ADJACENT");
  assert.equal(mention.mention, false);
  assert.equal(rec!.key, "NATURAL");
});

test("robotics post with no methodological hook stays WEAK (robot ≠ DEEPSIFT)", () => {
  const { a, rec } = run("Our new robot arm learned to grasp unseen objects after only 200 demonstrations.");
  assert.equal(a.relevance, "WEAK");
  assert.ok(!mentionsProject(rec!.text));
});

test("generic science journalism → WEAK, no project; unrelated topic → NONE + DON'T REPLY", () => {
  const j = run("NASA announced today a new mission to study Mars' atmosphere.");
  assert.equal(j.a.relevance, "WEAK");
  assert.ok(!mentionsProject(j.rec!.text));
  const u = run("Best sourdough recipe I've tried: 75% hydration, 18 hour cold proof.");
  assert.equal(u.a.relevance, "NONE");
  assert.ok(u.a.noConnection);
  assert.equal(u.rec, null);
  assert.equal(u.value.reply, false);
  assert.ok(u.opts.every((o) => !o.available && o.text === ""));
  assert.ok(u.opts[3].unavailableReason!.includes("NO NATURAL DEEPSIFT CONNECTION"));
});

test("'AI will transform Mars exploration' → pushback with evidence, not 'DEEPSIFT proves this'", () => {
  const { a, rec } = run("AI will transform Mars exploration within a decade.");
  assert.equal(a.stance?.id, "ai-will-transform");
  assert.match(rec!.text, /more cautious/);
  assert.ok(!/prove/i.test(rec!.text) && !/DEEPSIFT/.test(rec!.text));
  assert.equal(expertQuestion(a), a.stance!.question);
  assert.deepEqual(rec!.facts, ["jev_ranking", "embedding_gain"]);
});

test("constructive disagreement only on a real conflict", () => {
  const { a, angle } = run("Bandwidth remains one of the hardest constraints for Mars rover missions.");
  assert.match(draftStyle("CONSTRUCTIVE_DISAGREEMENT", a, angle).unavailableReason!, /manufactured/);
});

test("context 'don't mention DEEPSIFT' suppresses the project everywhere", () => {
  const { a, opts, mention } = run("Bandwidth remains one of the hardest constraints for Mars rover missions.", { context: "I don't want to mention DEEPSIFT directly" });
  assert.ok(a.suppressProject);
  assert.equal(mention.mention, false);
  for (const o of opts.filter((x) => x.available)) assert.ok(!mentionsProject(o.text), o.key);
});

test("technical option needs technical substance in the pasted post", () => {
  const { opts } = run("Onboard autonomy becomes essential as spacecraft operate farther from Earth.");
  assert.equal(opts[2].available, false);
  assert.match(opts[2].unavailableReason!, /technical substance/);
});

test("every talking point, question and stance passes the claim checker; project voices are the only ones naming DEEPSIFT", () => {
  for (const g of ANGLES) {
    for (const k of ["short", "natural", "technical", "deepsift", "plain"] as const) assert.equal(checkReply(g[k], { relevance: "DIRECT" }).status, "PASS", `${g.id}.${k}`);
    for (const k of ["short", "natural", "technical", "plain"] as const) assert.ok(!/DEEPSIFT/i.test(g[k]), `${g.id}.${k}`);
    assert.ok(g.facts.every((f) => FACT_BY_ID[f]), g.id);
  }
  for (const q of new Set(CONNECTIONS.flatMap((c) => c.questions))) assert.equal(checkReply(q).status, "PASS", q);
  for (const s of STANCES) {
    assert.equal(checkReply(`${s.acknowledge}\n\n${s.evidence}\n\n${s.question}`, { relevance: "ADJACENT" }).status, "PASS", s.id);
    assert.ok(s.facts.every((f) => FACT_BY_ID[f]), s.id);
  }
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
  ["This reminds me of DEEPSIFT", "OVERCLAIM"],
  ["As a NASA engineer, I think so.", "OVERCLAIM"],
  ["This proves water flowed there for millions of years.", "OVERCLAIM"],
  ["Great point #Mars #AI", "HASHTAG"],
  ["Agree @NASA @JPL", "MENTION"],
  ["More at deepsift.space", "LINK"],
];
for (const [text, rule] of REJECT) {
  test(`reply check rejects: ${text}`, () => {
    const r = checkReply(text, { relevance: "DIRECT" });
    assert.equal(r.status, "FAIL");
    assert.ok(r.issues.some((i) => i.rule === rule), `${rule} not in ${JSON.stringify(r.issues)}`);
  });
}

test("promotional risk: LOW project-free, MEDIUM one relevant mention, HIGH forced or repeated", () => {
  const direct = analyzePost({ text: "Bandwidth remains one of the hardest constraints for Mars rover missions." });
  const weak = analyzePost({ text: PERSEVERANCE });
  assert.equal(promoRisk("What evidence makes this different?", direct).risk, "LOW");
  assert.equal(promoRisk("In DEEPSIFT I found that geometry held up.", direct).risk, "MEDIUM");
  assert.equal(promoRisk("DEEPSIFT! DEEPSIFT again.", direct).risk, "HIGH");
  assert.equal(promoRisk("I tested this on archived Curiosity data.", weak).risk, "HIGH");
});

test("links: none by default, none for WEAK; GITHUB only when asked", () => {
  assert.equal(linkRecommendation(analyzePost({ text: "Bandwidth remains one of the hardest constraints for Mars rover missions." })).link, "NONE");
  assert.equal(linkRecommendation(analyzePost({ text: PERSEVERANCE })).link, "NONE");
  assert.equal(linkRecommendation(analyzePost({ text: "Rover downlink prioritization is hard. What did you build? Link?" })).link, "GITHUB");
});

const rec = (i: number, now: Date, project: boolean, facts: string[] = ["held_out_bytes"]): ReplyRecord => ({
  id: `r${i}`, created_at: new Date(now.getTime() - i * 3_600_000).toISOString(), updated_at: now.toISOString(), post_text: "x", post_url: null,
  author_name: "", author_handle: "", context: "", reply: project ? "In DEEPSIFT…" : "Good question.", style: "A", angle: project ? "held-out-result" : null,
  facts: project ? facts : [], relevance: "DIRECT", promo_risk: "LOW", value: "", link: null, posted: true, reply_url: null, mentions_project: project,
});

test("recent project mentions: 'N of last 10' and a warning above ~30%", () => {
  const now = new Date("2026-09-29T12:00:00Z");
  const two = repetition([0, 1, 2, 3, 4, 5, 6, 7, 8, 9].map((i) => rec(i, now, i < 2)), now);
  assert.equal(two.recentMentions, 2);
  assert.equal(two.recentCount, 10);
  assert.ok(!two.warnings.some((w) => w.includes("of your last")));
  const five = repetition([0, 1, 2, 3, 4, 5, 6, 7, 8, 9].map((i) => rec(i, now, i < 5)), now);
  assert.ok(five.warnings.some((w) => w.includes("5 of your last 10 replies mentioned DEEPSIFT")));
  const a = analyzePost({ text: "Most ML papers never test on out-of-distribution data. Generalization claims should require held-out evaluation." });
  assert.equal(shouldMention(a, five, false, pickAngles(a, five)[0]).mention, false, "ADJACENT post: stay project-free when the ratio is high");
});

test("repetition protection: repeated 26.1% → warning and a different first angle", () => {
  const now = new Date("2026-09-29T12:00:00Z");
  const rep = repetition([1, 2, 3, 4].map((i) => rec(i, now, true, ["held_out_bytes", "held_out_coverage"])), now);
  assert.ok(rep.warnings.some((w) => w.includes("26.1% held-out result in 4 recent replies")));
  const a = analyzePost({ text: "Rover image downlink bandwidth is the bottleneck: which images to send first?" });
  assert.ok(pickAngles(a, rep).map((x) => x.id).indexOf("held-out-result") > 0);
});
