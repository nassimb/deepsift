"use client";

import { useRef } from "react";
import type { EventRow, Simulation } from "@/lib/api";
import { TYPE_COLOR } from "@/lib/format";
import { Glyph } from "./Marker";
import { useSize } from "./useSize";

/** Mission timeline: downlink passes, blackout, candidate events by final action, storage fill.
 *  Click or drag to scrub the replay clock. */
export function Timeline({
  events,
  sim,
  domain,
  t,
  onScrub,
  onSelect,
}: {
  events: EventRow[];
  sim: Simulation | null;
  domain: [number, number];
  t: number;
  onScrub: (t: number) => void;
  onSelect?: (id: string) => void;
}) {
  const [ref, { w }] = useSize<HTMLDivElement>();
  const h = 118;
  const m = { l: 88, r: 10 };
  const iw = Math.max(1, w - m.l - m.r);
  const [a, b] = domain;
  const sx = (s: number) => m.l + ((s - a) / (b - a)) * iw;
  const dragging = useRef(false);
  const rows = { pass: 10, blackout: 10, accepted: 36, discarded: 56, storage: 74 };

  const scrubAt = (clientX: number, el: Element) => {
    const x = clientX - el.getBoundingClientRect().left;
    onScrub(Math.min(b, Math.max(a, a + ((x - m.l) / iw) * (b - a))));
  };

  const cap = sim ? Math.max(...sim.timeline.map((s) => s.capacity)) : 1;
  const area = sim
    ? "M" +
      sim.timeline
        .map((s) => `${sx(s.t).toFixed(1)},${(rows.storage + 36 - (s.storage_used / cap) * 34).toFixed(1)}`)
        .join("L") +
      `L${sx(sim.timeline.at(-1)?.t ?? b).toFixed(1)},${rows.storage + 36}L${sx(sim.timeline[0]?.t ?? a).toFixed(1)},${rows.storage + 36}Z`
    : "";

  const sols: number[] = [];
  for (let s = Math.ceil(a); s <= b; s++) sols.push(s);

  return (
    <div ref={ref} className="w-full select-none">
      {w > 0 && (
        <svg
          width={w}
          height={h}
          onPointerDown={(e) => {
            dragging.current = true;
            (e.currentTarget as Element).setPointerCapture(e.pointerId);
            scrubAt(e.clientX, e.currentTarget);
          }}
          onPointerMove={(e) => dragging.current && scrubAt(e.clientX, e.currentTarget)}
          onPointerUp={() => (dragging.current = false)}
          style={{ cursor: "ew-resize" }}
        >
          {sols.map((s) => (
            <g key={s}>
              <line x1={sx(s)} x2={sx(s)} y1={4} y2={h - 12} stroke="var(--grid)" />
              {(sols.length < 30 || s % 2 === 0) && (
                <text x={sx(s) + 2} y={h - 2} className="mono" fontSize={9} fill="var(--ink-4)">
                  {s}
                </text>
              )}
            </g>
          ))}
          {[
            ["DOWNLINK", rows.pass + 4],
            ["RETAINED", rows.accepted + 4],
            ["DISCARDED", rows.discarded + 4],
            ["STORAGE", rows.storage + 22],
          ].map(([l, y]) => (
            <text key={l as string} x={4} y={y as number} className="mono" fontSize={9} fill="var(--ink-3)">
              {l}
            </text>
          ))}
          {sim?.blackout_window && (
            <g>
              <rect
                x={sx(sim.blackout_window.start)}
                width={Math.max(1, sx(sim.blackout_window.end) - sx(sim.blackout_window.start))}
                y={2}
                height={h - 16}
                fill="var(--s-critical)"
                opacity={0.1}
              />
              <text x={sx(sim.blackout_window.start) + 3} y={rows.pass + 16} className="mono" fontSize={9} fill="var(--s-critical)">
                BLACKOUT
              </text>
            </g>
          )}
          {sim?.log
            .filter((l) => l.type === "pass" || l.type === "pass_missed")
            .map((l, i) => (
              <rect key={i} x={sx(l.t) - 1} y={rows.pass - 4} width={2} height={10} fill={l.type === "pass" ? "var(--ink-2)" : "var(--s-critical)"}>
                <title>{l.type === "pass" ? `relay pass · ${l.bytes} B` : "relay pass missed (blackout)"}</title>
              </rect>
            ))}
          {events.map((e) => {
            const kept = e.final_action && e.final_action !== "discard";
            return (
              <g key={e.id} opacity={e.sol_start <= t ? 1 : 0.18} style={{ cursor: "pointer" }} onPointerDown={(ev) => { ev.stopPropagation(); onSelect?.(e.id); }}>
                <Glyph type={e.event_type} size={7} x={sx(e.sol_start)} y={kept ? rows.accepted : rows.discarded} />
              </g>
            );
          })}
          <path d={area} fill="var(--a-compress)" opacity={0.35} />
          <line x1={m.l} x2={m.l + iw} y1={rows.storage + 2} y2={rows.storage + 2} stroke="var(--line)" strokeDasharray="2 3" />
          <line x1={sx(t)} x2={sx(t)} y1={0} y2={h - 12} stroke="var(--ink)" />
          <rect x={sx(t) - 4} y={0} width={8} height={4} fill="var(--ink)" />
        </svg>
      )}
      <div className="flex gap-4 px-2 pb-1 mono text-[10px] text-ink-3">
        <span>▮ relay pass</span>
        <span style={{ color: "var(--s-critical)" }}>▮ missed pass</span>
        <span>storage fill (vs max capacity)</span>
        <span>faded markers = not yet arrived at replay time</span>
        <span className="ml-auto" style={{ color: TYPE_COLOR.radiation }} />
      </div>
    </div>
  );
}
