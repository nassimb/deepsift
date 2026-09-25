"use client";

import { useState } from "react";
import { ACTION_COLOR } from "@/lib/format";
import { ACT_LABEL, ACT_ORDER, type CurvePoint, mb, p0, STRATEGY_LABEL } from "@/lib/home";

const STOPS = [1, 0.1, 0.05, 0.01, 0.005, 0.001];
const STRATS = ["RULES_PLUS_STATISTICAL", "RULES", "LOCAL_EDGE", "STATISTICAL"];

interface Props {
  real: Record<string, Record<string, CurvePoint>>;
  synthetic: Record<string, Record<string, CurvePoint>>;
  rawBytes: number;
  segments: string;
  runId: string;
}

/** "What survives?" — measured held-out test outcomes at each downlink budget. 100 % is definitional (no triage). */
export function SurvivalExplorer({ real, synthetic, rawBytes, segments, runId }: Props) {
  const [i, setI] = useState(4);
  const [s, setS] = useState(STRATS[0]);
  const f = STOPS[i];
  const all = f >= 1;
  const R = real[s]?.[String(f)];
  const Y = synthetic[s]?.[String(f)];
  const units = s === "STATISTICAL" ? "instrument windows" : s === "RULES_PLUS_STATISTICAL" ? "candidate events + statistical windows" : "candidate events";
  const acts = R?.actions ?? {};
  const nUnits = ACT_ORDER.reduce((t, a) => t + (acts[a] ?? 0), 0);

  return (
    <div className="space-y-6">
      <h2 className="text-[26px] sm:text-[38px] leading-[1.12] font-medium text-ink max-w-4xl">
        The held-out segments produced <span className="mono">{mb(rawBytes)}</span>. Earth can receive{" "}
        <span className="mono" style={{ color: "var(--a-full)" }}>{all ? mb(rawBytes) : mb(rawBytes * f)}</span>. What survives?
      </h2>

      <div className="panel p-4 sm:p-5 space-y-5">
        <div className="grid gap-4 lg:grid-cols-[1fr_auto] lg:items-end">
          <div>
            <div className="flex items-baseline justify-between">
              <label htmlFor="bw" className="label">Downlink budget · share of raw data</label>
              <span className="mono text-[20px] text-ink">{(f * 100).toLocaleString(undefined, { maximumFractionDigits: 1 })}%</span>
            </div>
            <input id="bw" type="range" min={0} max={STOPS.length - 1} step={1} value={i} onChange={(e) => setI(Number(e.target.value))}
              className="home-range w-full mt-3" aria-valuetext={`${f * 100}%`} />
            <div className="grid grid-cols-6 mono text-[10px] text-ink-3 mt-1">
              {STOPS.map((x, k) => (
                <button key={x} onClick={() => setI(k)} className="text-left" style={{ color: k === i ? "var(--ink)" : undefined }}>
                  {x * 100}%
                </button>
              ))}
            </div>
          </div>
          <div>
            <div className="label mb-1.5">Strategy</div>
            <div className="flex flex-wrap gap-1">
              {STRATS.map((k) => (
                <button key={k} className="btn" data-active={k === s} onClick={() => setS(k)}>{STRATEGY_LABEL[k].replace("Hybrid · ", "")}</button>
              ))}
            </div>
          </div>
        </div>

        {all ? (
          <div className="border border-line p-4 text-[14px] text-ink-2">
            At 100% everything is transmitted and no triage decision is needed — the case a mission can rarely afford. Move the slider to a
            measured budget.
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-3">
            <Cell label="Data sent to Earth">
              <div className="mono text-[26px] text-ink">{mb(R?.downlink_bytes)}</div>
              <div className="text-[12px] text-ink-3">of {mb(R?.raw_bytes)} raw · {mb(rawBytes - (R?.downlink_bytes ?? 0))} never leaves the rover</div>
            </Cell>
            <Cell label={`Decisions on ${nUnits.toLocaleString()} ${units}`}>
              <div className="flex h-6 w-full overflow-hidden border border-line-2">
                {ACT_ORDER.map((a) =>
                  acts[a] ? <div key={a} style={{ width: `${((acts[a] ?? 0) / nUnits) * 100}%`, background: ACTION_COLOR[a] }} title={`${ACT_LABEL[a]} ${Math.round(acts[a] ?? 0)}`} /> : null,
                )}
              </div>
              <div className="grid grid-cols-2 gap-x-3 mt-2 mono text-[11px]">
                {ACT_ORDER.map((a) => (
                  <span key={a} className="flex items-center gap-1.5 text-ink-3">
                    <i className="inline-block w-2 h-2" style={{ background: ACTION_COLOR[a] }} />
                    {ACT_LABEL[a]} <span className="text-ink ml-auto">{Math.round(acts[a] ?? 0).toLocaleString()}</span>
                  </span>
                ))}
              </div>
            </Cell>
            <Cell label="High-priority events preserved">
              <div className="flex items-baseline gap-3">
                <span className="mono text-[26px] text-ink">{p0(Y?.high_any)}</span>
                <span className="mono text-[13px] text-ink-2">{p0(Y?.high_full)} at full fidelity</span>
              </div>
              <div className="text-[12px] text-ink-3">of {Y?.high_labels.toLocaleString()} injected high-severity events (synthetic, controlled)</div>
              <div className="mono text-[12px] text-ink-2 mt-2">
                Documented real events: {Math.round((R?.high_any ?? 0) * (R?.high_labels ?? 0))}/{R?.high_labels} kept ·{" "}
                {Math.round((R?.high_full ?? 0) * (R?.high_labels ?? 0))}/{R?.high_labels} full
              </div>
            </Cell>
          </div>
        )}
        <p className="text-[11px] text-ink-4 leading-relaxed">
          Measured on the held-out test split ({segments}), run <span className="mono">{runId}</span>, frozen configuration, evaluated once.
          Synthetic events are clearly labelled injections into real data; documented events are published SEP, Forbush-decrease and
          dust-storm dates (n is small).
        </p>
      </div>
    </div>
  );
}

function Cell({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="border border-line p-3 space-y-1.5">
      <div className="label">{label}</div>
      {children}
    </div>
  );
}
