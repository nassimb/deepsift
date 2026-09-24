"use client";

import { useEffect, useState } from "react";
import { api, type Objective } from "@/lib/api";
import { ACTION_LABEL, TYPES, TYPE_LABEL, num } from "@/lib/format";

interface CompareRow {
  id: string;
  utility_before: number;
  utility_after: number;
  action_before: string;
  action_after: string;
  rank_before: number;
  rank_after: number;
}

/** Mission objective selector with a BEFORE / AFTER ranking comparison computed from stored
 *  decisions (no raw pipeline, no engine calls). */
export function ObjectivePanel({ activeId, onApplied, onClose }: { activeId: string; onApplied: () => void; onClose: () => void }) {
  const [objs, setObjs] = useState<Record<string, Objective>>({});
  const [target, setTarget] = useState<string>(activeId);
  const [rows, setRows] = useState<CompareRow[] | null>(null);
  const [ms, setMs] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [custom, setCustom] = useState<Objective>({
    id: "custom_1",
    name: "Custom objective",
    description: "",
    type_weights: { nominal: 0.05, atmospheric: 0.5, radiation: 0.5, thermal: 0.5, instrument_anomaly: 0.5, unknown: 0.5 },
    channel_weights: {},
    priority_weights: null,
    custom: true,
  });

  useEffect(() => {
    api<{ objectives: Record<string, Objective> }>("/api/objectives").then((r) => setObjs(r.objectives));
  }, []);

  const compare = async (apply = false) => {
    setBusy(true);
    try {
      const body = target === "__custom" ? { custom, apply } : { objective_id: target, apply };
      const r = await api<{ rows: CompareRow[]; rescore_ms: number }>("/api/objectives/compare", { method: "POST", body: JSON.stringify(body) });
      setRows(r.rows);
      setMs(r.rescore_ms);
      if (apply) onApplied();
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (!target || target === "__custom") return;
    let alive = true;
    api<{ rows: CompareRow[]; rescore_ms: number }>("/api/objectives/compare", { method: "POST", body: JSON.stringify({ objective_id: target, apply: false }) }).then(
      (r) => {
        if (!alive) return;
        setRows(r.rows);
        setMs(r.rescore_ms);
      },
    );
    return () => {
      alive = false;
    };
  }, [target]);

  const sel = target === "__custom" ? custom : objs[target];
  const changed = rows?.filter((r) => r.action_after !== r.action_before) ?? [];

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-2 px-3 h-8 border-b border-line">
        <span className="label" style={{ color: "var(--ink-2)" }}>Mission objective</span>
        <button className="btn ml-auto" onClick={onClose}>Close</button>
      </div>
      <div className="p-3 space-y-2 border-b border-line">
        <div className="flex flex-wrap gap-1">
          {Object.values(objs).map((o) => (
            <button key={o.id} className="btn" data-active={target === o.id} onClick={() => setTarget(o.id)}>
              {o.name}
              {o.id === activeId ? " ●" : ""}
            </button>
          ))}
          <button className="btn" data-active={target === "__custom"} onClick={() => setTarget("__custom")}>
            + Custom
          </button>
        </div>
        {sel && <div className="text-[12px] text-ink-2 leading-snug">{sel.description}</div>}
        {target === "__custom" && (
          <div className="space-y-1">
            <input type="text" value={custom.name} onChange={(e) => setCustom({ ...custom, name: e.target.value, id: "custom_" + e.target.value.toLowerCase().replace(/\W+/g, "_") })} className="w-full" />
            <textarea
              value={custom.description}
              placeholder="Describe the objective (stored with the audit record; scoring uses the structured weights below)"
              onChange={(e) => setCustom({ ...custom, description: e.target.value })}
              className="w-full h-12"
            />
          </div>
        )}
        {sel && (
          <div className="grid grid-cols-2 gap-x-4 gap-y-1">
            {TYPES.map((t) => (
              <label key={t} className="flex items-center gap-2 mono text-[10px]">
                <span className="w-28 text-ink-3">{TYPE_LABEL[t]}</span>
                {target === "__custom" ? (
                  <input
                    type="range"
                    min={0}
                    max={1}
                    step={0.05}
                    value={custom.type_weights[t] ?? 0}
                    onChange={(e) => setCustom({ ...custom, type_weights: { ...custom.type_weights, [t]: Number(e.target.value) } })}
                    onPointerUp={() => void compare(false)}
                    className="flex-1"
                  />
                ) : (
                  <div className="flex-1 h-1.5 bg-panel-2">
                    <div className="h-full" style={{ width: `${(sel.type_weights[t] ?? 0) * 100}%`, background: "var(--ink-2)" }} />
                  </div>
                )}
                <span className="w-8 text-right">{num(sel.type_weights[t] ?? 0)}</span>
              </label>
            ))}
          </div>
        )}
        {sel?.channel_weights && Object.keys(sel.channel_weights).length > 0 && (
          <div className="mono text-[10px] text-ink-3">channel weights: {Object.entries(sel.channel_weights).map(([k, v]) => `${k}=${v}`).join(", ")}</div>
        )}
        <div className="flex items-center gap-2">
          <button className="btn" disabled={busy || target === activeId} onClick={() => compare(true)}>
            Apply objective
          </button>
          <span className="mono text-[10px] text-ink-3">
            {ms != null && `re-scored ${rows?.length ?? 0} events in ${ms.toFixed(1)} ms · 0 engine calls · ${changed.length} actions change`}
          </span>
        </div>
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto">
        <table className="w-full mono text-[10px]">
          <thead className="text-ink-3 sticky top-0 bg-panel">
            <tr className="text-left">
              <th className="font-normal px-2 py-1">event</th>
              <th className="font-normal text-right">BEFORE rank</th>
              <th className="font-normal text-right">AFTER rank</th>
              <th className="font-normal text-right">Δ</th>
              <th className="font-normal text-right">U before→after</th>
              <th className="font-normal text-right pr-2">action</th>
            </tr>
          </thead>
          <tbody>
            {rows?.slice(0, 80).map((r) => {
              const d = r.rank_before - r.rank_after;
              return (
                <tr key={r.id} className="border-t border-line">
                  <td className="px-2 py-0.5 text-ink-2 truncate max-w-[170px]">{r.id}</td>
                  <td className="text-right text-ink-3">{r.rank_before}</td>
                  <td className="text-right text-ink">{r.rank_after}</td>
                  <td className="text-right" style={{ color: d > 0 ? "var(--ink)" : d < 0 ? "var(--ink-3)" : "var(--ink-4)" }}>
                    {d > 0 ? `▲${d}` : d < 0 ? `▼${-d}` : "·"}
                  </td>
                  <td className="text-right text-ink-2">
                    {num(r.utility_before, 3)}→{num(r.utility_after, 3)}
                  </td>
                  <td className="text-right pr-2" style={{ color: r.action_after !== r.action_before ? "var(--ink)" : "var(--ink-3)" }}>
                    {r.action_after !== r.action_before ? `${ACTION_LABEL[r.action_before]}→${ACTION_LABEL[r.action_after]}` : ACTION_LABEL[r.action_after]}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
