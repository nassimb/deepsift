/** LiveDataEvent builders + stable dedupe keys + state diffs. Pure — shared by the Tier 0 page (events since you opened
 *  the page) and the collector (stored history). Every event maps to real source data or a real poll outcome. */
import { SOURCE_BY_ID } from "./registry.ts";
import type { DonkiEvent, DsnContact, EventType, Geometry, LiveDataEvent, MarsImage, SolarWindSample, SourceId } from "./types.ts";

/** FNV-1a, stable across runtimes. */
export function hashKey(s: string): string {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return (h >>> 0).toString(36);
}

export const DEDUPE = {
  dsnStart: (c: DsnContact, since: string) => `dsn|start|${c.key}|${since}`,
  dsnEnd: (c: DsnContact, since: string) => `dsn|end|${c.key}|${since}`,
  dsnUpdate: (c: DsnContact, sourceTime: string) => `dsn|update|${c.key}|${sourceTime}`,
  noaa: (s: SolarWindSample) => `noaa|${s.time}|${s.source}`,
  donki: (e: DonkiEvent) => `donki|${e.id}|${e.version ?? ""}`,
  horizons: (g: Geometry) => `horizons|${g.computedFor}`,
  image: (i: MarsImage) => `img|${i.rover}|${i.imageId}`,
  sourceError: (src: SourceId, at: string) => `err|${src}|${at}`,
  sourceRecovered: (src: SourceId, at: string) => `ok|${src}|${at}`,
};

export function makeEvent(src: SourceId, type: EventType, dedupe: string, now: string, f: Partial<LiveDataEvent> & { title: string; summary: string }): LiveDataEvent {
  const d = SOURCE_BY_ID[src];
  return {
    event_id: `${src}-${hashKey(dedupe)}`, dedupe_key: dedupe, source_id: src, source_name: d.name, provider: d.provider, classification: d.classification,
    event_type: type, mission: null, spacecraft: null, instrument: null, timestamp_source: null, timestamp_ingested: now, timestamp_updated: null,
    status: null, bytes: null, raw_reference: null, source_url: null, metadata: {}, ...f,
  };
}

const rate = (bps: number | null) => (bps === null ? "rate not reported" : bps >= 1e6 ? `${(bps / 1e6).toFixed(2)} Mb/s` : bps >= 1e3 ? `${(bps / 1e3).toFixed(1)} kb/s` : `${bps.toFixed(0)} b/s`);
export const fmtRate = rate;

/** Material change worth an "updated" event: direction, band, or a ≥ 25 % data-rate change. */
function changed(a: Pick<DsnContact, "direction" | "band" | "downRate" | "upRate">, b: Pick<DsnContact, "direction" | "band" | "downRate" | "upRate">): boolean {
  const r = (x: number | null, y: number | null) => (x === null) !== (y === null) || (x !== null && y !== null && Math.abs(x - y) / Math.max(x, y, 1) >= 0.25);
  return a.direction !== b.direction || a.band !== b.band || r(a.downRate, b.downRate) || r(a.upRate, b.upRate);
}

export interface TrackedContact extends DsnContact {
  since: string;
  /** Last state that produced an event (updates are compared against it) and when. */
  emitted?: { direction: DsnContact["direction"]; band: string | null; downRate: number | null; upRate: number | null; at: string };
}

/** Minimum gap between two "updated" events for the same contact (signals can flicker every poll). */
export const DSN_UPDATE_MIN_GAP_S = 60;

/** Diff two consecutive DSN snapshots → start / update / end events. `prev` carries when each contact was first observed. */
export function diffDsn(prev: Map<string, TrackedContact>, cur: DsnContact[], sourceTime: string, now: string, seed = false): { events: LiveDataEvent[]; next: Map<string, TrackedContact> } {
  const events: LiveDataEvent[] = [];
  const next = new Map<string, TrackedContact>();
  const meta = (c: DsnContact) => ({ mission: c.mars ? "Mars" : null, spacecraft: c.spacecraftName, instrument: c.dish, metadata: { ...c } as Record<string, unknown>, bytes: null });
  for (const c of cur) {
    const p = prev.get(c.key);
    const snap = { direction: c.direction, band: c.band, downRate: c.downRate, upRate: c.upRate, at: sourceTime };
    if (!p) {
      next.set(c.key, { ...c, since: sourceTime, emitted: snap });
      if (!seed)
        events.push(makeEvent("dsn", "dsn_contact_started", DEDUPE.dsnStart(c, sourceTime), now, {
          ...meta(c), timestamp_source: sourceTime, status: c.direction,
          title: `${c.dish} · ${c.spacecraftName}`, summary: `Contact started · ${c.direction}${c.band ? ` · ${c.band}-band` : ""} · ${rate(c.downRate ?? c.upRate)}`,
        }));
    } else {
      const last = p.emitted ?? { ...p, at: p.since };
      const gapOk = (Date.parse(sourceTime) - Date.parse(last.at)) / 1000 >= DSN_UPDATE_MIN_GAP_S;
      const emit = changed(last, c) && gapOk;
      next.set(c.key, { ...c, since: p.since, emitted: emit ? snap : last });
      if (emit)
        events.push(makeEvent("dsn", "dsn_contact_updated", DEDUPE.dsnUpdate(c, sourceTime), now, {
          ...meta(c), timestamp_source: sourceTime, status: c.direction,
          title: `${c.dish} · ${c.spacecraftName}`, summary: `Contact updated · ${c.direction}${c.band ? ` · ${c.band}-band` : ""} · ${rate(c.downRate ?? c.upRate)}`,
        }));
    }
  }
  for (const [k, p] of prev)
    if (!next.has(k))
      events.push(makeEvent("dsn", "dsn_contact_ended", DEDUPE.dsnEnd(p, p.since), now, {
        ...meta(p), timestamp_source: sourceTime, status: "ENDED",
        title: `${p.dish} · ${p.spacecraftName}`, summary: `Contact ended (observed since ${p.since.slice(11, 19)} UTC)`,
        metadata: { ...p, ended: sourceTime },
      }));
  return { events, next };
}

export function noaaEvent(s: SolarWindSample, now: string): LiveDataEvent {
  return makeEvent("noaa", "solar_wind_sample", DEDUPE.noaa(s), now, {
    timestamp_source: s.time, spacecraft: s.source, status: s.quality ? `quality flag ${s.quality}` : null,
    title: `Solar wind · ${s.source}`, summary: `${s.speed ?? "—"} km/s · ${s.density ?? "—"} p/cm³ · Bz ${s.bz ?? "—"} nT`, metadata: { ...s },
  });
}

export function donkiEvent(e: DonkiEvent, now: string): LiveDataEvent {
  return makeEvent("donki", "donki_event", DEDUPE.donki(e), now, {
    timestamp_source: e.time, status: e.type, title: `${e.type} · ${e.title}`, summary: e.detail || e.id, raw_reference: e.id, source_url: e.link, metadata: { ...e },
  });
}

export function horizonsEvent(g: Geometry, now: string): LiveDataEvent {
  return makeEvent("horizons", "horizons_refresh", DEDUPE.horizons(g), now, {
    timestamp_source: g.computedFor, title: "Earth ↔ Mars geometry refreshed",
    summary: `${g.distanceKm ? `${(g.distanceKm / 1e6).toFixed(1)} million km` : "—"} · one-way light time ${g.lightTimeMin?.toFixed(2) ?? "—"} min`, metadata: { ...g },
  });
}

export function imageEvent(i: MarsImage, now: string): LiveDataEvent {
  const src: SourceId = i.rover === "Perseverance" ? "perseverance" : "curiosity";
  return makeEvent(src, "mars_image_published", DEDUPE.image(i), now, {
    mission: i.rover === "Perseverance" ? "Mars 2020" : "MSL", spacecraft: i.rover, instrument: i.cameraLabel, timestamp_source: i.acquired,
    timestamp_updated: i.published ?? i.reachedEarth, title: `${i.rover} · ${i.cameraLabel}`, summary: `New public image · sol ${i.sol ?? "—"}`,
    raw_reference: i.imageId, source_url: i.detailUrl ?? i.imageUrl, metadata: { ...i },
  });
}

export function sourceEvent(src: SourceId, ok: boolean, at: string, message: string): LiveDataEvent {
  return makeEvent(src, ok ? "source_recovered" : "source_error", ok ? DEDUPE.sourceRecovered(src, at) : DEDUPE.sourceError(src, at), at, {
    timestamp_source: at, status: ok ? "RECOVERED" : "ERROR", title: `${SOURCE_BY_ID[src].name} · ${ok ? "recovered" : "error"}`, summary: message.slice(0, 200),
  });
}

/** Newest-first, then by ingest time, then id — deterministic ordering for display. */
export function orderEvents(events: LiveDataEvent[]): LiveDataEvent[] {
  const t = (e: LiveDataEvent) => Date.parse(e.timestamp_ingested);
  return [...events].sort((a, b) => t(b) - t(a) || (b.timestamp_source ?? "").localeCompare(a.timestamp_source ?? "") || a.event_id.localeCompare(b.event_id));
}

/** Drop events whose dedupe key was already seen. */
export function dedupe(events: LiveDataEvent[], seen: Set<string>): LiveDataEvent[] {
  const out: LiveDataEvent[] = [];
  for (const e of events) if (!seen.has(e.dedupe_key)) { seen.add(e.dedupe_key); out.push(e); }
  return out;
}
