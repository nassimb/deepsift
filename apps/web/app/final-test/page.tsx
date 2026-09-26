import { ReleaseFooter, ReleaseTopBar, Section, Source } from "@/components/release/Shell";
import { TraverseReplay } from "@/components/release/TraverseReplay";
import { H, REL } from "@/lib/release";

const METHODS: [string, string][] = [
  ["EVERY_NTH_FRAME", "EVERY Nth"], ["UNIFORM_DISTANCE", "UNIFORM DISTANCE"], ["METADATA_POSITION", "POSITION"], ["POSITION_PLUS_EMBEDDING_CHANGE", "POSITION + EMBEDDING"],
];

export default function FinalTest() {
  const S = REL.final_summary;
  return (
    <div className="home">
      <ReleaseTopBar />
      <main>
        <Section kicker="Final test replay" title="Held-out test · Curiosity Navcam · sols 950–979"
          lead={<p>
            {REL.test_dataset.traverse_sequences_ge_10_frames} traverses, {REL.test_dataset.traverse_frames} archived frames. POSITION keeps 1/4 of the frames
            of each traverse at full quality and sends the rest as thumbnail pairs, through the stereo-safe Scheduler V3. The pre-registered criterion
            ({H.claim}) was <span className="text-ink">{H.result}</span>.
          </p>}>
          <TraverseReplay />
        </Section>
        <Section kicker="All frozen strategies on the held-out test" title="SEND ALL vs the four selection methods"
          lead="Visual-change coverage is shown for context only; it is not part of the primary criterion. 1/2 and 1/8 are context; 1/4 is the pre-registered operating point.">
          <div className="overflow-x-auto panel">
            <table className="w-full text-[12px]">
              <thead>
                <tr className="text-left text-ink-3 border-b border-line">
                  {["retention", "method", "bytes", "5 m coverage", "largest dist. to kept", "p95 gap", "max gap", "visual change", "stereo kept / broken"].map((h) => (
                    <th key={h} className="px-3 py-2 font-normal label">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="mono">
                <Tr f="all" m="SEND ALL" v={S["1.0|SEND_ALL"]} strong={false} />
                {(["0.5", "0.25", "0.125"] as const).flatMap((f) =>
                  METHODS.map(([k, label]) => <Tr key={`${f}${k}`} f={{ "0.5": "1/2", "0.25": "1/4", "0.125": "1/8" }[f]} m={label} v={S[`${f}|${k}`]} strong={f === "0.25" && k === "METADATA_POSITION"} />))}
              </tbody>
            </table>
          </div>
          <div className="mt-2"><Source path={`${REL.sources.final} → traverse.summary`} /></div>
        </Section>
        <Section kicker="Figures" title="Publication figures (drawn from the frozen artifacts)">
          <div className="grid gap-4 md:grid-cols-2">
            {[["fig1_bytes_vs_coverage", "Figure 1 · bytes vs spatial coverage (held-out test)"], ["fig5_representative_traverse", "Figure 5 · representative traverse and the nearest-kept metric"]].map(([f, c]) => (
              <figure key={f} className="panel p-2 bg-white">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={`/figures/${f}.svg`} alt={c} className="w-full h-auto" />
                <figcaption className="mono text-[10px] text-neutral-600 px-1 pt-1">{c}</figcaption>
              </figure>
            ))}
          </div>
        </Section>
      </main>
      <ReleaseFooter />
    </div>
  );
}

function Tr({ f, m, v, strong }: { f: string; m: string; v: (typeof REL.final_summary)[string]; strong: boolean }) {
  const c = strong ? "var(--ink)" : "var(--ink-2)";
  return (
    <tr className="border-b border-line" style={{ color: c, background: strong ? "var(--panel-2)" : undefined }}>
      <td className="px-3 py-1.5">{f}</td>
      <td className="px-3 py-1.5">{m}{strong ? " (primary)" : ""}</td>
      <td className="px-3 py-1.5">{v.bytes_fraction.toFixed(3)}</td>
      <td className="px-3 py-1.5">{v.coverage_5m.toFixed(3)}</td>
      <td className="px-3 py-1.5">{v.max_distance_to_kept_m_worst.toFixed(2)} m</td>
      <td className="px-3 py-1.5">{v.p95_gap_m?.toFixed(2)} m</td>
      <td className="px-3 py-1.5">{v.max_gap_m_worst.toFixed(1)} m</td>
      <td className="px-3 py-1.5">{v.visual_change_coverage.toFixed(3)}</td>
      <td className="px-3 py-1.5">{v.stereo_kept_full} / {v.stereo_broken}</td>
    </tr>
  );
}
