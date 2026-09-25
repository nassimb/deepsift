"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ACTION_COLOR, hm, SOL_SECONDS } from "@/lib/format";
import { ACT_LABEL, ACT_ORDER, type BlackoutExample, eventNoun, mb, type HomeSummary } from "@/lib/home";

type B = HomeSummary["replay"]["blackout"];
const RUN_MS = 6500;

/** Replays a RECORDED scheduler simulation (the /blackout defaults on the replay segment). Nothing here is generated. */
export function BlackoutDemo({ b, configVersion }: { b: B; configVersion: string }) {
  const [phase, setPhase] = useState<"idle" | "lost" | "restored">("idle");
  const [p, setP] = useState(0);
  const raf = useRef<number | null>(null);
  const tl = b.timeline.filter((x) => x[5]);                                        // snapshots taken while the link is down
  const before = [...b.timeline].reverse().find((x) => x[0] < b.start_sol);      // last recorded state with the link up
  const t = b.start_sol + p * (b.end_sol - b.start_sol);
  const snap = phase === "idle" ? before ?? tl[0] : [...tl].reverse().find((x) => x[0] <= t) ?? tl[0];
  const raw0 = tl[0]?.[3] ?? 0;
  const used = snap ? snap[1] : 0;
  const cap = snap ? snap[2] : b.storage_bytes;

  const start = () => {
    const reduce = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    setPhase("lost");
    if (reduce) {
      setP(1);
      setPhase("restored");
      return;
    }
    const t0 = performance.now();
    const step = (now: number) => {
      const q = Math.min(1, (now - t0) / RUN_MS);
      setP(q);
      if (q < 1) raf.current = requestAnimationFrame(step);
      else setPhase("restored");
    };
    raf.current = requestAnimationFrame(step);
  };
  const reset = () => {
    if (raf.current) cancelAnimationFrame(raf.current);
    setP(0);
    setPhase("idle");
  };
  useEffect(() => () => {
    if (raf.current) cancelAnimationFrame(raf.current);
  }, []);

  const lost = phase !== "idle";
  const showDecisions = p > 0.55 || phase === "restored";
  return (
    <div className="panel overflow-hidden">
      <div className="grid lg:grid-cols-[1.05fr_1fr]">
        <div className="p-5 sm:p-6 space-y-5 border-b lg:border-b-0 lg:border-r border-line">
          <div className="flex items-center gap-3">
            <span className={phase === "lost" ? "state-pulse" : ""}
              style={{ width: 9, height: 9, borderRadius: 9, background: phase === "idle" ? "var(--s-good)" : phase === "lost" ? "var(--s-critical)" : "var(--s-warn)" }} />
            <span className="mono text-[13px] tracking-[0.12em]" style={{ color: phase === "lost" ? "var(--s-critical)" : "var(--ink-2)" }}>
              {phase === "idle" ? "EARTH LINK NOMINAL" : phase === "lost" ? "EARTH LINK LOST" : "LINK RESTORED"}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <Metric k={phase === "restored" ? "Blackout lasted" : "Reconnect in"}
              v={phase === "idle" ? hm(b.duration_hours * 3600) : phase === "restored" ? hm(b.duration_hours * 3600) : hm((b.end_sol - t) * SOL_SECONDS)} />
            <Metric k="Raw data arriving" v={b.incoming_raw_bytes_per_s != null ? `${(b.incoming_raw_bytes_per_s / 1000).toFixed(2)} kB/s` : "—"}
              sub="replay average, REMS + RAD records" />
            <Metric k="Collected during outage" v={mb(phase === "restored" && b.report ? b.report.raw_collected : lost ? (snap?.[3] ?? raw0) - raw0 : 0)} />
            <Metric k="Onboard triage storage" v={`${mb(used)} / ${mb(cap)}`} sub={phase === "idle" ? "normal buffer, link up" : phase === "lost" ? "reserved during the outage" : "at the end of the outage"} />
          </div>
          <div>
            <div className="h-3 w-full border border-line-2 bg-panel-2">
              <div className="h-full" style={{ width: `${Math.min(100, (used / (cap || 1)) * 100)}%`, background: used / (cap || 1) > 0.9 ? "var(--s-serious)" : "var(--a-compress)" }} />
            </div>
            <div className="mono text-[10px] text-ink-3 mt-1">sol {t.toFixed(2)} · outage sols {b.start_sol.toFixed(1)}–{b.end_sol.toFixed(1)}</div>
          </div>

          <div className="flex flex-wrap gap-2">
            {phase === "idle" ? (
              <button className="btn" data-active="true" onClick={start} style={{ fontSize: 12, padding: "7px 14px" }}>Break the link</button>
            ) : (
              <button className="btn" onClick={reset}>Reset</button>
            )}
            <Link href="/blackout" className="btn">Run it with your own parameters →</Link>
          </div>
        </div>

        <div className="p-5 sm:p-6">
          <div className="label mb-3">What the scheduler decided · {b.events_during} events detected during the outage</div>
          <ul className="space-y-2">
            {ACT_ORDER.map((a, i) => {
              const ex = b.examples[a];
              const visible = (showDecisions && p >= 0.55 + i * 0.08) || phase === "restored";
              return (
                <li key={a} className="grid grid-cols-[92px_1fr] items-start gap-3 border border-line px-3 py-2 transition-opacity duration-500"
                  style={{ opacity: visible ? 1 : 0.18 }}>
                  <span className="mono text-[11px] px-1.5 py-0.5 text-center"
                    style={{ background: ACTION_COLOR[a], color: a === "full_data" ? "var(--bg)" : "var(--ink)" }}>
                    {ACT_LABEL[a]} · {b.actions_during[a] ?? 0}
                  </span>
                  <Example ex={ex} visible={visible} />
                </li>
              );
            })}
          </ul>
          {phase === "restored" && b.report && (
            <p className="mono text-[11px] text-ink-2 mt-3">
              {b.report.events_retained}/{b.report.events_detected} events preserved · {mb(b.report.retained_bytes)} kept of {mb(b.report.raw_collected)} collected
            </p>
          )}
          <p className="text-[10.5px] text-ink-4 mt-3 leading-snug">
            Recorded scheduler simulation on the mission replay (config {configVersion}, mock decision engine). Degradation is by utility per
            byte; examples are the highest-utility event given each final action.
          </p>
        </div>
      </div>
    </div>
  );
}

function Metric({ k, v, sub }: { k: string; v: string; sub?: string }) {
  return (
    <div>
      <div className="label">{k}</div>
      <div className="mono text-[22px] sm:text-[26px] text-ink leading-tight">{v}</div>
      {sub && <div className="text-[10.5px] text-ink-3">{sub}</div>}
    </div>
  );
}

function Example({ ex, visible }: { ex?: BlackoutExample; visible: boolean }) {
  if (!ex) return <span className="text-[12px] text-ink-4">none</span>;
  return (
    <div className="min-w-0">
      <div className="text-[13px] text-ink">{visible ? eventNoun(ex.event_type, ex.instrument) : "…"}</div>
      <div className="mono text-[10.5px] text-ink-3 truncate">
        {ex.id} · proposed {ACT_LABEL[ex.proposed]} → {ACT_LABEL[ex.final]} · {mb(ex.bytes)}
      </div>
    </div>
  );
}
