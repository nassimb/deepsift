// Every VERIFIED_FACT is re-checked against the frozen DEEPSIFT source it cites (read-only; nothing is recomputed).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { VERIFIED_FACTS, type Fmt } from "../lib/comms/facts.ts";

const ROOT = join(import.meta.dirname, "../../..");
const cache = new Map<string, string>();
const read = (f: string) => { if (!cache.has(f)) cache.set(f, readFileSync(join(ROOT, f), "utf8")); return cache.get(f)!; };

const fmt = (v: unknown, f: Fmt): string => {
  const n = v as number;
  switch (f) {
    case "pct1": return `${(n * 100).toFixed(1)}%`;
    case "pct0": return `${(n * 100).toFixed(0)}%`;
    case "m2": return `${n.toFixed(2)} m`;
    case "f2": return n.toFixed(2);
    case "f3": return n.toFixed(3);
    case "m0": return `${n.toFixed(0)} m`;
    case "sf3": return `${n >= 0 ? "+" : "-"}${Math.abs(n).toFixed(3)}`;
    case "int": return String(n);
    case "intc": return n.toLocaleString("en-US");
    case "x2": return `${n.toFixed(2)}×`;
    case "raw": return String(v);
  }
};

test("every fact has the required fields", () => {
  const ids = new Set<string>();
  for (const f of VERIFIED_FACTS) {
    assert.ok(!ids.has(f.id), `duplicate ${f.id}`); ids.add(f.id);
    for (const k of ["id", "category", "short_claim", "source_file", "source_field_or_section", "safe_public_wording", "scope"] as const) assert.ok(f[k], `${f.id}.${k}`);
    assert.ok(Array.isArray(f.forbidden_wording) && f.evidence.length > 0, f.id);
  }
});

test("every fact matches its frozen source", () => {
  for (const f of VERIFIED_FACTS) {
    for (const e of f.evidence) {
      if ("contains" in e) {
        assert.ok(read(e.file).includes(e.contains), `${f.id}: "${e.contains}" not in ${e.file}`);
      } else {
        let v: unknown = JSON.parse(read(e.file));
        for (const k of e.path) v = (v as Record<string | number, unknown>)[k];
        assert.equal(fmt(v, e.fmt), e.expect, `${f.id}: ${e.file} → ${e.path.join(" / ")}`);
      }
    }
  }
});

test("the required frozen facts are present", () => {
  const ids = new Set(VERIFIED_FACTS.map((f) => f.id));
  for (const id of ["held_out_bytes", "held_out_coverage", "held_out_max_distance", "held_out_stereo", "held_out_retention", "four_periods",
    "jev_ranking", "telemetry_ranking", "phash_failed", "quality_v2_failed", "embedding_gain", "lim_survivorship", "lim_no_onboard_stream",
    "lim_one_rover_camera", "lim_geometry_not_science", "lim_simulated_tier", "lim_no_flight_hw", "lim_no_nasa"]) assert.ok(ids.has(id), id);
});

test("config committed less than 25 s before the first test image", () => {
  const r = JSON.parse(read("apps/web/data/release.json")).reproducibility.frozen_before_download;
  const dt = (Date.parse(r.first_test_image_written) - Date.parse(r.config_commit_time)) / 1000;
  assert.ok(dt > 24 && dt < 25, String(dt));
});
