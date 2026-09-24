"use client";

import { useMemo, useState } from "react";
import type { EventRow, Series } from "@/lib/api";
import { ACTION_LABEL, TYPE_COLOR, solClock } from "@/lib/format";
import { useSize } from "./useSize";

/** One telemetry channel: min–max band + mean line, candidate-event spans, replay cursor.
 *  Data after the replay cursor is not drawn (it has not "arrived" yet). */
export function StripChart({
  series,
  label,
  unit,
  domain,
  cursor,
  events,
  onSelect,
  mode = "raw",
  height,
}: {
  series: Series | null;
  label: string;
  unit: string;
  domain: [number, number];
  cursor?: number;
  events: EventRow[];
  onSelect?: (id: string) => void;
  mode?: "raw" | "normalized";
  height?: number;
}) {
  const [ref, { w, h: hh }] = useSize<HTMLDivElement>();
  const h = height ?? hh;
  const [hx, setHx] = useState<number | null>(null);
  const m = { l: 52, r: 8, t: 4, b: 4 };
  const iw = Math.max(1, w - m.l - m.r);
  const ih = Math.max(1, h - m.t - m.b);
  const [a, b] = domain;
  const sx = (s: number) => m.l + ((s - a) / (b - a)) * iw;
  const upto = cursor ?? Infinity;

  const data = useMemo(() => {
    if (!series) return null;
    if (mode === "normalized") {
      const ws = series.windows.filter((p) => p[0] >= a && p[0] <= b && p[0] <= upto);
      return { kind: "win" as const, ws };
    }
    const ps = series.points.filter((p) => p[0] >= a && p[0] <= b && p[0] <= upto);
    return { kind: "pts" as const, ps };
  }, [series, a, b, upto, mode]);

  const [y0, y1] = useMemo(() => {
    if (!series) return [0, 1];
    if (mode === "normalized") return [-8, 8];
    const vis = series.points.filter((p) => p[0] >= a && p[0] <= b);
    if (!vis.length) return [0, 1];
    let lo = Infinity,
      hi = -Infinity;
    for (const p of vis) {
      lo = Math.min(lo, p[2]);
      hi = Math.max(hi, p[3]);
    }
    const pad = (hi - lo) * 0.08 || 1;
    return [lo - pad, hi + pad];
  }, [series, a, b, mode]);
  const sy = (v: number) => m.t + (1 - (v - y0) / (y1 - y0)) * ih;

  const channel = series?.channel;
  const spans = events.filter((e) => channel && e.sensors.includes(channel) && e.sol_end >= a && e.sol_start <= b && e.sol_start <= upto);

  let band = "";
  let line = "";
  if (data?.kind === "pts" && data.ps.length) {
    // break the path across sampling gaps (REMS samples in bursts)
    const gap = (b - a) / 200;
    let prev: number | null = null;
    for (const p of data.ps) {
      const cmd = prev == null || p[0] - prev > gap ? "M" : "L";
      line += `${cmd}${sx(p[0]).toFixed(1)},${sy(p[1]).toFixed(1)}`;
      prev = p[0];
    }
    const up = data.ps.map((p) => `${sx(p[0]).toFixed(1)},${sy(p[3]).toFixed(1)}`);
    const dn = data.ps.map((p) => `${sx(p[0]).toFixed(1)},${sy(p[2]).toFixed(1)}`).reverse();
    band = `M${up.join("L")}L${dn.join("L")}Z`;
  }

  const hoverVal = useMemo(() => {
    if (hx == null || !data) return null;
    const s = a + ((hx - m.l) / iw) * (b - a);
    const arr = data.kind === "pts" ? data.ps : data.ws;
    if (!arr.length) return null;
    let best = arr[0];
    for (const p of arr) if (Math.abs(p[0] - s) < Math.abs(best[0] - s)) best = p;
    return best;
  }, [hx, data, a, b, iw, m.l]);

  return (
    <div ref={ref} className="relative w-full" style={{ height: height ?? "100%" }}>
      {w > 0 && (
        <svg
          width={w}
          height={h}
          onPointerMove={(e) => setHx(e.clientX - (e.currentTarget as SVGElement).getBoundingClientRect().left)}
          onPointerLeave={() => setHx(null)}
        >
          <line x1={m.l} x2={m.l + iw} y1={m.t + ih} y2={m.t + ih} stroke="var(--line)" />
          {spans.map((e) => (
            <rect
              key={e.id}
              x={sx(e.sol_start)}
              y={m.t}
              width={Math.max(2, sx(e.sol_end) - sx(e.sol_start))}
              height={ih}
              fill={TYPE_COLOR[e.event_type ?? "nominal"]}
              opacity={e.final_action === "discard" ? 0.08 : 0.2}
              style={{ cursor: onSelect ? "pointer" : undefined }}
              onClick={() => onSelect?.(e.id)}
            >
              <title>{`${e.id} · ${ACTION_LABEL[e.final_action ?? ""] ?? ""}`}</title>
            </rect>
          ))}
          {data?.kind === "pts" && (
            <>
              <path d={band} fill="var(--ink-2)" opacity={0.14} />
              <path d={line} fill="none" stroke="var(--ink-2)" strokeWidth={1.25} />
              {data.ps.length < 120 &&
                data.ps.map((p, i) => <circle key={`d${i}`} cx={sx(p[0])} cy={sy(p[1])} r={2} fill="var(--ink-2)" />)}
              {data.ps
                .filter((p) => p[4])
                .map((p, i) => (
                  <circle key={i} cx={sx(p[0])} cy={sy(p[1])} r={2.5} fill="var(--s-warn)" />
                ))}
            </>
          )}
          {data?.kind === "win" && (
            <>
              {[-4, 0, 4].map((v) => (
                <line key={v} x1={m.l} x2={m.l + iw} y1={sy(v)} y2={sy(v)} stroke={v === 0 ? "var(--line-2)" : "var(--grid)"} strokeDasharray={v ? "2 3" : undefined} />
              ))}
              {data.ws.map((p, i) => (
                <rect key={i} x={sx(p[0]) - 1} width={2} y={Math.min(sy(0), sy(Math.max(-8, Math.min(8, p[1]))))} height={Math.abs(sy(0) - sy(Math.max(-8, Math.min(8, p[1]))))} fill={p[3] ? "var(--ink)" : "var(--ink-4)"} />
              ))}
            </>
          )}
          {cursor != null && cursor >= a && cursor <= b && <line x1={sx(cursor)} x2={sx(cursor)} y1={m.t} y2={m.t + ih} stroke="var(--ink)" strokeWidth={1} />}
          {hx != null && hx > m.l && <line x1={hx} x2={hx} y1={m.t} y2={m.t + ih} stroke="var(--ink-4)" strokeDasharray="2 2" />}
          <text x={4} y={m.t + 11} className="mono" fontSize={10} fill="var(--ink-2)">
            {label}
          </text>
          <text x={4} y={m.t + 23} className="mono" fontSize={9} fill="var(--ink-4)">
            {mode === "normalized" ? "robust z" : unit}
          </text>
          <text x={m.l - 4} y={m.t + 9} textAnchor="end" className="mono" fontSize={9} fill="var(--ink-4)">
            {mode === "normalized" ? "+8" : y1.toFixed(y1 > 100 ? 0 : 1)}
          </text>
          <text x={m.l - 4} y={m.t + ih - 1} textAnchor="end" className="mono" fontSize={9} fill="var(--ink-4)">
            {mode === "normalized" ? "−8" : y0.toFixed(y0 > 100 ? 0 : 1)}
          </text>
        </svg>
      )}
      {hoverVal && hx != null && (
        <div className="absolute pointer-events-none panel px-1.5 py-0.5 mono text-[10px] z-10" style={{ left: Math.min(hx + 8, w - 190), top: 2 }}>
          <span className="text-ink">
            {mode === "normalized" ? `${(hoverVal[1] as number).toFixed(2)} σ` : `${(hoverVal[1] as number).toFixed(2)} ${unit}`}
          </span>{" "}
          <span className="text-ink-3">{solClock(hoverVal[0] as number)}</span>
        </div>
      )}
    </div>
  );
}
