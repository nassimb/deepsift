"use client";

import { useEffect, useState } from "react";

/** Phones get their own chart geometry (larger type, fewer ticks), not a shrunken desktop chart. */
function useNarrow() {
  const [n, setN] = useState(false);
  useEffect(() => {
    const m = window.matchMedia("(max-width: 639px)");
    const f = () => setN(m.matches);
    f();
    m.addEventListener("change", f);
    return () => m.removeEventListener("change", f);
  }, []);
  return n;
}
import { type CurvePoint, p0, STRATEGY_LABEL } from "@/lib/home";

const SERIES: { k: string; stroke: string; dash?: string; w: number }[] = [
  { k: "RULES_PLUS_STATISTICAL", stroke: "var(--a-full)", w: 2.2 },
  { k: "RULES", stroke: "var(--ink)", w: 1.6 },
  { k: "LOCAL_EDGE", stroke: "var(--ink-2)", dash: "5 3", w: 1.6 },
  { k: "STATISTICAL", stroke: "var(--ink-3)", dash: "1.5 3", w: 1.8 },
  { k: "RANDOM", stroke: "var(--ink-4)", dash: "6 4", w: 1.2 },
];

/** High-priority recall vs downlink budget, held-out test (real measured curves; no placeholders). */
export function BenchmarkChart({ synthetic, budgets }: { synthetic: Record<string, Record<string, CurvePoint>>; budgets: number[] }) {
  const [mode, setMode] = useState<"high_any" | "high_full">("high_any");
  const [hover, setHover] = useState<number | null>(null);
  const [W, H, fs] = useNarrow() ? [360, 260, 12] : [720, 300, 10];
  const L = fs === 12 ? 40 : 44, R = 12, T = 14, B = 34;
  const showTick = (b: number) => fs === 10 || [0.001, 0.01, 0.1].includes(b);
  const lx = (b: number) => Math.log10(b);
  const x0 = lx(budgets[0]), x1 = lx(budgets[budgets.length - 1]);
  const X = (b: number) => L + ((lx(b) - x0) / (x1 - x0)) * (W - L - R);
  const Y = (v: number) => T + (1 - v) * (H - T - B);
  const v = (k: string, b: number) => synthetic[k]?.[String(b)]?.[mode] ?? null;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="label mr-1">Counted as preserved</span>
        <button className="btn" data-active={mode === "high_any"} onClick={() => setMode("high_any")}>any fidelity</button>
        <button className="btn" data-active={mode === "high_full"} onClick={() => setMode("high_full")}>full data only</button>
      </div>
      <div className="panel p-2">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img"
          aria-label="High-priority event recall versus downlink budget for each strategy, held-out test"
          onMouseLeave={() => setHover(null)}>
          <rect x={X(budgets[0])} y={T} width={X(0.01) - X(budgets[0])} height={H - T - B} fill="var(--panel-2)" />
          <text x={X(budgets[0]) + 6} y={T + 12} className="mono" fontSize={fs - 0.5} fill="var(--ink-3)">{fs === 10 ? "EXTREME BANDWIDTH ≤ 1%" : "≤ 1%"}</text>
          {[0, 0.25, 0.5, 0.75, 1].map((g) => (
            <g key={g}>
              <line x1={L} x2={W - R} y1={Y(g)} y2={Y(g)} stroke="var(--grid)" />
              <text x={L - 6} y={Y(g) + 3} textAnchor="end" fontSize={fs} className="mono" fill="var(--ink-3)">{g * 100}%</text>
            </g>
          ))}
          {budgets.map((b, i) => (
            <g key={b}>
              {showTick(b) && <text x={X(b)} y={H - B + 16} textAnchor="middle" fontSize={fs} className="mono" fill="var(--ink-3)">{b * 100}%</text>}
              <rect x={X(b) - 14} y={T} width={28} height={H - T - B} fill="transparent" onMouseEnter={() => setHover(i)} />
            </g>
          ))}
          <text x={(L + W - R) / 2} y={H - 4} textAnchor="middle" fontSize={fs - 1} className="mono" fill="var(--ink-4)">{fs === 10 ? "DOWNLINK BUDGET · SHARE OF RAW DATA (LOG)" : "BUDGET (LOG)"}</text>
          {hover != null && <line x1={X(budgets[hover])} x2={X(budgets[hover])} y1={T} y2={H - B} stroke="var(--ink-4)" />}
          {SERIES.map(({ k, stroke, dash, w }) => {
            const pts = budgets.map((b) => [X(b), v(k, b)] as const).filter(([, y]) => y != null) as [number, number][];
            return (
              <g key={k}>
                <polyline points={pts.map(([x, y]) => `${x},${Y(y)}`).join(" ")} fill="none" stroke={stroke} strokeWidth={w} strokeDasharray={dash} />
                {pts.map(([x, y], i) => <circle key={i} cx={x} cy={Y(y)} r={hover === i ? 3.2 : 2} fill={stroke} />)}
              </g>
            );
          })}
        </svg>
      </div>
      <div className="grid gap-x-6 gap-y-1 sm:grid-cols-2 lg:grid-cols-3">
        {SERIES.map(({ k, stroke, dash, w }) => (
          <div key={k} className="flex items-center gap-2 text-[12px]">
            <svg width="26" height="8" aria-hidden><line x1="0" x2="26" y1="4" y2="4" stroke={stroke} strokeWidth={w} strokeDasharray={dash} /></svg>
            <span className="text-ink-2">{STRATEGY_LABEL[k]}</span>
            <span className="mono text-ink ml-auto sm:ml-2">{hover != null ? p0(v(k, budgets[hover])) : ""}</span>
          </div>
        ))}
        <div className="flex items-center gap-2 text-[12px] text-ink-3">
          <span className="chip" style={{ color: "var(--s-warn)", borderColor: "#5a4412" }}>JEV · NOT ON HELD-OUT TEST</span>
        </div>
      </div>
      <p className="text-[11px] text-ink-4">
        {hover != null ? `At ${budgets[hover] * 100}% — ` : "Hover a budget for values. "}Oracle (knows the labels) is 100% at every budget
        and is omitted. Injected high-severity events, 3 held-out segments × 25 batches.
      </p>
    </div>
  );
}
