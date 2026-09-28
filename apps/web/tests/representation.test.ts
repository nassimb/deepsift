// node --test (Node ≥ 23 strips TypeScript types natively). Pure logic only — no data imports.
import assert from "node:assert/strict";
import { test } from "node:test";
import { eyeLabels, eyeTiers, representation, stereoBroken } from "../lib/representation.ts";

const stereo = { stereo: true, primary: ["NLB_1EDR_D0TRAV1M1", "NRB_1EDR_D0TRAV1M1"], thumbnails: ["NLB_1EDR_T0TRAV1M1", "NRB_1EDR_T0TRAV1M1"] };
const mono = { stereo: false, primary: ["NLB_2EDR_F0NCAM1M1"], thumbnails: ["NLB_2EDR_T0NCAM1M1"] };
const halfStereo = { stereo: true, primary: ["NLB_3EDR_D0TRAV1M1"], thumbnails: ["NLB_3EDR_T0TRAV1M1", "NRB_3EDR_T0TRAV1M1"] };

test("stereo representation labels", () => {
  assert.equal(representation(stereo, true), "FULL_STEREO_PAIR");
  assert.equal(representation(stereo, false), "THUMBNAIL_PAIR");
});

test("mono is never called stereo", () => {
  assert.equal(representation(mono, true), "FULL_MONO");
  assert.equal(representation(mono, false), "THUMBNAIL_MONO");
  assert.deepEqual(eyeLabels(mono).map((e) => e.label), ["MONO"]);
  assert.equal(stereoBroken(mono, true), false);
  for (const r of [representation(mono, true), representation(mono, false)]) assert.ok(!r.includes("PAIR") && !r.includes("STEREO"));
});

test("stereo eyes are LEFT and RIGHT", () => {
  assert.deepEqual(eyeLabels(stereo).map((e) => e.label), ["LEFT", "RIGHT"]);
});

test("stereo broken only when exactly one eye is at the full tier", () => {
  assert.deepEqual(eyeTiers(stereo, true), { L: "FULL", R: "FULL" });
  assert.equal(stereoBroken(stereo, true), false);
  assert.deepEqual(eyeTiers(stereo, false), { L: "THUMBNAIL", R: "THUMBNAIL" });
  assert.equal(stereoBroken(stereo, false), false);
  assert.deepEqual(eyeTiers(halfStereo, true), { L: "FULL", R: "THUMBNAIL" });
  assert.equal(stereoBroken(halfStereo, true), true);
});
