"use client";

/* Poll one public live route. Keeps the last GOOD payload with its own fetch time, so a failing source keeps showing
   its last value with an honest age (→ DEGRADED / STALE), never frozen as current. */
import { useEffect, useState } from "react";

export interface LiveResult<T> {
  data: T | null;
  /** Server fetch time of the last good payload (what its age is measured from). */
  lastOk: string | null;
  lastAttempt: string | null;
  error: string | null;
  consecutiveErrors: number;
  /** Increments on every good payload (lets consumers diff successive states). */
  version: number;
}

export function useLive<T>(url: string | null, everyMs: number): LiveResult<T> {
  const [r, setR] = useState<LiveResult<T>>({ data: null, lastOk: null, lastAttempt: null, error: null, consecutiveErrors: 0, version: 0 });
  useEffect(() => {
    if (!url) return;
    let alive = true;
    let busy = false; // per-effect, so a remount (e.g. React strict mode) never skips its first fetch
    const tick = async () => {
      if (busy) return;
      busy = true;
      const attempt = new Date().toISOString();
      try {
        const res = await fetch(url, { cache: "no-store" });
        const j = (await res.json()) as { ok?: boolean; error?: string; fetchedAt?: string } & T;
        if (!alive) return;
        if (res.ok && j.ok !== false) setR((p) => ({ data: j, lastOk: j.fetchedAt ?? attempt, lastAttempt: attempt, error: null, consecutiveErrors: 0, version: p.version + 1 }));
        else setR((p) => ({ ...p, lastAttempt: attempt, error: j.error ?? `HTTP ${res.status}`, consecutiveErrors: p.consecutiveErrors + 1 }));
      } catch (e) {
        if (alive) setR((p) => ({ ...p, lastAttempt: attempt, error: (e as Error).message || "network error", consecutiveErrors: p.consecutiveErrors + 1 }));
      } finally {
        busy = false;
      }
    };
    void tick();
    const id = setInterval(tick, everyMs);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [url, everyMs]);
  return r;
}

/** A ticking "now" for ages and clocks. */
export function useNow(everyMs = 1000): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), everyMs);
    return () => clearInterval(id);
  }, [everyMs]);
  return now;
}
