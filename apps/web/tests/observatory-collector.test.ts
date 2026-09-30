// Collector store (node:sqlite) — temp DB, recorded fixtures only.
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { Store } from "../../../services/collector/store.ts";
import { diffDsn, imageEvent, noaaEvent } from "../lib/observatory/events.ts";
import { dsnContacts, parseCuriosity, parseDsn, parseNoaa } from "../lib/observatory/parsers.ts";
import { SOURCES } from "../lib/observatory/registry.ts";

const F = join(import.meta.dirname, "fixtures/observatory");
const json = (f: string) => JSON.parse(readFileSync(join(F, f), "utf8"));
const fresh = () => {
  const s = new Store(join(mkdtempSync(join(tmpdir(), "obs-")), "t.sqlite"));
  s.registerSources(SOURCES.map((x) => ({ ...x, intervalS: x.pollS })));
  return s;
};

test("schema: all approved tables exist, WAL mode", () => {
  const s = fresh();
  const tables = (s.db.prepare("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").all() as { name: string }[]).map((t) => t.name);
  for (const t of ["collector_metrics", "donki_events", "dsn_contacts", "dsn_snapshots", "events", "geometry", "mars_images", "source_polls", "sources", "space_weather"]) assert.ok(tables.includes(t), t);
  assert.equal((s.db.prepare("PRAGMA journal_mode").get() as { journal_mode: string }).journal_mode, "wal");
});

test("events: unique dedupe key — re-inserting the same observation is dropped", () => {
  const s = fresh();
  const samples = parseNoaa(json("noaa-wind.json"), json("noaa-mag.json"));
  const e = noaaEvent(samples[0], "2026-09-30T18:00:00.000Z");
  assert.equal(s.insertEvent(e), true);
  assert.equal(s.insertEvent({ ...e, timestamp_ingested: "2026-09-30T18:05:00.000Z" }), false);
  assert.equal(s.counts().total, 1);
});

test("space weather: measurements stored once per (time, source)", () => {
  const s = fresh();
  const samples = parseNoaa(json("noaa-wind.json"), json("noaa-mag.json"));
  assert.equal(samples.filter((x) => s.insertWeather(x, "t")).length, samples.length);
  assert.equal(samples.filter((x) => s.insertWeather(x, "t2")).length, 0);
  assert.equal(s.latestWeatherTime(), samples.at(-1)!.time);
});

test("Mars images: first-seen recorded; backfill kept distinct from live discovery; three timestamps preserved", () => {
  const s = fresh();
  const im = parseCuriosity(json("curiosity.json"));
  for (const i of im.slice(3)) s.insertImage(i, "2026-09-30T18:00:00.000Z", true);
  assert.equal(s.hasImage(im[0].imageId), false);
  s.insertImage(im[0], "2026-09-30T18:10:00.000Z", false);
  assert.equal(s.insertImage(im[0], "2026-09-30T18:20:00.000Z", false), false, "first-seen never overwritten");
  const row = s.db.prepare("SELECT * FROM mars_images WHERE image_id=?").get(im[0].imageId) as Record<string, unknown>;
  assert.equal(row.first_seen, "2026-09-30T18:10:00.000Z");
  assert.equal(row.backfill, 0);
  assert.ok(row.acquired && row.reached_earth && row.published);
  assert.notEqual(row.acquired, row.first_seen);
  assert.equal(imageEvent(im[0], "t").event_type, "mars_image_published");
});

test("DSN contacts: intervals opened and closed; stale open contacts closed at last observation on restart", () => {
  const s = fresh();
  const st = parseDsn(readFileSync(join(F, "dsn.xml"), "utf8"));
  const c = dsnContacts(st);
  const d = diffDsn(new Map(), c, st.sourceTime, st.sourceTime);
  for (const x of d.next.values()) s.openContact(x, x.since);
  assert.equal(s.openContacts().length, c.length);
  const first = [...d.next.values()][0];
  s.touchContact(first, first.since, "2026-09-30T18:05:00.000Z");
  s.closeContact(first.key, first.since, "2026-09-30T18:06:00.000Z");
  assert.equal(s.openContacts().length, c.length - 1);
  s.closeStaleContacts();
  assert.equal(s.openContacts().length, 0);
  const tl = s.timeline("2026-09-30T17:00:00.000Z");
  assert.equal(tl.contacts.length, c.length);
  assert.ok(tl.contacts.every((x) => x.end));
});

test("polls: success resets errors; failures increment them (feeds health)", () => {
  const s = fresh();
  const base = { source: "donki", status: 200, notModified: false, durationMs: 900, bytes: 1000, newEvents: 0, drops: 0, sourceTime: null };
  s.recordPoll({ ...base, at: "2026-09-30T18:00:00.000Z", ok: false, parse: "error", error: "HTTP 503" });
  s.recordPoll({ ...base, at: "2026-09-30T18:10:00.000Z", ok: false, parse: "error", error: "HTTP 503" });
  let row = s.sources().find((x) => x.id === "donki")!;
  assert.equal(row.consecutive_errors, 2);
  assert.equal(row.last_error, "HTTP 503");
  s.recordPoll({ ...base, at: "2026-09-30T18:20:00.000Z", ok: true, parse: "ok", error: null, newEvents: 3 });
  row = s.sources().find((x) => x.id === "donki")!;
  assert.equal(row.consecutive_errors, 0);
  assert.equal(row.last_success, "2026-09-30T18:20:00.000Z");
  assert.equal(row.last_ingest, "2026-09-30T18:20:00.000Z");
});

test("retention: old raw snapshots / polls / sample events pruned; hourly weather + geometry kept; contacts + images kept", () => {
  const s = fresh();
  const now = new Date("2026-12-31T00:00:00Z");
  s.snapshot("2026-09-01T00:00:00.000Z", "x", {});
  s.snapshot("2026-12-30T00:00:00.000Z", "x", {});
  s.insertWeather({ time: "2026-09-01T10:00:00.000Z", source: "SOLAR1", speed: 1, density: 1, temperature: 1, bt: 1, bx: 1, by: 1, bz: 1, quality: 0 }, "t");
  s.insertWeather({ time: "2026-09-01T10:01:00.000Z", source: "SOLAR1", speed: 1, density: 1, temperature: 1, bt: 1, bx: 1, by: 1, bz: 1, quality: 0 }, "t");
  const r = s.retention(now);
  assert.equal(r.snapshots, 1);
  assert.equal(r.weather, 1, "the non-hourly old sample is removed, the hourly one stays");
  assert.equal((s.db.prepare("SELECT COUNT(*) AS n FROM space_weather").get() as { n: number }).n, 1);
});

test("collector store paths never point at science artifacts", () => {
  const src = readFileSync(join(import.meta.dirname, "../../../services/collector/collector.ts"), "utf8") + readFileSync(join(import.meta.dirname, "../../../services/collector/store.ts"), "utf8");
  for (const bad of ["artifacts/", "data/manifests", "config/phase3", "apps/web/data", "docs/release"]) assert.ok(!src.includes(bad), bad);
  assert.ok(src.includes("live_observatory/data/observatory.sqlite"));
});
