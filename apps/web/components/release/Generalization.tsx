import { PERIOD_LABEL, REL } from "@/lib/release";

type Metric = { key: "bytes_fraction" | "coverage_5m" | "max_distance_to_kept_m_worst" | "stereo_broken"; title: string; limit: string; max: number; lim: number | null; fmt: (v: number) => string };

const METRICS: Metric[] = [
  { key: "bytes_fraction", title: "Bytes retained", limit: "≤ 0.35", max: 0.4, lim: 0.35, fmt: (v) => v.toFixed(3) },
  { key: "coverage_5m", title: "5 m spatial coverage", limit: "≥ 0.90", max: 1, lim: 0.9, fmt: (v) => v.toFixed(3) },
  { key: "max_distance_to_kept_m_worst", title: "Largest distance to a kept frame", limit: "≤ 10 m", max: 11, lim: 10, fmt: (v) => `${v.toFixed(2)} m` },
  { key: "stereo_broken", title: "Broken stereo pairs", limit: "= 0", max: 1, lim: null, fmt: (v) => String(v) },
];

/** Four non-pooled periods for Scheduler V3 + POSITION at 1/4 retention (small multiples, one row per metric). */
export function FourPeriod() {
  return (
    <div className="space-y-5">
      <div className="grid gap-4 md:grid-cols-2">
        {METRICS.map((m) => (
          <div key={m.key} className="panel p-4">
            <div className="flex items-baseline justify-between mb-3">
              <span className="text-[13px] text-ink">{m.title}</span>
              <span className="mono text-[10px] text-ink-3">final-test criterion {m.limit}</span>
            </div>
            <div className="space-y-2">
              {REL.periods.map((p) => {
                const v = p.position[m.key];
                const w = m.key === "stereo_broken" ? 0 : Math.min(1, v / m.max);
                const test = p.id === "test";
                return (
                  <div key={p.id} className="grid grid-cols-[112px_1fr_70px] items-center gap-3">
                    <span className="mono text-[11px]" style={{ color: test ? "var(--ink)" : "var(--ink-3)" }}>
                      {PERIOD_LABEL[p.id]}
                      <span className="block text-[9px] text-ink-4">sols {p.sols[0]}–{p.sols[1]}</span>
                    </span>
                    <div className="relative h-3 bg-panel-2 border border-line">
                      <div className="absolute inset-y-0 left-0" style={{ width: `${w * 100}%`, background: test ? "var(--a-full)" : "var(--ink-4)" }} />
                      {m.lim !== null && <div className="absolute inset-y-[-3px] w-px" style={{ left: `${(m.lim / m.max) * 100}%`, background: "var(--ink-2)" }} title={`limit ${m.limit}`} />}
                    </div>
                    <span className="mono text-[12px] text-right" style={{ color: test ? "var(--ink)" : "var(--ink-2)" }}>{m.fmt(v)}</span>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
      <p className="mono text-[10px] text-ink-4">
        Scheduler V3 + POSITION at 1/4 of traverse frames. Periods are reported separately, never pooled. The vertical tick is the final-test limit; it was
        pre-registered for the test only. Development, validation 1 and validation 2 were recomputed by the frozen final-test runner. Source ·{" "}
        {REL.sources.final} → four_period
      </p>
    </div>
  );
}

/** Embedding gain over POSITION per period with 95 % CI, against the pre-registered 0.020 threshold. */
export function EmbeddingGain() {
  const lo = -0.01, hi = 0.08;
  const x = (v: number) => ((v - lo) / (hi - lo)) * 100;
  return (
    <div className="panel p-4 space-y-3">
      <div className="flex items-baseline justify-between">
        <span className="text-[13px] text-ink">Visual-change gain of POSITION + EMBEDDING over POSITION (1/4 retention)</span>
        <span className="mono text-[10px] text-ink-3">95 % sequence bootstrap</span>
      </div>
      <div className="relative">
        {REL.periods.map((p) => {
          const g = p.embedding_gain;
          return (
            <div key={p.id} className="grid grid-cols-[112px_1fr_64px] items-center gap-3 h-8">
              <span className="mono text-[11px] text-ink-3">{PERIOD_LABEL[p.id]}</span>
              <div className="relative h-full">
                <div className="absolute top-1/2 h-px" style={{ left: `${x(g.visual_change_gain_95ci[0])}%`, width: `${x(g.visual_change_gain_95ci[1]) - x(g.visual_change_gain_95ci[0])}%`, background: "var(--ink-2)" }} />
                <div className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-2.5 h-2.5" style={{ left: `${x(g.visual_change_gain)}%`, background: p.id === "development" ? "var(--s-serious)" : "var(--a-full)", borderRadius: p.id === "test" ? 0 : 10 }} />
                <div className="absolute inset-y-0 w-px" style={{ left: `${x(0)}%`, background: "var(--ink-4)" }} />
                <div className="absolute inset-y-0 w-px border-l border-dashed" style={{ left: `${x(0.02)}%`, borderColor: "var(--ink-2)" }} />
              </div>
              <span className="mono text-[12px] text-right text-ink">{g.visual_change_gain >= 0 ? "+" : ""}{g.visual_change_gain.toFixed(3)}</span>
            </div>
          );
        })}
      </div>
      <p className="text-[12px] text-ink-3">
        Dashed line: the pre-registered “meaningful” threshold (+0.020). The development gain did not persist on either validation period or on the held-out
        test, so embeddings get no credit in the primary claim. Visual-change coverage is a MobileNetV2 proxy, not a scientific judgement.
      </p>
    </div>
  );
}
