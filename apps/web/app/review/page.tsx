"use client";

/* Internal review page (development only; not linked from the navigation). Two modes:
   HUMAN REVIEW (Phase 3.1, future annotation — blinding: no algorithm score or sampler category before the answer is stored)
   AI REVIEW — JEV 1.13 (Phase 3.2, read-only JEV PAIRWISE PREFERENCE; Jev is text-only and never saw the images). */
import { useCallback, useEffect, useState } from "react";
import { API, api } from "@/lib/api";

interface Side { acq_id: string; sol: number; utc: string; sequence_id: string; primary_tier: string; stereo: boolean; label: string; image_url: string }
interface Next { done: boolean; pair_id?: string; question?: string; choices?: string[]; A?: Side; B?: Side; progress: { annotated: number; total: number } }
interface Revealed { category: string; scores: Record<string, Record<string, number | null>> }

function HumanReview() {
  const [next, setNext] = useState<Next | null>(null);
  const [note, setNote] = useState("");
  const [revealed, setRevealed] = useState<Revealed | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    api<Next>("/api/review/next")
      .then((x) => alive && setNext(x))
      .catch((e) => alive && setErr(String(e.message ?? e)));
    return () => {
      alive = false;
    };
  }, [tick]);
  const load = useCallback(() => {
    setRevealed(null);
    setNote("");
    setTick((x) => x + 1);
  }, []);

  const answer = async (choice: string) => {
    if (!next?.pair_id) return;
    const r = await api<{ revealed: Revealed }>("/api/review/annotations", { method: "POST", body: JSON.stringify({ pair_id: next.pair_id, choice, note }) });
    setRevealed(r.revealed);
  };

  return (
    <section className="space-y-4">
      <div className="flex items-baseline gap-3">
        <span className="label">HUMAN REVIEW · future annotation · development split</span>
        {next && <span className="mono text-[11px] text-ink-3 ml-auto">{next.progress.annotated} / {next.progress.total} annotated</span>}
      </div>
      {err && <div className="mono text-[12px]" style={{ color: "var(--s-warn)" }}>{err}</div>}
      {next?.done && <div className="panel p-4 text-ink-2">All pairs annotated.</div>}
      {next && !next.done && next.A && next.B && (
        <>
          <h1 className="text-[20px] text-ink">{next.question}</h1>
          <div className="grid gap-4 md:grid-cols-2">
            {(["A", "B"] as const).map((k) => {
              const s = next[k]!;
              return (
                <figure key={k} className="panel">
                  <div className="flex items-center gap-2 px-3 py-2 border-b border-line">
                    <span className="mono text-[14px] text-ink">{k}</span>
                    <span className="chip text-ink-2">{s.label}</span>
                    <span className="mono text-[10px] text-ink-3 ml-auto">sol {s.sol} · {s.sequence_id} · tier {s.primary_tier}{s.stereo ? " · stereo" : ""}</span>
                  </div>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={`${API}${s.image_url}`} alt={`${k}: ${s.acq_id}`} className="w-full h-auto bg-panel-2" />
                  <figcaption className="mono text-[10px] text-ink-4 px-3 py-1.5">{s.acq_id} · {s.utc}</figcaption>
                </figure>
              );
            })}
          </div>
          {!revealed ? (
            <div className="space-y-2">
              <textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="optional note" className="w-full h-16" />
              <div className="flex gap-2">
                {next.choices!.map((c) => <button key={c} className="btn" style={{ padding: "8px 18px" }} onClick={() => answer(c)}>{c}</button>)}
              </div>
            </div>
          ) : (
            <div className="panel p-3 space-y-2">
              <div className="label">Revealed after your answer · sampler category {revealed.category}</div>
              <pre className="mono text-[11px] text-ink-2 overflow-x-auto">{JSON.stringify(revealed.scores, null, 1)}</pre>
              <button className="btn" data-active="true" onClick={load}>Next pair</button>
            </div>
          )}
        </>
      )}
    </section>
  );
}

interface JevPair { pair_id: string; A: Side; B: Side; choice: string; choice_confidence: number; reason: string; reason_confidence: number; swapped_choice_mapped_back: string | null; swap_consistent: boolean | null }
interface JevData {
  available: boolean; label: string; notice: string; not?: string[]; run_id?: string; model_requested?: string; snapshots_returned?: Record<string, number>;
  calls?: Record<string, number>; cost_usd?: number; ab_swap?: Record<string, number | number[] | null>; repeatability?: Record<string, unknown>; pairs: JevPair[];
}

function JevReview() {
  const [d, setD] = useState<JevData | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [i, setI] = useState(0);
  useEffect(() => {
    let alive = true;
    api<JevData>("/api/review/jev")
      .then((x) => alive && setD(x))
      .catch((e) => alive && setErr(String(e.message ?? e)));
    return () => {
      alive = false;
    };
  }, []);
  const p = d?.pairs[i];
  return (
    <section className="space-y-4">
      <div className="panel p-3 space-y-1" style={{ borderColor: "var(--s-warn)" }}>
        <div className="mono text-[12px] text-ink">JEV PAIRWISE PREFERENCE · experimental · text-only</div>
        <div className="text-[13px] text-ink-2">Jev receives structured metadata/features only. It does not see the images.</div>
        <div className="mono text-[10px] text-ink-3">Not human review · not expert review · not scientific ground truth · not telemetry validation. Preference alignment only; never used for tuning. Images below are shown to you, not to Jev.</div>
      </div>
      {err && <div className="mono text-[12px]" style={{ color: "var(--s-warn)" }}>{err}</div>}
      {d && !d.available && <div className="panel p-4 text-ink-2">No Jev pairwise run stored yet.</div>}
      {d?.available && (
        <div className="mono text-[11px] text-ink-3 flex flex-wrap gap-x-4">
          <span>run {d.run_id}</span>
          <span>{d.model_requested} → {Object.keys(d.snapshots_returned ?? {}).join(", ")}</span>
          <span>{d.calls?.live} live calls · ${d.cost_usd?.toFixed(4)}</span>
          <span>A/B swap consistent {String(d.ab_swap?.consistent)} / {String(d.ab_swap?.pairs_compared)}</span>
        </div>
      )}
      {p && (
        <>
          <div className="flex items-center gap-2">
            <button className="btn" onClick={() => setI((x) => Math.max(0, x - 1))} disabled={i === 0}>Prev</button>
            <span className="mono text-[12px] text-ink-2">{p.pair_id} · {i + 1} / {d!.pairs.length}</span>
            <button className="btn" onClick={() => setI((x) => Math.min(d!.pairs.length - 1, x + 1))} disabled={i === d!.pairs.length - 1}>Next</button>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            {(["A", "B"] as const).map((k) => {
              const s = p[k];
              return (
                <figure key={k} className="panel" style={p.choice === k ? { borderColor: "var(--s-ok, currentColor)" } : undefined}>
                  <div className="flex items-center gap-2 px-3 py-2 border-b border-line">
                    <span className="mono text-[14px] text-ink">{k}</span>
                    <span className="chip text-ink-2">{s.label}</span>
                    {p.choice === k && <span className="chip text-ink">JEV PREFERENCE</span>}
                    <span className="mono text-[10px] text-ink-3 ml-auto">sol {s.sol} · {s.sequence_id} · tier {s.primary_tier}{s.stereo ? " · stereo" : ""}</span>
                  </div>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={`${API}${s.image_url}`} alt={`${k}: ${s.acq_id}`} className="w-full h-auto bg-panel-2" />
                </figure>
              );
            })}
          </div>
          <div className="panel p-3 mono text-[12px] text-ink-2 space-y-1">
            <div>choice <span className="text-ink">{p.choice}</span> (confidence {p.choice_confidence.toFixed(2)}) · reason <span className="text-ink">{p.reason}</span> ({p.reason_confidence.toFixed(2)})</div>
            <div>order swapped (B shown first) → {p.swapped_choice_mapped_back ?? "—"} · {p.swap_consistent ? "position-consistent" : "position-INCONSISTENT"}</div>
          </div>
        </>
      )}
    </section>
  );
}

export default function Review() {
  const [mode, setMode] = useState<"HUMAN" | "JEV">("HUMAN");
  return (
    <main className="max-w-[1200px] mx-auto px-4 py-6 space-y-4">
      <div className="flex flex-wrap items-baseline gap-3">
        <span className="mono tracking-[0.2em] text-[13px] text-ink">DEEPSIFT</span>
        <span className="label">internal pairwise review · development split</span>
        <div className="flex gap-2 ml-auto">
          <button className="btn" data-active={mode === "HUMAN"} onClick={() => setMode("HUMAN")}>HUMAN REVIEW</button>
          <button className="btn" data-active={mode === "JEV"} onClick={() => setMode("JEV")}>AI REVIEW — JEV 1.13</button>
        </div>
      </div>
      {mode === "HUMAN" ? <HumanReview /> : <JevReview />}
    </main>
  );
}
