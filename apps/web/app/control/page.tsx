"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { EventSpace } from "@/components/EventSpace";
import { Inspector } from "@/components/Inspector";
import { Kpi, Section } from "@/components/Kpi";
import { GlyphIcon } from "@/components/Marker";
import { Nav, SourceBadges, useStatus } from "@/components/Nav";
import { ObjectivePanel } from "@/components/ObjectivePanel";
import { StripChart } from "@/components/StripChart";
import { Timeline } from "@/components/Timeline";
import { api, type EventRow, type Mission, type Series, type Simulation } from "@/lib/api";
import { ACTIONS, ACTION_COLOR, ACTION_LABEL, SOL_SECONDS, TYPES, TYPE_LABEL, bytes, num, pct, solClock } from "@/lib/format";
import { SPEEDS, lastAtOrBefore, useReplayClock } from "@/lib/replay";

const CHANNELS = ["pressure", "air_temp", "ground_temp", "uv_abc", "rel_humidity", "dose_b"];

export default function ControlPage() {
  const { status } = useStatus();
  const [mission, setMission] = useState<Mission | null>(null);
  const [events, setEvents] = useState<EventRow[]>([]);
  const [sim, setSim] = useState<Simulation | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [series, setSeries] = useState<Record<string, Series>>({});
  const [showObjective, setShowObjective] = useState(false);
  const [mode, setMode] = useState<"raw" | "normalized">("raw");
  const [typeOff, setTypeOff] = useState<Set<string>>(new Set());
  const [actionOff, setActionOff] = useState<Set<string>>(new Set());
  const [showAll, setShowAll] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(
    () =>
      Promise.all([api<Mission>("/api/mission"), api<{ events: EventRow[] }>("/api/events"), api<Simulation>("/api/simulation")])
        .then(([m, ev, s]) => {
          setMission(m);
          setEvents(ev.events);
          setSim(s);
          setErr(null);
        })
        .catch((e) => setErr(String((e as Error).message))),
    [],
  );
  useEffect(() => {
    let alive = true;
    Promise.all([api<Mission>("/api/mission"), api<{ events: EventRow[] }>("/api/events"), api<Simulation>("/api/simulation")])
      .then(([m, ev, s]) => {
        if (!alive) return;
        setMission(m);
        setEvents(ev.events);
        setSim(s);
      })
      .catch((e) => alive && setErr(String((e as Error).message)));
    return () => {
      alive = false;
    };
  }, []);

  const sols = mission?.sols ?? [0, 1];
  const start = sols[0];
  const end = sols[sols.length - 1] + 1;
  const clock = useReplayClock(start, end);
  const t = showAll ? end : clock.t;
  const solKey = Math.floor(clock.t);

  // telemetry: fetch the current and previous sol whenever the replay crosses a sol boundary
  useEffect(() => {
    if (!mission) return;
    const from = showAll ? start : solKey - 1;
    const to = showAll ? end : solKey + 1;
    let alive = true;
    Promise.all(
      CHANNELS.map((c) => api<Series>(`/api/series?channel=${c}&sol_from=${from}&sol_to=${to}&max_points=${showAll ? 2000 : 1600}`)),
    ).then((all) => alive && setSeries(Object.fromEntries(all.map((s) => [s.channel, s]))));
    return () => {
      alive = false;
    };
  }, [mission, solKey, showAll, start, end]);

  const items = useMemo(() => new Map((sim?.items ?? []).map((i) => [i.id, i])), [sim]);
  const arrived = useMemo(() => events.filter((e) => e.sol_end <= t), [events, t]);
  const visibleIds = useMemo(
    () =>
      new Set(
        arrived
          .filter((e) => !typeOff.has(e.event_type ?? "") && !actionOff.has(e.final_action ?? ""))
          .map((e) => e.id),
      ),
    [arrived, typeOff, actionOff],
  );

  const snap = sim ? lastAtOrBefore(sim.timeline, t, (s) => s.t) : undefined;
  const downlinkedNow = useMemo(
    () => (sim?.items ?? []).filter((i) => i.kind === "event" && i.downlinked_at != null && i.downlinked_at <= t),
    [sim, t],
  );
  const svpb = useMemo(() => {
    const b = downlinkedNow.reduce((a, i) => a + i.sent, 0);
    const u = downlinkedNow.reduce((a, i) => a + i.utility, 0);
    return b ? u / (b / 1e6) : null;
  }, [downlinkedNow]);
  const queue = useMemo(
    () =>
      (sim?.items ?? [])
        .filter((i) => i.arrival <= t && i.final !== "discard" && (i.downlinked_at == null || i.downlinked_at > t))
        .sort((a, b) => b.utility - a.utility),
    [sim, t],
  );
  const nSols = sols.length || 1;
  const samplesPerSec = mission ? (mission.counts.samples ?? 0) / (nSols * SOL_SECONDS) : 0;
  const gates = arrived.reduce<Record<string, number>>((a, e) => ((a[e.gate ?? "?"] = (a[e.gate ?? "?"] ?? 0) + 1), a), {});
  const engineDecided = (gates.auto ?? 0) + (gates.uncertain ?? 0);
  const domain: [number, number] = showAll ? [start, end] : [Math.max(start, t - 1), Math.max(start + 1, t)];
  const specs = Object.fromEntries((mission?.channels ?? []).map((c) => [c.name, c]));

  const toggle = (set: Set<string>, k: string, f: (s: Set<string>) => void) => {
    const n = new Set(set);
    if (n.has(k)) n.delete(k);
    else n.add(k);
    f(n);
  };

  return (
    <div className="h-screen flex flex-col">
      <Nav right={<SourceBadges status={status} />} />

      {/* mission bar */}
      <div className="flex items-center gap-4 px-4 h-10 border-b border-line bg-bg">
        <div className="flex items-baseline gap-2">
          <span className="label">Mission</span>
          <span className="mono text-[12px] text-ink">{mission?.short_name ?? "—"}</span>
          <span className="mono text-[10px] text-ink-3 hidden xl:inline">{mission?.target}</span>
        </div>
        <div className="mono text-[13px] text-ink tabular-nums">{solClock(t)}</div>
        <div className="flex items-center gap-1">
          <button className="btn" onClick={() => clock.setPlaying(!clock.playing)} disabled={!mission || showAll}>
            {clock.playing ? "Pause" : "Play"}
          </button>
          <button className="btn" onClick={() => clock.step(1 / 24)} disabled={showAll} title="Step one Mars hour">
            Step
          </button>
          {SPEEDS.map((s) => (
            <button key={s} className="btn" data-active={clock.speed === s} onClick={() => clock.setSpeed(s)}>
              {s >= 1000 ? `${s / 1000}k` : s}×
            </button>
          ))}
          <button className="btn" onClick={() => clock.setT(start)} disabled={showAll}>
            Reset
          </button>
          <button className="btn" data-active={showAll} onClick={() => setShowAll(!showAll)} title="Show the whole processed segment">
            All sols
          </button>
        </div>
        {clock.playing && <span className="mono text-[10px] state-pulse" style={{ color: "var(--ink-2)" }}>● REPLAYING HISTORICAL DATA</span>}
        <div className="ml-auto flex items-center gap-2">
          <span className="label">Objective</span>
          <button className="btn" onClick={() => setShowObjective(true)}>
            {status?.objective?.name ?? "—"} ▾
          </button>
          <Link className="btn" href={`/blackout?start=${t.toFixed(3)}`} style={{ color: "var(--s-critical)", borderColor: "#5b2323" }}>
            Trigger blackout
          </Link>
        </div>
      </div>

      {err && <div className="px-4 py-2 mono text-[11px]" style={{ color: "var(--s-critical)" }}>API: {err} — is the pipeline service running on :8787?</div>}

      {/* KPI strip */}
      <div className="grid grid-cols-7 border-b border-line bg-panel">
        <Kpi
          label="Raw sensor rate"
          value={`${num(samplesPerSec, 1)} /s`}
          sub={`mission time · ${Math.round(samplesPerSec * (clock.playing ? clock.speed : 0)).toLocaleString()} /s wall at ${clock.speed}×`}
          title="Channel samples per Mars second in the processed REMS+RAD products"
        />
        <Kpi label="Event candidates" value={arrived.length} sub={`of ${events.length} in segment · ${mission?.counts.instrument_windows ?? "—"} windows`} />
        <Kpi
          label="Engine decisions"
          value={arrived.length}
          sub={`${engineDecided} routed by engine · ${(gates.fallback ?? 0) + (gates.engine_error ?? 0)} rules fallback`}
          title="Every candidate is judged; low-confidence judgments fall back to deterministic rules"
        />
        <Kpi label="Deep analyses" value={gates.escalated ?? 0} sub={status?.deep_available ? status.deep_provider ?? "" : "provider unavailable"} />
        <Kpi
          label="Data reduction"
          value={snap && snap.raw_generated ? pct(1 - snap.downlinked / snap.raw_generated, 2) : "—"}
          sub={`${bytes(snap?.downlinked)} of ${bytes(snap?.raw_generated)} raw`}
        />
        <Kpi label="Downlink queue" value={queue.length} sub={`${bytes(snap?.storage_used)} / ${bytes(snap?.capacity)} onboard`} />
        <Kpi
          label="Science value / byte"
          value={svpb == null ? "—" : `${num(svpb, 2)}`}
          sub="PROXY · Σ utility per MB downlinked"
          title="Proxy metric: sum of the engine-informed utility of fully downlinked events per MB. Self-estimated; not a measure of true scientific value."
        />
      </div>

      {/* main */}
      <div className="flex-1 min-h-0 grid grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)_380px] gap-px bg-line">
        <Section
          title="Telemetry · REMS + RAD"
          right={
            <>
              <button className="btn" data-active={mode === "raw"} onClick={() => setMode("raw")}>Raw</button>
              <button className="btn" data-active={mode === "normalized"} onClick={() => setMode("normalized")}>Normalized</button>
            </>
          }
        >
          <div className="h-full flex flex-col">
            {CHANNELS.map((c) => (
              <div key={c} className="flex-1 min-h-0 border-b border-line">
                <StripChart
                  series={series[c] ?? null}
                  label={c}
                  unit={specs[c]?.unit ?? ""}
                  domain={domain}
                  cursor={showAll ? undefined : t}
                  events={arrived}
                  onSelect={setSelected}
                  mode={mode}
                />
              </div>
            ))}
            <div className="px-2 py-1 mono text-[10px] text-ink-3">
              shaded = candidate event (colour = class) · <span style={{ color: "var(--s-warn)" }}>●</span> synthetic injection · REMS samples in bursts; gaps are real
            </div>
          </div>
        </Section>

        <Section
          title="Event space"
          right={<span className="mono text-[10px] text-ink-3">{visibleIds.size} shown</span>}
        >
          <div className="h-full flex flex-col">
            <div className="flex flex-wrap items-center gap-1 px-2 py-1.5 border-b border-line">
              {TYPES.map((k) => (
                <button key={k} className="btn flex items-center gap-1" style={{ opacity: typeOff.has(k) ? 0.35 : 1, padding: "2px 6px" }} onClick={() => toggle(typeOff, k, setTypeOff)}>
                  <GlyphIcon type={k} size={8} /> {TYPE_LABEL[k]}
                </button>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-1 px-2 py-1.5 border-b border-line">
              {ACTIONS.map((k) => (
                <button key={k} className="btn flex items-center gap-1" style={{ opacity: actionOff.has(k) ? 0.35 : 1, padding: "2px 6px" }} onClick={() => toggle(actionOff, k, setActionOff)}>
                  <span style={{ width: 8, height: 8, background: ACTION_COLOR[k], display: "inline-block" }} /> {ACTION_LABEL[k]}
                </button>
              ))}
              <span className="mono text-[10px] text-ink-4 ml-1">opacity = final action · size = expected science value</span>
            </div>
            <div className="flex-1 min-h-0">
              <EventSpace events={arrived} selected={selected} onSelect={setSelected} visibleIds={visibleIds} />
            </div>
          </div>
        </Section>

        <div className="bg-panel min-h-0 flex flex-col">
          {showObjective && status?.objective ? (
            <ObjectivePanel
              activeId={status.objective.id}
              onClose={() => setShowObjective(false)}
              onApplied={() => {
                void load();
              }}
            />
          ) : selected ? (
            <Inspector key={selected} id={selected} onClose={() => setSelected(null)} onSelect={setSelected} />
          ) : (
            <div className="h-full flex flex-col">
              <div className="flex items-center px-3 h-8 border-b border-line">
                <span className="label" style={{ color: "var(--ink-2)" }}>Downlink queue @ replay time</span>
              </div>
              <div className="flex-1 min-h-0 overflow-y-auto">
                <table className="w-full mono text-[10px]">
                  <tbody>
                    {queue.slice(0, 40).map((q) => {
                      const ev = events.find((e) => e.id === q.id);
                      return (
                        <tr key={q.id} className="border-b border-line cursor-pointer hover:bg-panel-2" onClick={() => ev && setSelected(q.id)}>
                          <td className="pl-3 py-1 w-5">{ev ? <GlyphIcon type={ev.event_type} size={7} /> : "·"}</td>
                          <td className="truncate max-w-[150px] text-ink-2">{q.id}</td>
                          <td className="text-right text-ink-3">{num(q.utility, 3)}</td>
                          <td className="text-right text-ink-2">{ACTION_LABEL[q.final]}</td>
                          <td className="text-right pr-3 text-ink-3">{bytes(q.bytes)}</td>
                        </tr>
                      );
                    })}
                    {!queue.length && (
                      <tr>
                        <td className="p-3 text-ink-3">Queue empty at this replay time. Press PLAY.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              <div className="flex items-center px-3 h-8 border-y border-line">
                <span className="label" style={{ color: "var(--ink-2)" }}>Latest candidates</span>
              </div>
              <div className="h-[38%] overflow-y-auto">
                {arrived
                  .slice()
                  .reverse()
                  .slice(0, 40)
                  .map((e) => {
                    const it = items.get(e.id);
                    return (
                      <button key={e.id} className="w-full flex items-center gap-2 px-3 py-1 border-b border-line text-left hover:bg-panel-2" onClick={() => setSelected(e.id)}>
                        <GlyphIcon type={e.event_type} size={7} />
                        <span className="mono text-[10px] text-ink-2 truncate flex-1">{e.id}</span>
                        {e.synthetic && <span className="mono text-[9px]" style={{ color: "var(--s-warn)" }}>SYN</span>}
                        <span className="mono text-[10px] text-ink-3">{e.gate}</span>
                        <span className="mono text-[10px] w-16 text-right" style={{ color: e.final_action === "discard" ? "var(--ink-4)" : "var(--ink)" }}>
                          {ACTION_LABEL[it && it.downlinked_at != null && it.downlinked_at <= t ? e.final_action ?? "" : e.proposed_action ?? ""]}
                        </span>
                      </button>
                    );
                  })}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* timeline */}
      <div className="border-t border-line bg-panel">
        <Timeline events={events} sim={sim} domain={[start, end]} t={t} onScrub={(x) => { setShowAll(false); clock.setT(x); }} onSelect={setSelected} />
      </div>
    </div>
  );
}
