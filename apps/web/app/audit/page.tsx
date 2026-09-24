"use client";

import { useEffect, useState } from "react";
import { Section } from "@/components/Kpi";
import { Nav, SourceBadges, useStatus } from "@/components/Nav";
import { api } from "@/lib/api";
import { ACTION_LABEL, num } from "@/lib/format";

interface Decision {
  run_id: string;
  event_id: string;
  recorded_at: string;
  pipeline_version: string;
  engine: string;
  model: string | null;
  confidence: number | null;
  gate: string;
  objective_id: string;
  config_version: string;
  proposed_action: string;
  final_action: string;
}
interface Run {
  run_id: string;
  created_at: string;
  pipeline_version: string;
  config_version: string;
  engine: string;
  deep_provider: string;
  objective_id: string;
  data_source: string;
  sols: number[];
  n_events: number;
  note: string;
}
interface Repro {
  match: boolean;
  stored: { utility: number; proposed_action: string };
  recomputed: { utility: number; proposed_action: string };
  note: string;
}

export default function AuditPage() {
  const { status } = useStatus();
  const [runs, setRuns] = useState<Run[]>([]);
  const [run, setRun] = useState<string | null>(null);
  const [rows, setRows] = useState<Decision[]>([]);
  const [filter, setFilter] = useState("");
  const [repro, setRepro] = useState<Record<string, Repro | string>>({});

  useEffect(() => {
    api<Run[]>("/api/audit/runs").then((r) => {
      setRuns(r);
      if (r[0]) setRun(r[0].run_id);
    });
  }, []);
  useEffect(() => {
    if (run) api<Decision[]>(`/api/audit/decisions?run_id=${encodeURIComponent(run)}&limit=500`).then(setRows);
  }, [run]);

  const reproduce = (d: Decision) =>
    api<Repro>("/api/audit/reproduce", { method: "POST", body: JSON.stringify({ run_id: d.run_id, event_id: d.event_id }) })
      .then((r) => setRepro((p) => ({ ...p, [d.event_id]: r })))
      .catch((e) => setRepro((p) => ({ ...p, [d.event_id]: String(e.message) })));

  const reproduceAll = async () => {
    for (const d of rows.slice(0, 200)) await reproduce(d);
  };
  const shown = rows.filter((r) => !filter || r.event_id.toLowerCase().includes(filter.toLowerCase()));
  const checked = Object.values(repro).filter((x) => typeof x !== "string") as Repro[];

  return (
    <div className="h-screen flex flex-col">
      <Nav right={<SourceBadges status={status} replay={false} />} />
      <div className="flex-1 min-h-0 grid grid-cols-[340px_minmax(0,1fr)] gap-px bg-line">
        <div className="bg-panel overflow-y-auto">
          <div className="label px-3 py-2 border-b border-line">Runs (pipeline + re-scores)</div>
          {runs.map((r) => (
            <button key={r.run_id} onClick={() => setRun(r.run_id)} className="w-full text-left px-3 py-1.5 border-b border-line hover:bg-panel-2" style={{ background: run === r.run_id ? "var(--panel-2)" : undefined }}>
              <div className="mono text-[10px] text-ink">{r.run_id}</div>
              <div className="mono text-[9px] text-ink-3">
                {r.note} · {r.objective_id} · cfg {r.config_version} · {r.engine} · {r.n_events} ev · {r.data_source}
              </div>
            </button>
          ))}
        </div>
        <div className="bg-bg p-3 min-h-0 flex flex-col gap-3">
          <div className="flex items-center gap-2">
            <input type="text" placeholder="filter event id" value={filter} onChange={(e) => setFilter(e.target.value)} className="w-64" />
            <button className="btn" onClick={reproduceAll}>Reproduce all decisions in run</button>
            <span className="mono text-[11px] text-ink-3">
              {checked.length > 0 && `${checked.filter((c) => c.match).length}/${checked.length} reproduced exactly from stored inputs`}
            </span>
          </div>
          <Section title={`Decisions · ${shown.length}`} className="flex-1">
            <div className="h-full overflow-auto">
              <table className="w-full mono text-[10px]">
                <thead className="text-ink-3 sticky top-0 bg-panel">
                  <tr className="text-left border-b border-line">
                    {["event", "recorded (UTC)", "pipeline", "engine", "gate", "confidence", "objective", "config", "proposed", "final", "reproduce"].map((h) => (
                      <th key={h} className="font-normal px-2 py-1 whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {shown.map((d) => {
                    const r = repro[d.event_id];
                    return (
                      <tr key={d.event_id + d.recorded_at} className="border-b border-line">
                        <td className="px-2 py-0.5 text-ink whitespace-nowrap">{d.event_id}</td>
                        <td className="px-2 text-ink-3 whitespace-nowrap">{d.recorded_at.slice(0, 19).replace("T", " ")}</td>
                        <td className="px-2 text-ink-3">v{d.pipeline_version}</td>
                        <td className="px-2 text-ink-2">{d.engine}</td>
                        <td className="px-2">{d.gate}</td>
                        <td className="px-2">{num(d.confidence, 3)}</td>
                        <td className="px-2 text-ink-2">{d.objective_id}</td>
                        <td className="px-2 text-ink-3">{d.config_version}</td>
                        <td className="px-2">{ACTION_LABEL[d.proposed_action] ?? d.proposed_action}</td>
                        <td className="px-2">{ACTION_LABEL[d.final_action] ?? d.final_action}</td>
                        <td className="px-2 whitespace-nowrap">
                          {r == null ? (
                            <button className="btn" style={{ padding: "0 6px" }} onClick={() => reproduce(d)}>run</button>
                          ) : typeof r === "string" ? (
                            <span style={{ color: "var(--s-critical)" }}>{r}</span>
                          ) : (
                            <span style={{ color: r.match ? "var(--s-good)" : "var(--s-critical)" }} title={r.note}>
                              {r.match ? "✓ exact" : "✗ differs"} U={num(r.recomputed.utility, 4)}
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Section>
          <div className="mono text-[10px] text-ink-4">
            Reproduction recomputes utility and proposed action from the stored event, stored engine answers, stored objective and stored config
            version. It does not re-query the decision engine (a real model may answer differently on a new call).
          </div>
        </div>
      </div>
    </div>
  );
}
