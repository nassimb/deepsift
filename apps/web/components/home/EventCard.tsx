import Link from "next/link";
import { ACTION_COLOR, duration } from "@/lib/format";
import { ACT_LABEL, HOME } from "@/lib/home";

const TERM_LABEL: Record<string, string> = {
  science_value: "science value",
  mission_relevance: "mission relevance",
  anomaly_strength: "anomaly strength",
  novelty: "novelty",
};

/** One real event from the replay, with its stored audit explanation (nothing generated for this page). */
export function EventCard() {
  const c = HOME.replay.event_card;
  const pb = c.priority;
  // "why" checks are read off stored fields with stated cut-offs — they restate the audit record, they add nothing to it
  const why: [boolean, string, string][] = [
    [pb.anomaly_strength >= 0.5, "strong deviation", `anomaly strength ${pb.anomaly_strength.toFixed(2)} (≥ 0.50)`],
    [c.rarity >= 0.95, "rare for this local time", `rarer than ${Math.floor(c.rarity * 100)}% of earlier observations`],
    [pb.mission_relevance >= 0.5, "matches the mission objective", `relevance ${pb.mission_relevance.toFixed(2)} · ${c.objective}`],
    [c.final === c.proposed, "fits the available bandwidth", `proposed ${ACT_LABEL[c.proposed]} · scheduled ${ACT_LABEL[c.final]}`],
  ];
  const terms = Object.entries(pb.contributions);
  return (
    <div className="panel">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5">
        <span className="label">Event</span>
        <span className="mono text-[13px] text-ink">{c.id}</span>
        <span className="chip text-ink-2 ml-auto">MISSION REPLAY</span>
        <span className="chip" style={{ color: c.engine.is_real_model ? "var(--ink-2)" : "var(--s-warn)" }}>
          {c.engine.is_real_model ? c.engine.name : "ENGINE: MOCK HEURISTIC · NOT JEV"}
        </span>
      </div>
      <div className="grid md:grid-cols-[1fr_1.1fr]">
        <div className="p-4 grid grid-cols-2 gap-4 border-b md:border-b-0 md:border-r border-line content-start">
          <Field k={c.instrument === "RAD" ? "Radiation deviation" : "Deviation"} v={`${c.robust_z > 0 ? "+" : ""}${c.robust_z.toFixed(1)}σ`} sub={`${c.top_channel} · vs same-local-time baseline`} />
          <Field k="Duration" v={`${Math.round(c.duration_s).toLocaleString()} s`} sub={duration(c.duration_s)} />
          <Field k="Science value" v={(c.science_value ?? "—").toUpperCase()} sub={`engine answer · confidence ${pb.confidence.toFixed(2)}`} />
          <div>
            <div className="label">Action</div>
            <div className="mono text-[15px] mt-1 inline-block px-2 py-0.5" style={{ background: ACTION_COLOR[c.final], color: c.final === "full_data" ? "var(--bg)" : "var(--ink)" }}>
              {ACT_LABEL[c.final]}
            </div>
            <div className="text-[11px] text-ink-3 mt-1">utility {pb.utility.toFixed(3)} ≥ 0.55</div>
          </div>
          <div className="col-span-2">
            <div className="label mb-1.5">Utility = Σ weight × term</div>
            <div className="flex h-4 w-full border border-line-2 overflow-hidden">
              {terms.map(([k, v], i) => (
                <div key={k} title={`${TERM_LABEL[k]} ${v.toFixed(3)}`} style={{ width: `${v * 100}%`, background: ["var(--a-full)", "var(--a-compress)", "var(--a-summary)", "var(--ink-4)"][i] }} />
              ))}
            </div>
            <div className="grid grid-cols-2 mt-1.5 mono text-[10.5px] text-ink-3 gap-x-3">
              {terms.map(([k, v]) => <span key={k}>{TERM_LABEL[k]} <span className="text-ink-2">{v.toFixed(3)}</span></span>)}
            </div>
          </div>
        </div>
        <div className="p-4 space-y-3">
          <div className="label">Why selected</div>
          <ul className="space-y-1.5">
            {why.map(([ok, t, d]) => (
              <li key={t} className="grid grid-cols-[18px_1fr] gap-1 text-[13px]">
                <span className="mono" style={{ color: ok ? "var(--s-good)" : "var(--ink-4)" }}>{ok ? "✓" : "–"}</span>
                <span className={ok ? "text-ink" : "text-ink-3"}>{t} <span className="text-[11px] text-ink-3">· {d}</span></span>
              </li>
            ))}
          </ul>
          <details className="border border-line">
            <summary className="label cursor-pointer px-2 py-1.5">Audit record · {c.explanation.length} lines</summary>
            <ol className="mono text-[10.5px] text-ink-2 px-2 pb-2 space-y-0.5">
              {c.explanation.map((x, i) => <li key={i}>{x}</li>)}
            </ol>
          </details>
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <Link href="/control" className="btn" data-active="true">Inspect decision</Link>
            <span className="mono text-[10px] text-ink-4">config {c.config_version} · {c.products[0]}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function Field({ k, v, sub }: { k: string; v: string; sub: string }) {
  return (
    <div>
      <div className="label">{k}</div>
      <div className="mono text-[22px] text-ink leading-tight mt-0.5">{v}</div>
      <div className="text-[11px] text-ink-3">{sub}</div>
    </div>
  );
}
