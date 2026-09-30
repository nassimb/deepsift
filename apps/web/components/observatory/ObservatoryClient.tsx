"use client";

/* The observatory is client-only: it shows a ticking UTC clock and ages relative to "now", which must not be
   server-rendered (hydration mismatch). */
import dynamic from "next/dynamic";

export const ObservatoryClient = dynamic(() => import("./Observatory").then((m) => m.Observatory), {
  ssr: false,
  loading: () => <p className="obs-mono text-[12px] text-ink-3 py-10">Connecting to live sources…</p>,
});
