/** Upstream fetchers (network side of the adapters). Shared by the Tier 0 routes and the collector. Timeouts, an
 *  identifying User-Agent, gzip and conditional requests — never hammer the sources. Parsing lives in parsers.ts. */
import { parseCuriosity, parseDonki, parseDsn, parseDsnConfig, parseHorizons, parseNoaa, parsePerseverance, horizonsQuery, DONKI_TYPES } from "./parsers.ts";
import { CURIOSITY_URL, DONKI_BASE, DSN_CONFIG_URL, DSN_URL, HORIZONS_URL, NOAA_MAG_URL, NOAA_WIND_URL, PERSEVERANCE_URL } from "./registry.ts";
import type { DonkiEvent, DsnState, Geometry, MarsImage, SolarWindSample } from "./types.ts";

export const USER_AGENT = "DEEPSIFT-observatory/1 (+https://deepsift.space; independent research monitoring)";

export interface FetchMeta {
  ok: boolean;
  status: number;
  bytes: number;
  durationMs: number;
  notModified?: boolean;
  lastModified?: string | null;
  error?: string;
}

async function get(url: string, opts: { timeoutMs?: number; ifModifiedSince?: string | null; accept?: string } = {}): Promise<{ meta: FetchMeta; text: string }> {
  const t0 = Date.now();
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), opts.timeoutMs ?? 20_000);
  try {
    const headers: Record<string, string> = { "user-agent": USER_AGENT, "accept-encoding": "gzip", accept: opts.accept ?? "application/json, text/xml;q=0.9, */*;q=0.5" };
    if (opts.ifModifiedSince) headers["if-modified-since"] = opts.ifModifiedSince;
    const res = await fetch(url, { headers, signal: ctl.signal, cache: "no-store", redirect: "manual" });
    const text = res.status === 304 ? "" : await res.text();
    const meta: FetchMeta = { ok: res.status === 200 || res.status === 304, status: res.status, bytes: text.length, durationMs: Date.now() - t0, notModified: res.status === 304, lastModified: res.headers.get("last-modified") };
    if (res.status >= 300 && res.status < 400) meta.error = `redirected (${res.status}) to ${res.headers.get("location") ?? "?"} — endpoint may have moved`;
    else if (!meta.ok) meta.error = `HTTP ${res.status}`;
    return { meta, text };
  } catch (e) {
    return { meta: { ok: false, status: 0, bytes: 0, durationMs: Date.now() - t0, error: (e as Error).name === "AbortError" ? "timeout" : (e as Error).message }, text: "" };
  } finally {
    clearTimeout(timer);
  }
}

export type Fetched<T> = { meta: FetchMeta; data: T | null };

const wrap = <T>(meta: FetchMeta, f: () => T): Fetched<T> => {
  if (!meta.ok || meta.notModified) return { meta, data: null };
  try {
    return { meta, data: f() };
  } catch (e) {
    return { meta: { ...meta, ok: false, error: (e as Error).message }, data: null };
  }
};

export async function fetchDsn(): Promise<Fetched<DsnState>> {
  const { meta, text } = await get(`${DSN_URL}?r=${Math.floor(Date.now() / 5000)}`, { timeoutMs: 8000, accept: "text/xml" });
  return wrap(meta, () => parseDsn(text));
}

export async function fetchDsnNames(): Promise<Fetched<Record<string, string>>> {
  const { meta, text } = await get(DSN_CONFIG_URL, { accept: "text/xml" });
  return wrap(meta, () => parseDsnConfig(text));
}

export async function fetchNoaa(ifModifiedSince: string | null = null): Promise<Fetched<SolarWindSample[]>> {
  const [w, m] = await Promise.all([get(NOAA_WIND_URL, { ifModifiedSince }), get(NOAA_MAG_URL, { ifModifiedSince })]);
  const meta: FetchMeta = {
    ok: w.meta.ok && m.meta.ok, status: w.meta.ok ? m.meta.status : w.meta.status, bytes: w.meta.bytes + m.meta.bytes, durationMs: Math.max(w.meta.durationMs, m.meta.durationMs),
    notModified: w.meta.notModified && m.meta.notModified, lastModified: w.meta.lastModified ?? m.meta.lastModified, error: w.meta.error ?? m.meta.error,
  };
  if (!meta.ok || meta.notModified) return { meta, data: null };
  // a partial 304 (one file unchanged) — treat as "nothing new" rather than guessing
  if (w.meta.notModified || m.meta.notModified) return { meta: { ...meta, notModified: true }, data: null };
  return wrap(meta, () => parseNoaa(JSON.parse(w.text), JSON.parse(m.text)));
}

const day = (d: Date) => d.toISOString().slice(0, 10);

export async function fetchDonki(now: Date, days = 7): Promise<Fetched<DonkiEvent[]>> {
  const start = day(new Date(now.getTime() - days * 86_400_000));
  const end = day(new Date(now.getTime() + 86_400_000));
  const one = async (t: (typeof DONKI_TYPES)[number]) => {
    const url = `${DONKI_BASE}/${t}?startDate=${start}&endDate=${end}`;
    let r = await get(url);
    if (!r.meta.ok && r.meta.status !== 400) { await new Promise((ok) => setTimeout(ok, 1500)); r = await get(url); } // one retry on transient failures
    return { t, ...r };
  };
  // three at a time — gentle on the new CCMC API
  const results = [...(await Promise.all(DONKI_TYPES.slice(0, 3).map(one))), ...(await Promise.all(DONKI_TYPES.slice(3).map(one)))];
  const failed = results.filter((r) => !r.meta.ok);
  const meta: FetchMeta = {
    ok: failed.length === 0, status: failed[0]?.meta.status ?? 200, bytes: results.reduce((n, r) => n + r.meta.bytes, 0),
    durationMs: Math.max(...results.map((r) => r.meta.durationMs)), error: failed.length ? `${failed.map((f) => `${f.t}: ${f.meta.error}`).join("; ")}` : undefined,
  };
  const events: DonkiEvent[] = [];
  const parseErrors: string[] = [];
  for (const r of results.filter((x) => x.meta.ok)) {
    try {
      events.push(...parseDonki(r.t, JSON.parse(r.text)));
    } catch (e) {
      parseErrors.push(`${r.t}: ${(e as Error).message}`);
    }
  }
  if (parseErrors.length) { meta.ok = false; meta.error = [meta.error, ...parseErrors].filter(Boolean).join("; "); }
  // partial data is still real data: return what parsed, with the error flagged (→ DEGRADED)
  return { meta, data: events.length || meta.ok ? events.sort((a, b) => b.time.localeCompare(a.time)) : null };
}

export async function fetchHorizons(now: Date): Promise<Fetched<Geometry>> {
  const q = new URLSearchParams(horizonsQuery(now));
  const { meta, text } = await get(`${HORIZONS_URL}?${q.toString()}`);
  return wrap(meta, () => parseHorizons(JSON.parse(text)));
}

export async function fetchPerseverance(num = 50): Promise<Fetched<MarsImage[]>> {
  const { meta, text } = await get(`${PERSEVERANCE_URL}&num=${num}`, { timeoutMs: 45_000 });
  return wrap(meta, () => parsePerseverance(JSON.parse(text)));
}

export async function fetchCuriosity(perPage = 50, page = 0): Promise<Fetched<MarsImage[]>> {
  const { meta, text } = await get(`${CURIOSITY_URL.replace("page=0", `page=${page}`)}&per_page=${perPage}`);
  return wrap(meta, () => parseCuriosity(JSON.parse(text)));
}
