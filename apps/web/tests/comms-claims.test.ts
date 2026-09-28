// Claim checker + seed library: every seed post passes; prohibited claims are rejected with a reason.
import assert from "node:assert/strict";
import { test } from "node:test";
import { checkPost, checkThread, xLength } from "../lib/comms/claims.ts";
import { HOOK_STYLES, IDEAS, PILLARS, composePost, composeThread } from "../lib/comms/library.ts";
import { ASSET_BY_ID } from "../lib/comms/assets.ts";
import { FACT_BY_ID } from "../lib/comms/facts.ts";
import { shareability } from "../lib/comms/shareability.ts";

test("at least 30 seed ideas, varied across every pillar, not the same claim 30 times", () => {
  assert.ok(IDEAS.length >= 30, String(IDEAS.length));
  for (const p of PILLARS) assert.ok(IDEAS.filter((i) => i.pillar === p).length >= 2, p);
  const withBytes = IDEAS.filter((i) => i.facts.includes("held_out_bytes")).length;
  assert.ok(withBytes <= 4, `26.1% used by ${withBytes} ideas`);
  assert.equal(new Set(IDEAS.map((i) => i.id)).size, IDEAS.length);
});

test("every seed idea references real facts and assets", () => {
  for (const i of IDEAS) {
    for (const f of i.facts) assert.ok(FACT_BY_ID[f], `${i.id}: unknown fact ${f}`);
    if (i.visual) assert.ok(ASSET_BY_ID[i.visual], `${i.id}: unknown asset ${i.visual}`);
  }
});

test("every hook variant of every seed idea passes the claim checker", () => {
  for (const i of IDEAS) for (const s of HOOK_STYLES) {
    const r = checkPost(composePost(i, s));
    assert.equal(r.status, "PASS", `${i.id}/${s}: ${JSON.stringify(r.issues)}`);
  }
});

test("every thread is 4–7 posts and every thread post passes independently", () => {
  for (const i of IDEAS) {
    const t = composeThread(i);
    assert.ok(t.length >= 4 && t.length <= 7, `${i.id}: ${t.length}`);
    const r = checkThread(t);
    assert.equal(r.status, "PASS", `${i.id}: ${JSON.stringify(r.posts.map((p) => p.issues))}`);
  }
});

const REJECT: [string, string][] = [
  ["DEEPSIFT reduced Curiosity bandwidth by 74%.", "NUMBER"],
  ["NASA could save 74% bandwidth with this.", "MISSION_GAIN"],
  ["DEEPSIFT preserves 100% scientific value.", "SCIENTIFIC_VALUE"],
  ["A NASA-approved method for rover downlink.", "AFFILIATION"],
  ["Validated by JPL engineers.", "AFFILIATION"],
  ["Our flight-ready scheduler is here.", "FLIGHT_READINESS"],
  ["DEEPSIFT is now running onboard Curiosity.", "FLIGHT_READINESS"],
  ["Watch the live feed from Mars in Mission Control.", "LIVE_DATA"],
  ["Mission Control lets you control the rover.", "LIVE_DATA"],
  ["It reconstructs the rover's onboard image stream.", "RECONSTRUCTION"],
  ["A new discovery about Mars terrain.", "DISCOVERY"],
  ["Our AI outperforms human operators.", "AI_SUPERIORITY"],
  ["This revolutionary, game-changing breakthrough.", "HYPE"],
  ["You won't believe what Curiosity sent.", "HYPE"],
  ["NASA should use my AI.", "AFFILIATION"],
  ["I solved Mars bandwidth.", "CAUSAL"],
  ["This proves geometry beats AI.", "CAUSAL"],
  ["Keeping 1/4 of frames used 26.1% of the bytes.", "SCOPE"],
  ["On the held-out Curiosity Navcam test, POSITION used 26.1% of the SEND ALL full-quality baseline.", "SCOPE"], // no archived/replay context
  ["Held-out Curiosity Navcam replay: a 26.1% reduction.", "SCOPE"],
  ["It used 26.2% of the bytes on the held-out Curiosity replay of archived data.", "NUMBER"],
  ["Curiosity takes 2012 photos a day.", "NUMBER"],
];

for (const [text, rule] of REJECT) {
  test(`rejects: ${text}`, () => {
    const r = checkPost(text);
    assert.equal(r.status, "FAIL");
    assert.ok(r.issues.some((i) => i.rule === rule), `${rule} not in ${JSON.stringify(r.issues)}`);
    assert.ok(r.issues.every((i) => i.message.length > 5), "every failure has a reason");
  });
}

test("the safe public wording of the headline fact passes with archived context", () => {
  const r = checkPost(`${FACT_BY_ID.held_out_bytes.safe_public_wording} Retrospective replay of archived PDS data.`);
  assert.equal(r.status, "PASS", JSON.stringify(r.issues));
  assert.ok(r.facts.includes("held_out_bytes"));
});

test("negated affiliation / readiness / value wording is allowed", () => {
  for (const t of [
    "DEEPSIFT is not affiliated with, reviewed or validated by NASA or JPL.",
    "It is not flight software and not NASA/JPL-reviewed.",
    "Geometric coverage is not scientific value.",
    "Mission Control is never a live feed; it is a historical replay.",
    "It does not reconstruct the onboard stream.",
  ]) assert.equal(checkPost(t).status, "PASS", `${t}: ${JSON.stringify(checkPost(t).issues)}`);
});

test("length uses X weighting (links = 23) and fails over 280", () => {
  assert.equal(xLength("see deepsift.space/mission-control"), 4 + 23);
  assert.equal(xLength("https://github.com/nassimb/deepsift"), 23);
  const long = "Held-out test. ".repeat(20);
  assert.ok(checkPost(long).issues.some((i) => i.rule === "LENGTH"));
});

test("shareability is YES/NO factors with suggestions, never a probability", () => {
  const f = shareability("AUROC pHash embeddings monotonic tier\n\n1% 2% 3% 4% 5%", false);
  assert.ok(f.every((x) => typeof x.ok === "boolean" && x.suggestion.length > 0));
  assert.ok(f.find((x) => x.key === "hook" && !x.ok)!.suggestion.includes("too technical"));
  assert.ok(f.find((x) => x.key === "visual" && !x.ok)!.suggestion.includes("Needs a visual"));
  assert.ok(f.find((x) => x.key === "jargon" && !x.ok)!.suggestion.includes("Too many numbers"));
  assert.ok(!JSON.stringify(f).match(/viral|probability/i));
});
