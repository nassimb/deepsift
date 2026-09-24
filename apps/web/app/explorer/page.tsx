"use client";

import { useEffect, useState } from "react";
import { Inspector } from "@/components/Inspector";
import { Section } from "@/components/Kpi";
import { GlyphIcon } from "@/components/Marker";
import { Nav, SourceBadges, useStatus } from "@/components/Nav";
import { StripChart } from "@/components/StripChart";
import { api, type EventRow, type Mission, type Series } from "@/lib/api";
import { ACTION_LABEL, TYPES, TYPE_LABEL, duration, num, solClock } from "@/lib/format";

export default function ExplorerPage() {
  const { status } = useStatus();
  const [mission, setMission] = useState<Mission | null>(null);
  const [events, setEvents] = useState<EventRow[]>([]);
  const [channel, setChannel] = useState("pressure");
  const [from, setFrom] = useState<number | null>(null);
  const [to, setTo] = useState<number | null>(null);
  const [cls, setCls] = useState<string>("all");
  const [series, setSeries] = useState<Series | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api<Mission>("/api/mission"), api<{ events: EventRow[] }>("/api/events")]).then(([m, e]) => {
      setMission(m);
      setEvents(e.events);
      setFrom(242);
      setTo(243);
    });
  }, []);

  useEffect(() => {
    if (from == null || to == null) return;
    api<Series>(`/api/series?channel=${channel}&sol_from=${from}&sol_to=${to}&max_points=2500`).then(setSeries);
  }, [channel, from, to]);

  const spec = mission?.channels.find((c) => c.name === channel);
  const inRange = events.filter(
    (e) => from != null && to != null && e.sol_end >= from && e.sol_start <= to && e.sensors.includes(channel) && (cls === "all" || e.event_type === cls),
  );

  return (
    <div className="h-screen flex flex-col">
      <Nav right={<SourceBadges status={status} replay={false} />} />
      <div className="flex flex-wrap items-center gap-3 px-4 py-2 border-b border-line">
        <span className="label">Data explorer</span>
        <select value={channel} onChange={(e) => setChannel(e.target.value)}>
          {mission?.channels.map((c) => (
            <option key={c.name} value={c.name}>
              {c.instrument} · {c.name} ({c.unit})
            </option>
          ))}
        </select>
        <label className="mono text-[11px] text-ink-3 flex items-center gap-1">
          sol from
          <input type="number" step={0.25} value={from ?? ""} onChange={(e) => setFrom(Number(e.target.value))} className="w-20" />
        </label>
        <label className="mono text-[11px] text-ink-3 flex items-center gap-1">
          to
          <input type="number" step={0.25} value={to ?? ""} onChange={(e) => setTo(Number(e.target.value))} className="w-20" />
        </label>
        <div className="flex gap-1">
          {mission && (
            <button className="btn" onClick={() => { setFrom(mission.sols[0]); setTo(mission.sols.at(-1)! + 1); }}>
              All sols
            </button>
          )}
        </div>
        <select value={cls} onChange={(e) => setCls(e.target.value)}>
          <option value="all">all event classes</option>
          {TYPES.map((t) => (
            <option key={t} value={t}>{TYPE_LABEL[t]}</option>
          ))}
        </select>
        <span className="mono text-[10px] text-ink-3 ml-auto">
          {series?.raw_points?.toLocaleString() ?? "—"} raw samples in range · {series?.points.length ?? 0} plotted (min/mean/max buckets) · {spec?.description}
        </span>
      </div>
      <div className="flex-1 min-h-0 grid grid-cols-[minmax(0,1fr)_380px] gap-px bg-line">
        <div className="bg-bg p-3 space-y-3 overflow-y-auto">
          {from != null && to != null && (
            <>
              <Section title={`Raw · ${channel} (${spec?.unit ?? ""})`}>
                <div className="p-1"><StripChart series={series} label={channel} unit={spec?.unit ?? ""} domain={[from, to]} events={inRange} onSelect={setSelected} height={260} /></div>
              </Section>
              <Section title="Normalized · robust z per window vs nearest-local-time baseline (bright = flagged window)">
                <div className="p-1"><StripChart series={series} label={channel} unit="σ" domain={[from, to]} events={inRange} onSelect={setSelected} mode="normalized" height={180} /></div>
              </Section>
            </>
          )}
          <Section title={`Detections in range · ${inRange.length}`}>
            <table className="w-full mono text-[11px]">
              <thead className="text-ink-3">
                <tr className="text-left border-b border-line">
                  {["", "event", "start", "duration", "deviation", "class", "action"].map((h) => (
                    <th key={h} className="font-normal px-2 py-1">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {inRange.map((e) => (
                  <tr key={e.id} className="border-b border-line cursor-pointer hover:bg-panel-2" onClick={() => setSelected(e.id)}>
                    <td className="px-2"><GlyphIcon type={e.event_type} size={7} /></td>
                    <td className="px-2 text-ink-2">{e.id}{e.synthetic ? " · SYNTHETIC" : ""}</td>
                    <td className="px-2 text-ink-3">{solClock(e.sol_start)}</td>
                    <td className="px-2">{duration(e.duration_s)}</td>
                    <td className="px-2">{num(e.deviation, 1)}σ</td>
                    <td className="px-2">{TYPE_LABEL[e.event_type ?? ""]}</td>
                    <td className="px-2">{ACTION_LABEL[e.final_action ?? ""]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>
        </div>
        <div className="bg-panel min-h-0">
          {selected ? <Inspector key={selected} id={selected} onClose={() => setSelected(null)} onSelect={setSelected} /> : <div className="p-4 label">Click a detection or a shaded span.</div>}
        </div>
      </div>
    </div>
  );
}
