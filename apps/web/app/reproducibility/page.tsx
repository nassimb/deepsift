import { ReleaseFooter, ReleaseTopBar, Section } from "@/components/release/Shell";
import { H, REL } from "@/lib/release";

const R = REL.reproducibility;
const ROLE: Record<string, string> = {
  development: "tuning and method design",
  validation1: "first out-of-sample check (informed post-validation simplification; not evidence for later claims)",
  validation2: "fresh validation of the simplified claim (selected from PDS listings only)",
  test: "final held-out test — config frozen before download, analysed once",
};

export default function Reproducibility() {
  return (
    <div className="home">
      <ReleaseTopBar />
      <main>
        <Section kicker="Reproducibility" title="What was frozen, when, and how to check it."
          lead="Every configuration and pass/fail rule was committed to git before the data that tested it was downloaded. This page lists the periods, hashes, commits, seeds and the order of operations.">
          <div className="panel p-4 space-y-2 max-w-3xl">
            <div className="label">The final test was frozen before download</div>
            <KV k="final config committed (git)" v={R.frozen_before_download.config_commit_time} />
            <KV k="first test image written (file system)" v={R.frozen_before_download.first_test_image_written} />
            <KV k="config committed before the first test image" v={R.frozen_before_download.config_before_download ? "yes" : "NO"} />
            <KV k="final config" v="config/phase3_final_test_config.json" />
            <KV k="final config hash" v={H.config_hash} />
            <KV k="config commit → result commit" v={`${H.config_commit} → ${H.result_commit}`} />
          </div>
        </Section>

        <Section kicker="Dataset periods" title="Four periods, never pooled">
          <div className="overflow-x-auto panel">
            <table className="w-full text-[12px]">
              <thead><tr className="text-left border-b border-line">{["period", "sols", "role", "dataset manifest", "manifest SHA-256", "run"].map((h) => <th key={h} className="px-3 py-2 label font-normal">{h}</th>)}</tr></thead>
              <tbody className="mono text-ink-2">
                {R.periods.map((p) => (
                  <tr key={p.id} className="border-b border-line align-top">
                    <td className="px-3 py-2 text-ink">{p.id}</td>
                    <td className="px-3 py-2">{p.sols[0]}–{p.sols[1]}</td>
                    <td className="px-3 py-2 font-sans text-ink-3">{ROLE[p.id]}</td>
                    <td className="px-3 py-2 break-all">{p.manifest}</td>
                    <td className="px-3 py-2 break-all text-ink-3">{R.manifest_sha256[p.manifest]?.slice(0, 16)}…</td>
                    <td className="px-3 py-2 break-all">{p.run}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>

        <Section kicker="Configurations" title="Frozen configuration hashes">
          <div className="panel p-4 space-y-2">
            {R.configs.map((c) => <KV key={c.path} k={c.path} v={c.hash} />)}
            <KV k="data/splits/phase3_splits.json" v={R.manifest_sha256["data/splits/phase3_splits.json"]} />
            <KV k="data/splits/phase3_validation2.json" v={R.manifest_sha256["data/splits/phase3_validation2.json"]} />
            <p className="text-[12px] text-ink-3 pt-2">Each runner recomputes its config hash and the SHA-256 of every listed source file and refuses to start if anything differs.</p>
          </div>
        </Section>

        <Section kicker="Run order" title="Git tags, in order">
          <div className="overflow-x-auto panel">
            <table className="w-full text-[12px]">
              <thead><tr className="text-left border-b border-line">{["#", "tag", "commit", "committed", "stage"].map((h) => <th key={h} className="px-3 py-2 label font-normal">{h}</th>)}</tr></thead>
              <tbody className="mono text-ink-2">
                {R.timeline.map((t, i) => (
                  <tr key={t.tag} className="border-b border-line">
                    <td className="px-3 py-1.5 text-ink-4">{i + 1}</td>
                    <td className="px-3 py-1.5 text-ink">{t.tag}</td>
                    <td className="px-3 py-1.5">{t.commit}</td>
                    <td className="px-3 py-1.5">{t.date}</td>
                    <td className="px-3 py-1.5 font-sans text-ink-3">{t.label}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>

        <Section kicker="Random seeds" title="Every stochastic component is seeded">
          <pre className="panel p-4 mono text-[11px] text-ink-2 overflow-x-auto">{JSON.stringify(R.seeds, null, 2)}</pre>
        </Section>

        <Section kicker="Integrity" title="Scientific artifacts are hash-locked">
          <div className="panel p-4 space-y-2">
            <KV k="manifest" v={R.integrity.file} />
            <KV k="artifacts covered" v={String(R.integrity.files)} />
            <KV k="aggregate SHA-256" v={R.integrity.aggregate_sha256} />
            <div className="label pt-3">Commands</div>
            <pre className="mono text-[11px] text-ink-2 overflow-x-auto">{R.commands.join("\n")}</pre>
            <p className="text-[12px] text-ink-3">
              Raw PDS products are not committed (they are re-downloadable from the URLs in each manifest and verified by SHA-256); manifests, configs, run
              artifacts and reports are.
            </p>
          </div>
        </Section>
      </main>
      <ReleaseFooter />
    </div>
  );
}

function KV({ k, v }: { k: string; v: string }) {
  return (
    <div className="grid md:grid-cols-[320px_1fr] gap-1 md:gap-4 text-[12px]">
      <span className="text-ink-3">{k}</span>
      <span className="mono text-ink-2 break-all">{v}</span>
    </div>
  );
}
