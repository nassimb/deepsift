import { notFound } from "next/navigation";
import { PUBLIC_RELEASE } from "@/lib/mode";
import Link from "next/link";
import { BenchmarkChart } from "@/components/home/BenchmarkChart";
import { BlackoutDemo } from "@/components/home/BlackoutDemo";
import { EventCard } from "@/components/home/EventCard";
import { HeroFunnel } from "@/components/home/HeroFunnel";
import { ReplayPreview } from "@/components/home/ReplayPreview";
import { StrategyTable } from "@/components/home/StrategyTable";
import { SurvivalExplorer } from "@/components/home/SurvivalExplorer";
import { HOME, mb, p0 } from "@/lib/home";

// Everything below is read from data/home-summary.json (scripts/build_home_summary.py): measured values only.
const bm = HOME.benchmark;
const split = (prefix: string) =>
  Object.fromEntries(Object.entries(bm.curves).filter(([k]) => k.startsWith(prefix)).map(([k, v]) => [k.slice(prefix.length), v]));
const REAL = split("real|");
const SYN = split("synthetic|");
const testRaw = REAL.RULES["0.005"].raw_bytes;
const testSols = bm.segments.reduce((s, x) => s + x.eval[1] - x.eval[0] + 1, 0);
const segText = bm.segments.map((s) => `sols ${s.eval[0]}–${s.eval[1]}`).join(", ");
const J = HOME.jev;
const r = HOME.replay;
const fun = HOME.data.validation_funnel;

export default function TelemetryHome() {
  if (PUBLIC_RELEASE) notFound(); // Phase 1–2 archive hidden from the public release for now (code kept; visible locally)
  const ceiling = Math.max(...Object.values(SYN.RULES).map((p) => p.high_any ?? 0), ...Object.values(SYN.LOCAL_EDGE).map((p) => p.high_any ?? 0));
  const bucket = bm["synthetic_by_bucket_at_0.5pct"].RULES;
  const sub = bm["real_by_subtype_at_0.5pct"].RULES;
  const st = bm.storage_1mib_high_preserved;
  return (
    <div className="home">
      <TopBar />
      <div className="border-b border-line bg-panel-2">
        <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-2 text-[12px] text-ink-3">
          <span className="chip mr-2" style={{ color: "var(--s-warn)" }}>PHASE 1–2 ARCHIVE</span>
          The original telemetry-triage homepage, kept unchanged for the record. The current research result is on the{" "}
          <Link href="/" className="underline text-ink">release homepage</Link>.
        </div>
      </div>
      <main>
        {/* 1–2 · HERO */}
        <section className="home-grid border-b border-line">
          <div className="max-w-[1240px] mx-auto px-4 sm:px-6 pt-8 pb-10 sm:pt-12 lg:pb-14 grid gap-8 lg:gap-12 lg:grid-cols-[1fr_minmax(0,520px)] items-center">
            <div className="space-y-5">
              <div className="mono tracking-[0.35em] text-[12px] text-ink-2">DEEPSIFT</div>
              <h1 className="text-[30px] sm:text-[44px] leading-[1.08] font-medium text-ink">
                Autonomous science triage for bandwidth-constrained missions.
              </h1>
              <p className="mono text-[15px] sm:text-[17px]" style={{ color: "var(--a-full)" }}>Not every bit deserves the trip to Earth.</p>
              <p className="text-[15px] sm:text-[16px] text-ink-2 leading-relaxed max-w-xl">
                A spacecraft can collect far more data than it can downlink. DEEPSIFT decides what survives — what to keep, compress,
                summarize or drop — and records why.
              </p>
              <div className="flex flex-wrap gap-2 pt-1">
                <Link href="/control" className="btn" data-active="true" style={{ fontSize: 12, padding: "9px 16px" }}>▶ Run Curiosity mission replay</Link>
                <Link href="#benchmark" className="btn" style={{ fontSize: 12, padding: "9px 16px" }}>View benchmark</Link>
              </div>
              <div className="mono text-[11px] text-ink-3">Real NASA PDS data · Reproducible experiments · Auditable decisions</div>
              <dl className="grid grid-cols-2 sm:grid-cols-4 border-t border-line pt-4 gap-y-3">
                <Stat k="Held-out test" v={`${testSols} sols`} />
                <Stat k="Raw PDS records" v={mb(testRaw)} />
                <Stat k="Injected events" v={SYN.RULES["0.005"].high_labels.toLocaleString()} sub="high severity" />
                <Stat k="Strategies × budgets" v={`5 × ${bm.budgets.length}`} />
              </dl>
            </div>
            <HeroFunnel />
          </div>
        </section>

        {/* 3 · CORE QUESTION */}
        <Section id="survives" n="01" kicker="The core question">
          <SurvivalExplorer real={REAL} synthetic={SYN} rawBytes={testRaw} segments={segText} runId={bm.run_id} />
        </Section>

        {/* 4 · STRATEGIES */}
        <Section n="02" kicker="Strategies" title="Different strategies make different tradeoffs."
          lead="DEEPSIFT is not one model. The same candidates are ranked by deterministic rules, statistics, a small onboard model and a semantic model, under the same byte budget.">
          <StrategyTable real={REAL} synthetic={SYN} latency={bm.latency_p50_ms}
            jev={{ p50: J.latency_ms.p50, costPer1k: J.cost_per_1k_requests_usd, aurocDiff: J.auroc_diff_vs_rules.with_objective.diff, ci: J.auroc_diff_vs_rules.with_objective.ci95, runId: J.run_id }}
            localEdge={bm.local_edge_model} />
        </Section>

        {/* 5 · REPLAY */}
        <Section n="03" kicker="Mission replay" title="Replay a real Curiosity mission segment."
          lead={`Historical REMS and RAD records from sols ${r.sols[0]}–${r.sols[1]} are replayed as if arriving from the rover now: candidates appear, the decision layer answers, the scheduler fills relay passes.`}>
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="chip" style={{ color: "var(--ink)", borderColor: "var(--ink-4)" }}>MISSION REPLAY</span>
              <span className="chip text-ink-3">NOT A LIVE NASA FEED</span>
              <span className="chip text-ink-3">{r.data_source.replace("_", " ")}</span>
            </div>
            <ReplayPreview />
            <div className="flex flex-wrap items-center gap-3">
              <Link href="/control" className="btn" data-active="true" style={{ fontSize: 12, padding: "8px 14px" }}>Launch mission replay</Link>
              <span className="text-[11px] text-ink-4">
                Runs locally (<span className="mono">npm run demo</span>) with the v0.1 demo configuration and a mock decision engine — no API
                key, no spend.
              </span>
            </div>
          </div>
        </Section>

        {/* 6 · BLACKOUT */}
        <Section n="04" kicker="Blackout" title="What happens when Earth disappears?"
          lead={`During a ${HOME.replay.blackout.duration_sols}-sol outage the rover keeps observing with ${mb(HOME.replay.blackout.storage_bytes)} of triage storage. Something has to give.`}>
          <BlackoutDemo b={HOME.replay.blackout} configVersion={r.config_version} />
        </Section>

        {/* 7 · EVENT */}
        <Section n="05" kicker="Event inspector" title="Why was this kept?"
          lead="Each decision is a utility built from named terms, and every line below is read from the stored audit record — no generated explanation.">
          <EventCard />
        </Section>

        {/* 8 · AUDIT */}
        <Section n="06" kicker="Auditability" title="Every decision can be inspected."
          lead="DEEPSIFT does not ask users to trust a black box. Every decision can be replayed from its audit record.">
          <ol className="border border-line">
            {r.audit_flow.map((s, i) => (
              <li key={s.stage} className="grid gap-1 sm:grid-cols-[34px_190px_1fr_1fr_90px] sm:items-baseline border-b border-line last:border-b-0 px-3 py-2.5">
                <span className="mono text-[10px] text-ink-4">{String(i + 1).padStart(2, "0")}</span>
                <span className="mono text-[12px] text-ink">{s.stage}</span>
                <span className="text-[12px] text-ink-3"><span className="label mr-1.5">in</span>{s.in}</span>
                <span className="text-[12px] text-ink-2"><span className="label mr-1.5">out</span>{s.out}{s.note && <span className="text-ink-4"> · {s.note}</span>}</span>
                <span className="mono text-[11px] text-ink-3 sm:text-right">{s.ms != null ? `${s.ms < 10 ? s.ms.toFixed(1) : Math.round(s.ms).toLocaleString()} ms` : "—"}</span>
              </li>
            ))}
          </ol>
          <p className="mono text-[11px] text-ink-4 mt-2">
            Replay of {r.events} events · config version {r.config_version} · timings measured on a development laptop · decisions logged to
            DuckDB with the event, answers, objective and config needed to reproduce them (<Link href="/audit" className="underline">/audit</Link>).
          </p>
        </Section>

        {/* 9 · BENCHMARK */}
        <Section id="benchmark" n="07" kicker="Benchmark" title="Does semantic reasoning actually help?"
          lead="Deterministic rules, statistical methods, a local model and a semantic decision model are compared under the same bandwidth constraints, on held-out data, with a harness built so the model can lose.">
          <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
            <BenchmarkChart synthetic={SYN} budgets={bm.budgets} />
            <aside className="border border-line p-4 space-y-3 self-start">
              <div className="flex items-center gap-2">
                <span className="label">Semantic model · Jev 1.13</span>
              </div>
              <span className="chip inline-block" style={{ color: "var(--s-warn)", borderColor: "#5a4412" }}>EVALUATION: VALIDATION ONLY</span>
              <p className="text-[12.5px] text-ink-2 leading-relaxed">
                Not run on the held-out test. In the latest validation pilot ({J.events} candidates, {J.high_labels} high-priority events, {J.live_calls.toLocaleString()} calls,
                ${J.cost_usd.toFixed(3)}) it did not improve candidate ordering over rules:
              </p>
              <div className="mono text-[12px] text-ink-2 space-y-0.5">
                <div>AUROC rules <span className="text-ink">{J.auroc.RULES.toFixed(3)}</span></div>
                <div>AUROC Jev <span className="text-ink">{J.auroc.JEV_V3_WITH_OBJECTIVE.toFixed(3)}</span></div>
                <div>Δ <span className="text-ink">{J.auroc_diff_vs_rules.with_objective.diff >= 0 ? "+" : ""}{J.auroc_diff_vs_rules.with_objective.diff.toFixed(3)}</span> [{J.auroc_diff_vs_rules.with_objective.ci95.map((x) => x.toFixed(3)).join(", ")}]</div>
              </div>
              <Link href="/study" className="btn inline-block">Full study →</Link>
            </aside>
          </div>
        </Section>

        {/* 10 · DATA */}
        <Section n="08" kicker="Data" title="Built on real mission data."
          lead="NASA Planetary Data System archives for Mars Science Laboratory (Curiosity). No endorsement is implied — the data is public.">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="border border-line p-4 space-y-2">
              <div className="label">REMS · environmental measurements</div>
              <p className="text-[13px] text-ink-2">Pressure, air and ground temperature, UV flux, relative humidity. PDS Atmospheres Node, MODRDR.</p>
              <div className="label pt-1">RAD · radiation measurements</div>
              <p className="text-[13px] text-ink-2">Surface dose rates (detectors B and E). PDS PPI Node, RDR.</p>
              <div className="mono text-[11px] text-ink-3 pt-1">
                {HOME.data.rems_products_on_disk} REMS + {HOME.data.rad_products_on_disk} RAD files on disk · held-out test: {HOME.data.test_raw_products?.files} products,
                sha256 <span className="break-all">{HOME.data.test_raw_products?.sha256.slice(0, 16)}…</span>
              </div>
            </div>
            <ul className="sm:hidden border border-line divide-y divide-line">
              {Object.entries(HOME.data.splits).flatMap(([name, segs]) =>
                segs.map((s) => (
                  <li key={s.id} className="px-3 py-2">
                    <div className="flex justify-between mono text-[12px]"><span className="text-ink-2">{s.id}</span><span className="text-ink-3">{name}</span></div>
                    <div className="mono text-[11px] text-ink-3">sols {s.sols[0]}–{s.sols[1]} · {s.utc[0]} → {s.utc[1]}</div>
                  </li>
                )),
              )}
            </ul>
            <div className="hidden sm:block border border-line overflow-x-auto">
              <table className="w-full text-[12px]">
                <thead><tr className="label text-left border-b border-line"><th className="px-3 py-2 font-normal">Split</th><th className="px-3 py-2 font-normal">Segment</th><th className="px-3 py-2 font-normal">Sols</th><th className="px-3 py-2 font-normal">UTC ≈</th></tr></thead>
                <tbody>
                  {Object.entries(HOME.data.splits).flatMap(([name, segs]) =>
                    segs.map((s, i) => (
                      <tr key={s.id} className="border-b border-line last:border-b-0">
                        <td className="px-3 py-1.5 mono text-ink-3">{i === 0 ? name : ""}</td>
                        <td className="px-3 py-1.5 mono text-ink-2">{s.id}</td>
                        <td className="px-3 py-1.5 mono text-ink-2">{s.sols[0]}–{s.sols[1]}</td>
                        <td className="px-3 py-1.5 mono text-ink-3">{s.utc[0]} → {s.utc[1]}</td>
                      </tr>
                    )),
                  )}
                </tbody>
              </table>
              <p className="text-[10.5px] text-ink-4 px-3 py-2 border-t border-line">
                Temporal splits; the test split was not inspected before the configuration was frozen. Dates from RAD product names.
              </p>
            </div>
          </div>
          <div className="mt-3"><Link href="/explorer" className="btn">View data provenance</Link></div>
        </Section>

        {/* 11 · HOW IT WORKS */}
        <Section n="09" kicker="How it works" title="Most of the work is deterministic."
          lead="Semantic models only ever see the small set of candidate events that survive detection. Numbers: validation split, real data.">
          <ol className="grid gap-px bg-line border border-line sm:grid-cols-3 lg:grid-cols-6">
            {[
              [fun.raw_samples.toLocaleString(), "sensor samples"],
              [fun.instrument_windows.toLocaleString(), "windows"],
              [fun.candidate_windows.toLocaleString(), "candidate windows"],
              [fun.candidate_events.toLocaleString(), "candidate events"],
              ["Decision layer", "rules · statistics · local model · semantic model"],
              ["Downlink queue", "priority × bytes × passes × storage"],
            ].map(([v, k], i) => (
              <li key={k} className="bg-bg p-3 sm:p-4 relative">
                <div className="mono text-[10px] text-ink-4">{String(i + 1).padStart(2, "0")}</div>
                <div className={`mono ${i < 4 ? "text-[20px]" : "text-[14px]"} text-ink mt-1`}>{v}</div>
                <div className="text-[11.5px] text-ink-3">{k}</div>
              </li>
            ))}
          </ol>
          <p className="text-[12px] text-ink-3 mt-2">
            {((fun.candidate_events / fun.raw_samples) * 1e6).toFixed(0)} candidate events per million samples reach the decision layer.
          </p>
        </Section>

        {/* 12 · WHY NOT SEND EVERYTHING */}
        <Section n="10" kicker="Context" title="Why not send everything?">
          <ul className="grid gap-px bg-line border border-line sm:grid-cols-2 lg:grid-cols-5 text-[13px]">
            {[
              ["Limited contact windows", "relay passes are minutes long and shared"],
              ["Limited bandwidth", "each pass carries a fixed number of bytes"],
              ["Limited onboard storage", "a buffer that fills during outages"],
              ["Long delays", "Earth cannot decide in real time"],
              ["Competing observations", "every instrument wants the same pass"],
            ].map(([k, v]) => (
              <li key={k} className="bg-bg p-3"><div className="text-ink">{k}</div><div className="text-ink-3 text-[12px]">{v}</div></li>
            ))}
          </ul>
        </Section>

        {/* 13 · ARCHITECTURE */}
        <Section n="11" kicker="Architecture" title="Where each decision is made.">
          <div className="grid gap-3 lg:grid-cols-4">
            {[
              ["Spacecraft / edge", ["signal processing", "feature extraction", "candidate detection", "storage simulation"], null],
              ["Decision layer", ["rules", "statistics", "local model (onboard-sized)", "semantic model"], "Jev currently runs remotely through OpenRouter — a research configuration, not spacecraft-ready inference. Mission Control uses a mock engine."],
              ["Mission policy", ["mission objective", "bandwidth", "storage", "priority rules (deterministic code)"], null],
              ["Earth / scientists", ["selected observations", "audit trail", "analysis"], null],
            ].map(([k, items, note], i) => (
              <div key={k as string} className="border border-line p-4 relative">
                <div className="mono text-[10px] text-ink-4">{String(i + 1).padStart(2, "0")}</div>
                <div className="mono text-[12px] tracking-[0.08em] uppercase text-ink mt-1">{k as string}</div>
                <ul className="mt-2 space-y-1 text-[12.5px] text-ink-2">
                  {(items as string[]).map((x) => <li key={x}>· {x}</li>)}
                </ul>
                {note && <p className="mt-3 text-[11px] leading-snug" style={{ color: "var(--s-warn)" }}>{note as string}</p>}
                {i < 3 && <span aria-hidden className="hidden lg:block absolute -right-[11px] top-1/2 -translate-y-1/2 mono text-ink-4 bg-bg">→</span>}
              </div>
            ))}
          </div>
        </Section>

        {/* 14 · FINDINGS */}
        <Section n="12" kicker="Research honesty" title="What DEEPSIFT has found so far."
          lead="Measured on held-out data unless stated. Negative results are kept as results.">
          <ol className="grid gap-px bg-line border border-line md:grid-cols-2 text-[13px]">
            <Finding n="1" t="Candidate detection sets a ceiling.">
              Event-based strategies plateau at or below <b className="mono">{p0(ceiling)}</b> of high-priority events, however much bandwidth they
              get — what the detector misses, no decision layer can recover.
            </Finding>
            <Finding n="2" t="A no-AI hybrid is strong once bandwidth loosens.">
              Rules + statistical keeps <b className="mono">{p0(SYN.RULES_PLUS_STATISTICAL["0.01"].high_any)} · {p0(SYN.RULES_PLUS_STATISTICAL["0.02"].high_any)} · {p0(SYN.RULES_PLUS_STATISTICAL["0.05"].high_any)}</b>{" "}
              at 1 · 2 · 5% budget, vs rules alone {p0(SYN.RULES["0.01"].high_any)} · {p0(SYN.RULES["0.02"].high_any)} · {p0(SYN.RULES["0.05"].high_any)}.
            </Finding>
            <Finding n="3" t="Weak anomalies near the background stay hard.">
              At 0.5%, rules recover {p0(bucket["bucket=NEAR_NOISE_FLOOR"].tolerant_recall)} of injections below 2σ and{" "}
              {p0(bucket["bucket=WEAK"].tolerant_recall)} at 2–4σ, vs {p0(bucket["bucket=OBVIOUS"].tolerant_recall)} for obvious ones.
            </Finding>
            <Finding n="4" t="Slow radiation events are poorly isolated.">
              Forbush decreases: {p0(sub["subtype=forbush_decrease"].coverage)} of their data covered at 0.5% (solar particle events:{" "}
              {p0(sub["subtype=solar_energetic_particle_event"].coverage)}). A multi-day 5% dose drop is ≈2σ of hourly scatter.
            </Finding>
            <Finding n="5" t="An intuitive storage rule did not generalize.">
              Protecting high-value products during a blackout preserved {st["RULES|PROTECTED_HIGH_VALUE_TIER"]?.[0]}/{st["RULES|PROTECTED_HIGH_VALUE_TIER"]?.[1]} high-priority events at 1 MiB,
              vs {st["RULES|VALUE_PER_BYTE_ONLY"]?.[0]}/{st["RULES|VALUE_PER_BYTE_ONLY"]?.[1]} for plain value-per-byte.
            </Finding>
            <Finding n="6" t="The semantic model has not beaten rules at ranking.">
              Validation pilots only: early question schemas produced degenerate answers; the science-only redesign was healthy but ordered
              candidates no better than rules (ΔAUROC {J.auroc_diff_vs_rules.no_objective.diff.toFixed(3)}). Under the pre-registered stop rule it was discontinued for
              this ranking role — a result about this experiment, not about Jev in general.
            </Finding>
          </ol>
          <div className="mt-3 flex flex-wrap gap-2">
            <Link href="/study" className="btn">Study results</Link>
            <Link href="/research" className="btn">Methodology</Link>
          </div>
        </Section>

        {/* 15 · FINAL CTA */}
        <section className="border-t border-line">
          <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-14 flex flex-col sm:flex-row sm:items-center gap-6">
            <div className="flex-1">
              <div className="text-[26px] sm:text-[32px] font-medium text-ink">Run the mission.</div>
              <p className="text-[14px] text-ink-2 mt-1">Open research prototype · one command locally: <span className="mono">npm run demo</span></p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Link href="/control" className="btn" data-active="true" style={{ fontSize: 12, padding: "10px 18px" }}>▶ Run the mission</Link>
              <Link href="/study" className="btn" style={{ fontSize: 12, padding: "10px 18px" }}>Explore the research</Link>
            </div>
          </div>
        </section>
      </main>
      <footer className="border-t border-line">
        <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-5 text-[11px] text-ink-4 leading-relaxed">
          Research prototype. Not affiliated with, endorsed or validated by NASA or JPL; not flight software; no onboard deployment. Data:
          NASA Planetary Data System (public). Figures on this page are read from stored runs ({bm.run_id}, {J.run_id}) and the mission replay;
          snapshot {HOME.generated_at.slice(0, 10)} · commit {HOME.git.commit}.
        </div>
      </footer>
    </div>
  );
}

function TopBar() {
  return (
    <header className="sticky top-0 z-20 border-b border-line bg-bg/95 backdrop-blur">
      <div className="max-w-[1240px] mx-auto px-4 sm:px-6 h-11 flex items-center gap-4">
        <Link href="/" className="mono font-semibold tracking-[0.2em] text-[13px] text-ink">DEEPSIFT</Link>
        <span className="chip text-ink-3 hidden sm:inline">RESEARCH PROTOTYPE</span>
        <nav className="ml-auto flex items-center gap-1 overflow-x-auto">
          {[["/control", "Mission Control"], ["/blackout", "Blackout"], ["/study", "Study"], ["/research", "Research"]].map(([h, l]) => (
            <Link key={h} href={h} className="mono text-[11px] uppercase tracking-[0.06em] px-2 py-1 whitespace-nowrap text-ink-3 hover:text-ink">{l}</Link>
          ))}
        </nav>
      </div>
    </header>
  );
}

function Section({ id, n, kicker, title, lead, children }: { id?: string; n: string; kicker: string; title?: string; lead?: string; children: React.ReactNode }) {
  return (
    <section id={id} className="border-b border-line scroll-mt-12">
      <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-12 sm:py-16">
        <div className="flex items-baseline gap-3 mb-2">
          <span className="mono text-[11px] text-ink-4">{n}</span>
          <span className="label">{kicker}</span>
        </div>
        {title && <h2 className="text-[24px] sm:text-[30px] leading-tight font-medium text-ink max-w-3xl">{title}</h2>}
        {lead && <p className="text-[14px] sm:text-[15px] text-ink-2 leading-relaxed max-w-3xl mt-2">{lead}</p>}
        <div className={title || lead ? "mt-6" : ""}>{children}</div>
      </div>
    </section>
  );
}

function Stat({ k, v, sub }: { k: string; v: string; sub?: string }) {
  return (
    <div>
      <dt className="label">{k}</dt>
      <dd className="mono text-[18px] text-ink">{v}{sub && <span className="text-[10px] text-ink-3 ml-1.5">{sub}</span>}</dd>
    </div>
  );
}

function Finding({ n, t, children }: { n: string; t: string; children: React.ReactNode }) {
  return (
    <li className="bg-bg p-4">
      <div className="flex items-baseline gap-2">
        <span className="mono text-[10px] text-ink-4">{n.padStart(2, "0")}</span>
        <span className="text-ink font-medium">{t}</span>
      </div>
      <p className="text-ink-2 mt-1 leading-relaxed [&_b]:font-normal [&_b]:text-ink">{children}</p>
    </li>
  );
}
