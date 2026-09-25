import jev from "@/data/jev-phase2.json";

/** Project-level Jev result (Phase 2), read from stored run artifacts via scripts/build_jev_phase2_summary.py.
 *  Independent of any API key: the evaluation already happened and its artifacts are kept. */
export const JEV_PHASE2 = jev;

/** Per-run wording: a stored run's own jev_status is historical and only says whether Jev ran IN THAT RUN. */
export function jevRunLabel(status: string | null | undefined): string {
  return status?.startsWith("enabled") ? "Jev evaluated in this run" : "Jev not evaluated in this run";
}

const sign = (x: number) => `${x >= 0 ? "+" : ""}${x.toFixed(3)}`;

export function JevStatus({ compact = false }: { compact?: boolean }) {
  const e = jev.evidence;
  const d = e.auroc_diff_vs_rules;
  return (
    <div className="panel p-3 space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="label">Jev status · project level</span>
        <span className="chip" style={{ color: "var(--ink)", borderColor: "var(--ink-4)" }}>{jev.status}</span>
        <span className="mono text-[10px] text-ink-3 ml-auto">{jev.model} via {jev.transport} · {jev.split} · tag {jev.tag}</span>
      </div>
      <p className="text-[12.5px] text-ink leading-relaxed">{jev.conclusion}</p>
      <p className="text-[11.5px] text-ink-3 leading-relaxed">{jev.scope}</p>
      {!compact && (
        <div className="grid gap-2 md:grid-cols-[1.2fr_1fr] text-[11px]">
          <div className="border border-line p-2 mono text-ink-2 space-y-0.5">
            <div className="label mb-1">Evidence · {e.run_id}</div>
            <div>{e.events} validation candidates · {e.high_severity_labels} high-severity labels · ordering-only AUROC</div>
            <div>rules {e.auroc.RULES.toFixed(3)} · local edge {e.auroc.LOCAL_EDGE.toFixed(3)} · Jev {e.auroc.JEV_V3_NO_OBJECTIVE.toFixed(3)} / {e.auroc.JEV_V3_WITH_OBJECTIVE.toFixed(3)} (no / with objective)</div>
            <div>Δ vs rules {sign(d.no_objective.diff)} [{d.no_objective.ci95.map((x) => x.toFixed(3)).join(", ")}] · {sign(d.with_objective.diff)} [{d.with_objective.ci95.map((x) => x.toFixed(3)).join(", ")}]</div>
            <div className="text-ink-3">source: {e.file}</div>
          </div>
          <div className="border border-line p-2 mono text-ink-2">
            <div className="label mb-1">Stored Jev runs · {jev.totals.live_calls.toLocaleString()} live calls · ${jev.totals.cost_usd.toFixed(3)}</div>
            {jev.history.map((h) => (
              <div key={h.run_id} className="flex gap-2">
                <span className="text-ink-3 w-[74px] shrink-0">{h.stage}</span>
                <span className="truncate" title={`${h.run_id} · ${h.what}`}>{h.what}</span>
                <span className="ml-auto text-ink-3 shrink-0">{h.live_calls}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
