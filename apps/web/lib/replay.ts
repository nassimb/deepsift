"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { SOL_SECONDS } from "./format";

export const SPEEDS = [1, 10, 100, 1000, 10000];

/** Mission replay clock in fractional sols. 1× = one Mars second per wall second. */
export function useReplayClock(start: number, end: number) {
  const [t, setT] = useState(start);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1000);
  const last = useRef<number | null>(null);

  useEffect(() => {
    if (!playing) {
      last.current = null;
      return;
    }
    let raf = 0;
    const loop = (now: number) => {
      if (last.current != null) {
        const dt = (now - last.current) / 1000;
        setT((cur) => {
          const nt = cur + (dt * speed) / SOL_SECONDS;
          if (nt >= end) {
            setPlaying(false);
            return end;
          }
          return nt;
        });
      }
      last.current = now;
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [playing, speed, end]);

  const step = useCallback((sols: number) => setT((cur) => Math.min(end, Math.max(start, cur + sols))), [start, end]);
  // the window can move (new blackout / new segment): clamp rather than reset in an effect
  const clamped = t < start || t > end ? start : t;
  return { t: clamped, setT, playing, setPlaying, speed, setSpeed, step };
}

/** Last element with key <= t (binary search). */
export function lastAtOrBefore<T>(arr: T[], t: number, key: (x: T) => number): T | undefined {
  let lo = 0,
    hi = arr.length - 1,
    ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (key(arr[mid]) <= t) {
      ans = mid;
      lo = mid + 1;
    } else hi = mid - 1;
  }
  return ans >= 0 ? arr[ans] : undefined;
}
