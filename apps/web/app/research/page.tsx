import Link from "next/link";
import { ReleaseFooter, ReleaseTopBar } from "@/components/release/Shell";
import { H, pct } from "@/lib/release";

const DOCS: [string, string][] = [
  ["docs/deepsift-paper.md", "technical paper (abstract, method, results, negative results, limitations)"],
  ["docs/phase3-final-test-report.md", "final held-out test report (sols 950–979)"],
  ["docs/phase3.4-report.md", "post-validation simplification + fresh validation (1100–1129)"],
  ["docs/phase3.3-report.md", "out-of-sample validation (779–820)"],
  ["docs/phase3.2-report.md · docs/phase3.1-report.md · docs/phase3-report.md", "Phase 3 development reports"],
  ["docs/jev-evaluation.md · docs/jev-model-selection.md", "Phase 2 Jev evaluation and stop decision"],
  ["docs/research-methodology.md", "methodology and pre-registration notes"],
  ["docs/architecture.md", "system architecture"],
  ["docs/demo-script.md", "60-second demo script"],
  ["docs/release/science-artifacts.json", "SHA-256 of every scientific artifact in the release"],
];
const FIGS: [string, string][] = [
  ["fig1_bytes_vs_coverage", "Figure 1 · bytes vs spatial coverage (held-out test)"],
  ["fig2_four_period_generalization", "Figure 2 · four-period generalization of POSITION"],
  ["fig3_embedding_gain_by_period", "Figure 3 · embedding gain by period"],
  ["fig4_research_funnel", "Figure 4 · research funnel"],
  ["fig5_example_traverse", "Figure 5 · example held-out traverse (not claimed statistically representative)"],
];

function S({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="grid md:grid-cols-[200px_1fr] gap-3 md:gap-6 border-t border-line pt-6">
      <h2 className="label pt-1">{title}</h2>
      <div className="text-[14px] text-ink-2 leading-relaxed space-y-3 min-w-0 break-words">{children}</div>
    </section>
  );
}

export default function Research() {
  return (
    <>
      <ReleaseTopBar />
      <main className="max-w-[1050px] mx-auto px-4 sm:px-6 py-10 space-y-8">
        <header>
          <div className="label">DEEPSIFT v1 · research release</div>
          <h1 className="text-[30px] font-medium text-ink mt-2">Which signals actually help decide what a rover should downlink?</h1>
          <p className="text-[14px] text-ink-2 mt-3 max-w-3xl">
            Held-out result (Curiosity Navcam, sols 950–979): Scheduler V3 + POSITION at 1/4 retention used {pct(H.bytes_fraction)} of full-quality
            traverse bytes with 5 m coverage {H.coverage_5m.toFixed(3)}, a largest distance to a kept frame of {H.max_distance_to_kept_m_worst.toFixed(2)} m
            and {H.stereo_broken} broken stereo pairs — pre-registered criterion {H.result}.{" "}
            <Link href="/limitations" className="underline text-ink">Limitations</Link> · <Link href="/reproducibility" className="underline text-ink">Reproducibility</Link>
          </p>
        </header>

        <S id="documents" title="Documents (repository paths)">
          <ul className="space-y-1">
            {DOCS.map(([path, what]) => (
              <li key={path}><span className="mono text-ink break-all">{path}</span> — {what}</li>
            ))}
          </ul>
        </S>

        <S id="figures" title="Figures">
          <div className="grid gap-3 md:grid-cols-2">
            {FIGS.map(([f, c]) => (
              <a key={f} href={`/figures/${f}.svg`} className="block border border-line bg-white p-1" target="_blank" rel="noreferrer">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={`/figures/${f}.svg`} alt={c} className="w-full h-auto" />
                <span className="block mono text-[10px] text-neutral-600 px-1">{c}</span>
              </a>
            ))}
          </div>
          <p className="mono text-[11px] text-ink-4">scripts/make_release_figures.py · drawn from frozen artifacts only · also in docs/figures/</p>
        </S>

        <div className="border-t border-line pt-6">
          <div className="label">Phase 1–2 methodology (telemetry triage) — historical record</div>
          <p className="text-[13px] text-ink-3 mt-2 max-w-3xl">
            The sections below describe the original REMS/RAD telemetry-triage study and the Jev evaluation (Phase 2 conclusion: Jev did not improve
            candidate ranking and was discontinued for that role). Full text: <span className="mono">docs/research-methodology.md</span>.
          </p>
        </div>

        <S id="question" title="Research question">
          <p>
            Given a fixed downlink budget, does placing a fast, bounded-output decision model (TypeSafe&apos;s Jev) between deterministic
            candidate detection and a deterministic priority engine retain more scientifically important events per downlinked byte than simple
            baselines — and how many expensive deep-model calls does it avoid?
          </p>
        </S>

        <S id="hypothesis" title="Hypothesis">
          <p>
            H1: Jev-informed triage achieves higher high-severity recall than threshold rules at equal downlinked bytes. H0: it does not. A
            second question is cost: the fraction of candidates that still need deep analysis. Either outcome is a valid result; the harness is
            designed so the model can lose.
          </p>
        </S>

        <S id="dataset" title="Dataset">
          <p>
            MSL/Curiosity REMS MODRDR (MSL-M-REMS-5-MODRDR-V1.0, PDS Atmospheres Node) and RAD RDR (MSL-M-RAD-3-RDR-V1.0, PDS PPI Node), sols
            232–251 (April 2013). Channels: pressure, ambient air temperature, ground brightness temperature, UV-ABC, relative humidity, RAD total
            dose rate B and E. Every file is recorded with its URL and SHA-256 in <span className="mono">data/raw/manifest.json</span>; a
            bundled subset (sols 238–243) is the offline fallback and is labelled LOCAL NASA SAMPLE.
          </p>
          <p>
            Timing: REMS UTC is derived per product from the label&apos;s spacecraft-clock/UTC pair; RAD local time is derived from
            START_OBS_UTC with a linear fit to the REMS UTC↔LMST relation (fitted sol length 88,775.244 s, max residual &lt; 0.5 s), because
            the RAD START_OBS_MARS field does not advance per observation in these products.
          </p>
        </S>

        <S id="strategies" title="Strategies">
          <ol className="list-decimal pl-5 space-y-1">
            <li><b className="text-ink font-medium">Random sampling</b> of instrument windows, full products, seeded.</li>
            <li><b className="text-ink font-medium">Threshold rules</b> — the deterministic candidate filter plus rule-based type and value; identical to the pipeline&apos;s fallback path.</li>
            <li><b className="text-ink font-medium">Statistical anomaly detection</b> — all windows ranked by multivariate robust deviation, independent of the candidate filter.</li>
            <li><b className="text-ink font-medium">Decision engine</b> — candidates → engine → gating → priority. A labelled heuristic mock by default; Jev was evaluated in Phase 2 and discontinued for the ranking role (see Study).</li>
            <li><b className="text-ink font-medium">Engine + deep analysis</b> — escalations go to a DeepAnalysisProvider; reported UNAVAILABLE without one.</li>
          </ol>
          <p>All strategies use the same greedy byte allocator and the same budget (passes/sol × bytes/pass × sols).</p>
        </S>

        <S id="ground-truth" title="Ground truth">
          <p>
            We do not know automatically what is scientifically important. Labels come from separate, never-merged sources:
            <span className="mono"> DOCUMENTED_EVENT</span> (cited literature; currently the 2013-04-11 solar particle event on sol 242,
            status “needs verification” for time bounds), <span className="mono">SYNTHETIC_ANOMALY</span> (nine injection types with known
            placement), and <span className="mono">HUMAN_LABEL</span> (entered in the Event Inspector). Model predictions are stored as
            predictions and are never used as labels.
          </p>
        </S>

        <S id="metrics" title="Metrics">
          <ul className="space-y-1">
            <li>Event recall and high-severity recall, overall and per label source.</li>
            <li>Retained-but-unlabeled rate — an <i>upper bound</i> on the false-positive rate, because unlabeled real phenomena exist.</li>
            <li>Downlinked bytes and data reduction (1 − downlinked / raw PDS bytes).</li>
            <li>
              <span className="text-ink">Science value per downlinked byte (proxy)</span> = Σ severity weight × assumed product fidelity over
              recovered labels, per MB. It depends on assumed fidelities (config) and on which labels exist. It does not measure true
              scientific value.
            </li>
            <li>Decision latency (measured wall time), engine calls, deep calls, fraction requiring expensive analysis, cost where the API reports tokens.</li>
          </ul>
        </S>

        <S id="limitations" title="Limitations">
          <ul className="space-y-1">
            <li>One documented event; recall is dominated by synthetic injections whose magnitudes we chose.</li>
            <li>The mock engine and the injection generator were written by the same authors — mock results say nothing about Jev.</li>
            <li>Byte costs are zlib sizes of PDS ASCII records; flight encodings, packetization and real relay allocations differ.</li>
            <li>Twenty sols of one season at one site; baselines use seven trailing sols.</li>
            <li>Multi-sensor correlated injections of a few Pa / K over minutes are usually not detected: they sit inside natural sol-to-sol variability at Gale.</li>
            <li>No hardware, power or timing constraints of flight processors are modelled.</li>
          </ul>
        </S>

        <S id="misclassification" title="Type-safe ≠ correct">
          <p>
            Bounded outputs guarantee that an answer is one of the allowed options with a probability attached. They do not guarantee that the
            answer is right. Jev&apos;s documentation notes weakness with raw numbers and dates, so every numeric feature is paired with a
            deterministic qualitative descriptor, raw rows are never sent, and low-confidence answers are routed to rules. Misclassification is
            still possible and is the reason actions are owned by code and every decision is reproducible from the audit log.
          </p>
        </S>

        <S id="reproducibility" title="Reproducibility">
          <p>
            Config is versioned by content hash; every change is recorded with a diff. Each decision stores the event, the engine&apos;s raw
            answers, the objective and the config version, and the Audit page recomputes utility and action exactly from those inputs.
            Benchmarks store seeds, injections, labels and per-label outcomes. Re-querying a real model may produce different answers; stored
            answers are the record.
          </p>
          <p>
            <Link href="/experiments" className="underline text-ink">Run the benchmark →</Link>
          </p>
        </S>

        <footer className="border-t border-line pt-4 text-[11px] text-ink-4">
          DEEPSIFT is a prototype and simulation. It claims no NASA validation, no flight readiness, no scientific discovery and no operational
          superiority.
        </footer>
      </main>
      <ReleaseFooter />
    </>
  );
}
