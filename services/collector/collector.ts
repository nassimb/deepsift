/** DEEPSIFT Live Observatory collector — a genuine always-running process.
 *  Polls the official sources (intervals configurable), normalizes + dedupes, stores history in SQLite, and serves a
 *  read-only API + Server-Sent Events on 127.0.0.1. Operational data only (live_observatory/data/), never science.
 *
 *    node services/collector/collector.ts            # defaults: DSN 5 s, NOAA 5 min, DONKI 10 min, Horizons 5 min,
 *                                                    #           Curiosity 3 min, Perseverance 5 min
 *  env: COLLECTOR_PORT (8790, full local API incl. token-protected admin) · COLLECTOR_DB (live_observatory/data/observatory.sqlite)
 *       COLLECTOR_ADMIN_TOKEN · COLLECTOR_PUBLIC_PORT (e.g. 8791: READ-ONLY listener — the only port a tunnel may expose)
 *       COLLECTOR_READ_TOKEN (optional; when set, the public listener requires "Authorization: Bearer <token>" except /healthz)
 *       POLL_DSN_S · POLL_NOAA_S · POLL_DONKI_S · POLL_HORIZONS_S · POLL_CURIOSITY_S · POLL_PERSEVERANCE_S · DISABLE_<SOURCE>=1 */
import { mkdirSync } from "node:fs";
import { createServer, type ServerResponse } from "node:http";
import { dirname, join } from "node:path";
import { diffDsn, donkiEvent, horizonsEvent, imageEvent, noaaEvent, sourceEvent, type TrackedContact } from "../../apps/web/lib/observatory/events.ts";
import { fetchCuriosity, fetchDonki, fetchDsn, fetchDsnNames, fetchHorizons, fetchNoaa, fetchPerseverance, type FetchMeta } from "../../apps/web/lib/observatory/fetchers.ts";
import { computeHealth } from "../../apps/web/lib/observatory/health.ts";
import { dsnContacts } from "../../apps/web/lib/observatory/parsers.ts";
import { SOURCES } from "../../apps/web/lib/observatory/registry.ts";
import type { LiveDataEvent, MarsImage, SourceId } from "../../apps/web/lib/observatory/types.ts";
import { Store } from "./store.ts";

export const COLLECTOR_VERSION = "collector/0.1.0";
const ROOT = join(import.meta.dirname, "../..");
const env = process.env;
const DB_PATH = env.COLLECTOR_DB ?? join(ROOT, "live_observatory/data/observatory.sqlite");
const PORT = Number(env.COLLECTOR_PORT ?? 8790);
const ADMIN_TOKEN = env.COLLECTOR_ADMIN_TOKEN ?? "";
const PUBLIC_PORT = env.COLLECTOR_PUBLIC_PORT ? Number(env.COLLECTOR_PUBLIC_PORT) : null;
const READ_TOKEN = env.COLLECTOR_READ_TOKEN ?? "";
/** Routes the public (tunnel-facing) listener serves. GET only; no admin, no writes. */
export const PUBLIC_ROUTES = new Set(["/healthz", "/status", "/metrics", "/events", "/stream", "/timeline", "/images", "/dsn-contacts", "/polls"]);
const DEFAULT_S: Record<SourceId, number> = { dsn: 5, noaa: 300, donki: 600, horizons: 300, curiosity: 180, perseverance: 300 };
const interval = (id: SourceId) => Number(env[`POLL_${id.toUpperCase()}_S`] ?? DEFAULT_S[id]);
const enabled = (id: SourceId) => env[`DISABLE_${id.toUpperCase()}`] !== "1";

mkdirSync(dirname(DB_PATH), { recursive: true });
const store = new Store(DB_PATH);
store.registerSources(SOURCES.map((s) => ({ ...s, intervalS: interval(s.id) })));
store.closeStaleContacts();
const startedAt = new Date();
const iso = () => new Date().toISOString();

// ─── SSE fan-out ───
const clients = new Set<ServerResponse>();
function emit(e: LiveDataEvent) {
  const line = `event: live\ndata: ${JSON.stringify(e)}\n\n`;
  for (const c of clients) c.write(line);
}
function store1(e: LiveDataEvent): boolean {
  const ok = store.insertEvent(e);
  if (ok) emit(e);
  return ok;
}

// ─── per-source pollers ───
type PollResult = { meta: FetchMeta; parse: string; events: LiveDataEvent[]; drops: number; sourceTime: string | null };
const failing: Partial<Record<SourceId, boolean>> = {};
const timers: Partial<Record<SourceId, NodeJS.Timeout>> = {};
const running: Partial<Record<SourceId, boolean>> = {};

let dsnNames: Record<string, string> = {};
let dsnNamesAt = 0;
let dsnContactsState: Map<string, TrackedContact> | null = null;
let lastSnapshot = 0;
let noaaLastModified: string | null = null;

const POLLERS: Record<SourceId, () => Promise<PollResult>> = {
  async dsn() {
    if (Date.now() - dsnNamesAt > 86_400_000) {
      const n = await fetchDsnNames();
      if (n.data) { dsnNames = n.data; dsnNamesAt = Date.now(); }
    }
    const r = await fetchDsn();
    if (!r.data) return { meta: r.meta, parse: r.meta.error?.includes("schema") ? "schema-error" : "no-data", events: [], drops: 0, sourceTime: null };
    const now = iso();
    const contacts = dsnContacts(r.data, dsnNames);
    const seed = dsnContactsState === null;
    const d = diffDsn(dsnContactsState ?? new Map(), contacts, r.data.sourceTime, now, false);
    // on (re)start, open contacts are recorded as starting now: we did not observe them earlier
    for (const [k, c] of d.next) {
      const prev = dsnContactsState?.get(k);
      if (!prev) store.openContact(c, c.since);
      else store.touchContact(c, c.since, r.data.sourceTime);
    }
    for (const [k, p] of dsnContactsState ?? new Map()) if (!d.next.has(k)) store.closeContact(k, p.since, r.data.sourceTime);
    dsnContactsState = d.next;
    if (Date.now() - lastSnapshot > 300_000) { store.snapshot(now, r.data.sourceTime, { contacts, dishes: r.data.dishes.map((x) => ({ n: x.name, a: x.activity, az: x.azimuth, el: x.elevation })) }); lastSnapshot = Date.now(); }
    let drops = 0;
    const events = seed ? d.events.filter((e) => e.event_type === "dsn_contact_started").map((e) => ({ ...e, summary: `${e.summary} (already active when the collector started)` })) : d.events;
    const stored = events.filter((e) => store1(e) || (drops++, false));
    return { meta: r.meta, parse: "ok", events: stored, drops, sourceTime: r.data.sourceTime };
  },
  async noaa() {
    const r = await fetchNoaa(noaaLastModified);
    if (r.meta.notModified) return { meta: r.meta, parse: "not-modified", events: [], drops: 0, sourceTime: null };
    if (!r.data) return { meta: r.meta, parse: "error", events: [], drops: 0, sourceTime: null };
    noaaLastModified = r.meta.lastModified ?? null;
    const now = iso();
    const lastStored = store.latestWeatherTime();
    let drops = 0;
    const events: LiveDataEvent[] = [];
    for (const s of r.data) {
      const fresh = store.insertWeather(s, now);
      if (!fresh) { drops++; continue; }
      // backfill of the 24 h file on first run is stored as measurements, but only samples newer than what we had become events
      if (lastStored && s.time > lastStored) { const e = noaaEvent(s, now); if (store1(e)) events.push(e); }
    }
    return { meta: r.meta, parse: "ok", events, drops, sourceTime: r.data.at(-1)?.time ?? null };
  },
  async donki() {
    const r = await fetchDonki(new Date(), 7);
    if (!r.data) return { meta: r.meta, parse: "error", events: [], drops: 0, sourceTime: null };
    const now = iso();
    const seed = store.donkiCount() === 0;
    let drops = 0;
    const events: LiveDataEvent[] = [];
    for (const e of r.data) {
      if (!store.insertDonki(e, now)) { drops++; continue; }
      if (!seed) { const ev = donkiEvent(e, now); if (store1(ev)) events.push(ev); }
    }
    return { meta: r.meta, parse: r.meta.ok ? "ok" : "partial", events, drops, sourceTime: r.data[0]?.time ?? null };
  },
  async horizons() {
    const r = await fetchHorizons(new Date());
    if (!r.data) return { meta: r.meta, parse: "error", events: [], drops: 0, sourceTime: null };
    const now = iso();
    if (!store.insertGeometry(r.data, now)) return { meta: r.meta, parse: "ok", events: [], drops: 1, sourceTime: r.data.computedFor };
    const e = horizonsEvent(r.data, now);
    return { meta: r.meta, parse: "ok", events: store1(e) ? [e] : [], drops: 0, sourceTime: r.data.computedFor };
  },
  async curiosity() {
    return pollImages("Curiosity", async (page) => fetchCuriosity(100, page));
  },
  async perseverance() {
    return pollImages("Perseverance", async () => fetchPerseverance(100));
  },
};

async function pollImages(rover: "Curiosity" | "Perseverance", fetchPage: (page: number) => Promise<{ meta: FetchMeta; data: MarsImage[] | null }>): Promise<PollResult> {
  const seed = store.imageCount(rover) === 0;
  let r = await fetchPage(0);
  if (!r.data) return { meta: r.meta, parse: "error", events: [], drops: 0, sourceTime: null };
  const meta = r.meta;
  const now = iso();
  const events: LiveDataEvent[] = [];
  let drops = 0;
  // newest first: walk until an already-known image; page back (Curiosity) if a whole page is new
  for (let page = 0; page < 4 && r.data; page++) {
    let hitKnown = false;
    for (const i of r.data) {
      if (store.hasImage(i.imageId)) { hitKnown = true; drops++; continue; }
      store.insertImage(i, now, seed);
      if (!seed && !i.thumbnail) { const e = imageEvent(i, now); if (store1(e)) events.push(e); }
    }
    if (hitKnown || seed || rover === "Perseverance") break;
    r = await fetchPage(page + 1);
  }
  return { meta, parse: "ok", events, drops, sourceTime: r.data?.[0]?.published ?? r.data?.[0]?.reachedEarth ?? null };
}

async function runPoll(id: SourceId) {
  if (running[id]) return;
  running[id] = true;
  const at = iso();
  let res: PollResult;
  try {
    res = await POLLERS[id]();
  } catch (e) {
    res = { meta: { ok: false, status: 0, bytes: 0, durationMs: 0, error: (e as Error).message }, parse: "exception", events: [], drops: 0, sourceTime: null };
  }
  const ok = res.meta.ok && res.parse !== "error" && res.parse !== "schema-error" && res.parse !== "no-data";
  store.recordPoll({ source: id, at, status: res.meta.status, ok, notModified: !!res.meta.notModified, durationMs: res.meta.durationMs, bytes: res.meta.bytes, parse: res.parse, error: ok ? null : res.meta.error ?? res.parse, newEvents: res.events.length, drops: res.drops, sourceTime: res.sourceTime });
  if (!ok && !failing[id]) { store1(sourceEvent(id, false, at, res.meta.error ?? res.parse)); console.warn(`[${at}] ${id}: ERROR ${res.meta.error ?? res.parse}`); }
  if (ok && failing[id]) { store1(sourceEvent(id, true, at, "source recovered")); console.log(`[${at}] ${id}: recovered`); }
  failing[id] = !ok;
  running[id] = false;
  schedule(id, ok);
}

const errors: Partial<Record<SourceId, number>> = {};
function schedule(id: SourceId, ok: boolean) {
  errors[id] = ok ? 0 : (errors[id] ?? 0) + 1;
  // exponential backoff on errors (max 16× the interval, capped at 30 min) — never hammer a failing source
  const base = interval(id) * 1000;
  const delay = ok ? base : Math.min(base * 2 ** Math.min(errors[id]!, 4), 30 * 60_000);
  clearTimeout(timers[id]);
  timers[id] = setTimeout(() => void runPoll(id), delay);
}

// ─── HTTP API (read-only) + SSE + token-protected force refresh ───
function status() {
  const now = new Date();
  const c = store.counts();
  return {
    ok: true, version: COLLECTOR_VERSION, startedAt: startedAt.toISOString(), uptimeS: Math.round((now.getTime() - startedAt.getTime()) / 1000), dbBytes: store.bytes(),
    eventsTotal: c.total, eventsToday: c.today, lastEventAt: c.last, dbPath: "live_observatory/data/observatory.sqlite",
    sources: store.sources().map((s) => {
      const id = s.id as SourceId;
      const st = { enabled: enabled(id), lastSuccess: (s.last_success as string) ?? null, lastAttempt: (s.last_poll as string) ?? null, lastError: (s.last_error as string) ?? null, consecutiveErrors: Number(s.consecutive_errors ?? 0) };
      return {
        id, name: s.name, classification: s.classification, enabled: st.enabled, intervalS: interval(id), health: computeHealth(st, interval(id), now),
        lastPoll: st.lastAttempt, lastSuccess: st.lastSuccess, lastSourceTime: s.last_source_time ?? null, lastIngest: s.last_ingest ?? null, lastError: st.lastError,
        consecutiveErrors: st.consecutiveErrors, pollMs: s.last_duration_ms ?? null, bytes: s.last_bytes ?? null, parse: s.last_parse ?? null, status: s.last_status ?? null,
        dedupeDrops: Number(s.dedupe_drops ?? 0), parserVersion: s.parser_version,
      };
    }),
  };
}

const json = (res: ServerResponse, code: number, body: unknown) => {
  res.writeHead(code, { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" });
  res.end(JSON.stringify(body));
};

function metrics() {
  const now = Date.now();
  const hourAgo = new Date(now - 3_600_000).toISOString();
  const polls = store.db.prepare(`SELECT source_id, COUNT(*) AS n, SUM(ok = 0) AS errors, AVG(duration_ms) AS avg_ms, MAX(duration_ms) AS max_ms, SUM(new_events) AS new_events, SUM(dedupe_drops) AS drops FROM source_polls WHERE at >= ? GROUP BY source_id`).all(hourAgo) as Record<string, unknown>[];
  const c = store.counts();
  return {
    ok: true, version: COLLECTOR_VERSION, uptimeS: Math.round((now - startedAt.getTime()) / 1000), dbBytes: store.bytes(), eventsTotal: c.total, eventsToday: c.today,
    sseClients: clients.size, memoryRssBytes: process.memoryUsage().rss,
    lastHour: Object.fromEntries(polls.map((p) => [p.source_id, { polls: Number(p.n), errors: Number(p.errors), avgMs: Math.round(Number(p.avg_ms)), maxMs: Number(p.max_ms), newEvents: Number(p.new_events), dedupeDrops: Number(p.drops) }])),
    lagS: Object.fromEntries(store.sources().map((s) => [s.id, s.last_success ? Math.round((now - Date.parse(s.last_success as string)) / 1000) : null])),
  };
}

/** Liveness for systemd / tunnels / Vercel: 200 while the process polls something successfully within 10 min. */
function healthz() {
  const st = status();
  const online = st.sources.filter((s) => s.health === "ONLINE").map((s) => s.id);
  const recent = st.sources.some((s) => s.lastSuccess && Date.now() - Date.parse(s.lastSuccess) < 600_000);
  return { code: recent ? 200 : 503, body: { ok: recent, version: COLLECTOR_VERSION, uptimeS: st.uptimeS, online, notOnline: st.sources.filter((s) => s.health !== "ONLINE").map((s) => `${s.id}:${s.health}`) } };
}

function handler(publicListener: boolean) {
  return (req: import("node:http").IncomingMessage, res: ServerResponse) => {
    const u = new URL(req.url ?? "/", "http://localhost");
    const q = (k: string) => u.searchParams.get(k);
    try {
      if (publicListener) {
        // read-only surface: GET on an allow-list only; optional bearer token (all but /healthz)
        if (req.method !== "GET" || !PUBLIC_ROUTES.has(u.pathname)) return json(res, 404, { ok: false, error: "not found" });
        if (READ_TOKEN && u.pathname !== "/healthz" && req.headers.authorization !== `Bearer ${READ_TOKEN}`) return json(res, 401, { ok: false, error: "unauthorized" });
      } else if (req.method === "POST" && u.pathname === "/admin/refresh") {
        const auth = req.headers.authorization ?? "";
        if (!ADMIN_TOKEN || auth !== `Bearer ${ADMIN_TOKEN}`) return json(res, 401, { ok: false, error: "unauthorized" });
        const id = q("source") as SourceId;
        if (!SOURCES.some((s) => s.id === id)) return json(res, 400, { ok: false, error: "unknown source" });
        console.log(`[${iso()}] force refresh: ${id}`);
        void runPoll(id);
        return json(res, 202, { ok: true, refreshing: id });
      }
      if (req.method !== "GET") return json(res, 405, { ok: false });
      if (u.pathname === "/healthz") { const h = healthz(); return json(res, h.code, h.body); }
      if (u.pathname === "/metrics") return json(res, 200, metrics());
      if (u.pathname === "/status") return json(res, 200, status());
      if (u.pathname === "/events") return json(res, 200, { events: store.events({ since: q("since"), limit: Number(q("limit") ?? 200), source: q("source"), afterSeq: q("after") ? Number(q("after")) : null }) });
      if (u.pathname === "/timeline") return json(res, 200, store.timeline(q("from") ?? new Date(Date.now() - 6 * 3_600_000).toISOString()));
      if (u.pathname === "/images") return json(res, 200, { images: store.latestImages(Math.min(Number(q("limit") ?? 40), 200)) });
      if (u.pathname === "/dsn-contacts") return json(res, 200, { open: store.openContacts() });
      if (u.pathname === "/polls") return json(res, 200, { polls: store.recentPolls(Math.min(Number(q("limit") ?? 60), 500)) });
      if (u.pathname === "/stream") {
        res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-store", connection: "keep-alive", "x-accel-buffering": "no" });
        res.write(`event: hello\ndata: ${JSON.stringify({ version: COLLECTOR_VERSION, at: iso() })}\n\n`);
        clients.add(res);
        const hb = setInterval(() => res.write(`: heartbeat ${iso()}\n\n`), 15_000);
        req.on("close", () => { clearInterval(hb); clients.delete(res); });
        return;
      }
      json(res, 404, { ok: false, error: "not found" });
    } catch (e) {
      json(res, 500, { ok: false, error: (e as Error).message });
    }
  };
}

const server = createServer(handler(false));
const publicServer = PUBLIC_PORT ? createServer(handler(true)) : null;

server.listen(PORT, "127.0.0.1", () => {
  console.log(`[${iso()}] ${COLLECTOR_VERSION} listening on http://127.0.0.1:${PORT} (full, local only) · db ${DB_PATH}`);
  if (publicServer) publicServer.listen(PUBLIC_PORT!, "127.0.0.1", () => console.log(`[${iso()}] read-only listener on http://127.0.0.1:${PUBLIC_PORT} (${READ_TOKEN ? "bearer token required" : "no token"}) — the only port a tunnel may expose`));
  for (const s of SOURCES) {
    if (!enabled(s.id)) { console.log(`  ${s.id}: disabled`); continue; }
    console.log(`  ${s.id}: every ${interval(s.id)} s`);
    timers[s.id] = setTimeout(() => void runPoll(s.id), 500 + SOURCES.indexOf(s) * 700);
  }
});

// retention hourly, metrics every 5 min
setInterval(() => { const r = store.retention(new Date()); console.log(`[${iso()}] retention`, r); }, 3_600_000);
setInterval(() => store.metric(iso(), Math.round((Date.now() - startedAt.getTime()) / 1000), { clients: clients.size }), 300_000);

let stopping = false;
const shutdown = (signal: string) => {
  if (stopping) return;
  stopping = true;
  console.log(`[${iso()}] ${signal}: shutting down`);
  for (const t of Object.values(timers)) clearTimeout(t);
  for (const c of clients) c.end();
  server.close();
  publicServer?.close();
  try {
    store.db.exec("PRAGMA wal_checkpoint(TRUNCATE)"); // fold the WAL back into the database file before exit
    store.db.close();
  } catch (e) {
    console.error(`[${iso()}] close error: ${(e as Error).message}`);
  }
  console.log(`[${iso()}] stopped cleanly`);
  process.exit(0);
};
process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));
// crash → non-zero exit so the supervisor (systemd Restart=always) restarts us; SQLite WAL recovers on the next open
process.on("uncaughtException", (e) => { console.error(`[${iso()}] FATAL ${e.stack ?? e}`); process.exit(1); });
process.on("unhandledRejection", (e) => { console.error(`[${iso()}] FATAL unhandled rejection ${String(e)}`); process.exit(1); });
