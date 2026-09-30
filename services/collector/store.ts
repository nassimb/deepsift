/** Live Observatory store — dedicated SQLite (node:sqlite, WAL) under live_observatory/data/. Operational data only:
 *  this module never touches DEEPSIFT science artifacts, manifests or the frozen release data. */
import { statSync } from "node:fs";
import { DatabaseSync } from "node:sqlite";
import type { DonkiEvent, DsnContact, Geometry, LiveDataEvent, MarsImage, SolarWindSample, SourceDef } from "../../apps/web/lib/observatory/types.ts";

export const SCHEMA = `
CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY, name TEXT, provider TEXT, classification TEXT, endpoints TEXT, interval_s INTEGER, parser_version TEXT,
  enabled INTEGER DEFAULT 1, last_poll TEXT, last_success TEXT, last_source_time TEXT, last_ingest TEXT, last_error TEXT,
  consecutive_errors INTEGER DEFAULT 0, last_status INTEGER, last_duration_ms INTEGER, last_bytes INTEGER, last_parse TEXT, dedupe_drops INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS source_polls (
  id INTEGER PRIMARY KEY, source_id TEXT, at TEXT, status INTEGER, ok INTEGER, not_modified INTEGER, duration_ms INTEGER, bytes INTEGER,
  parse TEXT, error TEXT, new_events INTEGER, dedupe_drops INTEGER
);
CREATE INDEX IF NOT EXISTS source_polls_at ON source_polls(at);
CREATE TABLE IF NOT EXISTS events (
  seq INTEGER PRIMARY KEY, event_id TEXT, dedupe_key TEXT UNIQUE, source_id TEXT, event_type TEXT, classification TEXT,
  mission TEXT, spacecraft TEXT, instrument TEXT, ts_source TEXT, ts_ingested TEXT, ts_updated TEXT, status TEXT, bytes INTEGER,
  title TEXT, summary TEXT, raw_reference TEXT, source_url TEXT, metadata TEXT
);
CREATE INDEX IF NOT EXISTS events_ingested ON events(ts_ingested);
CREATE TABLE IF NOT EXISTS dsn_contacts (
  id INTEGER PRIMARY KEY, key TEXT, dish TEXT, complex TEXT, spacecraft_code TEXT, spacecraft_name TEXT, mars INTEGER, direction TEXT,
  band TEXT, down_rate REAL, up_rate REAL, start TEXT, end TEXT, last_seen TEXT, UNIQUE(key, start)
);
CREATE INDEX IF NOT EXISTS dsn_contacts_open ON dsn_contacts(end);
CREATE TABLE IF NOT EXISTS dsn_snapshots (at TEXT PRIMARY KEY, source_time TEXT, payload TEXT);
CREATE TABLE IF NOT EXISTS space_weather (
  time TEXT, source TEXT, speed REAL, density REAL, temperature REAL, bt REAL, bx REAL, by REAL, bz REAL, quality INTEGER, ingested TEXT, PRIMARY KEY(time, source)
);
CREATE TABLE IF NOT EXISTS donki_events (id TEXT, version TEXT, type TEXT, time TEXT, title TEXT, detail TEXT, link TEXT, first_seen TEXT, PRIMARY KEY(id, version));
CREATE TABLE IF NOT EXISTS geometry (
  computed_for TEXT PRIMARY KEY, distance_au REAL, distance_km REAL, range_rate REAL, light_time_min REAL, elongation REAL, ra_dec TEXT, api_version TEXT, ingested TEXT
);
CREATE TABLE IF NOT EXISTS mars_images (
  image_id TEXT PRIMARY KEY, rover TEXT, camera TEXT, camera_label TEXT, sol INTEGER, lmst TEXT, acquired TEXT, reached_earth TEXT, published TEXT,
  first_seen TEXT, backfill INTEGER, image_url TEXT, thumb_url TEXT, detail_url TEXT, width INTEGER, height INTEGER, sample_type TEXT, thumbnail INTEGER, credit TEXT, title TEXT
);
CREATE INDEX IF NOT EXISTS mars_images_seen ON mars_images(first_seen);
CREATE TABLE IF NOT EXISTS collector_metrics (at TEXT PRIMARY KEY, uptime_s INTEGER, db_bytes INTEGER, events_total INTEGER, payload TEXT);
`;

export class Store {
  db: DatabaseSync;
  path: string;
  constructor(path: string) {
    this.path = path;
    this.db = new DatabaseSync(path);
    this.db.exec("PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA busy_timeout=5000;");
    this.db.exec(SCHEMA);
  }

  registerSources(defs: (SourceDef & { intervalS: number })[]) {
    const st = this.db.prepare(`INSERT INTO sources (id, name, provider, classification, endpoints, interval_s, parser_version) VALUES (:id, :name, :provider, :classification, :endpoints, :interval_s, :parser_version)
      ON CONFLICT(id) DO UPDATE SET name=excluded.name, provider=excluded.provider, classification=excluded.classification, endpoints=excluded.endpoints, interval_s=excluded.interval_s, parser_version=excluded.parser_version`);
    for (const d of defs) st.run({ id: d.id, name: d.name, provider: d.provider, classification: d.classification, endpoints: d.endpoints.join(" "), interval_s: d.intervalS, parser_version: d.parserVersion });
  }

  recordPoll(p: { source: string; at: string; status: number; ok: boolean; notModified: boolean; durationMs: number; bytes: number; parse: string; error: string | null; newEvents: number; drops: number; sourceTime: string | null }) {
    this.db.prepare(`INSERT INTO source_polls (source_id, at, status, ok, not_modified, duration_ms, bytes, parse, error, new_events, dedupe_drops) VALUES (?,?,?,?,?,?,?,?,?,?,?)`)
      .run(p.source, p.at, p.status, p.ok ? 1 : 0, p.notModified ? 1 : 0, p.durationMs, p.bytes, p.parse, p.error, p.newEvents, p.drops);
    if (p.ok)
      this.db.prepare(`UPDATE sources SET last_poll=?, last_success=?, last_source_time=COALESCE(?, last_source_time), last_ingest=CASE WHEN ?>0 THEN ? ELSE last_ingest END, last_error=NULL, consecutive_errors=0, last_status=?, last_duration_ms=?, last_bytes=?, last_parse=?, dedupe_drops=dedupe_drops+? WHERE id=?`)
        .run(p.at, p.at, p.sourceTime, p.newEvents, p.at, p.status, p.durationMs, p.bytes, p.parse, p.drops, p.source);
    else
      this.db.prepare(`UPDATE sources SET last_poll=?, last_error=?, consecutive_errors=consecutive_errors+1, last_status=?, last_duration_ms=?, last_bytes=?, last_parse=? WHERE id=?`)
        .run(p.at, p.error, p.status, p.durationMs, p.bytes, p.parse, p.source);
  }

  /** Insert if the dedupe key is new. Returns true when stored (false = duplicate, dropped). */
  insertEvent(e: LiveDataEvent): boolean {
    const r = this.db.prepare(`INSERT OR IGNORE INTO events (event_id, dedupe_key, source_id, event_type, classification, mission, spacecraft, instrument, ts_source, ts_ingested, ts_updated, status, bytes, title, summary, raw_reference, source_url, metadata)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`).run(e.event_id, e.dedupe_key, e.source_id, e.event_type, e.classification, e.mission, e.spacecraft, e.instrument, e.timestamp_source, e.timestamp_ingested, e.timestamp_updated, e.status, e.bytes, e.title, e.summary, e.raw_reference, e.source_url, JSON.stringify(e.metadata));
    return Number(r.changes) > 0;
  }

  openContact(c: DsnContact, start: string) {
    this.db.prepare(`INSERT OR IGNORE INTO dsn_contacts (key, dish, complex, spacecraft_code, spacecraft_name, mars, direction, band, down_rate, up_rate, start, end, last_seen) VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,?)`)
      .run(c.key, c.dish, c.complex, c.spacecraftCode, c.spacecraftName, c.mars ? 1 : 0, c.direction, c.band, c.downRate, c.upRate, start, start);
  }
  touchContact(c: DsnContact, start: string, at: string) {
    this.db.prepare(`UPDATE dsn_contacts SET direction=?, band=?, down_rate=?, up_rate=?, last_seen=? WHERE key=? AND start=?`).run(c.direction, c.band, c.downRate, c.upRate, at, c.key, start);
  }
  closeContact(key: string, start: string, end: string) {
    this.db.prepare(`UPDATE dsn_contacts SET end=? WHERE key=? AND start=?`).run(end, key, start);
  }
  /** Contacts left open by a previous run: closed at their last observation (we don't know what happened after). */
  closeStaleContacts() {
    this.db.prepare(`UPDATE dsn_contacts SET end=last_seen WHERE end IS NULL`).run();
  }
  snapshot(at: string, sourceTime: string, payload: unknown) {
    this.db.prepare(`INSERT OR IGNORE INTO dsn_snapshots (at, source_time, payload) VALUES (?,?,?)`).run(at, sourceTime, JSON.stringify(payload));
  }

  latestWeatherTime(): string | null {
    return (this.db.prepare(`SELECT MAX(time) AS t FROM space_weather`).get() as { t: string | null }).t;
  }
  insertWeather(s: SolarWindSample, at: string): boolean {
    const r = this.db.prepare(`INSERT OR IGNORE INTO space_weather VALUES (?,?,?,?,?,?,?,?,?,?,?)`).run(s.time, s.source, s.speed, s.density, s.temperature, s.bt, s.bx, s.by, s.bz, s.quality, at);
    return Number(r.changes) > 0;
  }
  insertDonki(e: DonkiEvent, at: string): boolean {
    const r = this.db.prepare(`INSERT OR IGNORE INTO donki_events VALUES (?,?,?,?,?,?,?,?)`).run(e.id, e.version ?? "", e.type, e.time, e.title, e.detail, e.link, at);
    return Number(r.changes) > 0;
  }
  donkiCount(): number {
    return Number((this.db.prepare(`SELECT COUNT(*) AS n FROM donki_events`).get() as { n: number }).n);
  }
  insertGeometry(g: Geometry, at: string): boolean {
    const r = this.db.prepare(`INSERT OR IGNORE INTO geometry VALUES (?,?,?,?,?,?,?,?,?)`).run(g.computedFor, g.distanceAu, g.distanceKm, g.rangeRateKmS, g.lightTimeMin, g.elongationDeg, g.raDec, g.apiVersion, at);
    return Number(r.changes) > 0;
  }
  hasImage(id: string): boolean {
    return !!this.db.prepare(`SELECT 1 FROM mars_images WHERE image_id=?`).get(id);
  }
  imageCount(rover: string): number {
    return Number((this.db.prepare(`SELECT COUNT(*) AS n FROM mars_images WHERE rover=?`).get(rover) as { n: number }).n);
  }
  insertImage(i: MarsImage, firstSeen: string, backfill: boolean): boolean {
    const r = this.db.prepare(`INSERT OR IGNORE INTO mars_images VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`).run(
      i.imageId, i.rover, i.camera, i.cameraLabel, i.sol, i.lmst, i.acquired, i.reachedEarth, i.published, firstSeen, backfill ? 1 : 0,
      i.imageUrl, i.thumbUrl, i.detailUrl, i.width, i.height, i.sampleType, i.thumbnail ? 1 : 0, i.credit, i.title);
    return Number(r.changes) > 0;
  }

  // ─── queries for the API ───
  sources() {
    return this.db.prepare(`SELECT * FROM sources ORDER BY rowid`).all() as Record<string, unknown>[];
  }
  events(opts: { since?: string | null; limit?: number; source?: string | null; afterSeq?: number | null }) {
    const where: string[] = [];
    const args: (string | number)[] = [];
    if (opts.since) { where.push("ts_ingested >= ?"); args.push(opts.since); }
    if (opts.source) { where.push("source_id = ?"); args.push(opts.source); }
    if (opts.afterSeq) { where.push("seq > ?"); args.push(opts.afterSeq); }
    const rows = this.db.prepare(`SELECT * FROM events ${where.length ? "WHERE " + where.join(" AND ") : ""} ORDER BY seq DESC LIMIT ?`).all(...args, Math.min(opts.limit ?? 200, 1000)) as Record<string, unknown>[];
    return rows.map(rowToEvent);
  }
  counts() {
    const today = new Date().toISOString().slice(0, 10);
    const t = this.db.prepare(`SELECT COUNT(*) AS n, MAX(ts_ingested) AS last FROM events`).get() as { n: number; last: string | null };
    const d = this.db.prepare(`SELECT COUNT(*) AS n FROM events WHERE ts_ingested >= ?`).get(today) as { n: number };
    return { total: Number(t.n), today: Number(d.n), last: t.last };
  }
  timeline(from: string) {
    const contacts = this.db.prepare(`SELECT * FROM dsn_contacts WHERE end IS NULL OR end >= ? ORDER BY start`).all(from) as Record<string, unknown>[];
    const hours = (Date.now() - Date.parse(from)) / 3_600_000;
    const weather = this.db.prepare(`SELECT * FROM space_weather WHERE time >= ? ${hours > 6 ? "AND CAST(strftime('%M', time) AS INTEGER) % 5 = 0" : ""} ORDER BY time`).all(from) as Record<string, unknown>[];
    const donki = this.db.prepare(`SELECT * FROM donki_events WHERE time >= ? ORDER BY time`).all(from) as Record<string, unknown>[];
    const geometry = this.db.prepare(`SELECT * FROM geometry WHERE computed_for >= ? ORDER BY computed_for`).all(from) as Record<string, unknown>[];
    // images discovered live are placed at first-seen; the start-up backfill is placed at NASA's own time (never at the collector start)
    const images = this.db.prepare(`SELECT * FROM mars_images WHERE thumbnail = 0 AND ((backfill = 0 AND first_seen >= ?) OR (backfill = 1 AND COALESCE(published, reached_earth) >= ?)) ORDER BY first_seen DESC LIMIT 800`).all(from, from) as Record<string, unknown>[];
    return {
      from,
      contacts: contacts.map((c) => ({ key: c.key, dish: c.dish, complex: c.complex, spacecraftName: c.spacecraft_name, mars: c.mars === 1, direction: c.direction, band: c.band, downRate: c.down_rate, start: c.start, end: c.end })),
      weather: weather.map((w) => ({ time: w.time, source: w.source, speed: w.speed, density: w.density, temperature: w.temperature, bt: w.bt, bx: w.bx, by: w.by, bz: w.bz, quality: w.quality })),
      donki: donki.map((d) => ({ id: d.id, type: d.type, time: d.time, title: d.title, detail: d.detail, link: d.link, version: d.version || null })),
      geometry: geometry.map((g) => ({ computedFor: g.computed_for, distanceAu: g.distance_au, distanceKm: g.distance_km, rangeRateKmS: g.range_rate, lightTimeMin: g.light_time_min, elongationDeg: g.elongation, raDec: g.ra_dec, apiVersion: g.api_version })),
      images: images.map(rowToImage),
    };
  }
  latestImages(limit = 40) {
    return (this.db.prepare(`SELECT * FROM mars_images WHERE thumbnail = 0 ORDER BY first_seen DESC, COALESCE(published, reached_earth) DESC LIMIT ?`).all(limit) as Record<string, unknown>[]).map(rowToImage);
  }
  openContacts() {
    return this.db.prepare(`SELECT * FROM dsn_contacts WHERE end IS NULL ORDER BY start`).all() as Record<string, unknown>[];
  }
  recentPolls(limit = 60) {
    return this.db.prepare(`SELECT * FROM source_polls ORDER BY id DESC LIMIT ?`).all(limit) as Record<string, unknown>[];
  }
  bytes(): number {
    let n = 0;
    for (const suffix of ["", "-wal", "-shm"]) try { n += statSync(this.path + suffix).size; } catch {}
    return n;
  }
  metric(at: string, uptimeS: number, payload: unknown) {
    this.db.prepare(`INSERT OR REPLACE INTO collector_metrics VALUES (?,?,?,?,?)`).run(at, uptimeS, this.bytes(), this.counts().total, JSON.stringify(payload));
  }

  /** Retention (architecture review §6): raw DSN snapshots 7 d; contacts forever; NOAA 1-min 90 d then hourly;
   *  Horizons 5-min 7 d then hourly; image metadata forever; solar-wind sample events 7 d (samples stay); polls 7 d. */
  retention(now: Date) {
    const d = (days: number) => new Date(now.getTime() - days * 86_400_000).toISOString();
    const r = {
      snapshots: this.db.prepare(`DELETE FROM dsn_snapshots WHERE at < ?`).run(d(7)).changes,
      polls: this.db.prepare(`DELETE FROM source_polls WHERE at < ?`).run(d(7)).changes,
      windEvents: this.db.prepare(`DELETE FROM events WHERE event_type='solar_wind_sample' AND ts_ingested < ?`).run(d(7)).changes,
      weather: this.db.prepare(`DELETE FROM space_weather WHERE time < ? AND substr(time, 15, 2) <> '00'`).run(d(90)).changes,
      geometry: this.db.prepare(`DELETE FROM geometry WHERE computed_for < ? AND substr(computed_for, 15, 2) <> '00'`).run(d(7)).changes,
      metrics: this.db.prepare(`DELETE FROM collector_metrics WHERE at < ?`).run(d(30)).changes,
    };
    return Object.fromEntries(Object.entries(r).map(([k, v]) => [k, Number(v)]));
  }
}

function rowToEvent(r: Record<string, unknown>): LiveDataEvent & { seq: number } {
  return {
    seq: Number(r.seq), event_id: r.event_id as string, dedupe_key: r.dedupe_key as string, source_id: r.source_id as LiveDataEvent["source_id"], source_name: "", provider: "",
    classification: r.classification as LiveDataEvent["classification"], event_type: r.event_type as LiveDataEvent["event_type"], mission: (r.mission as string) ?? null,
    spacecraft: (r.spacecraft as string) ?? null, instrument: (r.instrument as string) ?? null, timestamp_source: (r.ts_source as string) ?? null,
    timestamp_ingested: r.ts_ingested as string, timestamp_updated: (r.ts_updated as string) ?? null, status: (r.status as string) ?? null,
    bytes: r.bytes === null ? null : Number(r.bytes), title: r.title as string, summary: r.summary as string, raw_reference: (r.raw_reference as string) ?? null,
    source_url: (r.source_url as string) ?? null, metadata: JSON.parse((r.metadata as string) || "{}"),
  };
}

function rowToImage(r: Record<string, unknown>) {
  return {
    imageId: r.image_id, rover: r.rover, camera: r.camera, cameraLabel: r.camera_label, sol: r.sol, lmst: r.lmst, acquired: r.acquired, reachedEarth: r.reached_earth,
    published: r.published, firstSeen: r.first_seen, backfill: r.backfill === 1, imageUrl: r.image_url, thumbUrl: r.thumb_url, detailUrl: r.detail_url,
    width: r.width, height: r.height, sampleType: r.sample_type, thumbnail: r.thumbnail === 1, credit: r.credit, title: r.title,
  };
}
