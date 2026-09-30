"use client";

/* LIVE DATA FIELD — deterministic time-lane view. X = time (now at the right edge); Y = source → sub-source lane.
   DSN contact = horizontal interval (thickness ∝ log data rate, only when a rate is reported; fill = direction);
   NOAA = measured line (speed, Bz); DONKI = event diamond at official event time; Horizons = refresh tick;
   Mars image = point at first-seen (collector) or reached-Earth / published time (Tier 0). No decoration: every mark
   is a real record, new ones pulse once. */
import { useEffect, useMemo, useRef, useState } from "react";
import type { DonkiEvent, Geometry, SolarWindSample } from "@/lib/observatory/types";
import { SOURCE_COLOR, type Selection, type TimelineContact, type TimelineImage } from "./model";

export interface FieldData {
  contacts: (TimelineContact & { observedFromLoad?: boolean })[];
  weather: SolarWindSample[];
  donki: DonkiEvent[];
  geometry: Geometry[];
  images: (TimelineImage & { plotAt: string; plotBasis: string })[];
}

interface Lane { id: string; group: string; label: string; color: string; h: number }

const LABEL_W = 132;
const PAD_R = 14;
const AXIS_H = 22;
const t = (iso: string) => Date.parse(iso);

export function LiveField({ data, from, to, fresh, onSelect }: { data: FieldData; from: number; to: number; fresh: Set<string>; onSelect: (s: Selection) => void }) {
  const box = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(900);
  useEffect(() => {
    if (!box.current) return;
    const ro = new ResizeObserver((e) => setW(Math.max(320, Math.floor(e[0].contentRect.width))));
    ro.observe(box.current);
    return () => ro.disconnect();
  }, []);

  const inWin = (iso: string | null | undefined) => !!iso && t(iso) >= from && t(iso) <= to;
  const contacts = data.contacts.filter((c) => t(c.start) <= to && (!c.end || t(c.end) >= from));
  const images = data.images.filter((i) => inWin(i.plotAt));
  const donki = data.donki.filter((d) => inWin(d.time));
  const weather = data.weather.filter((s) => inWin(s.time));
  const geometry = data.geometry.filter((g) => inWin(g.computedFor));

  const lanes: Lane[] = useMemo(() => {
    const L: Lane[] = [];
    const dishes = [...new Set(contacts.map((c) => `${c.complex}|${c.dish}`))].sort();
    if (!dishes.length) L.push({ id: "dsn:none", group: "DSN NOW · LIVE", label: "no active contact", color: SOURCE_COLOR.dsn, h: 14 });
    for (const d of dishes) { const [cx, dish] = d.split("|"); L.push({ id: `dsn:${dish}`, group: "DSN NOW · LIVE", label: `${dish} · ${cx.slice(0, 3).toUpperCase()}`, color: SOURCE_COLOR.dsn, h: 14 }); }
    L.push({ id: "noaa:speed", group: "NOAA · NEAR REAL-TIME (L1)", label: "wind speed", color: SOURCE_COLOR.noaa, h: 30 });
    L.push({ id: "noaa:bz", group: "NOAA · NEAR REAL-TIME (L1)", label: "IMF Bz", color: SOURCE_COLOR.noaa, h: 30 });
    const types = [...new Set(donki.map((d) => d.type))].sort();
    for (const ty of types.length ? types : ["—"]) L.push({ id: `donki:${ty}`, group: "DONKI · EVENTS", label: ty === "—" ? "no event in window" : ty, color: SOURCE_COLOR.donki, h: 14 });
    L.push({ id: "horizons", group: "HORIZONS · COMPUTED", label: "Earth–Mars refresh", color: SOURCE_COLOR.horizons, h: 14 });
    for (const rover of ["Perseverance", "Curiosity"] as const) {
      const src = rover === "Perseverance" ? "perseverance" : "curiosity";
      const cams = [...new Set(images.filter((i) => i.rover === rover).map((i) => i.cameraLabel))].sort().slice(0, 6);
      for (const c of cams.length ? cams : ["—"]) L.push({ id: `${src}:${c}`, group: `${rover.toUpperCase()} · NEWLY PUBLISHED`, label: c === "—" ? "no image in window" : c, color: SOURCE_COLOR[src], h: 14 });
    }
    return L;
  }, [contacts, donki, images]);

  const y: Record<string, number> = {};
  let acc = 8;
  let lastGroup = "";
  const groupY: { g: string; y: number }[] = [];
  for (const l of lanes) {
    if (l.group !== lastGroup) { acc += 16; groupY.push({ g: l.group, y: acc - 5 }); lastGroup = l.group; }
    y[l.id] = acc;
    acc += l.h + 3;
  }
  const H = acc + AXIS_H + 4;
  const plotW = w - LABEL_W - PAD_R;
  const x = (ms: number) => LABEL_W + ((ms - from) / (to - from)) * plotW;

  const span = to - from;
  const step = [60e3, 5 * 60e3, 15 * 60e3, 30 * 60e3, 3600e3, 3 * 3600e3, 6 * 3600e3].find((s) => span / s <= 8) ?? 6 * 3600e3;
  const ticks: number[] = [];
  for (let k = Math.ceil(from / step) * step; k <= to; k += step) ticks.push(k);

  const series = (key: "speed" | "bz", laneId: string) => {
    const pts = weather.filter((s) => s[key] !== null);
    if (pts.length < 2) return null;
    const vals = pts.map((s) => s[key] as number);
    const lo = key === "bz" ? Math.min(-5, ...vals) : Math.min(...vals) - 5;
    const hi = key === "bz" ? Math.max(5, ...vals) : Math.max(...vals) + 5;
    const lane = lanes.find((l) => l.id === laneId)!;
    const yy = (v: number) => y[laneId] + lane.h - ((v - lo) / (hi - lo)) * lane.h;
    const d = pts.map((s, i) => `${i ? "L" : "M"}${x(t(s.time)).toFixed(1)},${yy(s[key] as number).toFixed(1)}`).join("");
    return (
      <g key={laneId}>
        {key === "bz" && <line x1={LABEL_W} x2={w - PAD_R} y1={yy(0)} y2={yy(0)} stroke="var(--line-2)" strokeDasharray="2 3" />}
        <path d={d} fill="none" stroke={SOURCE_COLOR.noaa} strokeWidth={1.2} opacity={0.9} />
        <text x={w - PAD_R - 2} y={y[laneId] + 9} textAnchor="end" className="obs-mono" fontSize={9} fill="var(--ink-3)">
          {key === "speed" ? `${vals.at(-1)} km/s` : `Bz ${vals.at(-1)} nT`}
        </text>
      </g>
    );
  };

  return (
    <div ref={box} className="w-full overflow-hidden" data-testid="live-field">
      <svg width={w} height={H} role="img" aria-label="Live data field: real events by time and source">
        <rect x={LABEL_W} y={0} width={plotW} height={H - AXIS_H} fill="var(--panel)" />
        {ticks.map((k) => (
          <g key={k}>
            <line x1={x(k)} x2={x(k)} y1={0} y2={H - AXIS_H} stroke="var(--grid)" />
            <text x={x(k)} y={H - 8} textAnchor="middle" fontSize={9} fill="var(--ink-4)" className="obs-mono">{new Date(k).toISOString().slice(11, 16)}</text>
          </g>
        ))}
        {groupY.map((g) => <text key={g.g} x={6} y={g.y} fontSize={9} fill="var(--ink-2)" className="obs-mono" letterSpacing="0.08em">{g.g}</text>)}
        {lanes.map((l) => (
          <g key={l.id}>
            <line x1={LABEL_W} x2={w - PAD_R} y1={y[l.id] + l.h / 2} y2={y[l.id] + l.h / 2} stroke="var(--grid)" />
            <text x={LABEL_W - 6} y={y[l.id] + l.h / 2 + 3} textAnchor="end" fontSize={9} fill="var(--ink-3)" className="obs-mono">{l.label}</text>
          </g>
        ))}

        {contacts.map((c) => {
          const x0 = x(Math.max(from, t(c.start)));
          const x1 = x(c.end ? Math.min(to, t(c.end)) : to);
          const rate = c.downRate;
          const th = rate ? Math.max(2, Math.min(10, Math.log10(rate) * 1.6)) : 1.5;
          const cy = y[`dsn:${c.dish}`] + 7;
          return (
            <g key={`${c.key}|${c.start}`} className={fresh.has(`${c.key}|${c.start}`) ? "obs-pulse" : undefined} style={{ cursor: "pointer" }}
              onClick={() => onSelect({ kind: "contact", contact: { key: c.key, dish: c.dish, complex: c.complex, spacecraftCode: "", spacecraftName: c.spacecraftName, mars: c.mars, direction: c.direction as "BOTH", band: c.band, downRate: c.downRate, upRate: null, downPower: null, rangeKm: null, azimuth: null, elevation: null, activity: "", since: c.start } })}>
              <rect x={x0} y={cy - th / 2} width={Math.max(1.5, x1 - x0)} height={th} fill={c.direction === "UPLINK" ? "none" : SOURCE_COLOR.dsn} stroke={SOURCE_COLOR.dsn} strokeWidth={c.direction === "UPLINK" ? 1 : 0} opacity={c.direction === "BOTH" ? 1 : 0.75} />
              {c.observedFromLoad && <line x1={x0} x2={x0} y1={cy - 6} y2={cy + 6} stroke="var(--ink-4)" strokeDasharray="1 2" />}
              {c.mars && <rect x={x0} y={cy - 7} width={Math.max(1.5, x1 - x0)} height={14} fill="none" stroke="#f0883e" strokeWidth={0.8} />}
              {x1 - x0 > 60 && <text x={x0 + 3} y={cy - 4} fontSize={8.5} fill="var(--ink)" className="obs-mono">{c.spacecraftName.slice(0, 28)}</text>}
            </g>
          );
        })}
        {series("speed", "noaa:speed")}
        {series("bz", "noaa:bz")}
        {donki.map((d) => {
          const cx = x(t(d.time));
          const cy = y[`donki:${d.type}`] + 7;
          return <path key={d.id} className={fresh.has(d.id) ? "obs-pulse" : undefined} d={`M${cx},${cy - 5}L${cx + 5},${cy}L${cx},${cy + 5}L${cx - 5},${cy}Z`} fill={SOURCE_COLOR.donki} style={{ cursor: "pointer" }} onClick={() => onSelect({ kind: "donki", event: d })}><title>{`${d.id} · ${d.title}`}</title></path>;
        })}
        {geometry.map((g) => <line key={g.computedFor} x1={x(t(g.computedFor))} x2={x(t(g.computedFor))} y1={y.horizons + 1} y2={y.horizons + 13} stroke={SOURCE_COLOR.horizons} strokeWidth={1.5}><title>{`Horizons computed for ${g.computedFor}`}</title></line>)}
        {images.map((i) => {
          const src = i.rover === "Perseverance" ? "perseverance" : "curiosity";
          const lane = y[`${src}:${i.cameraLabel}`];
          if (lane === undefined) return null;
          return <circle key={i.imageId} className={fresh.has(i.imageId) ? "obs-pulse" : undefined} cx={x(t(i.plotAt))} cy={lane + 7} r={2.6} fill={SOURCE_COLOR[src]} style={{ cursor: "pointer" }} onClick={() => onSelect({ kind: "image", image: i })}><title>{`${i.imageId} · ${i.plotBasis}`}</title></circle>;
        })}
        <line x1={x(to)} x2={x(to)} y1={0} y2={H - AXIS_H} stroke="var(--s-good)" strokeWidth={1} opacity={0.7} />
        <text x={x(to) - 3} y={10} textAnchor="end" fontSize={9} fill="var(--s-good)" className="obs-mono">NOW</text>
      </svg>
    </div>
  );
}
