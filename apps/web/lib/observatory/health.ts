/** Source health + staleness. Rules (architecture review §13):
 *  ONLINE   last success ≤ 2× expected cadence and no current error streak
 *  DEGRADED recent errors / partial, but last success ≤ 5× cadence (or > 2× cadence without errors)
 *  STALE    no success for > 5× cadence
 *  OFFLINE  disabled, never succeeded, or no success for > 1 h (and > 5× cadence). Pure. */
import type { Health } from "./types.ts";

export interface PollState {
  enabled: boolean;
  lastSuccess: string | null;
  lastAttempt: string | null;
  lastError: string | null;
  consecutiveErrors: number;
}

export function computeHealth(s: PollState, cadenceS: number, now: Date): Health {
  if (!s.enabled) return "OFFLINE";
  if (!s.lastSuccess) return s.lastAttempt ? "OFFLINE" : "STALE";
  const age = (now.getTime() - Date.parse(s.lastSuccess)) / 1000;
  if (age > Math.max(3600, 5 * cadenceS)) return "OFFLINE";
  if (age > 5 * cadenceS) return "STALE";
  if (s.consecutiveErrors > 0 || age > 2 * cadenceS) return "DEGRADED";
  return "ONLINE";
}

export function fmtAge(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 90) return `${s} s`;
  if (s < 5400) return `${Math.round(s / 60)} min`;
  if (s < 172800) return `${(s / 3600).toFixed(s < 36000 ? 1 : 0)} h`;
  return `${Math.round(s / 86400)} d`;
}

/** "updated 4 s ago" · "updated 3 min ago" · "STALE · last success 37 min ago" */
export function ageLabel(iso: string | null, health: Health, now: Date, verb = "updated"): string {
  if (!iso) return health === "OFFLINE" ? "OFFLINE · never succeeded" : "waiting for first update";
  const age = (now.getTime() - Date.parse(iso)) / 1000;
  if (health === "STALE" || health === "OFFLINE") return `${health} · last success ${fmtAge(age)} ago`;
  return `${verb} ${fmtAge(age)} ago`;
}
