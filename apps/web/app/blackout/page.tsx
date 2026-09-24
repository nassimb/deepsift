"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Inspector } from "@/components/Inspector";
import { Section } from "@/components/Kpi";
import { GlyphIcon } from "@/components/Marker";
import { Nav, SourceBadges, useStatus } from "@/components/Nav";
import { useSize } from "@/components/useSize";
import { api, type EventRow, type Mission, type SimItem, type Simulation, type Snapshot } from "@/lib/api";
import { ACTION_LABEL, SOL_SECONDS, bytes, hm, num, pct, solClock } from "@/lib/format";
import { SPEEDS, lastAtOrBefore, useReplayClock } from "@/lib/replay";

/** action of a sim item as of time t (replaying its degradation history) */
function actionAt(i: SimItem, t: number): string {
  let a: string = i.proposed;
  for (const h of i.history) if (h.t <= t) a = h.to;
  return a;
}

function StorageChart({ sim, t, window }: { sim: Simulation; t: number; window: [number, number] }) {
  const [ref, { w }] = useSize<HTMLDivElement>();
  const h = 150;
  const m = { l: 56, r: 10, t: 8, b: 18 };
  const [a, b] = window;
  const iw = Math.max(1, w - m.l - m.r);
  const ih = h - m.t - m.b;
  const cap = Math.max(...sim.timeline.map((s) => s.capacity));
  const sx = (x: number) => m.l + ((x - a) / (b - a)) * iw;
  const sy = (v: number) => m.t + ih - (v / cap) * ih;
  // step-after paths: storage and capacity only change at simulation events; extend to "now"
  const pts = sim.timeline.filter((s) => s.t >= a && s.t <= Math.min(b, t));
  const tEnd = Math.min(b, t);
  let used = "";
  let capL = "";
  pts.forEach((s, i) => {
    const x = sx(s.t).toFixed(1);
    used += i ? `H${x}V${sy(s.storage_used).toFixed(1)}` : `M${x},${sy(s.storage_used).toFixed(1)}`;
    capL += i ? `H${x}V${sy(s.capacity).toFixed(1)}` : `M${x},${sy(s.capacity).toFixed(1)}`;
  });
  if (pts.length) {
    const inB = sim.blackout_window && tEnd >= sim.blackout_window.start && tEnd < sim.blackout_window.end;
    used += `H${sx(tEnd).toFixed(1)}`;
    capL += `H${sx(tEnd).toFixed(1)}V${sy(inB ? sim.blackout_window!.storage_bytes : pts.at(-1)!.capacity).toFixed(1)}`;
  }
  const bw = sim.blackout_window!;
  return (
    <div ref={ref} className="w-full">
      {w > 0 && (
        <svg width={w} height={h}>
          <rect x={sx(bw.start)} width={Math.max(0, sx(Math.min(bw.end, b)) - sx(bw.start))} y={m.t} height={ih} fill="var(--s-critical)" opacity={0.08} />
          {[0, 0.5, 1].map((f) => (
            <g key={f}>
              <line x1={m.l} x2={m.l + iw} y1={sy(cap * f)} y2={sy(cap * f)} stroke="var(--grid)" />
              <text x={m.l - 4} y={sy(cap * f) + 3} textAnchor="end" className="mono" fontSize={9} fill="var(--ink-4)">
                {bytes(cap * f)}
              </text>
            </g>
          ))}
          {Array.from({ length: Math.floor(b) - Math.ceil(a) + 1 }, (_, i) => Math.ceil(a) + i).map((s) => (
            <text key={s} x={sx(s)} y={h - 4} className="mono" fontSize={9} fill="var(--ink-4)" textAnchor="middle">
              sol {s}
            </text>
          ))}
          <path d={capL} fill="none" stroke="var(--s-critical)" strokeDasharray="3 3" strokeWidth={1} />
          <path d={used} fill="none" stroke="var(--a-full)" strokeWidth={2} />
          <line x1={sx(t)} x2={sx(t)} y1={m.t} y2={m.t + ih} stroke="var(--ink)" />
        </svg>
      )}
      <div className="flex gap-4 mono text-[10px] text-ink-3 px-1">
        <span style={{ color: "var(--a-full)" }}>━ triage products stored onboard</span>
        <span style={{ color: "var(--s-critical)" }}>┅ storage capacity (drops during blackout)</span>
      </div>
    </div>
  );
}

function BlackoutInner() {
  const params = useSearchParams();
  const { status } = useStatus();
  const [mission, setMission] = useState<Mission | null>(null);
  const [events, setEvents] = useState<EventRow[]>([]);
  const [startSol, setStartSol] = useState<number | null>(null);
  const [dur, setDur] = useState(3);
  const [storage, setStorage] = useState(196608);
  const [sim, setSim] = useState<Simulation | null>(null);
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api<Mission>("/api/mission"), api<{ events: EventRow[] }>("/api/events"), api<{ config: { blackout: { duration_sols: number; storage_bytes: number } } }>("/api/config")]).then(
      ([m, ev, c]) => {
        setMission(m);
        setEvents(ev.events);
        setDur(c.config.blackout.duration_sols);
        setStorage(c.config.blackout.storage_bytes);
        const q = Number(params.get("start"));
        setStartSol(Number.isFinite(q) && q > m.sols[0] ? q : m.sols[0] + 8.5);
      },
    );
  }, [params]);

  const winStart = sim?.blackout_window ? sim.blackout_window.start - 0.25 : 0;
  const winEnd = sim?.blackout_window ? Math.min(sim.blackout_window.end + 1.0, (mission?.sols.at(-1) ?? 0) + 1) : 1;
  const clock = useReplayClock(winStart, winEnd);
  const t = clock.t;

  const run = async () => {
    if (startSol == null) return;
    setBusy(true);
    try {
      const s = await api<Simulation>("/api/simulate", { method: "POST", body: JSON.stringify({ blackout_start: startSol, duration_sols: dur, storage_bytes: storage }) });
      setSim(s);
      clock.setT(s.blackout_window!.start - 0.25);
      clock.setSpeed(10000);
      clock.setPlaying(true);
    } finally {
      setBusy(false);
    }
  };

  const bw = sim?.blackout_window;
  const active = !!bw && t >= bw.start && t < bw.end;
  const after = !!bw && t >= bw.end;
  const snap: Snapshot | undefined = sim ? lastAtOrBefore(sim.timeline, t, (s) => s.t) : undefined;
  const evMap = useMemo(() => new Map(events.map((e) => [e.id, e])), [events]);

  const during = useMemo(() => (sim && bw ? sim.items.filter((i) => i.kind === "event" && i.arrival >= bw.start && i.arrival < bw.end && i.arrival <= t) : []), [sim, bw, t]);
  const preserved = during.filter((i) => actionAt(i, t) !== "discard").sort((a, b) => b.utility - a.utility);
  // everything the scheduler removed during the blackout, including products that arrived before it
  const discarded = useMemo(
    () =>
      sim && bw
        ? sim.items.filter((i) => i.kind === "event" && i.history.some((h) => h.to === "discard" && h.t >= bw.start && h.t <= t))
        : [],
    [sim, bw, t],
  );
  const degradedNow = sim?.log.filter((l) => l.type === "degrade" && l.t <= t && bw && l.t >= bw.start).slice(-14).reverse() ?? [];

  // rates measured from the simulation timeline over the last 0.5 sol
  const rates = useMemo(() => {
    if (!sim) return { raw: 0, prod: 0 };
    const prev = lastAtOrBefore(sim.timeline, t - 0.5, (s) => s.t);
    const cur = snap;
    if (!prev || !cur || cur.t === prev.t) return { raw: 0, prod: 0 };
    const dtS = (cur.t - prev.t) * SOL_SECONDS;
    const arrivedBytes = sim.items.filter((i) => i.arrival > prev.t && i.arrival <= cur.t).reduce((a, i) => a + i.bytes, 0);
    return { raw: (cur.raw_generated - prev.raw_generated) / dtS, prod: arrivedBytes / dtS };
  }, [sim, t, snap]);
  const free = snap ? snap.capacity - snap.storage_used : 0;
  const exhaustion = rates.prod > 0 ? free / rates.prod : Infinity;

  return (
    <div className="h-screen flex flex-col">
      <Nav right={<SourceBadges status={status} />} />
      <div className="flex items-center gap-3 px-4 h-11 border-b border-line">
        <span className="label">Communication blackout simulation</span>
        <label className="mono text-[11px] text-ink-3 flex items-center gap-1">
          start sol
          <input type="number" step={0.1} value={startSol ?? ""} onChange={(e) => setStartSol(Number(e.target.value))} className="w-24" />
        </label>
        <label className="mono text-[11px] text-ink-3 flex items-center gap-1">
          duration (sols)
          <input type="number" step={0.25} min={0.25} value={dur} onChange={(e) => setDur(Number(e.target.value))} className="w-20" />
        </label>
        <label className="mono text-[11px] text-ink-3 flex items-center gap-1">
          storage (bytes)
          <input type="number" step={16384} value={storage} onChange={(e) => setStorage(Number(e.target.value))} className="w-28" />
        </label>
        <button className="btn" onClick={run} disabled={busy || startSol == null} style={{ color: "var(--s-critical)", borderColor: "#5b2323" }}>
          {busy ? "Simulating…" : "Cut Earth link"}
        </button>
        {sim && (
          <div className="flex items-center gap-1 ml-4">
            <button className="btn" onClick={() => clock.setPlaying(!clock.playing)}>{clock.playing ? "Pause" : "Play"}</button>
            {SPEEDS.map((s) => (
              <button key={s} className="btn" data-active={clock.speed === s} onClick={() => clock.setSpeed(s)}>
                {s >= 1000 ? `${s / 1000}k` : s}×
              </button>
            ))}
          </div>
        )}
        <span className="mono text-[12px] text-ink ml-auto">{sim ? solClock(t) : ""}</span>
      </div>

      {!sim ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="max-w-xl text-center space-y-3">
            <div className="mono text-[13px] text-ink-2">Simulate losing the relay link while real Curiosity data keeps arriving.</div>
            <div className="text-[12px] text-ink-3 leading-relaxed">
              During the blackout no relay passes occur and a smaller storage budget applies. DEEPSIFT&apos;s deterministic scheduler keeps
              products with the highest utility per byte and degrades the rest (FULL → COMPRESS → SUMMARY → DISCARD), logging every step.
              Storage sizes and the blackout are simulation parameters, not Curiosity&apos;s actual allocations.
            </div>
          </div>
        </div>
      ) : (
        <div className="flex-1 min-h-0 grid grid-cols-[minmax(0,1fr)_400px] gap-px bg-line">
          <div className="min-h-0 overflow-y-auto bg-bg">
            <div className="grid grid-cols-5 border-b border-line bg-panel">
              <div className="col-span-2 px-4 py-3 border-r border-line">
                <div className={`mono text-[22px] tracking-[0.12em] ${active ? "state-pulse" : ""}`} style={{ color: active ? "var(--s-critical)" : after ? "var(--s-good)" : "var(--ink-2)" }}>
                  {active ? "EARTH LINK LOST" : after ? "EARTH LINK RESTORED" : "EARTH LINK NOMINAL"}
                </div>
                <div className="mono text-[11px] text-ink-3">
                  {active ? `reconnect in ${hm((bw!.end - t) * SOL_SECONDS)} (Mars time)` : after ? `link restored at ${solClock(bw!.end)}` : `blackout begins ${solClock(bw!.start)}`}
                </div>
              </div>
              <div className="px-3 py-2 border-r border-line">
                <div className="label">Storage remaining</div>
                <div className="mono text-[18px]">{bytes(free)}</div>
                <div className="h-1.5 bg-panel-2 mt-1">
                  <div className="h-full" style={{ width: pct(snap ? snap.storage_used / snap.capacity : 0), background: snap && snap.storage_used / snap.capacity > 0.9 ? "var(--s-serious)" : "var(--a-full)" }} />
                </div>
                <div className="mono text-[10px] text-ink-3 mt-0.5">{bytes(snap?.storage_used)} / {bytes(snap?.capacity)}</div>
              </div>
              <div className="px-3 py-2 border-r border-line">
                <div className="label">Incoming raw data</div>
                <div className="mono text-[18px]">{bytes(rates.raw * 3600)}/h</div>
                <div className="mono text-[10px] text-ink-3">triage products {bytes(rates.prod * 3600)}/h · measured over last 0.5 sol</div>
              </div>
              <div className="px-3 py-2">
                <div className="label">Est. storage exhaustion</div>
                <div className="mono text-[18px]">{Number.isFinite(exhaustion) ? hm(exhaustion) : "—"}</div>
                <div className="mono text-[10px] text-ink-3">at current product rate, if nothing is degraded</div>
              </div>
            </div>

            <div className="p-3">
              <Section title="Onboard storage">
                <div className="p-2">
                  <StorageChart sim={sim} t={t} window={[winStart, winEnd]} />
                </div>
              </Section>
            </div>

            <div className="grid grid-cols-2 gap-3 px-3">
              <Section title={`Preserved · ${preserved.length}`} right={<span className="mono text-[10px] text-ink-3">arrived during blackout, still onboard</span>}>
                <table className="w-full mono text-[10px]">
                  <tbody>
                    {preserved.slice(0, 18).map((i) => (
                      <tr key={i.id} className="border-b border-line cursor-pointer hover:bg-panel-2" onClick={() => setSelected(i.id)}>
                        <td className="pl-2 py-0.5 w-5"><GlyphIcon type={evMap.get(i.id)?.event_type ?? null} size={7} /></td>
                        <td className="text-ink-2 truncate max-w-[180px]">{i.id}</td>
                        <td className="text-right text-ink-3">U {num(i.utility, 3)}</td>
                        <td className="text-right pr-2" style={{ color: actionAt(i, t) !== i.proposed ? "var(--s-serious)" : "var(--ink)" }}>
                          {ACTION_LABEL[actionAt(i, t)]}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Section>
              <Section title={`Discarded · ${discarded.length}`} right={<span className="mono text-[10px] text-ink-3">removed under storage pressure since link loss</span>}>
                <table className="w-full mono text-[10px]">
                  <tbody>
                    {discarded.slice(0, 18).map((i) => (
                      <tr key={i.id} className="border-b border-line cursor-pointer hover:bg-panel-2" onClick={() => setSelected(i.id)}>
                        <td className="pl-2 py-0.5 w-5"><GlyphIcon type={evMap.get(i.id)?.event_type ?? null} size={7} /></td>
                        <td className="text-ink-3 truncate max-w-[180px]">{i.id}</td>
                        <td className="text-right text-ink-4">U {num(i.utility, 3)}</td>
                        <td className="text-right pr-2 text-ink-4">was {ACTION_LABEL[i.proposed]}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Section>
            </div>

            <div className="p-3">
              <Section title="Scheduler log (deterministic)">
                <div className="p-2 mono text-[10px] space-y-0.5">
                  {degradedNow.map((l, i) => (
                    <div key={i} className="text-ink-2">
                      <span className="text-ink-4">{solClock(l.t)}</span> {String(l.item)}: {ACTION_LABEL[String(l.from)]} → {ACTION_LABEL[String(l.to)]}{" "}
                      <span className="text-ink-4">({String(l.reason)})</span>
                    </div>
                  ))}
                  {!degradedNow.length && <div className="text-ink-4">no degradations yet</div>}
                </div>
              </Section>
            </div>

            {after && sim.blackout && (
              <div className="p-3">
                <Section title="Link restored — blackout report">
                  <div className="grid grid-cols-5 border-b border-line">
                    {[
                      ["Raw data collected", bytes(sim.blackout.raw_collected)],
                      ["Events detected", sim.blackout.events_detected],
                      ["Events retained", sim.blackout.events_retained],
                      ["Events discarded", sim.blackout.events_discarded],
                      ["Retained bytes", bytes(sim.blackout.retained_bytes)],
                    ].map(([k, v]) => (
                      <div key={k as string} className="px-3 py-2 border-r border-line">
                        <div className="label">{k}</div>
                        <div className="mono text-[16px]">{v}</div>
                      </div>
                    ))}
                  </div>
                  <div className="grid grid-cols-2 gap-px bg-line">
                    <div className="bg-panel p-2">
                      <div className="label mb-1">Important events (utility ≥ FULL threshold)</div>
                      {sim.blackout.important_events.map((e) => (
                        <div key={e.id} className="mono text-[10px] flex gap-2">
                          <span className="text-ink-2 flex-1 truncate">{e.id}</span>
                          <span className="text-ink-3">{ACTION_LABEL[e.proposed]}→</span>
                          <span style={{ color: e.final === "discard" ? "var(--s-critical)" : "var(--ink)" }}>{ACTION_LABEL[e.final]}</span>
                        </div>
                      ))}
                      {!sim.blackout.important_events.length && <div className="text-ink-4 mono text-[10px]">none</div>}
                    </div>
                    <div className="bg-panel p-2">
                      <div className="label mb-1">Selected downlink (queue at reconnect, by utility)</div>
                      {sim.blackout.downlink_queue.slice(0, 12).map((q) => (
                        <div key={q.id} className="mono text-[10px] flex gap-2">
                          <span className="text-ink-2 flex-1 truncate">{q.id}</span>
                          <span className="text-ink-3">{num(q.utility, 3)}</span>
                          <span className="w-16 text-right">{ACTION_LABEL[q.action]}</span>
                          <span className="w-14 text-right text-ink-3">{bytes(q.bytes)}</span>
                        </div>
                      ))}
                      <div className="mono text-[10px] text-ink-4 mt-1">first pass after reconnect carries {bytes(sim.blackout.pass_bytes)}</div>
                    </div>
                  </div>
                </Section>
              </div>
            )}
          </div>
          <div className="bg-panel min-h-0">
            {selected ? <Inspector key={selected} id={selected} onClose={() => setSelected(null)} onSelect={setSelected} /> : <div className="p-4 label">Select an event to inspect why it was kept or dropped.</div>}
          </div>
        </div>
      )}
    </div>
  );
}

export default function BlackoutPage() {
  return (
    <Suspense>
      <BlackoutInner />
    </Suspense>
  );
}
