/** Homepage data: a measured snapshot built by scripts/build_home_summary.py (no invented values). */
import raw from "@/data/home-summary.json";

export type Act = "full_data" | "compress" | "summary_only" | "discard";

export interface CurvePoint {
  high_labels: number;
  high_any: number | null;
  high_full: number | null;
  downlink_bytes: number;
  raw_bytes: number;
  precision_lower_bound: number | null;
  actions: Partial<Record<Act, number>>;
}

export interface EventCardData {
  id: string;
  instrument: string;
  sol: number;
  sensors: string[];
  top_channel: string;
  top_unit: string;
  robust_z: number;
  duration_s: number;
  rarity: number;
  novelty: number;
  correlated_channels: number;
  science_value: string | null;
  event_type: string | null;
  gate: string | null;
  proposed: Act;
  final: Act;
  priority: {
    science_value: number;
    mission_relevance: number;
    anomaly_strength: number;
    novelty: number;
    confidence: number;
    utility: number;
    contributions: Record<string, number>;
    weights: Record<string, number>;
  };
  explanation: string[];
  engine: { name: string; is_real_model: boolean };
  objective: string;
  config_version: string;
  products: string[];
}

export interface BlackoutExample {
  id: string;
  instrument: string;
  sensors: string[];
  event_type: string | null;
  proposed: Act;
  final: Act;
  state: string;
  utility: number;
  bytes: number;
  raw: number;
  count_with_this_action: number;
}

export interface HomeSummary {
  generated_at: string;
  git: { commit: string; dirty: boolean };
  replay: {
    segment: string;
    sols: [number, number];
    utc: [string, string];
    data_source: string;
    products: number;
    samples: number;
    channel_windows: number;
    instrument_windows: number;
    candidate_windows: number;
    events: number;
    raw_bytes: number;
    downlink_capacity_bytes: number;
    downlink: { passes_per_sol: number; pass_bytes: number; passes: number };
    final_actions: Partial<Record<Act, number>>;
    engine: { name: string; is_real_model: boolean };
    objective: string;
    config_version: string;
    event_rows: [string, string, number, number, string | null, Act, number | null][];
    blackout: {
      start_sol: number;
      end_sol: number;
      duration_sols: number;
      duration_hours: number;
      storage_bytes: number;
      incoming_raw_bytes_per_s: number | null;
      events_during: number;
      actions_during: Record<Act, number>;
      timeline: [number, number, number, number, number, boolean][];
      examples: Partial<Record<Act, BlackoutExample>>;
      report: { raw_collected: number; events_detected: number; events_retained: number; events_discarded: number; events_degraded: number; retained_bytes: number } | null;
    };
    event_card: EventCardData;
    audit_flow: { stage: string; in: string; out: string; ms: number | null; note?: string }[];
  };
  benchmark: {
    run_id: string;
    segments: { id: string; eval: [number, number] }[];
    budgets: number[];
    curves: Record<string, Record<string, CurvePoint>>;
    latency_p50_ms: { RULES: number; LOCAL_EDGE: number; priority_only: number; preprocessing: number };
    "synthetic_by_bucket_at_0.5pct": Record<string, Record<string, { n: number; tolerant_recall: number }>>;
    "real_by_subtype_at_0.5pct": Record<string, Record<string, { n: number; tolerant_recall: number; coverage: number }>>;
    storage_1mib_high_preserved: Record<string, [number, number]>;
    local_edge_footprint: Record<string, unknown>;
    local_edge_model: { features: number; file_bytes: number };
    config_version: string;
  };
  jev: {
    run_id: string;
    events: number;
    high_labels: number;
    live_calls: number;
    cost_usd: number;
    cost_per_1k_requests_usd: number;
    latency_ms: { p50: number; p95: number };
    auroc: Record<string, number>;
    auroc_diff_vs_rules: Record<"no_objective" | "with_objective", { diff: number; ci95: [number, number] }>;
    ordering_only_retention: Record<string, Record<string, number | null>>;
  };
  data: {
    splits: Record<string, { id: string; sols: [number, number]; utc: [string | null, string | null] }[]>;
    validation_funnel: { raw_samples: number; instrument_windows: number; candidate_windows: number; candidate_events: number };
    test_raw_products: { files: number; sha256: string } | null;
    rad_products_on_disk: number;
    rems_products_on_disk: number;
  };
}

export const HOME = raw as unknown as HomeSummary;

export const STRATEGY_LABEL: Record<string, string> = {
  RULES: "Rules",
  STATISTICAL: "Statistical",
  LOCAL_EDGE: "Local edge model",
  RULES_PLUS_STATISTICAL: "Hybrid · rules + statistical",
  RANDOM: "Random (30 seeds)",
  "ORACLE — NOT DEPLOYABLE": "Oracle · not deployable",
};

export const ACT_LABEL: Record<Act, string> = { full_data: "KEEP", compress: "COMPRESS", summary_only: "SUMMARY", discard: "DROP" };
export const ACT_ORDER: Act[] = ["full_data", "compress", "summary_only", "discard"];

export function mb(n: number | null | undefined, d = 1): string {
  if (n == null) return "—";
  if (n >= 1e9) return `${(n / 1e9).toFixed(2)} GB`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(d)} MB`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(0)} kB`;
  return `${Math.round(n)} B`;
}

export function p0(x: number | null | undefined): string {
  return x == null ? "—" : `${Math.round(x * 100)}%`;
}

/** "atmospheric" + REMS → "Atmospheric event" (label from the stored event type, never generated text). */
export function eventNoun(type: string | null, instrument: string): string {
  const t = type ?? (instrument === "RAD" ? "radiation" : "unknown");
  const m: Record<string, string> = {
    radiation: "Radiation event",
    atmospheric: "Atmospheric anomaly",
    thermal: "Temperature variation",
    instrument_anomaly: "Instrument / data anomaly",
    nominal: "Routine measurement",
    unknown: "Unclassified candidate",
  };
  return m[t] ?? t;
}
