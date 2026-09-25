import { ACTION_COLOR } from "@/lib/format";
import { ACT_LABEL, ACT_ORDER, HOME, mb } from "@/lib/home";

/** Hero visual: the real Mission Control replay, reduced to its data funnel. Server-rendered, no client JS. */
export function HeroFunnel() {
  const r = HOME.replay;
  const total = ACT_ORDER.reduce((s, a) => s + (r.final_actions[a] ?? 0), 0) || 1;
  const share = r.downlink_capacity_bytes / r.raw_bytes;
  return (
    <figure className="panel relative" aria-label="Data funnel of the Curiosity mission replay">
      <div className="flex flex-wrap items-center gap-2 px-4 py-2.5 border-b border-line">
        <span className="chip" style={{ color: "var(--ink)", borderColor: "var(--ink-4)" }}>MISSION REPLAY</span>
        <span className="chip text-ink-2">NASA PDS · REAL DATA</span>
        <span className="label ml-auto">MSL · sols {r.sols[0]}–{r.sols[1]}</span>
      </div>

      <div className="px-4 py-4 space-y-1">
        <Stage k="Raw mission data" v={mb(r.raw_bytes)} sub={`${r.samples.toLocaleString()} sensor samples · ${r.products} PDS products · REMS + RAD`}>
          <Bar w={1} color="var(--ink-4)" />
        </Stage>
        <Arrow note={`${r.instrument_windows.toLocaleString()} windows → ${r.candidate_windows} flagged`} />
        <Stage k="Candidate events" v={r.events.toLocaleString()} sub="deterministic detection · the only events a decision layer sees">
          {null}
        </Stage>
        <Arrow note="priority utility → action" />
        <Stage k="Triage" v="" sub="">
          <div className="flex h-7 w-full overflow-hidden border border-line-2">
            {ACT_ORDER.map((a) => {
              const n = r.final_actions[a] ?? 0;
              if (!n) return null;
              return (
                <div key={a} className="h-full flex items-center justify-center mono text-[10px]" title={`${ACT_LABEL[a]} ${n}`}
                  style={{ width: `${(n / total) * 100}%`, background: ACTION_COLOR[a], color: a === "full_data" ? "var(--bg)" : "var(--ink)" }}>
                  {n}
                </div>
              );
            })}
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-y-0.5 mt-1.5 mono text-[10px] text-ink-3">
            {ACT_ORDER.map((a) => (
              <span key={a} className="flex items-center gap-1.5">
                <i className="inline-block w-2 h-2" style={{ background: ACTION_COLOR[a] }} />
                {ACT_LABEL[a]} <span className="text-ink-2">{r.final_actions[a] ?? 0}</span>
              </span>
            ))}
          </div>
        </Stage>
        <Arrow note={`${r.downlink.passes} relay passes × ${r.downlink.pass_bytes / 1024} KiB`} />
        <Stage k="Downlink available" v={mb(r.downlink_capacity_bytes, 2)} sub={`${(share * 100).toFixed(2)}% of the raw data can reach Earth`} accent>
          <Bar w={share} color="var(--a-full)" min />
        </Stage>
      </div>

      <figcaption className="border-t border-line px-4 py-2 text-[10.5px] leading-snug text-ink-3">
        Real Curiosity records, {r.utc[0].slice(0, 10)} → {r.utc[1].slice(0, 10)}. Downlink capacity is a simulation parameter, not
        Curiosity&apos;s real allocation. Decisions from the replay&apos;s {r.engine.is_real_model ? r.engine.name : "mock heuristic engine (not Jev)"}.
      </figcaption>
    </figure>
  );
}

function Stage({ k, v, sub, children, accent }: { k: string; v: string; sub: string; children: React.ReactNode; accent?: boolean }) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <span className="label" style={accent ? { color: "var(--a-full)" } : undefined}>{k}</span>
        {v && <span className="mono text-[22px] leading-none text-ink" style={accent ? { color: "var(--a-full)" } : undefined}>{v}</span>}
      </div>
      <div className="mt-1.5">{children}</div>
      {sub && <div className="text-[11px] text-ink-3 mt-1">{sub}</div>}
    </div>
  );
}

function Bar({ w, color, min }: { w: number; color: string; min?: boolean }) {
  return (
    <div className="h-2 w-full bg-panel-2 border border-line">
      <div className="h-full home-grow" style={{ width: `${Math.max(w * 100, min ? 0.6 : 0)}%`, background: color }} />
    </div>
  );
}

function Arrow({ note }: { note: string }) {
  return (
    <div className="flex items-center gap-2 pl-1 py-0.5 mono text-[10px] text-ink-4">
      <span aria-hidden>↓</span>
      <span>{note}</span>
    </div>
  );
}
