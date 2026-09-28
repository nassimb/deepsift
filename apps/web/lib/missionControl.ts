/** Public Phase 3 Mission Control data — built by scripts/build_mission_control_data.py from the frozen final-test
 *  artifacts only (POSITION retained sets asserted equal to the stored per-traverse rows). No API, no recomputation. */
import raw from "@/data/mission-control.json";

export type Frac = "0.5" | "0.25" | "0.125";
export const FRACS: Frac[] = ["0.5", "0.25", "0.125"];
export const FRAC_LABEL: Record<Frac, string> = { "0.5": "1/2", "0.25": "1/4", "0.125": "1/8" };
export const RADIUS_M = 5;

export interface Frame {
  i: number;
  acq_id: string;
  utc: string;
  t_s: number;
  sol: number;
  x: number;
  y: number;
  pose: [number, number, number];
  places_match: string;
  stereo: boolean;
  tier: string;
  primary: string[];
  thumbnails: string[];
  size: string;
  compression: string;
  full_bytes: number;
  thumb_bytes: number;
}

export interface PolicyMetrics {
  bytes_fraction: number;
  coverage_5m: number;
  max_distance_to_kept_m: number;
  frames_retained: number;
  stereo_broken: number;
  stereo_kept_full: number;
  unique_positions: number;
}

export interface Policy {
  kept: number[];
  trace: [number, number][];
  nearest: [number, number][];
  metrics: PolicyMetrics;
}

export interface Traverse {
  sequence: string;
  sol: number;
  sequence_id: string;
  frames_count: number;
  length_m: number;
  duration_s: number;
  frames: Frame[];
  send_all: { bytes: number; stereo_kept_full: number };
  policies: Record<Frac, Policy>;
}

export interface OperatingPoint {
  bytes_fraction: number;
  coverage_5m: number;
  max_distance_to_kept_m_worst: number;
  stereo_broken: number;
  stereo_kept_full: number;
  unique_positions: number;
  visual_change_coverage: number;
  sequences: number;
}

export interface MissionControlData {
  label: string;
  pds_base: string;
  source: { run: string; results: string; manifest: string; verification: string };
  primary: { claim: string; result: string; bytes_fraction: number; coverage_5m: number; max_distance_to_kept_m_worst: number; stereo_broken: number };
  operating_points: Record<"send_all" | Frac, OperatingPoint>;
  negative_results: { name: string; verdict: string; phase: string }[];
  representative: string;
  traverses: Traverse[];
}

export const MC = raw as unknown as MissionControlData;

export const pdsLabelUrl = (sol: number, productId: string) => `${MC.pds_base}SOL${String(sol).padStart(5, "0")}/${productId}.LBL`;

/** Deterministic decision text (fixed templates filled from the frozen selection trace — no generated prose). */
export function decisionReason(mode: "SEND_ALL" | "POSITION", f: Frame, policy: Policy | null, frames: Frame[]): string {
  if (mode === "SEND_ALL" || !policy) return "SEND ALL baseline: every archived acquisition is downlinked as a FULL_STEREO_PAIR.";
  const step = policy.trace.findIndex(([j]) => j === f.i);
  if (step === 0) return "Retained: first frame of the traverse — the position sampler's fixed starting point.";
  if (step > 0) {
    const d = policy.trace[step][1];
    return d > 0
      ? `Retained: at selection step ${step + 1} of ${policy.trace.length}, this was the archived position farthest from every previously retained position (${d.toFixed(2)} m), so it adds the most spatial coverage.`
      : `Retained at selection step ${step + 1} of ${policy.trace.length} to fill the frame quota: every archived position was already within 0 m of a retained one.`;
  }
  const [j, d] = policy.nearest[f.i];
  const near = frames[j];
  return d <= RADIUS_M
    ? `Deprioritized: ${d.toFixed(2)} m from retained frame ${near.acq_id} — inside the ${RADIUS_M} m coverage radius, so it is represented by a THUMBNAIL_PAIR.`
    : `Deprioritized: ${d.toFixed(2)} m from the nearest retained frame ${near.acq_id} — outside the ${RADIUS_M} m radius at this retention level; represented by a THUMBNAIL_PAIR.`;
}
