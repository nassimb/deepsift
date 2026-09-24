"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type Mission } from "@/lib/api";
import { pct } from "@/lib/format";

const STAGES = [
  ["RAW DATA", "REMS MODRDR + RAD RDR records from the NASA PDS"],
  ["NORMALIZE", "mission adapter → channel samples with UTC + LMST"],
  ["WINDOW", "5-min LMST-aligned windows · one per RAD integration"],
  ["FEATURES", "robust z vs nearest-local-time baseline, dips, stuck, dropout, noise, rarity"],
  ["CANDIDATE FILTER", "deterministic thresholds — most windows stop here"],
  ["DECISION ENGINE", "bounded questions → probabilities (Jev or mock)"],
  ["CONFIDENCE GATE", "auto · uncertain · rules fallback · deep escalation"],
  ["PRIORITY", "explainable utility under the active mission objective"],
  ["STORAGE + DOWNLINK", "degrade by utility-per-byte; relay passes; blackout"],
];

interface ExpSummary {
  id: string;
  engine: { name: string; is_real_model: boolean };
  trials: number;
  summary: Record<string, { available: boolean; recall?: { mean: number }; recall_high?: { mean: number } }>;
}

export default function Home() {
  const [m, setM] = useState<Mission | null>(null);
  const [x, setX] = useState<ExpSummary | null>(null);
  const [off, setOff] = useState(false);
  useEffect(() => {
    api<Mission>("/api/mission").then(setM).catch(() => setOff(true));
    api<ExpSummary[]>("/api/experiments").then((l) => setX(l[0] ?? null)).catch(() => {});
  }, []);
  const tot = m ? (m.counts as Record<string, number>) : null;

  return (
    <main className="max-w-[1100px] mx-auto px-6 py-14 space-y-16">
      <header className="space-y-5">
        <div className="mono tracking-[0.35em] text-[13px] text-ink-2">DEEPSIFT</div>
        <h1 className="text-[40px] leading-[1.1] font-medium text-ink max-w-3xl">Autonomous science triage for bandwidth-constrained missions.</h1>
        <p className="mono text-[15px] text-ink-2">Not every bit deserves the trip to Earth.</p>
        <p className="text-[15px] text-ink-2 max-w-2xl leading-relaxed">
          A research prototype that decides, onboard, which scientific data is worth downlinking — and makes every decision inspectable. It
          runs on real Mars Science Laboratory data, uses a fast decision model only for bounded judgments, and keeps thresholds, safety rules
          and final actions in deterministic code.
        </p>
        <div className="flex gap-2 pt-2">
          <Link href="/control" className="btn" data-active="true">Open Mission Control</Link>
          <Link href="/experiments" className="btn">Benchmark</Link>
          <Link href="/research" className="btn">Methodology</Link>
        </div>
        {off && <div className="mono text-[11px]" style={{ color: "var(--s-warn)" }}>Pipeline API offline — start it with `npm run demo`.</div>}
      </header>

      <section className="grid grid-cols-[180px_1fr] gap-6">
        <div className="label pt-1">The problem</div>
        <div className="text-[15px] text-ink-2 leading-relaxed space-y-3">
          <p>
            Instruments can produce far more data than a relay pass can carry. Today the choice of what to send is largely made on the ground,
            after the fact. When contact is lost, or storage is short, the spacecraft needs to decide on its own — and scientists need to be
            able to see why it decided what it did.
          </p>
          {tot && (
            <p className="mono text-[13px]">
              In this segment ({m!.short_name}, sols {m!.sols[0]}–{m!.sols.at(-1)}): {tot.samples?.toLocaleString()} channel samples →{" "}
              {tot.instrument_windows?.toLocaleString()} windows → {tot.events} candidate events. Downlink budget and storage are simulation
              parameters.
            </p>
          )}
        </div>
      </section>

      <section className="grid grid-cols-[180px_1fr] gap-6">
        <div className="label pt-1">The pipeline</div>
        <ol className="border border-line">
          {STAGES.map(([s, d], i) => (
            <li key={s} className="grid grid-cols-[32px_190px_1fr] items-baseline border-b border-line last:border-b-0 px-3 py-2">
              <span className="mono text-[10px] text-ink-4">{String(i + 1).padStart(2, "0")}</span>
              <span className="mono text-[12px] text-ink">{s}</span>
              <span className="text-[13px] text-ink-3">{d}</span>
            </li>
          ))}
        </ol>
      </section>

      <section className="grid grid-cols-[180px_1fr] gap-6">
        <div className="label pt-1">Mission replay</div>
        <div className="text-[15px] text-ink-2 leading-relaxed">
          Historical Curiosity data is replayed as though it were arriving now — labelled <span className="mono chip">MISSION REPLAY</span>, never
          as a live feed. Watch candidates appear, change the mission objective and see rankings move without re-running the pipeline, then
          cut the Earth link and watch the scheduler decide what survives.{" "}
          <Link href="/control" className="underline text-ink">Start the replay →</Link>
        </div>
      </section>

      <section className="grid grid-cols-[180px_1fr] gap-6">
        <div className="label pt-1">Benchmark</div>
        <div className="text-[15px] text-ink-2 leading-relaxed space-y-3">
          <p>
            Random sampling, threshold rules, statistical anomaly detection, the decision engine, and engine + deep analysis run on the same
            data under the same byte budget, scored against documented events and clearly tagged synthetic injections. The harness is built
            so that the model can lose to simple rules.
          </p>
          {x && (
            <div className="border border-line p-3 mono text-[12px] space-y-1">
              <div className="text-ink-3">latest stored run {x.id} · {x.trials} trials · engine {x.engine.name}{x.engine.is_real_model ? "" : " (heuristic stand-in, not Jev)"}</div>
              {Object.entries(x.summary).map(([k, v]) => (
                <div key={k} className="flex gap-4">
                  <span className="w-44 text-ink-2">{k}</span>
                  {v.available ? (
                    <span>recall {pct(v.recall?.mean, 0)} · high-severity recall {pct(v.recall_high?.mean, 0)}</span>
                  ) : (
                    <span className="text-ink-4">unavailable</span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </section>

      <section className="grid grid-cols-[180px_1fr] gap-6">
        <div className="label pt-1">How it works</div>
        <div className="grid grid-cols-2 gap-4 text-[13px] text-ink-2 leading-relaxed">
          <p><span className="text-ink">Decisions, not prose.</span> The engine answers five bounded questions (science value, event type, downlink action, needs deep analysis, instrument failure) and returns probabilities. No text is generated to explain a decision.</p>
          <p><span className="text-ink">Code owns the action.</span> A deterministic utility — science value, mission relevance, anomaly strength, novelty, confidence — picks FULL / COMPRESS / SUMMARY / DISCARD. The model can raise an action by one level at most.</p>
          <p><span className="text-ink">Confidence gating.</span> Below configurable thresholds the engine&apos;s answer is set aside for deterministic rules or escalated to a deep model — never treated as truth.</p>
          <p><span className="text-ink">Computed counterfactuals.</span> “What would change this to COMPRESS?” is answered by solving and re-running the scoring code, then shown with the exact input change.</p>
        </div>
      </section>

      <section className="grid grid-cols-[180px_1fr] gap-6">
        <div className="label pt-1">Technical architecture</div>
        <div className="text-[13px] text-ink-2 leading-relaxed space-y-2">
          <p className="mono text-[12px]">Python 3.12 · Polars · DuckDB · FastAPI — Next.js · TypeScript · Tailwind — TypeSafe SDK (Jev) · Anthropic SDK (optional deep analysis)</p>
          <p>A <span className="mono">MissionAdapter</span> interface isolates everything Curiosity-specific; the <span className="mono">DecisionEngine</span> and <span className="mono">DeepAnalysisProvider</span> abstractions isolate every model. Every decision is written to a DuckDB audit log with the event, engine answers, objective and config version needed to reproduce it.</p>
          <p className="mono text-[11px] text-ink-3">docs/architecture.md · docs/research-methodology.md</p>
        </div>
      </section>

      <section className="grid grid-cols-[180px_1fr] gap-6">
        <div className="label pt-1">Open source</div>
        <div className="text-[13px] text-ink-2 leading-relaxed">
          One command runs the whole demo locally (<span className="mono">npm run demo</span>). No API key is needed: without one the decision
          engine is a clearly labelled mock. Data: NASA PDS Atmospheres Node (REMS) and PPI Node (RAD).{" "}
          {m && <span className="mono text-[11px] text-ink-3">Current source: {m.data_source} · {m.products.length} products</span>}
        </div>
      </section>

      <footer className="border-t border-line pt-4 text-[11px] text-ink-4 leading-relaxed">
        Research prototype. Not validated by NASA or JPL, not flight software, and not a source of scientific findings. Metrics labelled
        “proxy” do not measure true scientific value.
      </footer>
    </main>
  );
}
