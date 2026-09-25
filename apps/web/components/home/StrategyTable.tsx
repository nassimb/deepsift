"use client";

import { useState } from "react";
import { type CurvePoint, mb, p0, STRATEGY_LABEL } from "@/lib/home";

const BUDGETS = [0.001, 0.0025, 0.005, 0.01];

interface Props {
  real: Record<string, Record<string, CurvePoint>>;
  synthetic: Record<string, Record<string, CurvePoint>>;
  latency: { RULES: number; LOCAL_EDGE: number; priority_only: number };
  jev: { p50: number; costPer1k: number; aurocDiff: number; ci: [number, number]; runId: string };
  localEdge: { features: number; file_bytes: number };
}

/** Tradeoffs, not a leaderboard: every row shows the same four measured quantities (or says why it cannot). */
export function StrategyTable({ real, synthetic, latency, jev, localEdge }: Props) {
  const [f, setF] = useState(0.005);
  const row = (k: string) => ({ Y: synthetic[k]?.[String(f)], R: real[k]?.[String(f)] });
  const rows: { k: string; what: string; lat: string; cost: string }[] = [
    { k: "RULES", what: "Thresholds on deviation, rarity, duration → deterministic utility", lat: `${latency.RULES.toFixed(0)} ms`, cost: "none · onboard" },
    { k: "STATISTICAL", what: "Every window ranked by robust deviation; ignores candidates", lat: "not separated", cost: "none · onboard" },
    { k: "LOCAL_EDGE", what: `Logistic model on ${localEdge.features} event features · ${(localEdge.file_bytes / 1024).toFixed(1)} KiB file`, lat: `${latency.LOCAL_EDGE.toFixed(0)} ms`, cost: "none · onboard" },
    { k: "RULES_PLUS_STATISTICAL", what: "Rules first, leftover budget to statistical windows", lat: "not separated", cost: "none · onboard" },
  ];
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="label mr-1">Downlink budget</span>
        {BUDGETS.map((b) => (
          <button key={b} className="btn" data-active={b === f} onClick={() => setF(b)}>{b * 100}%</button>
        ))}
      </div>
      {/* phones: one card per strategy (same numbers, no sideways scrolling) */}
      <ul className="md:hidden space-y-2">
        {[...rows.map((x) => x.k), "JEV", "RANDOM", "ORACLE — NOT DEPLOYABLE"].map((k) => {
          if (k === "JEV") {
            return (
              <li key={k} className="border border-line p-3 space-y-1.5" style={{ background: "var(--panel-2)" }}>
                <div className="text-ink">Semantic decision model <span className="mono text-[11px] text-ink-3">Jev 1.13</span></div>
                <span className="chip inline-block" style={{ color: "var(--s-warn)", borderColor: "#5a4412" }}>VALIDATION PILOT ONLY</span>
                <div className="text-[12px] text-ink-2">
                  Not on the held-out test · ΔAUROC vs rules <span className="mono">{jev.aurocDiff >= 0 ? "+" : ""}{jev.aurocDiff.toFixed(3)}</span>{" "}
                  <span className="mono text-ink-3">[{jev.ci[0].toFixed(3)}, {jev.ci[1].toFixed(3)}]</span>
                </div>
                <div className="mono text-[11px] text-ink-3">+{jev.p50.toFixed(0)} ms remote · ${jev.costPer1k.toFixed(3)} / 1k events</div>
              </li>
            );
          }
          const { Y, R } = row(k);
          const meta = rows.find((x) => x.k === k);
          return (
            <li key={k} className="border border-line p-3" style={meta ? undefined : { opacity: 0.7 }}>
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-ink text-[13px]">{STRATEGY_LABEL[k]}</span>
                <span className="mono text-[15px] text-ink">{p0(Y?.high_any)}<span className="text-[11px] text-ink-3"> · {p0(Y?.high_full)} full</span></span>
              </div>
              <div className="mono text-[11px] text-ink-3 mt-1">
                real {R ? `${Math.round((R.high_any ?? 0) * R.high_labels)}/${R.high_labels}` : "—"} · {mb(R?.downlink_bytes)} sent{meta ? ` · ${meta.lat}` : k === "RANDOM" ? " · floor" : " · upper bound"}
              </div>
            </li>
          );
        })}
      </ul>
      <div className="hidden md:block overflow-x-auto border border-line">
        <table className="w-full min-w-[760px] text-[12.5px]">
          <thead>
            <tr className="label text-left border-b border-line">
              <th className="px-3 py-2 font-normal">Strategy</th>
              <th className="px-3 py-2 font-normal">High-priority recall<br />any · full fidelity</th>
              <th className="px-3 py-2 font-normal">Documented events<br />kept (real)</th>
              <th className="px-3 py-2 font-normal">Bytes transmitted<br />(real, 3 segments)</th>
              <th className="px-3 py-2 font-normal">Latency / event<br />(p50, laptop)</th>
              <th className="px-3 py-2 font-normal">Inference cost</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ k, what, lat, cost }) => {
              const { Y, R } = row(k);
              return (
                <tr key={k} className="border-b border-line align-top">
                  <td className="px-3 py-2.5">
                    <div className="text-ink">{STRATEGY_LABEL[k]}</div>
                    <div className="text-[11px] text-ink-3">{what}</div>
                  </td>
                  <td className="px-3 py-2.5 mono"><span className="text-ink">{p0(Y?.high_any)}</span> · <span className="text-ink-2">{p0(Y?.high_full)}</span></td>
                  <td className="px-3 py-2.5 mono text-ink-2">{R ? `${Math.round((R.high_any ?? 0) * R.high_labels)}/${R.high_labels}` : "—"}</td>
                  <td className="px-3 py-2.5 mono text-ink-2">{mb(R?.downlink_bytes)}</td>
                  <td className="px-3 py-2.5 mono text-ink-2">{lat}</td>
                  <td className="px-3 py-2.5 text-ink-3">{cost}</td>
                </tr>
              );
            })}
            <tr className="border-b border-line align-top" style={{ background: "var(--panel-2)" }}>
              <td className="px-3 py-2.5">
                <div className="text-ink">Semantic decision model <span className="mono text-[11px] text-ink-3">Jev 1.13</span></div>
                <div className="text-[11px] text-ink-3">Bounded scientific judgments on candidates only</div>
              </td>
              <td colSpan={3} className="px-3 py-2.5 text-[12px] text-ink-2">
                <span className="chip mr-2" style={{ color: "var(--s-warn)", borderColor: "#5a4412" }}>VALIDATION PILOT ONLY</span>
                Not run on the held-out test. Ordering vs rules on 100 validation high-priority events: ΔAUROC{" "}
                <span className="mono">{jev.aurocDiff >= 0 ? "+" : ""}{jev.aurocDiff.toFixed(3)}</span>{" "}
                <span className="mono text-ink-3">[{jev.ci[0].toFixed(3)}, {jev.ci[1].toFixed(3)}]</span> — no measurable gain.
              </td>
              <td className="px-3 py-2.5 mono text-ink-2">+{jev.p50.toFixed(0)} ms<div className="text-[10px] text-ink-3 font-sans">remote round trip</div></td>
              <td className="px-3 py-2.5 text-ink-3"><span className="mono text-ink-2">${jev.costPer1k.toFixed(3)}</span> / 1k events · via OpenRouter</td>
            </tr>
            {["RANDOM", "ORACLE — NOT DEPLOYABLE"].map((k) => {
              const { Y, R } = row(k);
              return (
                <tr key={k} className="border-b border-line last:border-b-0 align-top text-ink-3">
                  <td className="px-3 py-2">{STRATEGY_LABEL[k]} <span className="text-[11px]">· reference</span></td>
                  <td className="px-3 py-2 mono">{p0(Y?.high_any)} · {p0(Y?.high_full)}</td>
                  <td className="px-3 py-2 mono">{R ? `${Math.round((R.high_any ?? 0) * R.high_labels)}/${R.high_labels}` : "—"}</td>
                  <td className="px-3 py-2 mono">{mb(R?.downlink_bytes)}</td>
                  <td className="px-3 py-2" colSpan={2}>{k === "RANDOM" ? "floor" : "knows the labels — upper bound"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-ink-4 leading-relaxed">
        High-priority recall: injected high-severity events (synthetic) with any retained product overlapping them · full fidelity = a
        FULL_DATA product. Latency is the measured per-event routing time on a development laptop including amortized preprocessing, not
        flight hardware. Jev figures: validation run <span className="mono">{jev.runId}</span>.
      </p>
    </div>
  );
}
