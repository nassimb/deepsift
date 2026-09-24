"use client";

import { useEffect, useState } from "react";
import { Section } from "@/components/Kpi";
import { Nav, SourceBadges, useStatus } from "@/components/Nav";
import { api } from "@/lib/api";
import { bytes, num, pct } from "@/lib/format";

type Stat = { mean: number; std: number; n: number } | null;
interface StrategySummary {
  available: boolean;
  reason?: string;
  recall?: Stat;
  recall_high?: Stat;
  retained_unlabeled_rate?: Stat;
  downlink_bytes?: Stat;
  data_reduction?: Stat;
  science_value_per_mb_proxy?: Stat;
  strategy_wall_ms?: Stat;
  deep_calls?: Stat;
  engine_calls?: Stat;
  expensive_fraction?: Stat;
  units_considered?: Stat;
  recall_by_source?: Record<string, number>;
  cost_usd?: number | null;
}
interface ExpListItem {
  id: string;
  created_at: string;
  engine: { name: string; is_real_model: boolean };
  trials: number;
  config_version: string;
  data_source: string;
  summary: Record<string, StrategySummary>;
}
interface Experiment extends ExpListItem {
  budget_bytes: number;
  sols: number[];
  caveats: string[];
  deep_provider: string;
  objective: string;
  pipeline_version: string;
  per_trial: { seed: number; injections: { id: string; kind: string; t_start: string; magnitude: number }[]; strategies: Record<string, { per_label?: Record<string, { source: string; severity: string; recovered: boolean; action: string | null }> }> }[];
}

const NAMES: Record<string, string> = {
  random: "Random sampling",
  rules: "Threshold rules",
  statistical: "Statistical anomaly",
  engine: "Decision engine",
  engine_deep: "Engine + deep analysis",
};

function Bars({ exp, metric, fmt, better }: { exp: Experiment; metric: keyof StrategySummary; fmt: (x: number) => string; better: "high" | "low" }) {
  const rows = Object.entries(exp.summary).map(([k, v]) => ({ k, v, s: v.available ? (v[metric] as Stat) : null }));
  const max = Math.max(1e-9, ...rows.map((r) => (r.s ? r.s.mean + r.s.std : 0)));
  return (
    <div className="space-y-1.5">
      {rows.map(({ k, v, s }) => (
        <div key={k} className="grid grid-cols-[150px_1fr_110px] items-center gap-2">
          <span className="mono text-[10px] text-ink-2 truncate">
            {NAMES[k] ?? k}
            {k.startsWith("engine") && v.available && !exp.engine.is_real_model ? " (mock)" : ""}
          </span>
          {s ? (
            <div className="relative h-3">
              <div className="absolute inset-y-0 left-0" style={{ width: `${(s.mean / max) * 100}%`, background: "var(--ink-2)" }} />
              {s.std > 0 && (
                <div
                  className="absolute top-1/2 h-px"
                  style={{ left: `${((s.mean - s.std) / max) * 100}%`, width: `${((2 * s.std) / max) * 100}%`, background: "var(--ink)" }}
                />
              )}
            </div>
          ) : (
            <span className="mono text-[10px] text-ink-4">UNAVAILABLE</span>
          )}
          <span className="mono text-[11px] text-right">{s ? `${fmt(s.mean)} ± ${fmt(s.std)}` : "—"}</span>
        </div>
      ))}
      <div className="mono text-[9px] text-ink-4">{better === "high" ? "higher is better" : "lower is better"} · bar = mean over trials, whisker = ±1 sd</div>
    </div>
  );
}

export default function ExperimentsPage() {
  const { status } = useStatus();
  const [list, setList] = useState<ExpListItem[]>([]);
  const [exp, setExp] = useState<Experiment | null>(null);
  const [trials, setTrials] = useState(3);
  const [running, setRunning] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const refresh = () =>
    api<ExpListItem[]>("/api/experiments").then((l) => {
      setList(l);
      if (l[0] && !exp) api<Experiment>(`/api/experiments/${l[0].id}`).then(setExp);
    });
  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const run = async () => {
    setRunning(true);
    setErr(null);
    try {
      const r = await api<Experiment>("/api/experiments", { method: "POST", body: JSON.stringify({ trials }) });
      setExp(r);
      void refresh();
    } catch (e) {
      setErr(String((e as Error).message));
    } finally {
      setRunning(false);
    }
  };

  const order = ["random", "rules", "statistical", "engine", "engine_deep"];

  return (
    <div className="min-h-screen flex flex-col">
      <Nav right={<SourceBadges status={status} replay={false} />} />
      <div className="flex items-center gap-3 px-4 h-11 border-b border-line">
        <span className="label">Experiment · same data, same byte budget, five strategies</span>
        <label className="mono text-[11px] text-ink-3 flex items-center gap-1 ml-auto">
          trials (injection seeds)
          <input type="number" min={1} max={10} value={trials} onChange={(e) => setTrials(Number(e.target.value))} className="w-14" />
        </label>
        <button className="btn" onClick={run} disabled={running}>
          {running ? "Running…" : "Run benchmark"}
        </button>
      </div>
      {running && <div className="px-4 py-2 mono text-[11px] text-ink-3 state-pulse">running {trials} trial(s) of detection + 5 strategies on the processed segment… (≈6 s per trial on the development machine)</div>}
      {err && <div className="px-4 py-2 mono text-[11px]" style={{ color: "var(--s-critical)" }}>{err}</div>}

      <div className="flex-1 grid grid-cols-[260px_minmax(0,1fr)] gap-px bg-line">
        <div className="bg-panel">
          <div className="label px-3 py-2 border-b border-line">Stored experiments</div>
          {list.map((x) => (
            <button key={x.id} className="w-full text-left px-3 py-1.5 border-b border-line hover:bg-panel-2" onClick={() => api<Experiment>(`/api/experiments/${x.id}`).then(setExp)} style={{ background: exp?.id === x.id ? "var(--panel-2)" : undefined }}>
              <div className="mono text-[10px] text-ink">{x.id}</div>
              <div className="mono text-[9px] text-ink-3">
                {x.engine.name} · {x.trials} trials · cfg {x.config_version}
              </div>
            </button>
          ))}
          {!list.length && <div className="p-3 text-ink-3 text-[12px]">No experiments yet. Run one.</div>}
        </div>

        <div className="bg-bg p-3 space-y-3 min-w-0">
          {!exp ? (
            <div className="text-ink-3 text-[12px]">No result selected.</div>
          ) : (
            <>
              <div className="panel p-3 grid grid-cols-6 gap-3">
                {[
                  ["Experiment", exp.id],
                  ["Engine", `${exp.engine.name}${exp.engine.is_real_model ? "" : " (NOT a model)"}`],
                  ["Data", `${exp.data_source} · sols ${exp.sols[0]}–${exp.sols.at(-1)}`],
                  ["Byte budget", bytes(exp.budget_bytes)],
                  ["Trials", `${exp.trials} (seeds ${exp.per_trial.map((t) => t.seed).join(", ")})`],
                  ["Config / pipeline", `${exp.config_version} / v${exp.pipeline_version}`],
                ].map(([k, v]) => (
                  <div key={k}>
                    <div className="label">{k}</div>
                    <div className="mono text-[11px] text-ink break-all">{v}</div>
                  </div>
                ))}
              </div>
              {!exp.engine.is_real_model && (
                <div className="panel p-2 mono text-[11px]" style={{ color: "var(--s-warn)", borderColor: "#5a4412" }}>
                  ENGINE ROWS USE THE MOCK HEURISTIC, NOT JEV. They show the pipeline works end-to-end; they are not evidence about Jev. Set
                  TYPESAFE_API_KEY (decision_engine.kind: auto) to measure the real model.
                </div>
              )}

              <div className="grid grid-cols-2 gap-3">
                <Section title="Event recall (all labels)"><div className="p-3"><Bars exp={exp} metric="recall" fmt={(x) => pct(x, 0)} better="high" /></div></Section>
                <Section title="High-severity recall"><div className="p-3"><Bars exp={exp} metric="recall_high" fmt={(x) => pct(x, 0)} better="high" /></div></Section>
                <Section title="Labeled science value per downlinked MB (PROXY)"><div className="p-3"><Bars exp={exp} metric="science_value_per_mb_proxy" fmt={(x) => num(x, 1)} better="high" /></div></Section>
                <Section title="Retained-but-unlabeled rate (upper bound on FPR)"><div className="p-3"><Bars exp={exp} metric="retained_unlabeled_rate" fmt={(x) => pct(x, 0)} better="low" /></div></Section>
              </div>

              <Section title="Full metric table (mean over trials)">
                <div className="overflow-x-auto">
                  <table className="w-full mono text-[11px]">
                    <thead className="text-ink-3">
                      <tr className="text-left border-b border-line">
                        {["strategy", "recall", "high recall", "documented", "synthetic", "unlabeled kept", "downlink", "reduction", "value/MB proxy", "units", "engine calls", "deep calls", "% expensive", "wall ms", "cost"].map((h) => (
                          <th key={h} className="font-normal px-2 py-1.5 whitespace-nowrap">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {order.map((k) => {
                        const v = exp.summary[k];
                        if (!v) return null;
                        if (!v.available)
                          return (
                            <tr key={k} className="border-b border-line text-ink-4">
                              <td className="px-2 py-1">{NAMES[k]}</td>
                              <td colSpan={14} className="px-2">UNAVAILABLE — {v.reason}</td>
                            </tr>
                          );
                        const m = (s: Stat | undefined, f: (x: number) => string) => (s ? f(s.mean) : "—");
                        return (
                          <tr key={k} className="border-b border-line">
                            <td className="px-2 py-1 text-ink">{NAMES[k]}{k.startsWith("engine") && !exp.engine.is_real_model ? " (mock)" : ""}</td>
                            <td className="px-2">{m(v.recall, (x) => pct(x, 1))}</td>
                            <td className="px-2">{m(v.recall_high, (x) => pct(x, 1))}</td>
                            <td className="px-2">{pct(v.recall_by_source?.DOCUMENTED_EVENT, 0)}</td>
                            <td className="px-2">{pct(v.recall_by_source?.SYNTHETIC_ANOMALY, 0)}</td>
                            <td className="px-2">{m(v.retained_unlabeled_rate, (x) => pct(x, 0))}</td>
                            <td className="px-2">{m(v.downlink_bytes, bytes)}</td>
                            <td className="px-2">{m(v.data_reduction, (x) => pct(x, 2))}</td>
                            <td className="px-2">{m(v.science_value_per_mb_proxy, (x) => num(x, 1))}</td>
                            <td className="px-2">{m(v.units_considered, (x) => x.toFixed(0))}</td>
                            <td className="px-2">{m(v.engine_calls, (x) => x.toFixed(0))}</td>
                            <td className="px-2">{m(v.deep_calls, (x) => x.toFixed(0))}</td>
                            <td className="px-2">{m(v.expensive_fraction, (x) => pct(x, 1))}</td>
                            <td className="px-2">{m(v.strategy_wall_ms, (x) => x.toFixed(1))}</td>
                            <td className="px-2">{v.cost_usd == null ? "n/a" : `$${v.cost_usd.toFixed(5)}`}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </Section>

              <div className="grid grid-cols-2 gap-3">
                <Section title="Caveats (read before citing)">
                  <ul className="p-3 space-y-1.5 text-[12px] text-ink-2">
                    {exp.caveats.map((c, i) => (
                      <li key={i}>— {c}</li>
                    ))}
                  </ul>
                </Section>
                <Section title={`Per-label outcome · trial seed ${exp.per_trial[0]?.seed}`}>
                  <div className="overflow-x-auto max-h-80">
                    <table className="w-full mono text-[10px]">
                      <thead className="text-ink-3 sticky top-0 bg-panel">
                        <tr className="text-left">
                          <th className="font-normal px-2 py-1">label</th>
                          <th className="font-normal">source</th>
                          {order.filter((k) => exp.summary[k]?.available).map((k) => (
                            <th key={k} className="font-normal text-center">{k}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(exp.per_trial[0]?.strategies.rules?.per_label ?? {}).map(([lid, l]) => (
                          <tr key={lid} className="border-t border-line">
                            <td className="px-2 py-0.5 text-ink-2 whitespace-nowrap">{lid}</td>
                            <td className="text-ink-3">{l.source === "DOCUMENTED_EVENT" ? "DOCUMENTED" : "SYNTHETIC"}</td>
                            {order.filter((k) => exp.summary[k]?.available).map((k) => {
                              const r = exp.per_trial[0].strategies[k]?.per_label?.[lid];
                              return (
                                <td key={k} className="text-center" style={{ color: r?.recovered ? "var(--ink)" : "var(--ink-4)" }}>
                                  {r?.recovered ? (r.action === "full_data" ? "FULL" : r.action === "compress" ? "CMP" : "SUM") : "·"}
                                </td>
                              );
                            })}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Section>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
