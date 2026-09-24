"use client";

import { useEffect, useState } from "react";
import { Inspector } from "@/components/Inspector";
import { Section } from "@/components/Kpi";
import { Nav, SourceBadges, useStatus } from "@/components/Nav";
import { API, api } from "@/lib/api";
import { bytes, num, pct } from "@/lib/format";

interface RunInfo {
  run_id: string;
  split: string;
  started_at: string;
  git: { commit: string | null; dirty: boolean } | null;
  config_version: string;
  jev_status: string;
  engines: string[];
  figures: string[];
}
type Stat = number | { mean: number | null; std: number | null; ci95: [number, number] | null } | null;
interface Point {
  labels?: Stat;
  strict_recall?: Stat;
  tolerant_recall?: Stat;
  high_tolerant_recall?: Stat;
  coverage?: Stat;
  precision_lower_bound?: Stat;
  downlink_bytes?: Stat;
  false_positive_units?: Stat;
  value_per_mb_proxy?: Stat;
}
interface Results {
  run_id: string;
  split: string;
  jev_status: string;
  real_reference: Record<string, Point | null>;
  synthetic_reference: Record<string, Point | null>;
  calibration: Record<string, { ece: number | null; n: number; overall_accuracy?: number; mean_confidence?: number }>;
  latency: Record<string, { n: number; p50?: number; p90?: number; p95?: number; p99?: number; max?: number }>;
  gating: Record<string, { auto: number; uncertain: number; high_tolerant_recall: number; precision_lower_bound: number; would_escalate: number; events: number; downlink_bytes: number; pareto: boolean }[]>;
  jev_usage: { calls: number; errors: number; cost_usd: number; input_tokens: number };
}

const TABS = ["Benchmark", "Failure analysis", "Calibration", "Run manifest"] as const;

function v(x: Stat | undefined): number | null {
  if (x == null) return null;
  return typeof x === "number" ? x : x.mean;
}
function civ(x: Stat | undefined): string {
  if (x == null || typeof x === "number" || !x.ci95) return "";
  return ` [${(x.ci95[0] * 100).toFixed(0)}–${(x.ci95[1] * 100).toFixed(0)}]`;
}

function TradeoffTable({ title, rows, note }: { title: string; rows: Record<string, Point | null>; note: string }) {
  const names = Object.keys(rows).filter((k) => rows[k]);
  const cols: [keyof Point, string, (x: number | null) => string][] = [
    ["labels", "labels", (x) => (x == null ? "—" : x.toFixed(0))],
    ["strict_recall", "strict recall", (x) => pct(x, 0)],
    ["tolerant_recall", "tolerant recall", (x) => pct(x, 0)],
    ["high_tolerant_recall", "high-sev recall", (x) => pct(x, 0)],
    ["coverage", "coverage", (x) => pct(x, 1)],
    ["precision_lower_bound", "precision (lb)", (x) => pct(x, 1)],
    ["false_positive_units", "unlabelled kept", (x) => (x == null ? "—" : x.toFixed(0))],
    ["downlink_bytes", "downlinked", (x) => bytes(x)],
    ["value_per_mb_proxy", "value/MB (proxy)", (x) => num(x, 1)],
  ];
  return (
    <Section title={title}>
      <div className="overflow-x-auto">
        <table className="w-full mono text-[11px]">
          <thead className="text-ink-3">
            <tr className="text-left border-b border-line">
              <th className="font-normal px-2 py-1.5">strategy</th>
              {cols.map(([, h]) => (
                <th key={h} className="font-normal px-2 whitespace-nowrap text-right">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {names.map((n) => (
              <tr key={n} className="border-b border-line" style={{ color: n.startsWith("ORACLE") ? "var(--ink-3)" : "var(--ink)" }}>
                <td className="px-2 py-1 whitespace-nowrap">{n}</td>
                {cols.map(([k, h, f]) => (
                  <td key={h} className="px-2 text-right whitespace-nowrap">
                    {f(v(rows[n]?.[k]))}
                    <span className="text-ink-4">{k.includes("recall") ? civ(rows[n]?.[k]) : ""}</span>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="px-2 py-1.5 mono text-[10px] text-ink-4">{note}</div>
    </Section>
  );
}

export default function StudyPage() {
  const { status } = useStatus();
  const [runs, setRuns] = useState<RunInfo[]>([]);
  const [rid, setRid] = useState<string | null>(null);
  const [tab, setTab] = useState<(typeof TABS)[number]>("Benchmark");
  const [res, setRes] = useState<Results | null>(null);
  const [fail, setFail] = useState<Record<string, Record<string, unknown>[]> | null>(null);
  const [man, setMan] = useState<Record<string, unknown> | null>(null);
  const [sel, setSel] = useState<string | null>(null);

  useEffect(() => {
    api<RunInfo[]>("/api/runs").then((r) => {
      setRuns(r);
      if (r[0]) setRid(r[0].run_id);
    });
  }, []);
  useEffect(() => {
    if (!rid) return;
    let alive = true;
    Promise.all([api<Results>(`/api/runs/${rid}/results`), api<Record<string, Record<string, unknown>[]>>(`/api/runs/${rid}/failures`), api<Record<string, unknown>>(`/api/runs/${rid}/manifest`)]).then(
      ([r, f, m]) => {
        if (!alive) return;
        setRes(r);
        setFail(f);
        setMan(m);
      },
    );
    return () => {
      alive = false;
    };
  }, [rid]);
  const run = runs.find((r) => r.run_id === rid);

  return (
    <div className="h-screen flex flex-col">
      <Nav right={<SourceBadges status={status} replay={false} />} />
      <div className="flex items-center gap-3 px-4 h-11 border-b border-line">
        <span className="label">Phase-2 study</span>
        <select value={rid ?? ""} onChange={(e) => setRid(e.target.value)}>
          {runs.map((r) => (
            <option key={r.run_id} value={r.run_id}>
              {r.run_id} · {r.split.toUpperCase()} · {r.jev_status.startsWith("enabled") ? "Jev" : "no Jev"}
            </option>
          ))}
        </select>
        <div className="flex gap-1 ml-2">
          {TABS.map((t) => (
            <button key={t} className="btn" data-active={tab === t} onClick={() => setTab(t)}>
              {t}
            </button>
          ))}
        </div>
        {run && (
          <span className="mono text-[10px] text-ink-3 ml-auto">
            {run.split.toUpperCase()} · git {run.git?.commit?.slice(0, 8)}
            {run.git?.dirty ? "-dirty" : ""} · cfg {run.config_version} · {run.jev_status}
          </span>
        )}
      </div>
      {!runs.length && <div className="p-4 text-ink-3 text-[12px]">No study runs yet: uv run python scripts/run_study.py --split validation</div>}

      <div className="flex-1 min-h-0 grid grid-cols-[minmax(0,1fr)_380px] gap-px bg-line">
        <div className="bg-bg p-3 space-y-3 overflow-y-auto">
          {tab === "Benchmark" && res && (
            <>
              <div className="panel p-2 mono text-[11px] text-ink-2">
                Measured trade-offs at the reference budget (0.5 % of generated raw bytes). No strategy is ranked — pick the operating point that matters.
                Documented events and synthetic injections are never pooled. RANDOM shows mean over 30 seeds [95 % CI].
                {!res.jev_status.startsWith("enabled") && <span style={{ color: "var(--s-warn)" }}> Jev: {res.jev_status}.</span>}
              </div>
              <TradeoffTable title="Documented events (real)" rows={res.real_reference} note="precision (lb) is a lower bound: unlabelled real phenomena exist. Coverage = fraction of the labelled event's raw data covered by retained products." />
              <TradeoffTable title="Synthetic stress test" rows={res.synthetic_reference} note="injections placed in scored sols only, magnitudes in σ of the local background; ORACLE — NOT DEPLOYABLE — is a label-aware upper bound." />
              <Section title="Figures">
                <div className="grid grid-cols-2 gap-2 p-2">
                  {run?.figures.map((f) => (
                    <a key={f} href={`${API}/api/runs/${rid}/figures/${f}`} target="_blank" rel="noreferrer" className="border border-line block">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={`${API}/api/runs/${rid}/figures/${f}`} alt={f} className="w-full bg-white" />
                      <div className="mono text-[10px] text-ink-3 px-1 py-0.5">{f}</div>
                    </a>
                  ))}
                  {!run?.figures.length && <div className="mono text-[11px] text-ink-3">no figures — uv run python scripts/make_figures.py {rid}</div>}
                </div>
              </Section>
            </>
          )}

          {tab === "Failure analysis" && fail && (
            <>
              <div className="panel p-2 mono text-[11px] text-ink-2">Examples collected automatically at the reference budget. Click an example with an event to open it in the Event Inspector (deterministic rules view; the engine&apos;s answers are listed in the row).</div>
              {Object.entries(fail)
                .sort()
                .map(([cat, items]) => (
                  <Section key={cat} title={`${cat} · ${items.length}${items.length >= 40 ? "+ (capped)" : ""}`}>
                    <table className="w-full mono text-[10px]">
                      <tbody>
                        {items.slice(0, 12).map((x, i) => (
                          <tr
                            key={i}
                            className={`border-b border-line ${x.has_event ? "cursor-pointer hover:bg-panel-2" : ""}`}
                            onClick={() => x.has_event && setSel(String(x.event_id))}
                          >
                            <td className="px-2 py-0.5 text-ink-3">{String(x.dataset)}</td>
                            <td className="px-2 text-ink-2">{String(x.segment)}</td>
                            <td className="px-2">{String(x.label ?? "")}</td>
                            <td className="px-2 text-ink-3">{String(x.subtype ?? x.expected_type ?? "")} {x.bucket ? `· ${x.bucket}` : ""}</td>
                            <td className="px-2 text-ink">{String(x.event_id ?? "—")}</td>
                            <td className="px-2 text-ink-3 truncate max-w-[340px]">
                              {x.engine_decision ? JSON.stringify(x.engine_decision) : String(x.note ?? "")}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </Section>
                ))}
            </>
          )}

          {tab === "Calibration" && res && (
            <>
              <div className="panel p-2 mono text-[11px] text-ink-2">
                Reliability of MODEL CONFIDENCE — not the probability of scientific truth. &quot;importance&quot; = P(science value ≥ medium) vs overlap with a label (a lower
                bound on accuracy, since unlabelled real phenomena exist). &quot;event_type&quot; = type confidence vs the injected type, on events overlapping exactly one injection.
              </div>
              <Section title="Expected calibration error">
                <table className="w-full mono text-[11px]">
                  <thead className="text-ink-3">
                    <tr className="text-left border-b border-line">
                      {["series", "n", "ECE", "mean confidence", "observed agreement"].map((h) => (
                        <th key={h} className="font-normal px-2 py-1">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(res.calibration).map(([k, c]) => (
                      <tr key={k} className="border-b border-line">
                        <td className="px-2 py-1">{k}{k.includes(":MOCK:") ? " (mock heuristic — not Jev)" : ""}</td>
                        <td className="px-2">{c.n}</td>
                        <td className="px-2">{num(c.ece, 3)}</td>
                        <td className="px-2">{pct(c.mean_confidence, 1)}</td>
                        <td className="px-2">{pct(c.overall_accuracy, 1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Section>
              {run?.figures.includes("confidence_calibration.png") && (
                /* eslint-disable-next-line @next/next/no-img-element */
                <img src={`${API}/api/runs/${rid}/figures/confidence_calibration.png`} alt="reliability diagram" className="w-full bg-white border border-line" />
              )}
              <Section title="Gating threshold sweep (Pareto-optimal points marked ●)">
                <div className="p-2 space-y-3">
                  {Object.entries(res.gating).map(([k, pts]) => (
                    <div key={k}>
                      <div className="label mb-1">{k}</div>
                      <table className="w-full mono text-[10px]">
                        <tbody>
                          {pts.map((p, i) => (
                            <tr key={i} className="border-b border-line" style={{ color: p.pareto ? "var(--ink)" : "var(--ink-4)" }}>
                              <td className="px-2">{p.pareto ? "●" : ""}</td>
                              <td className="px-2">auto ≥ {p.auto}</td>
                              <td className="px-2">uncertain ≥ {p.uncertain}</td>
                              <td className="px-2">high-sev recall {pct(p.high_tolerant_recall, 0)}</td>
                              <td className="px-2">precision (lb) {pct(p.precision_lower_bound, 1)}</td>
                              <td className="px-2">would escalate {p.would_escalate}/{p.events}</td>
                              <td className="px-2">{bytes(p.downlink_bytes)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ))}
                </div>
              </Section>
            </>
          )}

          {tab === "Run manifest" && man && (
            <Section title="manifest.json (per-file hashes omitted here; full file in artifacts/runs/<run_id>/)">
              <pre className="mono text-[10px] text-ink-2 p-2 whitespace-pre-wrap">{JSON.stringify(man, null, 1)}</pre>
            </Section>
          )}
        </div>
        <div className="bg-panel min-h-0">
          {sel && rid ? (
            <Inspector key={sel} id={sel} detailUrl={`/api/runs/${rid}/events/${encodeURIComponent(sel)}`} onClose={() => setSel(null)} />
          ) : (
            <div className="p-4 label">Select a failure example to inspect it.</div>
          )}
        </div>
      </div>
    </div>
  );
}
