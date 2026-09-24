"use client";

import { useEffect, useState } from "react";
import { api, type EventRow, type Series } from "@/lib/api";
import { ACTION_COLOR, ACTION_LABEL, TYPE_LABEL, bytes, duration, num, pct, solClock } from "@/lib/format";
import { GlyphIcon } from "./Marker";
import { StripChart } from "./StripChart";

interface Answer {
  kind: string;
  choice: string | null;
  noul: number | null;
  confidence: number | null;
  probabilities: Record<string, number>;
}
interface Detail {
  event: {
    id: string;
    features: {
      deviation_score: number;
      rarity_score: number;
      duration_s: number;
      novelty: number;
      most_similar_event: string | null;
      correlated_channels: number;
      cross_instrument_coincidence: boolean;
      lmst_hour: number;
      channels: Record<string, { unit: string; n: number; mean: number | null; baseline: number | null; robust_z: number; dip: number; flat_fraction: number; missing_fraction: number; noise_ratio: number; rarity: number }>;
    };
    source: { instrument: string; products: string[]; row_start: number | null; row_end: number | null; data_source: string };
    decision: { engine: string; model: string | null; answers: Record<string, Answer>; latency_ms: number; error: string | null; state_sent: unknown; cost_usd: number | null } | null;
    deep: { provider: string; rationale: string | null; error: string | null; science_value: string | null; event_type: string | null } | null;
    gate: string;
    gate_reason: string;
    explanation: string[];
    trace: { stage: string; ms: number | null; measured: boolean; detail: string }[];
    priority: { weights: Record<string, number>; contributions: Record<string, number>; utility: number; confidence_penalty: number; density: number };
    synthetic_injection_ids: string[];
  };
  row: EventRow;
  effective_decision: { engine: string; answers: Record<string, Answer> };
  effective_source: string;
  counterfactuals: {
    current_action: string;
    utility: number;
    terms: Record<string, number>;
    confidence: number;
    changes: { input: string; from: number; to: number; delta: number; action: string; utility: number }[];
    by_objective: { objective: string; name: string; action: string; utility: number; mission_relevance: number }[];
    detection: { max_flagged_abs_z: number; note: string };
    method: string;
  };
  audit: { run_id: string; recorded_at: string; engine: string; gate: string; objective_id: string; config_version: string; proposed_action: string; final_action: string }[];
  sim_item: { history: { t: number; from: string; to: string; reason: string }[]; downlinked_at: number | null; state: string } | null;
}

function Dist({ a, order }: { a: Answer | undefined; order?: string[] }) {
  if (!a) return <span className="text-ink-4">—</span>;
  if (a.kind === "noul") {
    return (
      <div className="flex items-center gap-2">
        <div className="h-1.5 flex-1 bg-panel-2">
          <div className="h-full" style={{ width: pct(a.noul ?? 0), background: "var(--ink-2)" }} />
        </div>
        <span className="mono text-[11px] w-12 text-right">{pct(a.noul, 1)}</span>
      </div>
    );
  }
  const keys = order ?? Object.keys(a.probabilities);
  return (
    <div className="space-y-0.5">
      {keys.map((k) => (
        <div key={k} className="flex items-center gap-2 mono text-[10px]">
          <span className="w-28 truncate" style={{ color: k === a.choice ? "var(--ink)" : "var(--ink-3)" }}>
            {k}
          </span>
          <div className="h-1.5 flex-1 bg-panel-2">
            <div className="h-full" style={{ width: pct(a.probabilities[k] ?? 0), background: k === a.choice ? "var(--ink)" : "var(--ink-4)" }} />
          </div>
          <span className="w-11 text-right" style={{ color: k === a.choice ? "var(--ink)" : "var(--ink-3)" }}>
            {pct(a.probabilities[k] ?? 0, 1)}
          </span>
        </div>
      ))}
    </div>
  );
}

const H = ({ children }: { children: React.ReactNode }) => <div className="label mt-4 mb-1.5 pb-1 border-b border-line">{children}</div>;

export function Inspector({ id, onClose, onSelect }: { id: string; onClose: () => void; onSelect?: (id: string) => void }) {
  const [d, setD] = useState<Detail | null>(null);
  const [series, setSeries] = useState<Series | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [labelMsg, setLabelMsg] = useState<string | null>(null);
  const [sev, setSev] = useState("high");
  const [showState, setShowState] = useState(false);

  useEffect(() => {
    let alive = true;
    api<Detail>(`/api/events/${encodeURIComponent(id)}`)
      .then((x) => {
        if (!alive) return;
        setD(x);
        const ch = x.row.sensors[0];
        const pad = Math.max(0.03, (x.row.sol_end - x.row.sol_start) * 0.3);
        if (ch)
          api<Series>(`/api/series?channel=${ch}&sol_from=${x.row.sol_start - pad}&sol_to=${x.row.sol_end + pad}&max_points=800`).then(
            (s) => alive && setSeries(s),
          );
      })
      .catch((e) => alive && setErr(String(e.message)));
    return () => {
      alive = false;
    };
  }, [id]);

  if (err) return <div className="p-3 mono text-[11px]" style={{ color: "var(--s-critical)" }}>{err}</div>;
  if (!d) return <div className="p-3 label">loading {id}…</div>;
  const e = d.event;
  const r = d.row;
  const eff = d.effective_decision.answers;
  const eng = e.decision?.answers ?? {};
  const cf = d.counterfactuals;
  const ch = e.features.channels;
  const firstCh = r.sensors[0];
  const pad = Math.max(0.03, (r.sol_end - r.sol_start) * 0.3);

  return (
    <div className="h-full overflow-y-auto px-3 pb-6 text-[12px]">
      <div className="sticky top-0 bg-panel pt-3 pb-2 border-b border-line z-10">
        <div className="flex items-start gap-2">
          <div className="min-w-0">
            <div className="label">Event</div>
            <div className="mono text-[14px] text-ink truncate">{e.id}</div>
            <div className="mono text-[10px] text-ink-3">
              {solClock(r.sol_start)} · {duration(r.duration_s)} · {e.source.instrument}
            </div>
          </div>
          <button className="btn ml-auto" onClick={onClose}>
            Close
          </button>
        </div>
        <div className="flex flex-wrap gap-1.5 mt-2">
          {e.synthetic_injection_ids.length > 0 && (
            <span className="chip" style={{ color: "var(--s-warn)", borderColor: "#5a4412" }}>
              SYNTHETIC ANOMALY · {e.synthetic_injection_ids.join(", ")}
            </span>
          )}
          <span className="chip text-ink-2">{e.source.data_source === "NASA_PDS" ? "REAL OBSERVATION" : e.source.data_source}</span>
          <span className="chip text-ink-2">GATE {e.gate?.toUpperCase()}</span>
          <span className="chip text-ink-2">DECIDED BY {d.effective_source.toUpperCase()}</span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-2 mt-3">
        <div>
          <div className="label">Type</div>
          <div className="flex items-center gap-1.5 mono text-[13px]">
            <GlyphIcon type={r.event_type} /> {TYPE_LABEL[r.event_type ?? ""] ?? "—"}{" "}
            <span className="text-ink-3">{pct(eff.event_type?.confidence, 1)}</span>
          </div>
        </div>
        <div>
          <div className="label">Scientific value</div>
          <div className="mono text-[13px] uppercase">
            {r.science_value} <span className="text-ink-3">{pct(eff.science_value?.confidence, 1)}</span>
          </div>
        </div>
        <div>
          <div className="label">Downlink action</div>
          <div className="mono text-[13px] flex items-center gap-1.5">
            <span style={{ width: 8, height: 8, background: ACTION_COLOR[r.final_action ?? "discard"], display: "inline-block" }} />
            {ACTION_LABEL[r.final_action ?? ""]}
            {r.final_action !== r.proposed_action && <span className="text-ink-3">(proposed {ACTION_LABEL[r.proposed_action ?? ""]})</span>}
          </div>
        </div>
        <div>
          <div className="label">Instrument failure</div>
          <div className="mono text-[13px]">{pct(eff.instrument_failure?.probabilities?.yes, 1)}</div>
        </div>
        <div>
          <div className="label">Mission relevance</div>
          <div className="mono text-[13px]">{num(r.mission_relevance)}</div>
        </div>
        <div>
          <div className="label">Utility · downlinked</div>
          <div className="mono text-[13px]">
            {num(r.utility, 3)} · {bytes(r.downlink_bytes)}
          </div>
        </div>
      </div>

      {firstCh && (
        <div className="mt-3 border border-line" style={{ height: 90 }}>
          <StripChart series={series} label={firstCh} unit={ch[firstCh]?.unit ?? ""} domain={[r.sol_start - pad, r.sol_end + pad]} events={[r]} />
        </div>
      )}

      <H>Why was this selected?</H>
      <ul className="space-y-1">
        {e.explanation.map((x, i) => (
          <li key={i} className="flex gap-2 leading-snug">
            <span className="text-ink-4 mono">—</span>
            <span className="text-ink-2">{x}</span>
          </li>
        ))}
      </ul>
      <div className="mono text-[10px] text-ink-4 mt-1">Assembled from features, config and decision metadata. No text is model-generated.</div>

      <H>Features</H>
      <div className="grid grid-cols-3 gap-2 mono text-[11px]">
        <div><div className="label">deviation</div>{num(e.features.deviation_score, 1)}σ</div>
        <div><div className="label">rarity</div>{num(e.features.rarity_score, 2)}</div>
        <div><div className="label">novelty</div>{num(e.features.novelty, 2)}</div>
        <div><div className="label">duration</div>{duration(e.features.duration_s)}</div>
        <div><div className="label">channels flagged</div>{e.features.correlated_channels}</div>
        <div><div className="label">cross-instrument</div>{e.features.cross_instrument_coincidence ? "yes" : "no"}</div>
      </div>
      <table className="w-full mt-2 mono text-[10px]">
        <thead className="text-ink-3">
          <tr className="text-left">
            <th className="font-normal">channel</th>
            <th className="font-normal text-right">mean</th>
            <th className="font-normal text-right">baseline</th>
            <th className="font-normal text-right">z</th>
            <th className="font-normal text-right">dip</th>
            <th className="font-normal text-right">miss</th>
            <th className="font-normal text-right">noise×</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(ch).map(([k, c]) => (
            <tr key={k} style={{ color: r.sensors.includes(k) ? "var(--ink)" : "var(--ink-3)" }}>
              <td>{k}</td>
              <td className="text-right">{c.mean == null ? "—" : c.mean.toFixed(2)}</td>
              <td className="text-right">{c.baseline == null ? "—" : c.baseline.toFixed(2)}</td>
              <td className="text-right">{c.robust_z.toFixed(1)}</td>
              <td className="text-right">{c.dip ? c.dip.toFixed(2) : "—"}</td>
              <td className="text-right">{pct(c.missing_fraction, 0)}</td>
              <td className="text-right">{c.noise_ratio.toFixed(1)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <H>Priority breakdown</H>
      <div className="space-y-1">
        {Object.entries(e.priority.contributions).map(([k, v]) => (
          <div key={k} className="flex items-center gap-2 mono text-[10px]">
            <span className="w-32 text-ink-2">{k.replace("_", " ")}</span>
            <span className="w-24 text-ink-3">
              {num(cf.terms[k], 2)} × {num(e.priority.weights[k], 2)}
            </span>
            <div className="flex-1 h-1.5 bg-panel-2">
              <div className="h-full" style={{ width: pct(v / 0.5), background: "var(--ink-2)" }} />
            </div>
            <span className="w-12 text-right">{num(v, 3)}</span>
          </div>
        ))}
        <div className="mono text-[10px] text-ink-3">
          × confidence penalty {num(e.priority.confidence_penalty, 3)} = utility <span className="text-ink">{num(e.priority.utility, 3)}</span> · density{" "}
          {num(e.priority.density, 3)}/KB^β
        </div>
      </div>

      <H>Decision engine answers {e.decision?.engine ? `· ${e.decision.engine}` : ""}</H>
      {e.decision?.error && <div className="mono text-[11px]" style={{ color: "var(--s-critical)" }}>engine error: {e.decision.error}</div>}
      <div className="space-y-2">
        <div><div className="label mb-0.5">science_value</div><Dist a={eng.science_value} order={["none", "low", "medium", "high", "critical"]} /></div>
        <div><div className="label mb-0.5">event_type</div><Dist a={eng.event_type} /></div>
        <div><div className="label mb-0.5">downlink_action</div><Dist a={eng.downlink_action} order={["discard", "summary_only", "compress", "full_data"]} /></div>
        <div><div className="label mb-0.5">instrument_failure</div><Dist a={eng.instrument_failure} order={["yes", "no", "uncertain"]} /></div>
        <div><div className="label mb-0.5">needs_deep_analysis (P yes)</div><Dist a={eng.needs_deep_analysis} /></div>
      </div>
      <div className="mono text-[10px] text-ink-3 mt-1">{e.gate_reason}</div>
      {e.deep && (
        <div className="mt-2 border border-line p-2">
          <div className="label">Deep analysis · {e.deep.provider}</div>
          {e.deep.error ? (
            <div className="mono text-[11px] text-ink-3">{e.deep.error}</div>
          ) : (
            <>
              <div className="mono text-[11px]">{e.deep.science_value} · {e.deep.event_type}</div>
              <div className="text-[11px] text-ink-2 mt-1">
                <span className="chip mr-1">MODEL-GENERATED TEXT</span>
                {e.deep.rationale}
              </div>
            </>
          )}
        </div>
      )}
      <button className="btn mt-2" onClick={() => setShowState((s) => !s)}>
        {showState ? "Hide" : "Show"} exact state sent to engine
      </button>
      {showState && <pre className="mono text-[10px] text-ink-2 bg-panel-2 p-2 mt-1 overflow-x-auto whitespace-pre-wrap">{JSON.stringify(e.decision?.state_sent, null, 1)}</pre>}

      <H>Decision trace</H>
      <ol className="space-y-0.5">
        {e.trace.map((s, i) => (
          <li key={i} className="grid grid-cols-[14px_130px_70px_1fr] gap-1 mono text-[10px]">
            <span className="text-ink-4">{i === 0 ? "" : "↓"}</span>
            <span className="text-ink uppercase">{s.stage.replace(/_/g, " ")}</span>
            <span className="text-right text-ink-2" title={s.measured ? "measured" : "amortized share of a batch stage"}>
              {s.ms == null ? "" : `${s.ms < 0.01 ? s.ms.toExponential(1) : s.ms.toFixed(3)} ms${s.measured ? "" : "*"}`}
            </span>
            <span className="text-ink-3 truncate" title={s.detail}>
              {s.detail}
            </span>
          </li>
        ))}
      </ol>
      <div className="mono text-[10px] text-ink-4 mt-1">* amortized share of a batch-timed stage (by raw bytes); unstarred = measured per event.</div>
      {d.sim_item?.history?.length ? (
        <div className="mono text-[10px] text-ink-2 mt-1">
          {d.sim_item.history.map((h, i) => (
            <div key={i}>
              {solClock(h.t)} storage: {h.from} → {h.to} ({h.reason})
            </div>
          ))}
        </div>
      ) : null}

      <H>Counterfactuals (computed)</H>
      {cf.changes.length === 0 ? (
        <div className="text-ink-3 text-[11px]">No single input in [0, 1] changes the action — the event is far from every threshold.</div>
      ) : (
        <ul className="space-y-1">
          {cf.changes.slice(0, 8).map((c, i) => (
            <li key={i} className="text-[11px] text-ink-2 leading-snug">
              If <span className="mono text-ink">{c.input.replace("_", " ")}</span> went {num(c.from, 2)} → <span className="mono text-ink">{num(c.to, 2)}</span>, action becomes{" "}
              <span className="mono text-ink">{ACTION_LABEL[c.action]}</span> <span className="mono text-ink-4">(U={num(c.utility, 3)})</span>
            </li>
          ))}
        </ul>
      )}
      <table className="w-full mt-2 mono text-[10px]">
        <thead className="text-ink-3">
          <tr className="text-left">
            <th className="font-normal">under objective</th>
            <th className="font-normal text-right">relevance</th>
            <th className="font-normal text-right">utility</th>
            <th className="font-normal text-right">action</th>
          </tr>
        </thead>
        <tbody>
          {cf.by_objective.map((o) => (
            <tr key={o.objective} style={{ color: o.action === cf.current_action ? "var(--ink-3)" : "var(--ink)" }}>
              <td>{o.name}</td>
              <td className="text-right">{num(o.mission_relevance)}</td>
              <td className="text-right">{num(o.utility, 3)}</td>
              <td className="text-right">{ACTION_LABEL[o.action]}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mono text-[10px] text-ink-3 mt-1">{cf.detection.note}</div>
      <div className="mono text-[10px] text-ink-4">method: {cf.method}</div>

      <H>Source</H>
      <div className="mono text-[10px] text-ink-2 break-all">
        {e.source.products.join(", ")} {e.source.row_start != null && `· records ${e.source.row_start}–${e.source.row_end}`}
      </div>
      <div className="mono text-[10px] text-ink-3">
        raw {bytes(r.bytes.raw)} · full {bytes(r.bytes.full)} · compressed {bytes(r.bytes.compressed)} · summary {bytes(r.bytes.summary)} (zlib-measured)
      </div>
      {e.features.most_similar_event && (
        <button className="mono text-[10px] text-ink-2 underline mt-1" onClick={() => onSelect?.(e.features.most_similar_event!)}>
          most similar earlier event: {e.features.most_similar_event}
        </button>
      )}

      <H>Audit trail</H>
      <table className="w-full mono text-[10px]">
        <tbody>
          {d.audit.slice(0, 6).map((a, i) => (
            <tr key={i} className="text-ink-2">
              <td className="pr-2">{a.recorded_at.slice(5, 19).replace("T", " ")}</td>
              <td className="pr-2 truncate max-w-[110px]">{a.objective_id}</td>
              <td className="pr-2">cfg {a.config_version}</td>
              <td className="text-right">{ACTION_LABEL[a.final_action] ?? a.final_action}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <H>Human label (HUMAN_LABEL — kept separate from predictions)</H>
      <div className="flex items-center gap-2">
        <select value={sev} onChange={(x) => setSev(x.target.value)}>
          <option value="high">severity high</option>
          <option value="medium">severity medium</option>
          <option value="low">severity low</option>
        </select>
        <button
          className="btn"
          onClick={() =>
            api<{ label_id: string }>("/api/labels", { method: "POST", body: JSON.stringify({ event_id: e.id, severity: sev, expected_type: r.event_type }) })
              .then((l) => setLabelMsg(`recorded ${l.label_id}`))
              .catch((x) => setLabelMsg(String(x.message)))
          }
        >
          Mark as scientifically important
        </button>
      </div>
      {labelMsg && <div className="mono text-[10px] text-ink-3 mt-1">{labelMsg}</div>}
    </div>
  );
}
