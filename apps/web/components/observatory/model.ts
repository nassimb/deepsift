/** Client-side payload types for the /api/live/* routes and the collector, plus display constants. */
import type { Classification, DonkiEvent, DsnContact, DsnDish, Geometry, Health, LiveDataEvent, MarsImage, SolarWindSample, SourceId } from "@/lib/observatory/types";

export interface Envelope {
  ok: boolean;
  fetchedAt: string;
  error?: string;
  source: { id: SourceId; name: string; provider: string; classification: Classification; parserVersion: string; attribution: string; cacheS: number };
}
export interface DsnPayload extends Envelope { sourceTime: string; stations: { code: string; name: string; time: string }[]; dishes: DsnDish[]; contacts: DsnContact[] }
export interface WeatherPayload extends Envelope { latest: SolarWindSample | null; latestPlasma: SolarWindSample | null; latestField: SolarWindSample | null; samples: SolarWindSample[] }
export interface DonkiPayload extends Envelope { events: DonkiEvent[]; partialError: string | null }
export interface GeometryPayload extends Envelope { geometry: Geometry }
export interface ImagesPayload extends Envelope { images: MarsImage[] }

export interface CollectorSource {
  id: SourceId;
  health: Health;
  lastPoll: string | null;
  lastSuccess: string | null;
  lastError: string | null;
  pollMs: number | null;
  bytes: number | null;
  parse: string | null;
  dedupeDrops: number;
  consecutiveErrors: number;
  enabled: boolean;
  intervalS: number;
}
export interface CollectorStatus {
  ok: boolean;
  version: string;
  startedAt: string;
  uptimeS: number;
  dbBytes: number;
  eventsTotal: number;
  eventsToday: number;
  lastEventAt: string | null;
  sources: CollectorSource[];
}
export interface TimelineContact { key: string; dish: string; complex: string; spacecraftName: string; mars: boolean; direction: string; band: string | null; downRate: number | null; start: string; end: string | null }
export interface TimelineImage extends MarsImage { firstSeen: string; backfill?: boolean }
export interface Timeline {
  from: string;
  contacts: TimelineContact[];
  weather: SolarWindSample[];
  donki: DonkiEvent[];
  geometry: Geometry[];
  images: TimelineImage[];
}

export const SOURCE_COLOR: Record<SourceId, string> = {
  dsn: "#6da7ec",
  noaa: "#e3b341",
  donki: "#e5534b",
  horizons: "#a78bfa",
  perseverance: "#39c5bb",
  curiosity: "#f0883e",
};

export const HEALTH_COLOR: Record<Health, string> = { ONLINE: "var(--s-good)", DEGRADED: "var(--s-warn)", STALE: "var(--s-serious)", OFFLINE: "var(--s-critical)" };

export type Selection =
  | { kind: "event"; event: LiveDataEvent }
  | { kind: "contact"; contact: DsnContact & { since?: string } }
  | { kind: "image"; image: MarsImage & { firstSeen?: string } }
  | { kind: "donki"; event: DonkiEvent };
