// Visuals for X must be PNG or JPEG (X does not accept SVG); shared copies are byte-identical to the frozen release files.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { ASSETS } from "../lib/comms/assets.ts";

const ROOT = join(import.meta.dirname, "../../..");
const PUBLIC = join(import.meta.dirname, "../public");
const sha = (p: string) => createHash("sha256").update(readFileSync(p)).digest("hex");
const IMAGE_KINDS = new Set(["FIGURE", "SCREENSHOT", "NAVCAM"]);

test("every image asset has an attachable PNG/JPEG and nothing for X is SVG", () => {
  for (const a of ASSETS) {
    if (IMAGE_KINDS.has(a.kind)) assert.ok(a.files.length > 0, `${a.id} has no attachable file`);
    for (const f of a.files) {
      assert.match(f.url, /\.(png|jpe?g)$/i, `${a.id}: ${f.url}`);
      assert.equal(f.format, /\.png$/i.test(f.url) ? "PNG" : "JPEG");
    }
    assert.ok(!/\.svg/i.test(a.preview ?? ""), `${a.id} preview is SVG`);
    assert.ok(!/\.svg/i.test(a.open), `${a.id} open is SVG`);
  }
});

test("attachable files are real images with valid signatures, byte-identical to their frozen source", () => {
  for (const a of ASSETS)
    for (const f of a.files) {
      const served = join(PUBLIC, f.url);
      const head = readFileSync(served).subarray(0, 8);
      if (f.format === "PNG") assert.deepEqual([...head], [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a], f.url);
      else assert.deepEqual([...head.subarray(0, 3)], [0xff, 0xd8, 0xff], f.url);
      assert.equal(sha(served), sha(join(ROOT, f.source)), `${f.url} differs from ${f.source}`);
      assert.ok(readFileSync(served).length < 5 * 1024 * 1024, `${f.url} over X's 5 MB image limit`);
    }
});
