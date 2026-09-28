"use client";

/* PUBLIC PHASE 3 MISSION CONTROL — historical replay of the held-out Curiosity Navcam traverses (sols 950–979).
   Data: data/mission-control.json only (frozen final-test artifacts; POSITION retained sets verified at build time).
   No API, no network requests, no recomputation: the replay only reveals stored frames over mission time and sums their
   stored byte costs. Decision texts are fixed templates filled from the frozen selection trace. */
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { GITHUB_URL, TopBarRow } from "@/components/release/Shell";
import { SiteFooter } from "@/components/site/SiteFooter";
import { FRAC_LABEL, FRACS, MC, RADIUS_M, decisionReason, pdsLabelUrl, previewUrl, type Frac, type Frame, type Policy, type Traverse } from "@/lib/missionControl";
import { eyeLabels, eyeTiers, productForEye, representation, stereoBroken } from "@/lib/representation";

const RUN_URL = `${GITHUB_URL}/blob/main/${MC.source.results}`;
const CONFIG_URL = `${GITHUB_URL}/blob/main/config/phase3_final_test_config.json`;
const PROVENANCE_URL = `${GITHUB_URL}/blob/main/apps/web/public/navcam/provenance.json`;

type Mode = "SEND_ALL" | "POSITION";
const SPEEDS = [1, 10, 100, 1000];
const pct = (x: number, d = 1) => `${(x * 100).toFixed(d)}%`;
const kb = (b: number) => (b >= 1e6 ? `${(b / 1e6).toFixed(2)} MB` : `${(b / 1e3).toFixed(1)} kB`);
const hms = (s: number) => `${String(Math.floor(s / 3600)).padStart(2, "0")}:${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

export function MissionControl() {
  const T = MC.traverses;
  const [ti, setTi] = useState(() => Math.max(0, T.findIndex((t) => t.sequence === MC.representative)));
  const tr: Traverse = T[ti];
  const [mode, setMode] = useState<Mode>("POSITION");
  const [frac, setFrac] = useState<Frac>("0.25");
  const [t, setT] = useState(tr.duration_s);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(100);
  const [sel, setSel] = useState<number | null>(null);
  const [radius, setRadius] = useState(true);
  const [demo, setDemo] = useState(false);
  const last = useRef<number | null>(null);

  useEffect(() => {
    if (!playing) {
      last.current = null;
      return;
    }
    let raf = 0;
    const loop = (now: number) => {
      if (last.current != null) {
        const dt = (now - last.current) / 1000;
        setT((cur) => {
          const nt = cur + dt * speed;
          if (nt >= tr.duration_s) {
            setPlaying(false);
            return tr.duration_s;
          }
          return nt;
        });
      }
      last.current = now;
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [playing, speed, tr.duration_s]);

  const policy: Policy | null = mode === "POSITION" ? tr.policies[frac] : null;
  const kept = useMemo(() => new Set(policy ? policy.kept : tr.frames.map((f) => f.i)), [policy, tr]);
  const seen = tr.frames.filter((f) => f.t_s <= t + 1e-6);
  const cursor = seen.length ? seen[seen.length - 1] : null;
  const focus: Frame | null = sel != null ? tr.frames[sel] : cursor;

  // accumulated over the frames revealed so far (stored per-frame byte costs; nothing recomputed)
  let used = 0;
  let pairsWhole = 0;
  let pairsBroken = 0;
  for (const f of seen) {
    const k = kept.has(f.i);
    used += k ? f.full_bytes : f.thumb_bytes;
    if (f.stereo && k) {
      const tiers = eyeTiers(f, true);
      if (tiers.L === "FULL" && tiers.R === "FULL") pairsWhole++;
    }
    if (stereoBroken(f, k)) pairsBroken++; // one eye at the full tier while its paired eye is not
  }
  const keptSeen = seen.filter((f) => kept.has(f.i));
  const covSoFar = seen.length ? seen.filter((f) => keptSeen.some((k) => Math.hypot(k.x - f.x, k.y - f.y) <= RADIUS_M)).length / seen.length : null;

  const op = mode === "SEND_ALL" ? MC.operating_points.send_all : MC.operating_points[frac];
  const trM = policy ? policy.metrics : { bytes_fraction: 1, coverage_5m: 1, max_distance_to_kept_m: 0, frames_retained: tr.frames_count, stereo_broken: 0, stereo_kept_full: tr.send_all.stereo_kept_full, unique_positions: 1 };

  const finalState = !playing && t >= tr.duration_s - 1e-6;
  const pickTraverse = (i: number) => {
    setTi(i);
    setSel(null);
    setPlaying(false);
    setDemo(false);
    setT(T[i].duration_s);
  };
  const replayFromStart = () => {
    setSel(null);
    setT(0);
    setPlaying(true);
  };
  const startDemo = () => {
    setTi(Math.max(0, T.findIndex((q) => q.sequence === MC.representative)));
    setMode("POSITION");
    setFrac("0.25");
    setSpeed(100);
    setSel(null);
    setT(0);
    setDemo(true);
    setPlaying(true);
  };
  const stepNext = () => {
    setPlaying(false);
    const next = tr.frames.find((f) => f.t_s > t + 1e-6);
    setT(next ? next.t_s : tr.duration_s);
  };

  const replayBar = (
    <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <select aria-label="traverse" className="bg-panel-2 border border-line text-ink mono text-[11px] px-2 py-1 min-w-0 max-w-full" value={ti} onChange={(e) => pickTraverse(Number(e.target.value))}>
            {T.map((q, i) => <option key={q.sequence} value={i}>sol {q.sequence} · {q.frames_count} frames · {q.length_m.toFixed(0)} m{q.sequence === MC.representative ? " · example (shown first)" : ""}</option>)}
          </select>
          <button className="btn" data-active="true" style={{ padding: "5px 12px" }} onClick={replayFromStart}>↺ Replay from start</button>
          <button className="btn" data-active={playing} onClick={() => { if (!playing && t >= tr.duration_s - 1e-6) { setT(0); setSel(null); } setPlaying((p) => !p); }}>{playing ? "Pause" : "Play"}</button>
          <button className="btn" onClick={stepNext}>Step</button>
          {SPEEDS.map((s) => <button key={s} className="btn" data-active={speed === s} onClick={() => setSpeed(s)}>{s}×</button>)}
          <button className="btn" onClick={() => { setPlaying(false); setT(0); setSel(null); }}>Reset</button>
          <span className="chip ml-auto" style={{ color: finalState ? "var(--ink)" : "var(--s-warn)", borderColor: finalState ? "var(--ink-4)" : "#5a4412" }}>
            {finalState ? "FINAL STATE" : playing ? "HISTORICAL REPLAY IN PROGRESS" : "HISTORICAL REPLAY PAUSED"}
          </span>
          <span className="mono text-[11px] text-ink-2">{cursor ? `SOL ${cursor.sol} · ${cursor.utc.slice(11, 19)} UTC` : `SOL ${tr.sol}`} · T+{hms(t)} / {hms(tr.duration_s)}</span>
        </div>
        <Timeline tr={tr} kept={kept} t={t} onSeek={(v) => { setPlaying(false); setT(v); }} />
        <div className="mono text-[9px] text-ink-4 flex flex-wrap gap-x-3">
          <span>HISTORICAL REPLAY — never a live NASA feed</span>
          <Link href="/final-test" className="underline">exact tables & figures: Final test →</Link>
          <a href={GITHUB_URL} className="underline" target="_blank" rel="noreferrer">source & artifacts ↗</a>
        </div>
    </div>
  );

  return (
    <div className="min-h-screen flex flex-col">
      {/* TOP BAR */}
      <header className="lg:sticky top-0 z-20 border-b border-line bg-bg/95 backdrop-blur">
        <TopBarRow label="MISSION CONTROL" />
        <div className="px-3 sm:px-4 py-1.5 border-t border-line flex flex-wrap items-center gap-2 text-[10px]">
          <span className="chip" style={{ color: "var(--ink)", borderColor: "var(--ink-4)" }}>HISTORICAL REPLAY</span>
          <span className="chip text-ink-2">CURIOSITY / NAVCAM</span>
          <span className="chip text-ink-2">SOL RANGE 950–979 · HELD-OUT TEST</span>
          <span className="chip text-ink-3">STATIC RELEASE · NO LIVE DATA</span>
          <span className="mono text-ink-4 hidden md:inline">archived (downlinked) PDS observations only — not the rover&apos;s full onboard stream</span>
        </div>
      </header>

      {/* KPI STRIP (held-out test, all 12 traverses, frozen) */}
      <div className="border-b border-line">
        <div className="px-3 sm:px-4 pt-2 flex flex-wrap items-baseline gap-2">
          <span className="label" style={{ color: "var(--ink)" }}>Held-out test · all {op.sequences} traverses</span>
          <span className="mono text-[9px] text-ink-4">frozen result at the selected policy · not the traverse on the map</span>
        </div>
        <div className="overflow-x-auto">
        <dl className="flex min-w-max">
          <Kpi k="Traverse downlink cost" v={pct(op.bytes_fraction)} sub="of SEND ALL full-quality baseline" />
          <Kpi k="Frames retained" v={mode === "SEND_ALL" ? "ALL" : FRAC_LABEL[frac]} sub={mode === "SEND_ALL" ? "full quality" : frac === "0.25" ? "primary operating point" : "context"} />
          <Kpi k="5 m coverage" v={pct(op.coverage_5m, op.coverage_5m === 1 ? 0 : 1)} sub="archived frames ≤ 5 m of a retained one" />
          <Kpi k="Max distance to retained" v={`${op.max_distance_to_kept_m_worst.toFixed(2)} m`} sub="worst traverse" />
          <Kpi k="Broken stereo pairs" v={String(op.stereo_broken)} sub={`${op.stereo_kept_full} pairs kept whole`} />
          <Kpi k="Traverse on map" v={`${ti + 1} / ${T.length}`} sub={`sol ${tr.sol} · ${tr.sequence_id}`} />
          <div className="px-4 py-2 flex items-center">
            <a href={RUN_URL} target="_blank" rel="noreferrer" className="mono text-[9px] text-ink-4 leading-tight max-w-[220px] underline">source · frozen final-test run results.json ↗</a>
          </div>
        </dl>
        </div>
      </div>

      {/* CONTROLS: policy + bandwidth */}
      <div className="border-b border-line px-3 sm:px-4 py-2 flex flex-wrap items-center gap-2">
        <span className="label">Policy</span>
        <div className="flex gap-1">
          {(["SEND_ALL", "POSITION"] as Mode[]).map((m) => (
            <button key={m} className="btn" data-active={mode === m} onClick={() => setMode(m)}>{m === "SEND_ALL" ? "Send all" : "Position"}</button>
          ))}
        </div>
        <span className="label ml-2">Retention</span>
        <div className="flex flex-wrap gap-1" role="group" aria-label="retention">
          <button className="btn" data-active={mode === "SEND_ALL"} onClick={() => setMode("SEND_ALL")}>Send all</button>
          {FRACS.map((f) => (
            <button key={f} className="btn" data-active={mode === "POSITION" && frac === f} onClick={() => { setMode("POSITION"); setFrac(f); }}>
              {FRAC_LABEL[f]}{f === "0.25" ? " · primary · held-out operating point" : ""}
            </button>
          ))}
        </div>
        <label className="mono text-[10px] text-ink-3 flex items-center gap-1 ml-auto">
          <input type="checkbox" checked={radius} onChange={(e) => setRadius(e.target.checked)} /> 5 m radius
        </label>
        <button className="btn" onClick={demo ? () => { setDemo(false); setPlaying(false); } : startDemo}>{demo ? "Exit guided demo" : "Guided demo"}</button>
      </div>
      <div className="border-b border-line px-3 sm:px-4 py-1.5 text-[11px] text-ink-3">
        <span className="label mr-2">Research question</span>
        How much full-quality traverse imagery can be removed while preserving spatial coverage and stereo integrity?
      </div>
      {demo && (
        <div className="border-b border-line px-3 sm:px-4 py-2 text-[12px]" style={{ background: "#0e1520" }} role="status">
          <span className="label mr-2" style={{ color: "var(--a-full)" }}>Guided demo</span>
          <span className="text-ink-2">{demoCallout(finalState, cursor, tr, policy, kept)}</span>
        </div>
      )}

      {/* MAIN: map · observation stream · inspector */}
      <main className="flex-1 grid gap-px bg-line lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)_minmax(0,1fr)]">
        <section className="bg-bg p-3 min-w-0">
          <PanelTitle t="Rover path · traverse map" right={`${tr.frames_count} frames · ${tr.length_m.toFixed(0)} m`} />
          {tr.sequence === MC.representative && (
            <p className="mono text-[9px] text-ink-4 mb-2">
              Example held-out traverse (shown first by a fixed rule: the longest path). This traverse is shown as an example from the held-out test set; it is not
              claimed to be statistically representative of all traverses.
            </p>
          )}
          <RouteMap tr={tr} kept={kept} seenCount={seen.length} cursor={cursor} focus={focus} policy={policy} radius={radius && mode === "POSITION"} onPick={(i) => setSel(i)} />
          <Legend />
          {/* mobile: replay controls directly under the map */}
          <div className="lg:hidden mt-3 border border-line bg-panel p-2">{replayBar}</div>
        </section>

        <section className="bg-bg p-3 min-w-0 space-y-3">
          <PanelTitle t="Observation stream" right={cursor ? `frame ${cursor.i + 1} / ${tr.frames_count}` : "—"} />
          {focus ? <ObservationCard f={focus} kept={kept.has(focus.i)} /> : <p className="text-[12px] text-ink-3">Press play.</p>}
          <div className="panel p-3 space-y-2">
            <div className="label" style={{ color: "var(--ink-2)" }}>Selected traverse · so far in the replay</div>
            <div className="h-2.5 bg-panel-2 border border-line relative"><div className="absolute inset-y-0 left-0" style={{ width: `${(used / tr.send_all.bytes) * 100}%`, background: "var(--a-full)" }} /></div>
            <Row k="downlink cost so far" v={`${kb(used)} · ${pct(used / tr.send_all.bytes)} of this traverse's SEND ALL`} />
            <Row k="5 m coverage (frames seen)" v={covSoFar == null ? "—" : covSoFar.toFixed(3)} />
            <Row k="stereo pairs at full tier (both eyes)" v={`${pairsWhole}`} />
            <Row k="stereo pairs broken (one eye full, other not)" v={`${pairsBroken}`} />
          </div>
          <div className="panel p-3 space-y-1">
            <div className="label" style={{ color: "var(--ink-2)" }}>Selected traverse · frozen result</div>
            <Row k="traverse downlink cost" v={`${pct(trM.bytes_fraction)} of its SEND ALL`} />
            <Row k="5 m coverage" v={trM.coverage_5m.toFixed(3)} />
            <Row k="max distance to retained" v={`${trM.max_distance_to_kept_m.toFixed(2)} m`} />
            <Row k="frames retained" v={`${trM.frames_retained} / ${tr.frames_count}`} />
            <Row k="broken stereo pairs" v={String(trM.stereo_broken)} />
          </div>
          <ul className="space-y-0.5 max-h-40 overflow-y-auto" aria-label="recent acquisitions">
            {[...seen].reverse().slice(0, 12).map((f) => (
              <li key={f.i}>
                <button className="w-full flex items-center gap-2 text-left mono text-[10px] px-1.5 py-0.5 hover:bg-panel-2" onClick={() => setSel(f.i)}>
                  <span style={{ color: kept.has(f.i) ? "var(--a-full)" : "var(--ink-4)" }}>{kept.has(f.i) ? "■" : "○"}</span>
                  <span className="text-ink-2">{f.acq_id}</span>
                  <span className="ml-auto" style={{ color: kept.has(f.i) ? "var(--a-full)" : "var(--ink-4)" }}>{representation(f, kept.has(f.i))}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section className="bg-bg p-3 min-w-0">
          <details open className="group">
            <summary className="cursor-pointer list-none"><PanelTitle t="Downlink decision · inspector" right={sel != null ? "selected" : "replay cursor"} /></summary>
            {focus ? <Inspector f={focus} tr={tr} mode={mode} policy={policy} kept={kept.has(focus.i)} onPick={(i) => setSel(i)} /> : <p className="text-[12px] text-ink-3">No acquisition yet.</p>}
          </details>
          <details className="mt-4 panel p-3">
            <summary className="cursor-pointer label">What did not improve the final policy</summary>
            <ul className="mt-2 space-y-1 text-[12px] text-ink-3">
              {MC.negative_results.map((n) => (
                <li key={n.name}><span className="text-ink-2">{n.name}</span> — {n.verdict === "DROP" ? "dropped" : "no measurable added value"} <span className="mono text-[10px] text-ink-4">({n.phase})</span></li>
              ))}
            </ul>
            <Link href="/research" className="mono text-[10px] underline text-ink-3">evidence →</Link>
          </details>
        </section>
      </main>

      {/* TIMELINE / REPLAY CONTROLS (desktop: pinned bottom bar) */}
      <footer className="hidden lg:block border-t border-line bg-panel px-4 py-2 sticky bottom-0">{replayBar}</footer>
      <SiteFooter />
    </div>
  );
}

function Kpi({ k, v, sub }: { k: string; v: string; sub: string }) {
  return (
    <div className="px-4 py-2 border-r border-line min-w-[150px]">
      <dt className="label">{k}</dt>
      <dd className="mono text-[22px] leading-tight text-ink">{v}</dd>
      <div className="mono text-[9px] text-ink-4">{sub}</div>
    </div>
  );
}

function PanelTitle({ t, right }: { t: string; right?: string }) {
  return (
    <div className="flex items-baseline gap-2 mb-2">
      <span className="label">{t}</span>
      {right && <span className="mono text-[10px] text-ink-4 ml-auto">{right}</span>}
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-3 text-[12px]">
      <span className="text-ink-3">{k}</span>
      <span className="mono text-ink text-right break-all">{v}</span>
    </div>
  );
}

function Legend() {
  return (
    <div className="mono text-[9px] text-ink-4 flex flex-wrap gap-x-3 gap-y-1 mt-1">
      <span><span style={{ color: "var(--a-full)" }}>■■</span> retained stereo · FULL_STEREO_PAIR (■ = FULL_MONO)</span>
      <span>○ deprioritized · THUMBNAIL_PAIR / THUMBNAIL_MONO</span>
      <span>◌ replay cursor</span>
      <span>— nearest retained frame of the selected acquisition</span>
      <span>PLACES landing-frame x/y, metres, relative to the first frame</span>
    </div>
  );
}

function RouteMap({ tr, kept, seenCount, cursor, focus, policy, radius, onPick }: {
  tr: Traverse; kept: Set<number>; seenCount: number; cursor: Frame | null; focus: Frame | null; policy: Policy | null; radius: boolean; onPick: (i: number) => void;
}) {
  const xs = tr.frames.map((f) => f.x), ys = tr.frames.map((f) => f.y);
  const pad = 7;
  const minX = Math.min(...xs) - pad, maxX = Math.max(...xs) + pad, minY = Math.min(...ys) - pad, maxY = Math.max(...ys) + pad;
  const W = maxX - minX, H = maxY - minY;
  const X = (x: number) => x - minX, Y = (y: number) => maxY - y;
  const s = Math.max(W, H) / 100; // glyph scale
  const near = focus && policy && !kept.has(focus.i) ? tr.frames[policy.nearest[focus.i][0]] : null;
  return (
    <div className="panel">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto max-h-[62vh]" role="img" aria-label={`Rover traverse ${tr.sequence}`}>
        <rect width={W} height={H} fill="var(--panel)" />
        <polyline points={tr.frames.map((f) => `${X(f.x)},${Y(f.y)}`).join(" ")} fill="none" stroke="var(--line-2)" strokeWidth={s * 0.3} />
        {radius && tr.frames.slice(0, seenCount).filter((f) => kept.has(f.i)).map((f) => (
          <circle key={`r${f.i}`} cx={X(f.x)} cy={Y(f.y)} r={RADIUS_M} fill="var(--a-full)" fillOpacity={0.06} stroke="var(--a-full)" strokeOpacity={0.3} strokeWidth={s * 0.12} />
        ))}
        {near && focus && <line x1={X(focus.x)} y1={Y(focus.y)} x2={X(near.x)} y2={Y(near.y)} stroke="var(--s-warn)" strokeWidth={s * 0.35} />}
        {tr.frames.map((f) => {
          const shown = f.i < seenCount;
          const k = kept.has(f.i);
          const cx = X(f.x), cy = Y(f.y);
          return (
            <g key={f.i} onClick={() => onPick(f.i)} style={{ cursor: "pointer" }} opacity={shown ? 1 : 0.12}>
              <circle cx={cx} cy={cy} r={s * 1.6} fill="transparent" />
              {k ? (
                f.stereo ? (
                  <>
                    <rect x={cx - s * 1.15} y={cy - s * 0.5} width={s * 1} height={s * 1} fill="var(--a-full)" />
                    <rect x={cx + s * 0.15} y={cy - s * 0.5} width={s * 1} height={s * 1} fill="var(--a-full)" />
                  </>
                ) : <rect x={cx - s * 0.5} y={cy - s * 0.5} width={s} height={s} fill="var(--a-full)" />
              ) : <circle cx={cx} cy={cy} r={s * 0.45} fill="var(--panel)" stroke="var(--ink-3)" strokeWidth={s * 0.15} />}
            </g>
          );
        })}
        {cursor && <circle cx={X(cursor.x)} cy={Y(cursor.y)} r={s * 2.4} fill="none" stroke="var(--ink)" strokeWidth={s * 0.25} />}
        {focus && focus !== cursor && <circle cx={X(focus.x)} cy={Y(focus.y)} r={s * 2.4} fill="none" stroke="var(--s-warn)" strokeWidth={s * 0.25} strokeDasharray={`${s} ${s * 0.6}`} />}
        <line x1={s * 3} y1={H - s * 3} x2={s * 3 + 10} y2={H - s * 3} stroke="var(--ink-3)" strokeWidth={s * 0.3} />
        <text x={s * 3} y={H - s * 4.2} fontSize={s * 2.4} fill="var(--ink-3)" fontFamily="monospace">10 m</text>
      </svg>
    </div>
  );
}

function Preview({ sol, id, label, tier, size }: { sol: number; id: string | null; label: string; tier: "FULL" | "THUMBNAIL" | "NONE"; size: string }) {
  const full = tier === "FULL";
  return (
    <figure className="border p-1.5 min-w-0" style={{ borderColor: full ? "var(--a-full)" : "var(--line-2)" }}>
      <div className="flex items-baseline justify-between mono text-[10px] mb-1">
        <span style={{ color: full ? "var(--a-full)" : "var(--ink-2)" }}>{label}</span>
        <span className="text-ink-4">{tier === "NONE" ? "no product" : full ? `FULL · ${size}` : "THUMBNAIL · 64×64"}</span>
      </div>
      {id ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={previewUrl(sol, id)} alt={`${label} Navcam product ${id}`} width={160} height={160}
          className="w-full h-auto bg-panel-2" style={{ imageRendering: full ? "auto" : "pixelated", aspectRatio: "1 / 1", objectFit: "contain" }} />
      ) : <div className="aspect-square bg-panel-2" />}
      <figcaption className="mono text-[8px] text-ink-4 break-all mt-1">{id ?? "—"}</figcaption>
    </figure>
  );
}

function ObservationCard({ f, kept }: { f: Frame; kept: boolean }) {
  const rep = representation(f, kept);
  const tiers = eyeTiers(f, kept);
  const eyes = eyeLabels(f);
  return (
    <div className="panel p-3 space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="chip text-ink-2">NASA PDS OBSERVATION</span>
        <span className="chip" style={{ color: kept ? "var(--a-full)" : "var(--ink-3)" }}>{rep}</span>
        <span className="chip text-ink-3">{f.stereo ? "STEREO" : "MONO"}</span>
      </div>
      <div className="mono text-[13px] text-ink break-all">{f.acq_id}</div>
      <div className={`grid gap-2 ${eyes.length === 2 ? "grid-cols-2" : "grid-cols-1 max-w-[50%]"}`}>
        {eyes.map((e) => {
          const tier = tiers[e.key] ?? "NONE";
          const id = tier === "FULL" ? productForEye(f.primary, e.key, f.stereo) : productForEye(f.thumbnails, e.key, f.stereo);
          return <Preview key={e.key} sol={f.sol} id={id} label={e.label} tier={tier} size={`${f.tier} ${f.size}`} />;
        })}
      </div>
      <div className="border border-line px-2 py-1.5 space-y-0.5" title="Image size here reflects the downlink representation shown in the replay, not a judgement of scientific importance.">
        <div className="mono text-[10px] text-ink-2">DISPLAY RESOLUTION ≠ SCIENCE VALUE</div>
        <div className="text-[11px] text-ink-3 leading-snug">Image size here reflects the downlink representation shown in the replay, not a judgement of scientific importance.</div>
        <div className="text-[11px] text-ink-3 leading-snug">Display preview: contrast-stretched for visualization; previews are not photometrically comparable across observations.</div>
      </div>
      <p className="mono text-[9px] text-ink-4">
        Shown: the representation this policy downlinks ({kept ? "full-quality product, 160 px preview" : "the rover's own 64×64 thumbnail product"}). Real PDS
        products, deterministic previews (NASA/JPL-Caltech) — presentation only, not used by any metric. <a href={PROVENANCE_URL} target="_blank" rel="noreferrer" className="underline">provenance ↗</a>
      </p>
      <Row k="sol · UTC" v={`${f.sol} · ${f.utc.replace("T", " ").slice(0, 19)}`} />
      <Row k="rover position (site/drive/pose)" v={`${f.pose.join(" / ")} · x ${f.x.toFixed(1)} m, y ${f.y.toFixed(1)} m`} />
      <Row k="estimated downlink" v={`${kb(kept ? f.full_bytes : f.thumb_bytes)} (${rep})`} />
    </div>
  );
}

function Inspector({ f, tr, mode, policy, kept, onPick }: { f: Frame; tr: Traverse; mode: Mode; policy: Policy | null; kept: boolean; onPick: (i: number) => void }) {
  const near = policy ? policy.nearest[f.i] : [f.i, 0];
  const nearF = tr.frames[near[0]];
  const step = policy ? policy.trace.findIndex(([j]) => j === f.i) : -1;
  const rep = representation(f, kept);
  const thumbRep = representation(f, false);
  const TRACE = [
    ["Navcam acquisition", `${f.stereo ? "stereo (left + right)" : "mono"} · tier ${f.tier} · ${f.size}`],
    ["Rover position", `site ${f.pose[0]} · drive ${f.pose[1]} · pose ${f.pose[2]} (PLACES ${f.places_match.replaceAll("_", " ")})`],
    ["Position sampler", mode === "SEND_ALL" ? "not applied (SEND ALL)" : step >= 0 ? `selected at step ${step + 1} of ${policy!.trace.length}` : "not selected"],
    ["Scheduler V3", kept ? `${thumbRep} first, then ${rep}` : `${thumbRep} only`],
    [rep, `${kb(kept ? f.full_bytes : f.thumb_bytes)} downlinked`],
  ];
  return (
    <div className="space-y-3 text-[12px]">
      <div className="panel p-3 space-y-1">
        <Row k="acquisition" v={f.acq_id} />
        <Row k="sol · timestamp" v={`${f.sol} · ${f.utc.replace("T", " ").slice(0, 23)} UTC`} />
        <Row k="site / drive / pose" v={f.pose.join(" / ")} />
        <Row k="sequence" v={`${tr.sequence_id} (sol ${tr.sol})`} />
        <Row k="camera" v={f.stereo ? "Navcam stereo (left + right)" : "Navcam mono"} />
        <Row k="product tier" v={`${f.tier} · ${f.size} · ${f.compression}`} />
        <Row k="estimated downlink" v={`${f.stereo ? "full pair" : "full"} ${kb(f.full_bytes)} · ${f.stereo ? "thumbnail pair" : "thumbnail"} ${kb(f.thumb_bytes)}`} />
        <Row k="POSITION retained?" v={mode === "SEND_ALL" ? "all retained (SEND ALL)" : kept ? "YES" : "NO"} />
        <Row k="representation" v={rep} />
        <Row k="nearest retained" v={kept ? "itself" : nearF.acq_id} />
        <Row k="distance" v={`${(near[1] as number).toFixed(2)} m`} />
        <Row k="stereo preserved?" v={f.stereo ? (stereoBroken(f, kept) ? "NO — one eye only" : "YES — left and right at the same tier") : "mono acquisition (not applicable)"} />
      </div>
      {!kept && <button className="btn w-full" onClick={() => onPick(nearF.i)}>Inspect nearest retained frame</button>}
      <div className="panel p-3">
        <div className="label mb-1">Why</div>
        <p className="text-ink-2 leading-snug">{decisionReason(mode, f, policy, tr.frames)}</p>
      </div>
      <div className="panel p-3">
        <div className="label mb-2">Decision trace</div>
        <ol className="space-y-1">
          {TRACE.map(([a, b], n) => (
            <li key={n}>
              <div className="mono text-[11px]" style={{ color: n === TRACE.length - 1 ? (kept ? "var(--a-full)" : "var(--ink-2)") : "var(--ink)" }}>{a.toUpperCase()}</div>
              <div className="mono text-[10px] text-ink-3">{b}</div>
              {n < TRACE.length - 1 && <div className="mono text-[10px] text-ink-4 pl-1">↓</div>}
            </li>
          ))}
        </ol>
      </div>
      <div className="panel p-3 space-y-1">
        <div className="label">Source evidence</div>
        {[...f.primary, ...f.thumbnails].map((p) => (
          <a key={p} href={pdsLabelUrl(f.sol, p)} target="_blank" rel="noreferrer" className="block mono text-[10px] text-ink-3 underline break-all">{p}.LBL (PDS label) ↗</a>
        ))}
        <a href={RUN_URL} target="_blank" rel="noreferrer" className="block mono text-[10px] text-ink-3 underline">frozen final-test run · results.json ↗</a>
        <a href={CONFIG_URL} target="_blank" rel="noreferrer" className="block mono text-[10px] text-ink-3 underline">frozen final-test config ↗</a>
        <div className="flex gap-3 pt-1">
          <Link href="/final-test" className="mono text-[10px] text-ink-3 underline">Final test →</Link>
          <Link href="/reproducibility" className="mono text-[10px] text-ink-3 underline">Reproducibility →</Link>
        </div>
      </div>
    </div>
  );
}

/** Guided-demo callout: fixed templates over the frozen state (only shown after the visitor starts the demo). */
function demoCallout(finalState: boolean, cursor: Frame | null, tr: Traverse, policy: Policy | null, kept: Set<number>): string {
  if (!cursor) return "The rover begins the traverse. Each archived Navcam acquisition appears when it was taken.";
  if (finalState && policy) {
    const m = policy.metrics;
    return `Final state for this traverse (frozen): ${(m.bytes_fraction * 100).toFixed(1)}% of its SEND ALL bytes, 5 m coverage ${m.coverage_5m.toFixed(3)}, maximum distance to a retained frame ${m.max_distance_to_kept_m.toFixed(2)} m, ${m.stereo_broken} broken stereo pairs.`;
  }
  const r = representation(cursor, kept.has(cursor.i));
  return kept.has(cursor.i)
    ? `Frame ${cursor.i + 1}/${tr.frames_count}: retained — this position extends spatial coverage, so it is sent as ${r}.`
    : `Frame ${cursor.i + 1}/${tr.frames_count}: already within ${policy ? policy.nearest[cursor.i][1].toFixed(2) : "0"} m of a retained frame — sent only as ${r}.`;
}

function Timeline({ tr, kept, t, onSeek }: { tr: Traverse; kept: Set<number>; t: number; onSeek: (v: number) => void }) {
  const D = tr.duration_s || 1;
  return (
    <div className="relative h-7">
      <div className="absolute inset-x-0 top-3 h-px bg-line-2" />
      {tr.frames.map((f) => (
        <span key={f.i} className="absolute top-1.5 w-px h-3" style={{ left: `${(f.t_s / D) * 100}%`, background: kept.has(f.i) ? "var(--a-full)" : "var(--ink-4)", opacity: f.t_s <= t ? 1 : 0.35 }} />
      ))}
      <span className="absolute top-0 w-0.5 h-6 bg-ink" style={{ left: `${(t / D) * 100}%` }} />
      <input type="range" aria-label="replay time" min={0} max={D} step={1} value={Math.min(t, D)} onChange={(e) => onSeek(Number(e.target.value))}
        className="absolute inset-0 w-full opacity-0 cursor-pointer" />
    </div>
  );
}
