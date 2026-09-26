/** DEEPSIFT v1 research release data — built by scripts/build_release_data.py from frozen artifacts only.
 *  Every number shown on the release pages is read from here; nothing is typed in by hand. */
import raw from "@/data/release.json";

export interface Summary {
  sequences: number;
  bytes_fraction: number;
  coverage_5m: number;
  unique_positions: number;
  mean_gap_m: number;
  p95_gap_m: number | null;
  max_gap_m_worst: number;
  max_distance_to_kept_m_worst: number;
  visual_change_coverage: number;
  stereo_broken: number;
  stereo_kept_full: number;
}

export interface Gain {
  sequences: number;
  visual_change_gain: number;
  visual_change_gain_95ci: [number, number];
  coverage_difference: number;
  coverage_difference_95ci: [number, number];
  largest_distance_difference_m: number;
}

export interface Period {
  id: "development" | "validation1" | "validation2" | "test";
  label: string;
  sols: [number, number];
  position: { bytes_fraction: number; coverage_5m: number; max_distance_to_kept_m_worst: number; stereo_broken: number; stereo_kept_full: number; visual_change_coverage: number; sequences: number };
  position_plus_embedding: { bytes_fraction: number; coverage_5m: number; max_distance_to_kept_m_worst: number; stereo_broken: number; visual_change_coverage: number };
  embedding_gain: Gain;
}

export interface ReplayPoint {
  x: number;
  y: number;
  utc: string;
  stereo: boolean;
  pose: number[];
  full_bytes: number;
  thumb_bytes: number;
  nearest_kept_m_quarter: number;
}

export interface ReplaySequence {
  sequence: string;
  sol: number;
  frames: number;
  length_m: number;
  points: ReplayPoint[];
  kept_position: Record<"0.5" | "0.25" | "0.125", number[]>;
  metrics: Record<"0.5" | "0.25" | "0.125", { bytes: number; bytes_send_all: number; position_coverage: number; max_distance_to_kept_m: number; stereo_broken: number; frames_retained: number }>;
}

export interface Release {
  generated_at: string;
  git_head: string;
  sources: Record<string, string>;
  headline: Summary & {
    claim: string;
    result: "PASS" | "FAIL";
    fraction: number;
    criteria: Record<string, boolean>;
    scheduler_violations: number;
    single_eye_violations: number;
    config_hash: string;
    config_commit: string;
    result_commit: string;
  };
  test_dataset: {
    n_active_sols: number;
    acquisitions: number;
    stereo: number;
    mono: number;
    products: number;
    download_bytes_archive: number;
    sequences: number;
    traverse_sequences_ge_10_frames: number;
    traverse_frames: number;
    traverse_frames_with_places_position: number;
    estimated_downlink_full_bytes: number;
  };
  final_summary: Record<string, Summary>;
  secondary: { by_fraction: Record<string, Gain>; position_visual_1_4: number; position_plus_embedding_visual_1_4: number; CONCLUSION: string };
  periods: Period[];
  funnel: { name: string; verdict: "DROP" | "KEEP" | "NO MEASURABLE ADDED VALUE"; phase: string; evidence: string; source: string }[];
  reproducibility: {
    periods: { id: string; sols: [number, number]; manifest: string; run: string }[];
    manifest_sha256: Record<string, string>;
    configs: { path: string; hash: string }[];
    seeds: Record<string, Record<string, unknown>>;
    timeline: { tag: string; commit: string; date: string; label: string }[];
    frozen_before_download: { config_commit_time: string; first_test_image_written: string; config_before_download: boolean };
    integrity: { file: string; files: number; aggregate_sha256: string };
    commands: string[];
  };
  replay: { label: string; sequences: ReplaySequence[]; representative: string; representative_rule: string };
}

export const REL = raw as unknown as Release;
export const H = REL.headline;
export const pct = (x: number, d = 1) => `${(x * 100).toFixed(d)}%`;
export const PERIOD_LABEL: Record<Period["id"], string> = {
  development: "Development",
  validation1: "Validation 1",
  validation2: "Validation 2",
  test: "Held-out test",
};
