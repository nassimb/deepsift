/** DEEPSIFT Live Observatory — shared types. Pure, no imports (used by the web app, the collector and node tests).
 *  Operational infrastructure only: nothing here reads or writes DEEPSIFT science artifacts. */

/** Truthful source-mode labels. Never blurred, never upgraded. */
export type Classification = "LIVE" | "NEAR REAL-TIME" | "NEAR REAL-TIME EVENTS" | "CURRENT COMPUTED" | "NEWLY PUBLISHED" | "ARCHIVAL / RESEARCH";

export type Health = "ONLINE" | "DEGRADED" | "STALE" | "OFFLINE";

export type SourceId = "dsn" | "noaa" | "donki" | "horizons" | "perseverance" | "curiosity";

export interface SourceDef {
  id: SourceId;
  name: string;
  provider: string;
  classification: Classification;
  /** Official human-facing page. */
  officialUrl: string;
  /** Machine-readable endpoint(s) actually used (from the 2026-09-30 audit). */
  endpoints: string[];
  documentedApi: boolean;
  /** Expected refresh interval of the source itself (seconds). */
  sourceCadenceS: number;
  /** Default collector polling interval (seconds). */
  pollS: number;
  /** CDN cache for the public Tier 0 route (seconds). */
  cacheS: number;
  parserVersion: string;
  fields: string[];
  attribution: string;
  /** Optional adapter: failure must never break the observatory. */
  optional: boolean;
  notes: string;
}

export type EventType =
  | "dsn_contact_started" | "dsn_contact_updated" | "dsn_contact_ended"
  | "solar_wind_sample"
  | "donki_event"
  | "horizons_refresh"
  | "mars_image_published"
  | "source_error" | "source_recovered";

/** Unified event. Every event maps to real source data (or a real poll outcome for source_error/recovered). */
export interface LiveDataEvent {
  event_id: string;
  dedupe_key: string;
  source_id: SourceId;
  source_name: string;
  provider: string;
  classification: Classification;
  event_type: EventType;
  mission: string | null;
  spacecraft: string | null;
  instrument: string | null;
  /** When the source says the thing happened / was measured / was acquired (ISO, UTC). */
  timestamp_source: string | null;
  /** When DEEPSIFT ingested it (ISO, UTC). */
  timestamp_ingested: string;
  timestamp_updated: string | null;
  status: string | null;
  bytes: number | null;
  title: string;
  summary: string;
  raw_reference: string | null;
  source_url: string | null;
  metadata: Record<string, unknown>;
}

// ─── normalized source records ─────────────────────────────────────────────
export interface DsnSignal {
  direction: "up" | "down";
  active: boolean;
  signalType: string;
  /** bits per second; null when the source reports 0 or blank (not shown). */
  dataRate: number | null;
  band: string | null;
  /** dBm as reported (down: received power, up: kW); null when blank. */
  power: number | null;
  spacecraftCode: string;
  spacecraftId: string | null;
}

export interface DsnTarget {
  code: string;
  id: string | null;
  /** km; null when the source reports -1. */
  uplegRangeKm: number | null;
  downlegRangeKm: number | null;
  /** seconds; null when the source reports -1 (usually). */
  rtltS: number | null;
}

export interface DsnDish {
  name: string;
  complex: "Goldstone" | "Madrid" | "Canberra" | string;
  azimuth: number | null;
  elevation: number | null;
  windSpeed: number | null;
  activity: string;
  isMSPA: boolean;
  isArray: boolean;
  isDDOR: boolean;
  signals: DsnSignal[];
  targets: DsnTarget[];
}

export interface DsnState {
  /** Source time (max station timeUTC), ISO. */
  sourceTime: string;
  stations: { code: string; name: string; time: string }[];
  dishes: DsnDish[];
}

/** One active link (dish ↔ spacecraft), the unit of a DSN "contact". */
export interface DsnContact {
  key: string;
  dish: string;
  complex: string;
  spacecraftCode: string;
  spacecraftName: string;
  mars: boolean;
  direction: "UPLINK" | "DOWNLINK" | "BOTH";
  band: string | null;
  downRate: number | null;
  upRate: number | null;
  downPower: number | null;
  rangeKm: number | null;
  azimuth: number | null;
  elevation: number | null;
  activity: string;
}

export interface SolarWindSample {
  time: string;
  source: string;
  speed: number | null;
  density: number | null;
  temperature: number | null;
  bt: number | null;
  bx: number | null;
  by: number | null;
  bz: number | null;
  quality: number | null;
}

export interface DonkiEvent {
  id: string;
  type: "CME" | "FLR" | "SEP" | "IPS" | "GST" | "NOTIFICATION";
  time: string;
  title: string;
  detail: string;
  link: string | null;
  version: string | null;
}

export interface Geometry {
  computedFor: string;
  raDec: string | null;
  distanceAu: number | null;
  distanceKm: number | null;
  rangeRateKmS: number | null;
  lightTimeMin: number | null;
  elongationDeg: number | null;
  apiVersion: string | null;
}

export interface MarsImage {
  imageId: string;
  rover: "Perseverance" | "Curiosity";
  camera: string;
  cameraLabel: string;
  sol: number | null;
  lmst: string | null;
  acquired: string | null;
  reachedEarth: string | null;
  published: string | null;
  imageUrl: string;
  thumbUrl: string | null;
  detailUrl: string | null;
  width: number | null;
  height: number | null;
  sampleType: string | null;
  thumbnail: boolean;
  credit: string;
  title: string;
}

export class SchemaError extends Error {
  constructor(source: string, msg: string) {
    super(`${source}: schema check failed — ${msg}`);
    this.name = "SchemaError";
  }
}
