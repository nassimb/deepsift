export const API = process.env.NEXT_PUBLIC_DEEPSIFT_API ?? "http://localhost:8787";

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!r.ok) {
    let detail = r.statusText;
    try {
      detail = (await r.json()).detail ?? detail;
    } catch {}
    throw new Error(`${r.status} ${typeof detail === "string" ? detail : JSON.stringify(detail)}`);
  }
  return r.json() as Promise<T>;
}

export type Action = "discard" | "summary_only" | "compress" | "full_data";

export interface EventRow {
  id: string;
  instrument: string;
  sol: number;
  sol_start: number;
  sol_end: number;
  t_start: string;
  t_end: string;
  sensors: string[];
  event_type: string | null;
  type_probs: Record<string, number>;
  science_value: string | null;
  engine_event_type: string | null;
  deviation: number;
  rarity: number;
  duration_s: number;
  novelty: number;
  gate: string | null;
  confidence: number | null;
  utility: number | null;
  mission_relevance: number | null;
  anomaly_strength: number | null;
  science_expected: number | null;
  proposed_action: Action | null;
  final_action: Action | null;
  status: string;
  bytes: { raw: number; full: number; compressed: number; summary: number };
  downlink_bytes: number;
  synthetic: boolean;
  injection_ids: string[];
  correlated_channels: number;
}

export interface Status {
  online: boolean;
  error: string | null;
  engine: { name: string; is_real_model: boolean } | null;
  jev_key_present: boolean;
  deep_provider: string | null;
  deep_available: boolean;
  run_id: string | null;
  config_version: string;
  objective: Objective | null;
  data_source: string | null;
  benchmark_running: boolean;
}

export interface Objective {
  id: string;
  name: string;
  description: string;
  type_weights: Record<string, number>;
  channel_weights: Record<string, number>;
  priority_weights: Record<string, number> | null;
  custom: boolean;
}

export interface ChannelSpec {
  name: string;
  instrument: string;
  unit: string;
  description: string;
}

export interface Mission {
  mission: string;
  name: string;
  short_name: string;
  target: string;
  location: string;
  instruments: Record<string, string>;
  channels: ChannelSpec[];
  citations: string[];
  data_source: string;
  sols: number[];
  products: string[];
  counts: Record<string, number>;
  synthetic_injections: unknown[];
  run_id: string;
  timings_ms: Record<string, number>;
  performance: Record<string, number | string | null>;
  engine: { name: string; is_real_model: boolean };
  deep_provider: string;
  pipeline_version: string;
  config_version: string;
}

export interface SimItem {
  id: string;
  kind: string;
  arrival: number;
  utility: number;
  proposed: Action;
  final: Action;
  state: string;
  bytes: number;
  sent: number;
  downlinked_at: number | null;
  raw: number;
  history: { t: number; from: string; to: string; reason: string }[];
}

export interface Snapshot {
  t: number;
  kind: string;
  storage_used: number;
  capacity: number;
  raw_generated: number;
  downlinked: number;
  queued: number;
  blackout: boolean;
  degradations: number;
}

export interface Simulation {
  timeline: Snapshot[];
  log: { type: string; t: number; [k: string]: unknown }[];
  totals: Record<string, number | Record<string, number>>;
  passes: number[];
  items: SimItem[];
  blackout: BlackoutReport | null;
  blackout_window: { start: number; end: number; storage_bytes: number } | null;
}

export interface BlackoutReport {
  raw_collected: number;
  events_detected: number;
  events_retained: number;
  events_discarded: number;
  events_degraded: number;
  retained_bytes: number;
  important_events: { id: string; utility: number; proposed: string; final: string; state: string }[];
  downlink_queue: { id: string; utility: number; action: string; bytes: number }[];
  pass_bytes: number;
}

export interface Series {
  channel: string;
  raw_points?: number;
  points: [number, number, number, number, string | null][];
  windows: [number, number, number | null, boolean][];
}
