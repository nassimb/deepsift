// Live Observatory source adapters — recorded fixtures only (captured 2026-09-30). No network.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { DEDUPE, dedupe, diffDsn, donkiEvent, imageEvent, noaaEvent, orderEvents, sourceEvent } from "../lib/observatory/events.ts";
import { ageLabel, computeHealth } from "../lib/observatory/health.ts";
import { dsnContacts, parseCuriosity, parseDonki, parseDsn, parseDsnConfig, parseHorizons, parseNoaa, parsePerseverance } from "../lib/observatory/parsers.ts";
import { DONKI_BASE, SOURCES, SOURCE_BY_ID } from "../lib/observatory/registry.ts";
import { SchemaError } from "../lib/observatory/types.ts";

const F = join(import.meta.dirname, "fixtures/observatory");
const txt = (f: string) => readFileSync(join(F, f), "utf8");
const json = (f: string) => JSON.parse(txt(f));

// ─── registry ──────────────────────────────────────────────────────────────
test("registry: six sources, truthful classifications, pinned parser versions, attribution", () => {
  assert.deepEqual(SOURCES.map((s) => s.id), ["dsn", "noaa", "donki", "horizons", "perseverance", "curiosity"]);
  assert.equal(SOURCE_BY_ID.dsn.classification, "LIVE");
  assert.equal(SOURCE_BY_ID.noaa.classification, "NEAR REAL-TIME");
  assert.equal(SOURCE_BY_ID.donki.classification, "NEAR REAL-TIME EVENTS");
  assert.equal(SOURCE_BY_ID.horizons.classification, "CURRENT COMPUTED");
  assert.equal(SOURCE_BY_ID.perseverance.classification, "NEWLY PUBLISHED");
  assert.equal(SOURCE_BY_ID.curiosity.classification, "NEWLY PUBLISHED");
  for (const s of SOURCES) {
    assert.match(s.parserVersion, /\/\d+$/);
    assert.ok(s.attribution.length > 5 && s.endpoints.every((u) => u.startsWith("https://")));
  }
  assert.ok(SOURCE_BY_ID.dsn.optional && !SOURCE_BY_ID.dsn.documentedApi, "DSN is an optional, undocumented adapter");
  assert.equal(DONKI_BASE, "https://ccmc.gsfc.nasa.gov/DONKI-API/get", "new DONKI base (old endpoints redirect since 2026-09-30)");
  const endpoints = SOURCES.flatMap((s) => s.endpoints).join(" ");
  assert.ok(!endpoints.includes("kauai.ccmc") && !endpoints.includes("api.nasa.gov/DONKI"), "obsolete DONKI endpoints are not used");
});

test("no source may claim to be a live Mars feed", () => {
  const blob = JSON.stringify(SOURCES).toUpperCase();
  for (const bad of ["LIVE FROM MARS", "LIVE ROVER CAMERA", "LIVE CURIOSITY TELEMETRY", "LIVE PERSEVERANCE"]) assert.ok(!blob.includes(bad), bad);
});

// ─── DSN ───────────────────────────────────────────────────────────────────
test("DSN: parses stations, dishes, signals; unreported frequency / RTLT never surface", () => {
  const s = parseDsn(txt("dsn.xml"));
  assert.deepEqual(s.stations.map((x) => x.name), ["Goldstone", "Madrid", "Canberra"]);
  assert.equal(s.dishes.length, 14);
  assert.equal(s.sourceTime, "2026-09-30T18:02:13.000Z");
  const d25 = s.dishes.find((d) => d.name === "DSS25")!;
  assert.equal(d25.complex, "Goldstone");
  const down = d25.signals.find((x) => x.direction === "down")!;
  assert.equal(down.dataRate, 714300);
  assert.equal(down.band, "X");
  assert.ok(s.dishes.every((d) => d.targets.every((t) => t.rtltS === null || t.rtltS >= 0)), "-1 RTLT → null");
  assert.ok(!JSON.stringify(s).includes('"frequency"'), "frequency is not carried (always 0 upstream)");
  const upRate0 = d25.signals.find((x) => x.direction === "up")!;
  assert.equal(upRate0.dataRate, null, "dataRate 0 → not reported");
});

test("DSN: contacts = active links, Mars-linked flagged, names from config", () => {
  const names = parseDsnConfig(txt("dsn-config.xml"));
  assert.equal(names.msl, "Mars Science Laboratory (Curiosity)");
  assert.equal(names.m01o, "Mars Odyssey");
  const c = dsnContacts(parseDsn(txt("dsn.xml")), names);
  const keys = c.map((x) => x.key).sort();
  assert.deepEqual(keys, ["DSS25|imap", "DSS36|m01o", "DSS43|jno", "DSS54|chdr", "DSS56|eurc", "DSS65|rst"]);
  const ody = c.find((x) => x.spacecraftCode === "m01o")!;
  assert.equal(ody.mars, true);
  assert.equal(ody.direction, "DOWNLINK");
  assert.equal(ody.complex, "Canberra");
  assert.equal(c.find((x) => x.spacecraftCode === "imap")!.direction, "BOTH");
  assert.equal(c.find((x) => x.spacecraftCode === "imap")!.mars, false);
});

test("DSN: missing fields tolerated; broken payload throws a schema error (→ DEGRADED, never a crash)", () => {
  const minimal = '<dsn><station name="cdscc" friendlyName="Canberra" timeUTC="1790791333000"/><dish name="DSS43" activity=""><downSignal active="true" spacecraft="VGR2" dataRate="" band="" power=""/></dish></dsn>';
  const s = parseDsn(minimal);
  const c = dsnContacts(s);
  assert.equal(c.length, 1);
  assert.equal(c[0].downRate, null);
  assert.equal(c[0].band, null);
  assert.equal(c[0].downPower, null);
  assert.equal(c[0].azimuth, null);
  assert.throws(() => parseDsn(txt("dsn-broken.xml")), SchemaError);
  assert.throws(() => parseDsn("<dsn></dsn>"), SchemaError);
});

test("DSN: contact transitions (start / update / end) with stable dedupe keys", () => {
  const s = parseDsn(txt("dsn.xml"));
  const c = dsnContacts(s);
  const seeded = diffDsn(new Map(), c, s.sourceTime, "2026-09-30T18:02:14.000Z", true);
  assert.equal(seeded.events.length, 0, "first snapshot seeds state without a flood of 'started' events");
  const t2 = "2026-09-30T18:03:18.000Z"; // ≥ 60 s later: updates are rate-limited per contact
  const changed = c.filter((x) => x.spacecraftCode !== "jno").map((x) => (x.spacecraftCode === "imap" ? { ...x, downRate: 2_000_000 } : x));
  const added = [...changed, { ...c[0], key: "DSS14|msl", dish: "DSS14", spacecraftCode: "msl", spacecraftName: "Curiosity", mars: true }];
  const r = diffDsn(seeded.next, added, t2, t2);
  const types = r.events.map((e) => e.event_type).sort();
  assert.deepEqual(types, ["dsn_contact_ended", "dsn_contact_started", "dsn_contact_updated"]);
  const ended = r.events.find((e) => e.event_type === "dsn_contact_ended")!;
  assert.equal(ended.dedupe_key, `dsn|end|DSS43|jno|${s.sourceTime}`);
  const again = diffDsn(r.next, added, "2026-09-30T18:03:23.000Z", "2026-09-30T18:03:23.000Z");
  assert.equal(again.events.length, 0, "an unchanged poll creates no events");
  const flicker = added.map((x) => (x.spacecraftCode === "imap" ? { ...x, band: "S+X" } : x));
  assert.equal(diffDsn(again.next, flicker, "2026-09-30T18:03:28.000Z", "t").events.length, 0, "a change within 60 s of the last update is held back");
  const later = diffDsn(again.next, flicker, "2026-09-30T18:04:30.000Z", "t");
  assert.deepEqual(later.events.map((e) => e.event_type), ["dsn_contact_updated"], "…and reported once the gap has passed");
  assert.equal(r.events.find((e) => e.event_type === "dsn_contact_started")!.mission, "Mars");
});

// ─── NOAA ──────────────────────────────────────────────────────────────────
test("NOAA: active L1 source only, wind + field merged per minute, nulls kept as missing", () => {
  const s = parseNoaa(json("noaa-wind.json"), json("noaa-mag.json"));
  assert.ok(s.length > 5);
  assert.ok(s.every((x) => x.time.endsWith(":00.000Z")));
  assert.ok(new Set(s.map((x) => x.source)).size === 1, "one active source at a time");
  assert.deepEqual([...s].sort((a, b) => a.time.localeCompare(b.time)), s, "ascending");
  const withNull = parseNoaa([{ time_tag: "2026-09-30T18:00:00", active: true, source: "SOLAR1", proton_speed: null, proton_density: 3.2, proton_temperature: null, overall_quality: 0 }], []);
  assert.equal(withNull[0].speed, null, "no silent interpolation");
  assert.equal(withNull[0].bz, null);
  assert.throws(() => parseNoaa({ nope: 1 }, []), SchemaError);
});

test("NOAA: dedupe key = measurement time + source", () => {
  const s = parseNoaa(json("noaa-wind.json"), json("noaa-mag.json"));
  const seen = new Set<string>();
  const first = dedupe(s.map((x) => noaaEvent(x, "t")), seen);
  const second = dedupe(s.map((x) => noaaEvent(x, "t2")), seen);
  assert.equal(first.length, s.length);
  assert.equal(second.length, 0);
  assert.equal(first[0].dedupe_key, DEDUPE.noaa(s[0]));
});

// ─── DONKI ─────────────────────────────────────────────────────────────────
test("DONKI: all six types parse with official IDs and links; HTTP error payload → schema error", () => {
  const all = (["CME", "FLR", "SEP", "IPS", "GST", "notifications"] as const).flatMap((t) => parseDonki(t, json(`donki-${t}.json`)));
  assert.ok(all.length > 40);
  const flr = all.find((e) => e.type === "FLR")!;
  assert.match(flr.id, /-FLR-\d+$/);
  assert.match(flr.title, /^Solar flare [ABCMX]/);
  assert.ok(all.every((e) => !Number.isNaN(Date.parse(e.time))));
  assert.ok(all.filter((e) => e.type !== "NOTIFICATION").every((e) => !e.link || e.link.startsWith("https://ccmc.gsfc.nasa.gov/")));
  assert.throws(() => parseDonki("CME", json("donki-error-400.json")), /HTTP 400/);
});

test("DONKI: dedupe by official ID (+ version) — re-polls create no duplicates", () => {
  const ev = parseDonki("FLR", json("donki-FLR.json"));
  const seen = new Set<string>();
  assert.equal(dedupe(ev.map((e) => donkiEvent(e, "a")), seen).length, ev.length);
  assert.equal(dedupe(ev.map((e) => donkiEvent(e, "b")), seen).length, 0);
});

// ─── Horizons ──────────────────────────────────────────────────────────────
test("Horizons: Earth–Mars geometry parsed; API version checked; errors surfaced", () => {
  const g = parseHorizons(json("horizons.json"));
  assert.equal(g.computedFor, "2026-09-30T18:03:00.000Z");
  assert.equal(g.apiVersion, "1.2");
  assert.ok(Math.abs(g.distanceAu! - 1.66713444726491) < 1e-12);
  assert.ok(Math.abs(g.distanceKm! / 1e6 - 249.4) < 0.1);
  assert.equal(g.rangeRateKmS, -11.8333686);
  assert.equal(g.lightTimeMin, 13.86513441);
  assert.equal(g.elongationDeg, 66.0554);
  assert.equal(g.raDec, "08 14 32.06 / +20 52 55.6");
  assert.throws(() => parseHorizons({ error: "Missing COMMAND specification" }), SchemaError);
  assert.throws(() => parseHorizons({ result: "x", signature: { version: "2.0" } }), SchemaError);
});

// ─── Mars images ───────────────────────────────────────────────────────────
test("Perseverance: images normalized with acquired / reached-Earth kept distinct; published unknown", () => {
  const im = parsePerseverance(json("perseverance.json"));
  assert.equal(im.length, 12);
  for (const i of im) {
    assert.equal(i.rover, "Perseverance");
    assert.ok(i.imageId && i.imageUrl.startsWith("https://"));
    assert.ok(i.acquired && i.reachedEarth && i.acquired <= i.reachedEarth, "acquired before reaching Earth");
    assert.equal(i.published, null, "the Mars 2020 feed has no publication timestamp — not invented");
    assert.equal(i.credit, "NASA/JPL-Caltech");
  }
});

test("Curiosity: acquired, reached-Earth and published are three distinct fields", () => {
  const im = parseCuriosity(json("curiosity.json"));
  assert.equal(im.length, 12);
  const i = im[0];
  assert.equal(i.rover, "Curiosity");
  assert.ok(i.acquired && i.reachedEarth && i.published);
  assert.ok(i.imageUrl.startsWith("https://"));
  assert.ok(typeof i.thumbnail === "boolean");
  assert.match(i.lmst ?? "", /^\d\d:\d\d:\d\d$/);
});

test("Mars image detection: new vs duplicate by image ID", () => {
  const im = parseCuriosity(json("curiosity.json"));
  const seen = new Set<string>();
  const first = dedupe(im.slice(4).map((i) => imageEvent(i, "t1")), seen);
  const next = dedupe(im.map((i) => imageEvent(i, "t2")), seen);
  assert.equal(first.length, im.length - 4);
  assert.equal(next.length, 4, "only the 4 not-yet-seen images are new");
  assert.ok(next.every((e) => e.event_type === "mars_image_published"));
  assert.ok(!/live/i.test(next[0].summary), "published, not 'live'");
});

// ─── health, staleness, ordering, time zones ───────────────────────────────
test("health: ONLINE / DEGRADED / STALE / OFFLINE and age labels", () => {
  const now = new Date("2026-09-30T18:10:00Z");
  const at = (s: number) => new Date(now.getTime() - s * 1000).toISOString();
  const st = (lastS: number | null, errs = 0, enabled = true) => ({ enabled, lastSuccess: lastS === null ? null : at(lastS), lastAttempt: at(1), lastError: errs ? "HTTP 500" : null, consecutiveErrors: errs });
  assert.equal(computeHealth(st(4), 5, now), "ONLINE");
  assert.equal(computeHealth(st(4, 1), 5, now), "DEGRADED");
  assert.equal(computeHealth(st(12), 5, now), "DEGRADED");
  assert.equal(computeHealth(st(40), 5, now), "STALE");
  assert.equal(computeHealth(st(3700), 5, now), "OFFLINE");
  assert.equal(computeHealth(st(null), 5, now), "OFFLINE");
  assert.equal(computeHealth(st(1, 0, false), 5, now), "OFFLINE");
  assert.equal(computeHealth(st(900), 300, now), "DEGRADED");
  assert.equal(ageLabel(at(4), "ONLINE", now), "updated 4 s ago");
  assert.equal(ageLabel(at(180), "ONLINE", now), "updated 3 min ago");
  assert.equal(ageLabel(at(37 * 60), "STALE", now), "STALE · last success 37 min ago");
});

test("time zones: every timestamp normalized to UTC ISO", () => {
  const p = parsePerseverance(json("perseverance.json"))[0];
  const c = parseCuriosity(json("curiosity.json"))[0];
  for (const t of [p.acquired, p.reachedEarth, c.acquired, c.reachedEarth, c.published]) assert.match(t!, /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$/);
  const d = parseDonki("FLR", json("donki-FLR.json"))[0];
  assert.match(d.time, /Z$/);
});

test("event ordering is deterministic (newest ingest first)", () => {
  const a = sourceEvent("dsn", false, "2026-09-30T18:00:01.000Z", "timeout");
  const b = sourceEvent("dsn", true, "2026-09-30T18:00:06.000Z", "recovered");
  assert.deepEqual(orderEvents([a, b]).map((e) => e.event_type), ["source_recovered", "source_error"]);
  assert.notEqual(a.dedupe_key, b.dedupe_key);
});

test("DSN: several signals per direction are combined stably (no update-event flapping)", () => {
  const xml = (order: string) => `<dsn><station name="cdscc" friendlyName="Canberra" timeUTC="1790791333000"/><dish name="DSS34" activity="x">${order}<target name="LRO" id="85" uplegRange="-1" downlegRange="368000" rtlt="-1"/></dish></dsn>`;
  const s1 = '<downSignal active="true" band="S" dataRate="146400" spacecraft="LRO" power="-120"/><downSignal active="true" band="K" dataRate="100000000" spacecraft="LRO" power="-118"/><upSignal active="true" band="S" dataRate="0" spacecraft="LRO" power="2"/>';
  const s2 = '<upSignal active="true" band="S" dataRate="0" spacecraft="LRO" power="2"/><downSignal active="true" band="K" dataRate="100000000" spacecraft="LRO" power="-118"/><downSignal active="true" band="S" dataRate="146400" spacecraft="LRO" power="-120"/>';
  const a = dsnContacts(parseDsn(xml(s1)))[0];
  const b = dsnContacts(parseDsn(xml(s2)))[0];
  assert.equal(a.band, "K+S");
  assert.equal(a.downRate, 100146400);
  assert.equal(a.downPower, -118);
  assert.deepEqual(a, b, "signal order in the XML does not change the contact");
  const seeded = diffDsn(new Map(), [a], "t0", "t0", true);
  assert.equal(diffDsn(seeded.next, [b], "t1", "t1").events.length, 0, "no spurious 'updated' event");
});
