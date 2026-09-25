"use client";

/* Internal Phase 3.1 review page (development only; not linked from the navigation).
   Blinding: no algorithm score or sampler category is shown until the answer has been stored. */
import { useCallback, useEffect, useState } from "react";
import { API, api } from "@/lib/api";

interface Side { acq_id: string; sol: number; utc: string; sequence_id: string; primary_tier: string; stereo: boolean; label: string; image_url: string }
interface Next { done: boolean; pair_id?: string; question?: string; choices?: string[]; A?: Side; B?: Side; progress: { annotated: number; total: number } }
interface Revealed { category: string; scores: Record<string, Record<string, number | null>> }

export default function Review() {
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
    <main className="max-w-[1200px] mx-auto px-4 py-6 space-y-4">
      <div className="flex items-baseline gap-3">
        <span className="mono tracking-[0.2em] text-[13px] text-ink">DEEPSIFT</span>
        <span className="label">Phase 3.1 · internal pairwise review · development split</span>
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
    </main>
  );
}
