export const TYPE_COLOR: Record<string, string> = {
  atmospheric: "var(--c-atmospheric)",
  radiation: "var(--c-radiation)",
  thermal: "var(--c-thermal)",
  instrument_anomaly: "var(--c-instrument)",
  unknown: "var(--c-unknown)",
  nominal: "var(--c-nominal)",
};

export const TYPE_LABEL: Record<string, string> = {
  atmospheric: "Atmospheric",
  radiation: "Radiation",
  thermal: "Thermal",
  instrument_anomaly: "Instrument anomaly",
  unknown: "Unknown",
  nominal: "Nominal",
};

export const TYPES = ["atmospheric", "radiation", "thermal", "instrument_anomaly", "unknown", "nominal"];

export const ACTION_COLOR: Record<string, string> = {
  discard: "var(--a-discard)",
  summary_only: "var(--a-summary)",
  compress: "var(--a-compress)",
  full_data: "var(--a-full)",
};

export const ACTION_LABEL: Record<string, string> = {
  discard: "DISCARD",
  summary_only: "SUMMARY",
  compress: "COMPRESS",
  full_data: "FULL DATA",
};

export const ACTIONS = ["full_data", "compress", "summary_only", "discard"];

export function bytes(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  const a = Math.abs(n);
  if (a >= 1e9) return `${(n / 1e9).toFixed(2)} GB`;
  if (a >= 1e6) return `${(n / 1e6).toFixed(2)} MB`;
  if (a >= 1e3) return `${(n / 1e3).toFixed(1)} kB`;
  return `${Math.round(n)} B`;
}

export function pct(x: number | null | undefined, d = 1): string {
  if (x == null || Number.isNaN(x)) return "—";
  return `${(x * 100).toFixed(d)}%`;
}

export function num(x: number | null | undefined, d = 2): string {
  if (x == null || Number.isNaN(x)) return "—";
  return x.toFixed(d);
}

/** fractional sol → "SOL 0242 · 14:03 LMST" */
export function solClock(t: number): string {
  const sol = Math.floor(t);
  const f = t - sol;
  const secs = Math.floor(f * 86400);
  const hh = String(Math.floor(secs / 3600)).padStart(2, "0");
  const mm = String(Math.floor((secs % 3600) / 60)).padStart(2, "0");
  const ss = String(secs % 60).padStart(2, "0");
  return `SOL ${String(sol).padStart(4, "0")} · ${hh}:${mm}:${ss} LMST`;
}

export function duration(s: number): string {
  if (s < 120) return `${s.toFixed(0)} s`;
  if (s < 7200) return `${(s / 60).toFixed(0)} min`;
  return `${(s / 3600).toFixed(1)} h`;
}

/** Mars-seconds → "17h 34m" */
export function hm(secs: number): string {
  if (!Number.isFinite(secs) || secs < 0) return "—";
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  return `${h}h ${String(m).padStart(2, "0")}m`;
}

export const SOL_SECONDS = 88775.244;
