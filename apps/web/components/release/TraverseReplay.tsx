"use client";

/* FINAL TEST REPLAY — historical replay of the held-out Curiosity Navcam traverses (sols 950–979).
   Geometry and the frames POSITION keeps come from data/release.json (re-derived with the frozen code and asserted equal to
   the stored final-test rows). The playback only accumulates stored per-frame bytes; the end-of-traverse numbers shown in the
   "stored result" panel are the frozen per-sequence metrics, not recomputed here. SEND ALL and POSITION only. */
import { useEffect, useMemo, useState } from "react";
import { REL, type ReplaySequence } from "@/lib/release";

type Mode = "SEND_ALL" | "POSITION";
type Frac = "0.25" | "0.5" | "0.125";
const FRAC_LABEL: Record<Frac, string> = { "0.25": "1/4 · primary", "0.5": "1/2 · context", "0.125": "1/8 · context" };

export function TraverseReplay() {
  const seqs = REL.replay.sequences;
  const [name, setName] = useState(REL.replay.representative);
  const [mode, setMode] = useState<Mode>("POSITION");
  const [frac, setFrac] = useState<Frac>("0.25");
  const [t, setT] = useState(() => (seqs.find((x) => x.sequence === REL.replay.representative) ?? seqs[0]).points.length);
  const [playing, setPlaying] = useState(false);
  const s = seqs.find((x) => x.sequence === name) ?? seqs[0];
  const n = s.points.length;
  const step = playing && t < n;

  useEffect(() => {
    if (!step) return;
    const id = setInterval(() => setT((v) => (v >= n ? v : v + 1)), 180);
    return () => clearInterval(id);
  }, [step, n]);

  const kept = useMemo(() => new Set(mode === "SEND_ALL" ? s.points.map((_, i) => i) : s.kept_position[frac]), [s, mode, frac]);
  const shown = Math.min(t, n);
  const sendAllTotal = s.points.reduce((a, p) => a + p.full_bytes, 0);
  let sent = 0, full = 0, thumbs = 0, pairs = 0, broken = 0;
  for (let i = 0; i < shown; i++) {
    const p = s.points[i];
    if (kept.has(i)) { sent += p.full_bytes ?? 0; full++; if (p.stereo) { if (p.full_bytes == null) broken++; else pairs++; } } else { sent += p.thumb_bytes; thumbs++; }
  }
  const covSoFar = useMemo(() => {
    if (shown === 0) return null;
    const k = [...kept];
    let c = 0;
    for (let i = 0; i < shown; i++) {
      const p = s.points[i];
      if (k.some((j) => Math.hypot(s.points[j].x - p.x, s.points[j].y - p.y) <= 5)) c++;
    }
    return c / shown;
  }, [kept, shown, s]);
  const stored = mode === "SEND_ALL" ? null : s.metrics[frac];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="chip" style={{ color: "var(--ink)", borderColor: "var(--ink-4)" }}>HISTORICAL REPLAY</span>
        <span className="mono text-[11px] text-ink-2">Curiosity Navcam · sols 950–979 · held-out test</span>
        <span className="mono text-[10px] text-ink-4">archived (downlinked) frames only — not the rover’s full onboard stream</span>
      </div>
      <div className="panel p-3 flex flex-wrap items-center gap-3">
        <label className="mono text-[11px] text-ink-3">traverse
          <select className="ml-2 bg-panel-2 border border-line text-ink mono text-[11px] px-2 py-1" value={name}
            onChange={(e) => { const q = seqs.find((x) => x.sequence === e.target.value); setName(e.target.value); setT(q ? q.points.length : 0); setPlaying(false); }}>
            {seqs.map((q) => <option key={q.sequence} value={q.sequence}>sol {q.sequence} · {q.frames} frames · {q.length_m.toFixed(0)} m{q.sequence === REL.replay.representative ? " · representative" : ""}</option>)}
          </select>
        </label>
        <div className="flex gap-1">
          {(["SEND_ALL", "POSITION"] as Mode[]).map((m) => (
            <button key={m} className="btn" data-active={mode === m} onClick={() => setMode(m)}>{m === "SEND_ALL" ? "SEND ALL" : "POSITION"}</button>
          ))}
        </div>
        {mode === "POSITION" && (
          <div className="flex gap-1">
            {(["0.25", "0.5", "0.125"] as Frac[]).map((f) => <button key={f} className="btn" data-active={frac === f} onClick={() => setFrac(f)}>{FRAC_LABEL[f]}</button>)}
          </div>
        )}
        <div className="flex gap-1 ml-auto">
          <button className="btn" data-active={playing} onClick={() => { if (t >= n) setT(0); setPlaying((p) => !p); }}>{playing && t < n ? "❚❚ pause" : "▶ play"}</button>
          <button className="btn" onClick={() => { setPlaying(false); setT(n); }}>show all</button>
          <button className="btn" onClick={() => { setPlaying(false); setT(0); }}>reset</button>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <RouteMap s={s} kept={kept} shown={shown} showRadius={mode === "POSITION"} />
        <div className="space-y-3">
          <div className="panel p-3 space-y-2">
            <div className="label">Bandwidth meter</div>
            <div className="h-3 bg-panel-2 border border-line relative">
              <div className="absolute inset-y-0 left-0" style={{ width: `${(sent / sendAllTotal) * 100}%`, background: "var(--a-full)" }} />
            </div>
            <div className="mono text-[11px] text-ink-2">{(sent / 1e3).toFixed(0)} kB sent · {((sent / sendAllTotal) * 100).toFixed(1)}% of SEND ALL for this traverse</div>
            <div className="mono text-[10px] text-ink-4">full-quality stereo pairs {full} · thumbnail pairs {thumbs} · frame {shown}/{n}</div>
          </div>
          <div className="panel p-3 space-y-1">
            <div className="label">So far in the replay</div>
            <Line k="5 m coverage (frames seen)" v={covSoFar === null ? "—" : covSoFar.toFixed(3)} />
            <Line k="stereo pairs sent whole" v={`${pairs}`} />
            <Line k="stereo pairs broken" v={String(broken)} />
          </div>
          <div className="panel p-3 space-y-1">
            <div className="label">Stored final-test result for this traverse</div>
            {stored ? (
              <>
                <Line k="bytes / SEND ALL" v={(stored.bytes / stored.bytes_send_all).toFixed(3)} />
                <Line k="5 m coverage" v={stored.position_coverage.toFixed(3)} />
                <Line k="largest distance to kept" v={`${stored.max_distance_to_kept_m.toFixed(2)} m`} />
                <Line k="frames kept" v={`${stored.frames_retained} / ${s.frames}`} />
                <Line k="broken stereo pairs" v={String(stored.stereo_broken)} />
                <div className="mono text-[10px] text-ink-4 pt-1 break-all">source · {REL.sources.final} → traverse.rows ({s.sequence}, {frac}, METADATA_POSITION)</div>
              </>
            ) : (
              <p className="text-[12px] text-ink-3">SEND ALL downlinks every archived frame at full quality: 1.000 of bytes, coverage 1.000, distance 0 m.</p>
            )}
          </div>
          <p className="text-[11px] text-ink-3 leading-snug">
            Hollow circles are archived frames sent only as a thumbnail pair; filled squares are kept at full quality. Shaded discs show the 5 m radius around
            kept frames; thin lines join each thumbnail-only frame to its nearest kept frame — the distance the headline metric bounds.
          </p>
        </div>
      </div>
    </div>
  );
}

function Line({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between text-[12px]">
      <span className="text-ink-3">{k}</span>
      <span className="mono text-ink">{v}</span>
    </div>
  );
}

function RouteMap({ s, kept, shown, showRadius }: { s: ReplaySequence; kept: Set<number>; shown: number; showRadius: boolean }) {
  const xs = s.points.map((p) => p.x), ys = s.points.map((p) => p.y);
  const pad = 8;
  const minX = Math.min(...xs) - pad, maxX = Math.max(...xs) + pad, minY = Math.min(...ys) - pad, maxY = Math.max(...ys) + pad;
  const W = maxX - minX, Hh = maxY - minY;
  const X = (x: number) => x - minX, Y = (y: number) => maxY - y;
  const keptIdx = [...kept];
  const nearest = (i: number) => keptIdx.reduce((b, j) => (Math.hypot(xs[j] - xs[i], ys[j] - ys[i]) < Math.hypot(xs[b] - xs[i], ys[b] - ys[i]) ? j : b), keptIdx[0]);
  return (
    <div className="panel p-2">
      <svg viewBox={`0 0 ${W} ${Hh}`} className="w-full h-auto max-h-[560px]" role="img" aria-label={`Rover traverse ${s.sequence}`}>
        <rect x={0} y={0} width={W} height={Hh} fill="var(--panel)" />
        <polyline points={s.points.map((p) => `${X(p.x)},${Y(p.y)}`).join(" ")} fill="none" stroke="var(--line-2)" strokeWidth={0.4} />
        {showRadius && keptIdx.filter((j) => j < shown).map((j) => (
          <circle key={`r${j}`} cx={X(xs[j])} cy={Y(ys[j])} r={5} fill="var(--a-full)" fillOpacity={0.07} stroke="var(--a-full)" strokeOpacity={0.35} strokeWidth={0.15} />
        ))}
        {showRadius && s.points.map((p, i) => {
          if (i >= shown || kept.has(i)) return null;
          const j = nearest(i);
          return <line key={`n${i}`} x1={X(p.x)} y1={Y(p.y)} x2={X(xs[j])} y2={Y(ys[j])} stroke="var(--s-warn)" strokeWidth={0.2} />;
        })}
        {s.points.map((p, i) => i < shown && !kept.has(i) && (
          <circle key={`f${i}`} cx={X(p.x)} cy={Y(p.y)} r={0.55} fill="var(--panel)" stroke="var(--ink-3)" strokeWidth={0.2} />
        ))}
        {s.points.map((p, i) => i < shown && kept.has(i) && (
          <rect key={`k${i}`} x={X(p.x) - 0.7} y={Y(p.y) - 0.7} width={1.4} height={1.4} fill="var(--a-full)" />
        ))}
        {shown > 0 && shown <= s.points.length && (
          <circle cx={X(xs[shown - 1])} cy={Y(ys[shown - 1])} r={1.6} fill="none" stroke="var(--ink)" strokeWidth={0.25} />
        )}
        <g>
          <line x1={2} y1={Hh - 3} x2={12} y2={Hh - 3} stroke="var(--ink-3)" strokeWidth={0.3} />
          <text x={2} y={Hh - 4} fontSize={2} fill="var(--ink-3)" fontFamily="monospace">10 m</text>
        </g>
      </svg>
      <div className="mono text-[10px] text-ink-4 px-1 pt-1">PLACES landing-frame positions relative to the first frame (m) · sol {s.sol} · {s.frames} frames · path {s.length_m.toFixed(0)} m</div>
    </div>
  );
}
