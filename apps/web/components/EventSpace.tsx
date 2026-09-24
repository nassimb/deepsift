"use client";

import { useMemo, useRef, useState } from "react";
import type { EventRow } from "@/lib/api";
import { ACTION_LABEL, TYPE_LABEL, bytes, num, pct } from "@/lib/format";
import { Glyph } from "./Marker";
import { useSize } from "./useSize";

/** Event space: x = anomaly magnitude (max |robust z| / dip σ, log), y = mission relevance under the
 *  active objective, size = expected science value, glyph = event class, opacity = final action. */
const OPACITY: Record<string, number> = { full_data: 1, compress: 0.85, summary_only: 0.5, discard: 0.22 };

type Domain = { x0: number; x1: number; y0: number; y1: number };
const FULL: Domain = { x0: Math.log10(0.8), x1: Math.log10(120), y0: -0.02, y1: 1.04 };

export function EventSpace({
  events,
  selected,
  onSelect,
  visibleIds,
}: {
  events: EventRow[];
  selected: string | null;
  onSelect: (id: string) => void;
  visibleIds?: Set<string>;
}) {
  const [ref, { w, h }] = useSize<HTMLDivElement>();
  const [dom, setDom] = useState<Domain>(FULL);
  const [hover, setHover] = useState<EventRow | null>(null);
  const drag = useRef<{ x: number; y: number; d: Domain } | null>(null);
  const [dragging, setDragging] = useState(false);
  const m = { l: 44, r: 12, t: 10, b: 30 };
  const iw = Math.max(10, w - m.l - m.r);
  const ih = Math.max(10, h - m.t - m.b);
  const sx = (v: number) => m.l + ((Math.log10(Math.max(v, 0.8)) - dom.x0) / (dom.x1 - dom.x0)) * iw;
  const sy = (v: number) => m.t + (1 - (v - dom.y0) / (dom.y1 - dom.y0)) * ih;

  const pts = useMemo(
    () =>
      events
        .filter((e) => !visibleIds || visibleIds.has(e.id))
        .map((e) => ({ e, x: sx(e.deviation), y: sy(e.mission_relevance ?? 0), r: 3.5 + 6 * (e.science_expected ?? 0) })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [events, visibleIds, dom, w, h],
  );

  const xticks = [1, 2, 5, 10, 20, 50, 100].filter((v) => Math.log10(v) >= dom.x0 && Math.log10(v) <= dom.x1);
  const yticks = [0, 0.25, 0.5, 0.75, 1].filter((v) => v >= dom.y0 && v <= dom.y1);

  function onWheel(ev: React.WheelEvent) {
    const rect = (ev.currentTarget as SVGElement).getBoundingClientRect();
    const fx = (ev.clientX - rect.left - m.l) / iw;
    const fy = 1 - (ev.clientY - rect.top - m.t) / ih;
    const k = ev.deltaY > 0 ? 1.15 : 1 / 1.15;
    setDom((d) => {
      const cx = d.x0 + fx * (d.x1 - d.x0);
      const cy = d.y0 + fy * (d.y1 - d.y0);
      return { x0: cx - (cx - d.x0) * k, x1: cx + (d.x1 - cx) * k, y0: cy - (cy - d.y0) * k, y1: cy + (d.y1 - cy) * k };
    });
  }

  function nearest(px: number, py: number) {
    let best: (typeof pts)[number] | null = null;
    let bd = 24 * 24;
    for (const p of pts) {
      const d = (p.x - px) ** 2 + (p.y - py) ** 2;
      if (d < bd) {
        bd = d;
        best = p;
      }
    }
    return best;
  }

  return (
    <div ref={ref} className="relative w-full h-full select-none">
      {w > 0 && (
        <svg
          width={w}
          height={h}
          onWheel={onWheel}
          onDoubleClick={() => setDom(FULL)}
          onPointerDown={(ev) => {
            drag.current = { x: ev.clientX, y: ev.clientY, d: dom };
            setDragging(true);
          }}
          onPointerUp={(ev) => {
            const moved = drag.current && Math.hypot(ev.clientX - drag.current.x, ev.clientY - drag.current.y) > 3;
            drag.current = null;
            setDragging(false);
            if (!moved) {
              const rect = (ev.currentTarget as SVGElement).getBoundingClientRect();
              const n = nearest(ev.clientX - rect.left, ev.clientY - rect.top);
              if (n) onSelect(n.e.id);
            }
          }}
          onPointerLeave={() => {
            drag.current = null;
            setDragging(false);
            setHover(null);
          }}
          onPointerMove={(ev) => {
            const rect = (ev.currentTarget as SVGElement).getBoundingClientRect();
            if (drag.current && ev.buttons) {
              const d = drag.current.d;
              const dx = ((ev.clientX - drag.current.x) / iw) * (d.x1 - d.x0);
              const dy = ((ev.clientY - drag.current.y) / ih) * (d.y1 - d.y0);
              setDom({ x0: d.x0 - dx, x1: d.x1 - dx, y0: d.y0 + dy, y1: d.y1 + dy });
              return;
            }
            const n = nearest(ev.clientX - rect.left, ev.clientY - rect.top);
            setHover(n ? n.e : null);
          }}
          style={{ cursor: dragging ? "grabbing" : "crosshair" }}
        >
          <defs>
            <clipPath id="es-clip">
              <rect x={m.l} y={m.t} width={iw} height={ih} />
            </clipPath>
          </defs>
          {xticks.map((v) => (
            <g key={`x${v}`}>
              <line x1={sx(v)} x2={sx(v)} y1={m.t} y2={m.t + ih} stroke="var(--grid)" />
              <text x={sx(v)} y={m.t + ih + 14} textAnchor="middle" className="mono" fontSize={10} fill="var(--ink-3)">
                {v}σ
              </text>
            </g>
          ))}
          {yticks.map((v) => (
            <g key={`y${v}`}>
              <line x1={m.l} x2={m.l + iw} y1={sy(v)} y2={sy(v)} stroke="var(--grid)" />
              <text x={m.l - 6} y={sy(v) + 3} textAnchor="end" className="mono" fontSize={10} fill="var(--ink-3)">
                {v.toFixed(2)}
              </text>
            </g>
          ))}
          <text x={m.l + iw} y={m.t + ih + 26} textAnchor="end" className="mono" fontSize={9} fill="var(--ink-4)">
            ANOMALY MAGNITUDE · max |robust z| (log)
          </text>
          <text transform={`translate(10,${m.t + ih / 2}) rotate(-90)`} textAnchor="middle" className="mono" fontSize={9} fill="var(--ink-4)">
            MISSION RELEVANCE
          </text>
          <g clipPath="url(#es-clip)">
            {pts.map(({ e, x, y, r }) => (
              <g key={e.id} opacity={OPACITY[e.final_action ?? "discard"] ?? 0.4}>
                {(selected === e.id || hover?.id === e.id) && (
                  <circle cx={x} cy={y} r={r + 5} fill="none" stroke="var(--ink)" strokeWidth={1.5} />
                )}
                <Glyph type={e.event_type} size={r * 2} x={x} y={y} />
                {e.synthetic && <circle cx={x + r + 2} cy={y - r - 2} r={2} fill="var(--s-warn)" />}
              </g>
            ))}
          </g>
        </svg>
      )}
      {hover && (
        <div
          className="absolute pointer-events-none panel px-2 py-1.5 mono text-[11px] leading-4 z-10"
          style={{ left: Math.min(sx(hover.deviation) + 14, w - 230), top: Math.max(4, sy(hover.mission_relevance ?? 0) - 10), width: 220 }}
        >
          <div className="text-ink">{hover.id}</div>
          <div className="text-ink-2">{TYPE_LABEL[hover.event_type ?? ""] ?? "—"} · {hover.science_value ?? "—"}</div>
          <div className="text-ink-3">
            dev <span className="text-ink">{num(hover.deviation, 1)}σ</span> · rel <span className="text-ink">{num(hover.mission_relevance)}</span> · U{" "}
            <span className="text-ink">{num(hover.utility, 3)}</span>
          </div>
          <div className="text-ink-3">
            {ACTION_LABEL[hover.final_action ?? ""] ?? "—"} · {bytes(hover.downlink_bytes)} · conf {pct(hover.confidence, 0)}
          </div>
          {hover.synthetic && <div style={{ color: "var(--s-warn)" }}>SYNTHETIC ANOMALY INJECTED</div>}
        </div>
      )}
      <div className="absolute top-1 right-2 mono text-[10px] text-ink-4">wheel: zoom · drag: pan · dbl-click: reset</div>
    </div>
  );
}
