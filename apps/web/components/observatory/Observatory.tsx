"use client";

/* DEEPSIFT · LIVE DATA OBSERVATORY — real public signals only.
   Tier 0: cached public routes (/api/live/*) → current state + "events since you opened this page".
   Collector mode (when /api/live/collector/status answers): stored history, first-seen timestamps, SSE event stream.
   Every value shows its age; failing sources go DEGRADED / STALE instead of freezing as current. */
import { useEffect, useMemo, useRef, useState } from "react";
import { diffDsn, dedupe, donkiEvent, fmtRate, horizonsEvent, imageEvent, noaaEvent, orderEvents, sourceEvent, type TrackedContact } from "@/lib/observatory/events";
import { ageLabel, computeHealth, fmtAge } from "@/lib/observatory/health";
import { RESEARCH_ARCHIVE, SOURCES, SOURCE_BY_ID } from "@/lib/observatory/registry";
import type { Classification, DsnContact, Health, LiveDataEvent, MarsImage, SourceId } from "@/lib/observatory/types";
import { LiveField, type FieldData } from "./LiveField";
import { HEALTH_COLOR, SOURCE_COLOR, type CollectorStatus, type DonkiPayload, type DsnPayload, type GeometryPayload, type ImagesPayload, type Selection, type Timeline, type WeatherPayload } from "./model";
import { useLive, useNow, type LiveResult } from "./useLive";

const POLL: Record<SourceId, number> = { dsn: 10_000, noaa: 60_000, donki: 300_000, horizons: 300_000, perseverance: 180_000, curiosity: 180_000 };
const WINDOWS: [string, number][] = [["NOW", 10 * 60e3], ["15 MIN", 15 * 60e3], ["1 H", 3600e3], ["6 H", 6 * 3600e3], ["24 H", 24 * 3600e3]];
const FILTERS: [string, (e: LiveDataEvent) => boolean][] = [
  ["ALL", () => true],
  ["DSN", (e) => e.source_id === "dsn"],
  ["MARS IMAGES", (e) => e.source_id === "perseverance" || e.source_id === "curiosity"],
  ["SPACE WEATHER", (e) => e.source_id === "noaa" || e.source_id === "donki"],
  ["GEOMETRY", (e) => e.source_id === "horizons"],
];
const CLASSES: Classification[] = ["LIVE", "NEAR REAL-TIME", "NEAR REAL-TIME EVENTS", "CURRENT COMPUTED", "NEWLY PUBLISHED"];
const utc = (iso: string | null | undefined) => (iso ? `${iso.slice(0, 10)} ${iso.slice(11, 19)} UTC` : "—");
const km = (v: number | null) => (v === null ? "—" : v >= 1e6 ? `${(v / 1e6).toFixed(1)} million km` : `${Math.round(v).toLocaleString("en-US")} km`);

export function Observatory() {
  const now = useNow(1000);
  const dsn = useLive<DsnPayload>("/api/live/dsn", POLL.dsn);
  const noaa = useLive<WeatherPayload>("/api/live/space-weather", POLL.noaa);
  const donki = useLive<DonkiPayload>("/api/live/donki", POLL.donki);
  const geo = useLive<GeometryPayload>("/api/live/geometry", POLL.horizons);
  const pers = useLive<ImagesPayload>("/api/live/mars-images/perseverance", POLL.perseverance);
  const curi = useLive<ImagesPayload>("/api/live/mars-images/curiosity", POLL.curiosity);
  const col = useLive<CollectorStatus>("/api/live/collector/status", 10_000);
  const collector = !!col.data?.ok;
  const results: Record<SourceId, LiveResult<{ fetchedAt: string }>> = { dsn, noaa, donki, horizons: geo, perseverance: pers, curiosity: curi };

  const [selected, setSelected] = useState<Selection | null>(null);
  const [win, setWin] = useState(WINDOWS[3][1]);
  const [filter, setFilter] = useState("ALL");
  const [cls, setCls] = useState<Classification | "ALL">("ALL");

  // ─── Tier 0: events since this page was opened (real diffs of successive source states) ───
  const [openedAt] = useState(() => new Date().toISOString());
  const [tracked, setTracked] = useState<TrackedContact[]>([]);
  const [session, setSession] = useState<LiveDataEvent[]>([]);
  const seen = useRef(new Set<string>());
  const contactsRef = useRef<Map<string, TrackedContact> | null>(null);
  const firstVer = useRef<Partial<Record<SourceId, boolean>>>({});
  const lastNoaa = useRef<string | null>(null);
  const donkiSeen = useRef<Set<string> | null>(null);
  const imgSeen = useRef<Record<string, Set<string>>>({});
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  const push = (evs: LiveDataEvent[], keys: string[] = []) => {
    const out = dedupe(evs, seen.current);
    if (!out.length) return;
    setSession((s) => orderEvents([...out, ...s]).slice(0, 400));
    if (keys.length) {
      setFresh((f) => new Set([...f, ...keys]));
      setTimeout(() => setFresh((f) => { const n = new Set(f); keys.forEach((k) => n.delete(k)); return n; }), 2200);
    }
  };
  const errState = useRef<Partial<Record<SourceId, boolean>>>({});
  useEffect(() => {
    for (const [id, r] of Object.entries(results) as [SourceId, LiveResult<{ fetchedAt: string }>][]) {
      const failing = r.consecutiveErrors > 0;
      if (failing && !errState.current[id] && r.lastAttempt) push([sourceEvent(id, false, r.lastAttempt, r.error ?? "error")]);
      if (!failing && errState.current[id] && r.lastOk) push([sourceEvent(id, true, new Date().toISOString(), "source recovered")]);
      errState.current[id] = failing;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dsn.consecutiveErrors, noaa.consecutiveErrors, donki.consecutiveErrors, geo.consecutiveErrors, pers.consecutiveErrors, curi.consecutiveErrors]);

  useEffect(() => {
    if (!dsn.data) return;
    const n = new Date().toISOString();
    const r = diffDsn(contactsRef.current ?? new Map(), dsn.data.contacts, dsn.data.sourceTime, n, !contactsRef.current);
    if (!contactsRef.current) for (const v of r.next.values()) v.since = openedAt;
    contactsRef.current = r.next;
    setTracked([...r.next.values()]);
    push(r.events, r.events.map((e) => `${(e.metadata.key as string) ?? ""}|${(e.metadata.since as string) ?? e.timestamp_source}`));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dsn.version]);
  useEffect(() => {
    if (!noaa.data?.samples.length) return;
    const n = new Date().toISOString();
    const newer = noaa.data.samples.filter((s) => !lastNoaa.current || s.time > lastNoaa.current);
    if (lastNoaa.current) push(newer.map((s) => noaaEvent(s, n)));
    lastNoaa.current = noaa.data.samples.at(-1)!.time;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [noaa.version]);
  useEffect(() => {
    if (!donki.data) return;
    const n = new Date().toISOString();
    if (donkiSeen.current) { const nw = donki.data.events.filter((e) => !donkiSeen.current!.has(e.id)); push(nw.map((e) => donkiEvent(e, n)), nw.map((e) => e.id)); }
    donkiSeen.current = new Set(donki.data.events.map((e) => e.id));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [donki.version]);
  useEffect(() => {
    if (!geo.data) return;
    if (firstVer.current.horizons) push([horizonsEvent(geo.data.geometry, new Date().toISOString())]);
    firstVer.current.horizons = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [geo.version]);
  useEffect(() => {
    for (const [rover, r] of [["perseverance", pers], ["curiosity", curi]] as const) {
      if (!r.data) continue;
      const prev = imgSeen.current[rover];
      if (prev) { const nw = r.data.images.filter((i) => !prev.has(i.imageId)); push(nw.map((i) => imageEvent(i, new Date().toISOString())), nw.map((i) => i.imageId)); }
      imgSeen.current[rover] = new Set([...(prev ?? []), ...r.data.images.map((i) => i.imageId)]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pers.version, curi.version]);

  // ─── collector mode: stored history + SSE ───
  const [stored, setStored] = useState<LiveDataEvent[]>([]);
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  useEffect(() => {
    if (!collector) return;
    let es: EventSource | null = null;
    fetch("/api/live/collector/events?limit=300", { cache: "no-store" }).then((r) => r.json()).then((j: { events: LiveDataEvent[] }) => setStored(orderEvents(j.events ?? []))).catch(() => {});
    es = new EventSource("/api/live/collector/stream");
    es.addEventListener("live", (m) => {
      const e = JSON.parse((m as MessageEvent).data) as LiveDataEvent;
      setStored((s) => (s.some((x) => x.event_id === e.event_id) ? s : orderEvents([e, ...s]).slice(0, 600)));
      const k = (e.raw_reference as string) ?? `${(e.metadata.key as string) ?? ""}|${(e.metadata.since as string) ?? ""}`;
      setFresh((f) => new Set([...f, k]));
      setTimeout(() => setFresh((f) => { const n = new Set(f); n.delete(k); return n; }), 2200);
    });
    return () => es?.close();
  }, [collector]);
  useEffect(() => {
    if (!collector) return;
    const load = () => fetch(`/api/live/collector/timeline?from=${new Date(Date.now() - Math.max(win, 3600e3)).toISOString()}`, { cache: "no-store" }).then((r) => r.json()).then((j: Timeline) => setTimeline(j)).catch(() => {});
    void load();
    const id = setInterval(load, 20_000);
    return () => clearInterval(id);
  }, [collector, win]);

  // ─── health per source ───
  const health = (id: SourceId): { h: Health; label: string; last: string | null; connecting?: boolean } => {
    if (collector && col.data) {
      const s = col.data.sources.find((x) => x.id === id);
      if (s) {
        const h = computeHealth({ enabled: s.enabled, lastSuccess: s.lastSuccess, lastAttempt: s.lastPoll, lastError: s.lastError, consecutiveErrors: s.consecutiveErrors }, s.intervalS, now);
        return { h, label: ageLabel(s.lastSuccess, h, now, id === "perseverance" || id === "curiosity" ? "checked" : "updated"), last: s.lastSuccess };
      }
    }
    const r = results[id];
    const cadence = SOURCE_BY_ID[id].cacheS + POLL[id] / 1000;
    const h = computeHealth({ enabled: true, lastSuccess: r.lastOk, lastAttempt: r.lastAttempt, lastError: r.error, consecutiveErrors: r.consecutiveErrors }, cadence, now);
    if (!r.lastOk && !r.lastAttempt) return { h, label: "connecting…", last: null, connecting: true };
    return { h, label: ageLabel(r.lastOk, h, now, id === "perseverance" || id === "curiosity" ? "checked" : "updated"), last: r.lastOk };
  };
  const hs = Object.fromEntries(SOURCES.map((s) => [s.id, health(s.id)])) as Record<SourceId, ReturnType<typeof health>>;
  const online = SOURCES.filter((s) => hs[s.id].h === "ONLINE").length;

  const events = collector ? stored : session;
  const shown = events.filter((e) => (FILTERS.find((f) => f[0] === filter)?.[1] ?? (() => true))(e) && (cls === "ALL" || e.classification === cls));
  const lastEventAt = collector ? col.data?.lastEventAt ?? null : events[0]?.timestamp_ingested ?? null;

  // ─── field data ───
  const field: FieldData = useMemo(() => {
    if (collector && timeline) {
      return {
        contacts: timeline.contacts, weather: timeline.weather, donki: timeline.donki, geometry: timeline.geometry,
        images: timeline.images.map((i) => (i.backfill
          ? { ...i, plotAt: (i.published ?? i.reachedEarth ?? i.firstSeen)!, plotBasis: "collector start-up backfill · plotted at NASA's time" }
          : { ...i, plotAt: i.firstSeen, plotBasis: "first seen by DEEPSIFT" })),
      };
    }
    const contacts = tracked.map((c) => ({ key: c.key, dish: c.dish, complex: c.complex, spacecraftName: c.spacecraftName, mars: c.mars, direction: c.direction, band: c.band, downRate: c.downRate, start: c.since, end: null, observedFromLoad: c.since === openedAt }));
    const ended = session.filter((e) => e.event_type === "dsn_contact_ended").map((e) => {
      const m = e.metadata as unknown as TrackedContact & { ended: string };
      return { key: m.key, dish: m.dish, complex: m.complex, spacecraftName: m.spacecraftName, mars: m.mars, direction: m.direction, band: m.band, downRate: m.downRate, start: m.since, end: m.ended, observedFromLoad: m.since === openedAt };
    });
    const imgs = [...(pers.data?.images ?? []), ...(curi.data?.images ?? [])].map((i) => ({ ...i, firstSeen: "", plotAt: (i.published ?? i.reachedEarth ?? i.acquired)!, plotBasis: i.published ? "published by NASA" : "reached Earth (NASA)" })).filter((i) => i.plotAt);
    return { contacts: [...contacts, ...ended], weather: noaa.data?.samples ?? [], donki: donki.data?.events ?? [], geometry: geo.data ? [geo.data.geometry] : [], images: imgs };
  }, [collector, timeline, tracked, openedAt, session, pers.data, curi.data, noaa.data, donki.data, geo.data]);

  const to = now.getTime();
  const firstSeenMap = new Map((timeline?.images ?? []).filter((i) => !i.backfill).map((i) => [i.imageId, i.firstSeen]));

  return (
    <div className="obs space-y-5" data-testid="observatory">
      {/* header */}
      <header className="border-b border-line pb-3 grid gap-3 lg:grid-cols-[1fr_auto] items-end">
        <div>
          <div className="obs-mono text-[11px] tracking-[0.25em] text-ink-3">DEEPSIFT</div>
          <h1 className="obs-mono text-[20px] sm:text-[26px] tracking-[0.12em] text-ink">LIVE DATA OBSERVATORY</h1>
          <p className="text-[12px] text-ink-3 max-w-3xl">Real-time and near-real-time public signals across deep-space communications, Mars data publication and the space environment.</p>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-1 obs-mono text-[11px]" data-testid="obs-header">
          <Stat k="SOURCES ONLINE" v={<span style={{ color: online === SOURCES.length ? "var(--s-good)" : "var(--s-warn)" }}>● {online} / {SOURCES.length}</span>} />
          <Stat k="UTC" v={<span data-testid="utc-clock">{now.toISOString().slice(11, 19)}</span>} />
          <Stat k="LAST EVENT" v={lastEventAt ? `${fmtAge((to - Date.parse(lastEventAt)) / 1000)} ago` : "—"} />
          <Stat k={collector ? "EVENTS TODAY" : "EVENTS SINCE OPEN"} v={collector ? String(col.data?.eventsToday ?? 0) : String(session.length)} />
        </div>
      </header>

      <div className="flex flex-wrap items-center gap-2 text-[11px]" data-testid="mode">
        <span className="obs-mono px-1.5 py-0.5 border" style={{ borderColor: collector ? "var(--s-good)" : "var(--line-2)", color: collector ? "var(--s-good)" : "var(--ink-3)" }}>
          {collector ? "COLLECTOR · STORED HISTORY" : "TIER 0 · CACHED PUBLIC SOURCES"}
        </span>
        <span className="text-ink-4">
          {collector ? `Collector ${col.data?.version} · up ${fmtAge(col.data?.uptimeS ?? 0)} · ${col.data?.eventsTotal ?? 0} events stored` : "No durable history on this deployment yet: the event stream shows changes since you opened this page."}
        </span>
      </div>

      {/* source chips */}
      <div className="grid gap-2 grid-cols-2 md:grid-cols-3 xl:grid-cols-6" data-testid="source-chips">
        {SOURCES.map((s) => (
          <div key={s.id} className="panel px-2.5 py-2 space-y-0.5" data-testid="chip" data-source={s.id} data-health={hs[s.id].h}>
            <div className="flex items-center gap-1.5">
              <span className="inline-block w-1.5 h-1.5" style={{ background: SOURCE_COLOR[s.id] }} />
              <span className="obs-mono text-[11px] text-ink truncate">{s.name.toUpperCase()}</span>
            </div>
            <div className="obs-mono text-[9.5px] tracking-[0.08em] text-ink-3">{s.classification}</div>
            <div className="obs-mono text-[10px]" style={{ color: hs[s.id].connecting ? "var(--ink-3)" : HEALTH_COLOR[hs[s.id].h] }}>{hs[s.id].connecting ? "CONNECTING" : hs[s.id].h} · <span className="text-ink-3">{hs[s.id].label}</span></div>
            {results[s.id].error && <div className="text-[10px] truncate" style={{ color: "var(--s-warn)" }} title={results[s.id].error ?? ""}>{s.id === "dsn" ? "DSN feed unavailable" : "SOURCE DEGRADED"}: {results[s.id].error}</div>}
          </div>
        ))}
      </div>

      {/* live data field */}
      <section className="panel p-2 space-y-2" data-testid="field-section">
        <div className="flex flex-wrap items-center gap-2 px-1">
          <span className="obs-mono text-[11px] tracking-[0.15em] text-ink">LIVE DATA FIELD</span>
          <span className="text-[10.5px] text-ink-4">x = time (UTC) · rows = source / sub-source · every mark is a real record · new marks pulse once</span>
          <div className="ml-auto flex flex-wrap gap-1">
            {WINDOWS.map(([l, ms]) => <button key={l} type="button" className="btn" data-active={win === ms ? "true" : undefined} onClick={() => setWin(ms)} data-testid={`win-${l}`}>{l}</button>)}
          </div>
        </div>
        <LiveField data={field} from={to - win} to={to} fresh={fresh} onSelect={setSelected} />
        <p className="text-[10.5px] text-ink-4 px-1">
          DSN bars: filled = downlink, outlined = uplink only, full opacity = both; thickness ∝ log(reported data rate), hairline when not reported; orange frame = Mars-linked.
          {collector ? " Mars images are plotted when DEEPSIFT first saw them (images already published when the collector started are plotted at NASA's time)." : " Tier 0: DSN contacts start at the moment you opened this page (dotted edge); Mars images are plotted at NASA's published (Curiosity) or reached-Earth (Perseverance) time."}
        </p>
      </section>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        <DsnPanel p={dsn.data} h={hs.dsn} onSelect={setSelected} />
        <div className="space-y-4">
          <WeatherPanel p={noaa.data} h={hs.noaa} />
          <GeometryPanel p={geo.data} h={hs.horizons} />
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {([["perseverance", pers], ["curiosity", curi]] as const).map(([id, r]) => (
          <ImagesPanel key={id} id={id} p={r.data} h={hs[id]} firstSeen={firstSeenMap} collectorMode={collector} onSelect={setSelected} />
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <DonkiPanel p={donki.data} h={hs.donki} onSelect={setSelected} />
        <section className="panel p-3 space-y-2" data-testid="event-stream">
          <div className="flex flex-wrap items-center gap-2">
            <span className="obs-mono text-[11px] tracking-[0.15em] text-ink">{collector ? "LIVE EVENT STREAM · STORED" : "EVENTS SINCE YOU OPENED THIS PAGE"}</span>
            <span className="text-[10.5px] text-ink-4">{collector ? "" : `opened ${utc(openedAt)}`}</span>
          </div>
          <div className="flex flex-wrap gap-1">
            {FILTERS.map(([f]) => <button key={f} type="button" className="btn" data-active={filter === f ? "true" : undefined} onClick={() => setFilter(f)} data-testid={`filter-${f}`}>{f}</button>)}
            <select value={cls} onChange={(e) => setCls(e.target.value as Classification | "ALL")} className="bg-panel-2 border border-line text-ink-2 text-[11px] px-1.5 py-1" data-testid="filter-class">
              <option value="ALL">all classifications</option>
              {CLASSES.map((c) => <option key={c}>{c}</option>)}
            </select>
          </div>
          <ul className="obs-mono text-[11px] divide-y divide-[var(--line)] max-h-[420px] overflow-y-auto" data-testid="events">
            {shown.length === 0 && <li className="py-3 text-ink-4 font-sans text-[12px]">{collector ? "No stored events match." : "Waiting for the first real change (DSN transitions, new NOAA minutes, new images, new DONKI events, Horizons refreshes)."}</li>}
            {shown.slice(0, 200).map((e) => (
              <li key={e.event_id} className={`py-1.5 grid grid-cols-[62px_92px_minmax(0,1fr)] gap-2 cursor-pointer hover:bg-panel-2 ${fresh.has((e.raw_reference as string) ?? "") ? "obs-pulse" : ""}`} onClick={() => setSelected({ kind: "event", event: e })} data-testid="event-row">
                <span className="text-ink-3">{e.timestamp_ingested.slice(11, 19)}</span>
                <span style={{ color: SOURCE_COLOR[e.source_id] }}>{e.source_id.toUpperCase()}</span>
                <span className="truncate"><span className="text-ink">{e.title}</span> <span className="text-ink-3">· {e.summary}</span></span>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <section className="border border-dashed border-line-2 p-3 space-y-2" data-testid="research-archive">
        <div className="flex flex-wrap items-baseline gap-2">
          <span className="obs-mono text-[11px] tracking-[0.15em] text-ink-2">RESEARCH ARCHIVE</span>
          <span className="obs-mono text-[10px] text-ink-4 border border-line-2 px-1">ARCHIVAL / RESEARCH</span>
          <span className="text-[11px] text-ink-4">DEEPSIFT&apos;s frozen research datasets. Never mixed into the live views above.</span>
        </div>
        <div className="grid gap-2 sm:grid-cols-3">
          {RESEARCH_ARCHIVE.map((r) => (
            <a key={r.id} href={r.href} className="panel p-2 block hover:border-[var(--ink-4)]">
              <div className="text-[12px] text-ink">{r.name}</div>
              <div className="text-[11px] text-ink-3">{r.note}</div>
            </a>
          ))}
        </div>
        <p className="text-[11px] text-ink-4">Data stream = what is arriving and happening now. Mission Control = the DEEPSIFT prioritization experiment on archived data.</p>
      </section>

      <footer className="text-[11px] text-ink-4 space-y-1 border-t border-line pt-3" data-testid="attribution">
        <div>Sources: {SOURCES.map((s) => s.attribution).join(" · ")}.</div>
        <div>Independent DEEPSIFT research / monitoring interface. Not affiliated with or endorsed by NASA, JPL, NOAA or mission teams. DSN Now data comes from the file used by NASA&apos;s DSN Now web app (not a published API).</div>
      </footer>

      {selected && <Inspector s={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

function Stat({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div>
      <div className="text-[9px] tracking-[0.15em] text-ink-4">{k}</div>
      <div className="text-[13px] text-ink">{v}</div>
    </div>
  );
}

function PanelHead({ id, title, h, extra }: { id: SourceId; title: string; h: { h: Health; label: string; connecting?: boolean }; extra?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-baseline gap-2 border-b border-line pb-1.5">
      <span className="inline-block w-1.5 h-1.5 self-center" style={{ background: SOURCE_COLOR[id] }} />
      <span className="obs-mono text-[11px] tracking-[0.15em] text-ink">{title}</span>
      <span className="obs-mono text-[9.5px] text-ink-4 border border-line-2 px-1">{SOURCE_BY_ID[id].classification}</span>
      <span className="obs-mono text-[10px] ml-auto" style={{ color: h.connecting ? "var(--ink-3)" : HEALTH_COLOR[h.h] }}>{h.connecting ? "CONNECTING" : h.h} · <span className="text-ink-3">{h.label}</span></span>
      {extra}
    </div>
  );
}

function DsnPanel({ p, h, onSelect }: { p: DsnPayload | null; h: { h: Health; label: string }; onSelect: (s: Selection) => void }) {
  const complexes = ["Goldstone", "Madrid", "Canberra"];
  const marsLinks = p?.contacts.filter((c) => c.mars) ?? [];
  return (
    <section className="panel p-3 space-y-3" data-testid="dsn-panel">
      <PanelHead id="dsn" title="DEEP SPACE NETWORK · DSN NOW" h={h} />
      {!p && <p className="text-[12px] text-ink-3">Waiting for DSN Now…</p>}
      {p && marsLinks.length > 0 && (
        <div className="border px-2 py-1.5 text-[11px] obs-mono" style={{ borderColor: "#f0883e", color: "#f0883e" }} data-testid="mars-linked">
          MARS-LINKED DSN ACTIVITY · {marsLinks.map((c) => `${c.dish} ↔ ${c.spacecraftName} (${c.direction})`).join(" · ")}
        </div>
      )}
      {p && (
        <div className="grid gap-3 md:grid-cols-3">
          {complexes.map((cx) => {
            const st = p.stations.find((s) => s.name === cx);
            const dishes = p.dishes.filter((d) => d.complex === cx);
            return (
              <div key={cx} className="space-y-1.5" data-testid="dsn-complex" data-complex={cx}>
                <div className="flex items-baseline justify-between obs-mono text-[11px]">
                  <span className="text-ink tracking-[0.12em]">{cx.toUpperCase()}</span>
                  <span className="text-ink-4 text-[9.5px]">{st ? st.time.slice(11, 19) : ""} UTC</span>
                </div>
                {dishes.map((d) => {
                  const cs = p.contacts.filter((c) => c.dish === d.name);
                  return (
                    <div key={d.name} className="border border-line px-1.5 py-1 space-y-0.5" style={{ borderColor: cs.length ? "var(--line-2)" : "var(--line)" }}>
                      <div className="flex items-baseline gap-2 obs-mono text-[10.5px]">
                        <span className={cs.length ? "text-ink" : "text-ink-3"}>{d.name}</span>
                        <span className="text-ink-4 text-[9.5px]">{d.azimuth !== null ? `az ${d.azimuth}°` : ""} {d.elevation !== null ? `el ${d.elevation}°` : ""}</span>
                      </div>
                      <div className="text-[10px] text-ink-4 truncate" title={d.activity}>{d.activity || "—"}</div>
                      {cs.map((c) => (
                        <button key={c.key} type="button" onClick={() => onSelect({ kind: "contact", contact: c })} className="w-full text-left obs-mono text-[10.5px] flex flex-wrap gap-x-2 hover:bg-panel-2" data-testid="dsn-contact">
                          <span style={{ color: c.mars ? "#f0883e" : SOURCE_COLOR.dsn }}>{c.direction === "BOTH" ? "⇅" : c.direction === "DOWNLINK" ? "↓" : "↑"} {c.spacecraftName}</span>
                          <span className="text-ink-3">{c.band ? `${c.band}-band` : ""} {c.downRate !== null ? fmtRate(c.downRate) : c.upRate !== null ? fmtRate(c.upRate) : ""}</span>
                          {c.rangeKm !== null && <span className="text-ink-4">{km(c.rangeKm)}</span>}
                        </button>
                      ))}
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
      )}
      <p className="text-[10.5px] text-ink-4">Shows only fields DSN Now reports. Frequency (always 0) and round-trip light time (usually −1) are not displayed. A DSN contact is never claimed to carry any specific image.</p>
    </section>
  );
}

function WeatherPanel({ p, h }: { p: WeatherPayload | null; h: { h: Health; label: string; connecting?: boolean } }) {
  const pl = p?.latestPlasma ?? null;
  const f = p?.latestField ?? null;
  const cell = (k: string, v: number | null | undefined, u: string) => (
    <div><div className="obs-mono text-[9px] tracking-[0.12em] text-ink-4">{k}</div><div className="obs-mono text-[15px] text-ink" data-testid={`wx-${k.split(" ")[0].toLowerCase()}`}>{v === null || v === undefined ? <span className="text-ink-4 text-[11px]">unavailable</span> : <>{v}<span className="text-[10px] text-ink-3"> {u}</span></>}</div></div>
  );
  return (
    <section className="panel p-3 space-y-2" data-testid="weather-panel">
      <PanelHead id="noaa" title="SOLAR WIND / IMF" h={h} />
      <div className="obs-mono text-[10px] tracking-[0.1em]" style={{ color: SOURCE_COLOR.noaa }}>EARTH / L1 SPACE ENVIRONMENT — NOT MARS CONDITIONS</div>
      {!p ? <p className="text-[12px] text-ink-3">Waiting for NOAA SWPC…</p> : (
        <>
          <div className="grid grid-cols-3 gap-2">{cell("SPEED", pl?.speed, "km/s")}{cell("DENSITY", pl?.density, "p/cm³")}{cell("TEMPERATURE", pl?.temperature, "K")}</div>
          <div className="text-[10px] text-ink-4 obs-mono">plasma measured {utc(pl?.time)} · {pl?.source ?? "—"}{pl?.quality ? ` · quality flag ${pl.quality}` : ""}</div>
          <div className="grid grid-cols-4 gap-2">{cell("Bt", f?.bt, "nT")}{cell("Bx (GSM)", f?.bx, "nT")}{cell("By (GSM)", f?.by, "nT")}{cell("Bz (GSM)", f?.bz, "nT")}</div>
          <div className="text-[10px] text-ink-4 obs-mono">field measured {utc(f?.time)} · current source spacecraft <span className="text-ink-2">{f?.source ?? pl?.source ?? "—"}</span>{f?.quality ? ` · quality flag ${f.quality}` : ""}</div>
        </>
      )}
    </section>
  );
}

function GeometryPanel({ p, h }: { p: GeometryPayload | null; h: { h: Health; label: string } }) {
  const g = p?.geometry;
  return (
    <section className="panel p-3 space-y-2" data-testid="geometry-panel">
      <PanelHead id="horizons" title="EARTH ↔ MARS" h={h} />
      <div className="obs-mono text-[10px] tracking-[0.1em]" style={{ color: SOURCE_COLOR.horizons }}>COMPUTED BY JPL HORIZONS · EPHEMERIS, NOT TELEMETRY</div>
      {!g ? <p className="text-[12px] text-ink-3">Waiting for JPL Horizons…</p> : (
        <div className="grid grid-cols-2 gap-2 obs-mono">
          <div><div className="text-[9px] tracking-[0.12em] text-ink-4">DISTANCE</div><div className="text-[15px] text-ink" data-testid="distance">{km(g.distanceKm)}</div><div className="text-[10px] text-ink-3">{g.distanceAu?.toFixed(4)} AU</div></div>
          <div><div className="text-[9px] tracking-[0.12em] text-ink-4">ONE-WAY LIGHT TIME</div><div className="text-[15px] text-ink" data-testid="light-time">{g.lightTimeMin?.toFixed(2)} min</div></div>
          <div><div className="text-[9px] tracking-[0.12em] text-ink-4">RANGE-RATE</div><div className="text-[13px] text-ink">{g.rangeRateKmS} km/s</div></div>
          <div><div className="text-[9px] tracking-[0.12em] text-ink-4">SOLAR ELONGATION</div><div className="text-[13px] text-ink">{g.elongationDeg}°</div></div>
          <div className="col-span-2 text-[10px] text-ink-3">RA / DEC {g.raDec} · computed for {utc(g.computedFor)} · API {g.apiVersion}</div>
        </div>
      )}
    </section>
  );
}

function ImagesPanel({ id, p, h, firstSeen, collectorMode, onSelect }: { id: "perseverance" | "curiosity"; p: ImagesPayload | null; h: { h: Health; label: string; connecting?: boolean }; firstSeen: Map<string, string>; collectorMode: boolean; onSelect: (s: Selection) => void }) {
  const list = p?.images.slice(0, 8) ?? [];
  return (
    <section className="panel p-3 space-y-2" data-testid={`images-${id}`}>
      <PanelHead id={id} title={`${id.toUpperCase()} · NEW PUBLIC IMAGES`} h={h} />
      {!p && <p className="text-[12px] text-ink-3">Checking the NASA raw-image feed…</p>}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {list.map((i) => (
          <button key={i.imageId} type="button" className="text-left space-y-1 group" onClick={() => onSelect({ kind: "image", image: { ...i, firstSeen: firstSeen.get(i.imageId) } })} data-testid="mars-image">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={i.thumbUrl ?? i.imageUrl} alt={`${i.rover} ${i.cameraLabel} sol ${i.sol}`} loading="lazy" className="w-full aspect-square object-cover bg-panel-2 border border-line group-hover:border-[var(--ink-4)]" />
            <div className="obs-mono text-[10px] text-ink truncate">{i.cameraLabel}</div>
            <div className="obs-mono text-[9.5px] text-ink-3">sol {i.sol ?? "—"}{i.lmst ? ` · ${i.lmst} LMST` : ""}</div>
            <div className="obs-mono text-[9px] text-ink-4">acquired {i.acquired ? i.acquired.slice(0, 16).replace("T", " ") : "—"}</div>
            {firstSeen.get(i.imageId) && <div className="obs-mono text-[9px]" style={{ color: SOURCE_COLOR[id] }}>first seen {firstSeen.get(i.imageId)!.slice(11, 19)} UTC</div>}
          </button>
        ))}
      </div>
      <p className="text-[10.5px] text-ink-4">NEWLY PUBLISHED raw images, not a live camera. Image credit: NASA/JPL-Caltech. {collectorMode ? "“First seen by DEEPSIFT” appears for images the collector discovers after it started." : "“First seen by DEEPSIFT” needs the collector."}</p>
    </section>
  );
}

function DonkiPanel({ p, h, onSelect }: { p: DonkiPayload | null; h: { h: Health; label: string }; onSelect: (s: Selection) => void }) {
  return (
    <section className="panel p-3 space-y-2" data-testid="donki-panel">
      <PanelHead id="donki" title="SPACE WEATHER EVENTS · NASA DONKI" h={h} />
      {p?.partialError && <div className="text-[10.5px]" style={{ color: "var(--s-warn)" }}>Partially degraded: {p.partialError}</div>}
      {!p && <p className="text-[12px] text-ink-3">Waiting for DONKI…</p>}
      <ul className="divide-y divide-[var(--line)] max-h-[420px] overflow-y-auto">
        {(p?.events ?? []).slice(0, 30).map((e) => (
          <li key={e.id} className="py-1.5 cursor-pointer hover:bg-panel-2" onClick={() => onSelect({ kind: "donki", event: e })} data-testid="donki-event">
            <div className="flex gap-2 obs-mono text-[10.5px]"><span style={{ color: SOURCE_COLOR.donki }} className="w-24 shrink-0">{e.type}</span><span className="text-ink truncate">{e.title}</span></div>
            <div className="obs-mono text-[9.5px] text-ink-4">{utc(e.time)} · {e.id}</div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Inspector({ s, onClose }: { s: Selection; onClose: () => void }) {
  let src: SourceId = "dsn";
  let rows: [string, string][] = [];
  let img: (MarsImage & { firstSeen?: string }) | null = null;
  let url: string | null = null;
  let raw: unknown = null;
  if (s.kind === "event") {
    const e = s.event;
    src = e.source_id;
    rows = [["event", e.event_type], ["title", e.title], ["summary", e.summary], ["source timestamp", utc(e.timestamp_source)], ["DEEPSIFT ingest", utc(e.timestamp_ingested)], ["updated", utc(e.timestamp_updated)], ["raw ID", e.raw_reference ?? "—"], ["mission", e.mission ?? "—"], ["spacecraft", e.spacecraft ?? "—"], ["instrument", e.instrument ?? "—"], ["dedupe key", e.dedupe_key]];
    url = e.source_url;
    raw = e.metadata;
  } else if (s.kind === "contact") {
    const c = s.contact as DsnContact & { since?: string };
    src = "dsn";
    rows = [["antenna", c.dish], ["complex", c.complex], ["spacecraft", c.spacecraftName], ["Mars-linked", c.mars ? "yes" : "no"], ["direction", c.direction], ["band", c.band ?? "not reported"], ["downlink rate", c.downRate !== null ? fmtRate(c.downRate) : "not reported"], ["uplink rate", c.upRate !== null ? fmtRate(c.upRate) : "not reported"], ["received power", c.downPower !== null ? `${c.downPower} dBm` : "not reported"], ["range", km(c.rangeKm)], ["azimuth / elevation", `${c.azimuth ?? "—"}° / ${c.elevation ?? "—"}°`], ["activity", c.activity || "—"], ["observed since", utc(c.since)]];
    url = SOURCE_BY_ID.dsn.officialUrl;
    raw = c;
  } else if (s.kind === "image") {
    const i = s.image;
    img = i;
    src = i.rover === "Perseverance" ? "perseverance" : "curiosity";
    rows = [["rover", i.rover], ["camera", `${i.cameraLabel} (${i.camera})`], ["sol", String(i.sol ?? "—")], ["local solar time", i.lmst ? `${i.lmst} LMST` : "—"], ["ACQUIRED ON MARS", utc(i.acquired)], ["REACHED EARTH", utc(i.reachedEarth)], ["PUBLISHED", i.published ? utc(i.published) : "not reported by this feed"], ["FIRST SEEN BY DEEPSIFT", i.firstSeen ? utc(i.firstSeen) : "needs the collector"], ["image ID", i.imageId], ["dimensions", i.width && i.height ? `${i.width} × ${i.height}` : "—"], ["sample type", i.sampleType ?? "—"], ["credit", i.credit]];
    url = i.detailUrl ?? i.imageUrl;
  } else {
    const e = s.event;
    src = "donki";
    rows = [["type", e.type], ["official ID", e.id], ["event time", utc(e.time)], ["title", e.title], ["detail", e.detail || "—"], ["version", e.version ?? "—"]];
    url = e.link;
    raw = e;
  }
  const d = SOURCE_BY_ID[src];
  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-stretch sm:items-center justify-center p-0 sm:p-6" onClick={onClose} data-testid="inspector">
      <div className="panel w-full sm:max-w-[720px] max-h-full overflow-y-auto p-4 space-y-3" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-baseline gap-2">
          <span className="inline-block w-2 h-2" style={{ background: SOURCE_COLOR[src] }} />
          <span className="obs-mono text-[12px] text-ink tracking-[0.12em]">INSPECTOR · {d.name.toUpperCase()}</span>
          <button type="button" className="btn ml-auto" onClick={onClose} data-testid="inspector-close">Close</button>
        </div>
        {img && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={img.imageUrl} alt={`${img.rover} ${img.cameraLabel}`} className="w-full max-h-[380px] object-contain bg-panel-2 border border-line" />
        )}
        <dl className="grid grid-cols-[150px_minmax(0,1fr)] gap-x-3 gap-y-1 text-[11.5px]">
          {[["source", d.name], ["provider", d.provider], ["classification", d.classification], ["parser version", d.parserVersion], ...rows].map(([k, v]) => (
            <div key={k} className="contents"><dt className="text-ink-4 obs-mono text-[10.5px]">{k}</dt><dd className="text-ink-2 obs-mono break-words">{v}</dd></div>
          ))}
        </dl>
        {url && <a href={url} target="_blank" rel="noopener noreferrer" className="btn inline-block">Original source ↗</a>}
        {raw !== null && (
          <details>
            <summary className="text-[11px] text-ink-3 cursor-pointer">Normalized payload excerpt</summary>
            <pre className="obs-mono text-[10px] text-ink-3 bg-panel-2 p-2 overflow-x-auto max-h-60">{JSON.stringify(raw, null, 2).slice(0, 3000)}</pre>
          </details>
        )}
        <p className="text-[10.5px] text-ink-4">{d.attribution}. Independent DEEPSIFT monitoring; not affiliated with or endorsed by the source.</p>
      </div>
    </div>
  );
}
