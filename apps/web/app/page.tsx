import Link from "next/link";
import { EmbeddingGain, FourPeriod } from "@/components/release/Generalization";
import { ReleaseFooter, ReleaseTopBar, Section, Source } from "@/components/release/Shell";
import { PUBLIC_RELEASE } from "@/lib/mode";
import { H, REL, pct } from "@/lib/release";

// DEEPSIFT v1 research release homepage. Every number is read from data/release.json (scripts/build_release_data.py,
// frozen artifacts only). The Phase 1–2 telemetry homepage is preserved at /telemetry.
const DS = REL.test_dataset;
const VERDICT_COLOR: Record<string, string> = { KEEP: "var(--a-full)", DROP: "var(--ink-3)", "NO MEASURABLE ADDED VALUE": "var(--s-warn)" };

export default function Home() {
  const kept = REL.funnel.filter((f) => f.verdict === "KEEP");
  const notKept = REL.funnel.filter((f) => f.verdict !== "KEEP");
  return (
    <div className="home">
      <ReleaseTopBar />
      <main>
        {/* 1 · HERO */}
        <section className="home-grid border-b border-line">
          <div className="max-w-[1240px] mx-auto px-4 sm:px-6 pt-10 pb-12 sm:pt-14 space-y-8">
            <div className="space-y-4 max-w-3xl">
              <div className="mono tracking-[0.35em] text-[12px] text-ink-2">DEEPSIFT</div>
              <h1 className="text-[28px] sm:text-[40px] leading-[1.1] font-medium text-ink">Autonomous downlink research for bandwidth-constrained missions.</h1>
              <p className="mono text-[15px] sm:text-[16px]" style={{ color: "var(--a-full)" }}>Not every bit deserves the trip to Earth.</p>
              <p className="text-[15px] text-ink-2 leading-relaxed">
                On a held-out Curiosity Navcam interval, position-based traverse sampling with a stereo-safe progressive scheduler kept 1/4 of traverse frames at
                full quality — {pct(H.bytes_fraction)} of full-quality traverse bytes — while every archived traverse frame stayed within 5 m of a kept frame
                (at most {H.max_distance_to_kept_m_worst.toFixed(2)} m) and no stereo pair was broken.
              </p>
            </div>
            <div className="panel">
              <div className="flex flex-wrap items-center gap-2 px-4 py-2 border-b border-line">
                <span className="chip" style={{ color: "var(--ink)", borderColor: "var(--ink-4)" }}>HELD-OUT TEST</span>
                <span className="mono text-[11px] text-ink-2">Curiosity Navcam · sols 950–979</span>
                <span className="mono text-[11px] text-ink-3">· {H.claim} · {DS.traverse_sequences_ge_10_frames} traverses · {DS.traverse_frames} frames</span>
                <span className="chip ml-auto" style={{ color: "var(--s-good)", borderColor: "#1d4d1d" }}>PRE-REGISTERED CRITERION · {H.result}</span>
              </div>
              <dl className="grid grid-cols-2 lg:grid-cols-4">
                <Kpi v={pct(H.bytes_fraction)} k="of full-quality traverse bytes" note="criterion ≤ 35 %" />
                <Kpi v={pct(H.coverage_5m, 0)} k="5 m spatial coverage" note="criterion ≥ 90 %" />
                <Kpi v={`${H.max_distance_to_kept_m_worst.toFixed(2)} m`} k="maximum distance to a retained frame" note="criterion ≤ 10 m, every traverse" />
                <Kpi v={String(H.stereo_broken)} k="broken stereo pairs" note={`${H.stereo_kept_full} stereo pairs kept whole`} />
              </dl>
              <div className="px-4 py-2 border-t border-line flex flex-wrap gap-x-4 gap-y-1">
                <Source path={REL.sources.final} />
                <span className="mono text-[10px] text-ink-4">config {H.config_hash.slice(0, 12)}… committed ({H.config_commit}) before the first test image was downloaded</span>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Link href="/final-test" className="btn" data-active="true" style={{ fontSize: 12, padding: "9px 16px" }}>▶ Replay the held-out test</Link>
              <Link href="/research" className="btn" style={{ fontSize: 12, padding: "9px 16px" }}>Research & paper</Link>
              <Link href="#didnt-work" className="btn" style={{ fontSize: 12, padding: "9px 16px" }}>What didn’t work</Link>
            </div>
          </div>
        </section>

        {/* 2 · PROBLEM */}
        <Section n="01" kicker="The problem" title="A rover collects more imagery than it can send home."
          lead={<>
            <p>
              Every image a Mars rover takes has to wait for a relay pass to reach Earth, and relay capacity is finite. When storage and bandwidth run short,
              something must decide what goes first, what is sent as a thumbnail and what waits. That decision is usually made by people on the ground, a sol
              at a time.
            </p>
            <p className="mt-3">
              DEEPSIFT asks a narrower, measurable question: <span className="text-ink">which signals actually help decide what should be transmitted</span> —
              and which only look helpful on the data they were tuned on.
            </p>
          </>}>
          <dl className="grid grid-cols-2 lg:grid-cols-4 border-t border-line pt-4 gap-y-4 max-w-4xl">
            <Stat k="Test interval" v={`${DS.n_active_sols} active sols`} sub="sols 950–979" />
            <Stat k="Navcam acquisitions" v={DS.acquisitions.toLocaleString()} sub={`${DS.stereo.toLocaleString()} stereo`} />
            <Stat k="Archived products" v={DS.products.toLocaleString()} sub={`${(DS.download_bytes_archive / 1e9).toFixed(2)} GB from PDS`} />
            <Stat k="Full-quality downlink" v={`${(DS.estimated_downlink_full_bytes / 1e6).toFixed(0)} MB`} sub="label estimate, all acquisitions" />
          </dl>
        </Section>

        {/* 3 · WHAT DEEPSIFT DOES */}
        <Section n="02" kicker="What DEEPSIFT does" title="A small, inspectable pipeline."
          lead="The released path uses rover geometry and a byte-accurate scheduler. Nothing in it needs a network, a cloud model or a learned score.">
          <ol className="grid gap-2 md:grid-cols-5 items-stretch">
            {[
              ["Archived observations", "Curiosity Navcam raw EDR from the PDS Imaging Node, with URLs, labels and SHA-256."],
              ["Sequence analysis", "Acquisitions grouped by capture clock; stereo pairs kept together; traverses located with PLACES."],
              ["Position-aware selection", "Farthest-point sampling on rover position keeps frames that cover the traverse."],
              ["Stereo-safe scheduler", "Scheduler V3 fills thumbnail pairs, then compressed pairs, then full pairs — never one eye alone."],
              ["Bandwidth-constrained downlink", "Coverage can only grow as the budget grows (monotonic by construction and by test)."],
            ].map(([t, d], i) => (
              <li key={t} className="panel p-3 relative">
                <div className="mono text-[10px] text-ink-4">{String(i + 1).padStart(2, "0")}</div>
                <div className="text-[13px] text-ink mt-1">{t}</div>
                <div className="text-[12px] text-ink-3 mt-1 leading-snug">{d}</div>
                {i < 4 && <span className="hidden md:block absolute -right-2 top-1/2 -translate-y-1/2 mono text-ink-4">→</span>}
              </li>
            ))}
          </ol>
        </Section>

        {/* 4 · WHAT WE TESTED */}
        <Section id="didnt-work" n="03" kicker="What we tested" title="Most of what we tried did not earn a place."
          lead="Each branch was tested against pre-declared rules on data it was not tuned on. The negative results are part of the result.">
          <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
            <div>
              <div className="label mb-2">What didn’t work</div>
              <ul className="space-y-2">
                {notKept.map((f) => <FunnelRow key={f.name} f={f} />)}
              </ul>
            </div>
            <div>
              <div className="label mb-2">What generalized</div>
              <ul className="space-y-2">
                {kept.map((f) => <FunnelRow key={f.name} f={f} />)}
              </ul>
              <p className="text-[13px] text-ink-2 leading-relaxed mt-4 panel p-3">
                The simplest signal that generalized was rover position. More complex signals — a semantic model, telemetry context, perceptual hashing, a
                learned quality detector and image embeddings — either failed validation or added nothing measurable outside development.
              </p>
            </div>
          </div>
        </Section>

        {/* 5 · GENERALIZATION */}
        <Section n="04" kicker="Generalization" title="One result, four separate periods."
          lead="Development, two validation periods and a final held-out test, each reported on its own. The test interval was frozen before any image was downloaded and used once.">
          <div className="space-y-6">
            <FourPeriod />
            <EmbeddingGain />
          </div>
        </Section>

        {/* TIMELINE */}
        <Section n="05" kicker="How we got here" title="Not one benchmark run."
          lead="Every stage is a git tag. Configurations and pass/fail rules were committed before the data that tested them.">
          <ol className="border-l border-line ml-1 space-y-3">
            {REL.reproducibility.timeline.map((t) => (
              <li key={t.tag} className="pl-4 relative">
                <span className="absolute -left-[4px] top-1.5 w-[7px] h-[7px] bg-ink-3" />
                <div className="text-[13px] text-ink">{t.label}</div>
                <div className="mono text-[10px] text-ink-4">{t.tag} · {t.commit} · {t.date.slice(0, 16).replace("T", " ")}</div>
              </li>
            ))}
          </ol>
        </Section>

        {/* 6 · REPLAY */}
        <Section n="06" kicker="Mission replay" title="Watch the held-out traverses replay.">
          <div className="grid gap-3 md:grid-cols-2">
            <LinkCard href="/final-test" title="Final test replay" chip="HISTORICAL REPLAY · sols 950–979"
              body="Rover path, every archived traverse frame, the frames POSITION keeps, the bandwidth meter, 5 m coverage and stereo state — SEND ALL vs POSITION." />
            {PUBLIC_RELEASE ? (
              <LinkCard href="/telemetry" title="Phase 1–2 telemetry study (archive)" chip="REMS / RAD · STATIC ARCHIVE"
                body="The earlier telemetry-triage study. Its interactive mission-control replay needs the local pipeline API (npm run demo) and is not part of the public site." />
            ) : (
              <LinkCard href="/control" title="Telemetry mission control (Phase 1–2)" chip="MISSION REPLAY · REMS / RAD"
                body="The earlier telemetry-triage replay: candidate events, bounded decisions and relay-pass scheduling on real REMS and RAD records." />
            )}
          </div>
        </Section>

        {/* 7 · RESEARCH */}
        <Section n="07" kicker="Research" title="Read the method, the results and the limits.">
          <div className="grid gap-3 md:grid-cols-3">
            <LinkCard href="/research" title="Research overview" chip="PAPER · REPORTS · FIGURES" body="Technical paper, phase reports, methodology, architecture and figures." />
            <LinkCard href="/reproducibility" title="Reproducibility" chip="HASHES · TAGS · SEEDS" body="Periods, config hashes, commits, seeds, dataset hashes and the run order." />
            <LinkCard href="/limitations" title="Limitations" chip="READ FIRST" body="Survivorship bias, simulated compressed tier, PLACES interpolation, one rover, one camera." />
          </div>
        </Section>

        {/* 8 · OPEN SOURCE / REPRODUCIBILITY */}
        <Section n="08" kicker="Reproducibility" title="Frozen before it was tested.">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="panel p-4 space-y-2 min-w-0">
              <div className="label">Final test ordering (from git and the file system)</div>
              <Row k="config committed" v={REL.reproducibility.frozen_before_download.config_commit_time} />
              <Row k="first test image written" v={REL.reproducibility.frozen_before_download.first_test_image_written.slice(0, 19)} />
              <Row k="config before download" v={REL.reproducibility.frozen_before_download.config_before_download ? "yes" : "NO"} />
              <Row k="final config hash" v={`${H.config_hash.slice(0, 20)}…`} />
            </div>
            <div className="panel p-4 space-y-2 min-w-0">
              <div className="label">Artifact structure</div>
              <pre className="mono text-[11px] text-ink-2 leading-5 overflow-x-auto">{`config/phase3_final_test_config.json   frozen criterion + source hashes
data/splits/                            dev / validation / test intervals
data/manifests/navcam_*.json            URLs, labels, SHA-256 per product
artifacts/phase3_final/<run>/           results.json · run_manifest.json
docs/release/science-artifacts.json     ${REL.reproducibility.integrity.files} artifact hashes`}</pre>
            </div>
          </div>
        </Section>
      </main>
      <ReleaseFooter />
    </div>
  );
}

function Kpi({ v, k, note }: { v: string; k: string; note: string }) {
  return (
    <div className="px-4 py-4 border-line [&:not(:last-child)]:border-r">
      <dd className="mono text-[30px] sm:text-[36px] leading-none text-ink">{v}</dd>
      <dt className="text-[12px] text-ink-2 mt-2">{k}</dt>
      <div className="mono text-[10px] text-ink-4 mt-1">{note}</div>
    </div>
  );
}

function Stat({ k, v, sub }: { k: string; v: string; sub?: string }) {
  return (
    <div>
      <dt className="label">{k}</dt>
      <dd className="mono text-[18px] text-ink mt-1">{v}</dd>
      {sub && <div className="mono text-[10px] text-ink-4">{sub}</div>}
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-4 text-[12px]">
      <span className="text-ink-3">{k}</span>
      <span className="mono text-ink-2 text-right break-all">{v}</span>
    </div>
  );
}

function FunnelRow({ f }: { f: (typeof REL.funnel)[number] }) {
  return (
    <li className="panel p-3">
      <div className="flex flex-wrap items-baseline gap-2">
        <span className="text-[13px] text-ink">{f.name}</span>
        <span className="chip" style={{ color: VERDICT_COLOR[f.verdict], borderColor: "var(--line-2)" }}>{f.verdict}</span>
        <span className="mono text-[10px] text-ink-4 ml-auto">{f.phase}</span>
      </div>
      <p className="text-[12px] text-ink-3 mt-1 leading-snug">{f.evidence}</p>
      <Source path={f.source} />
    </li>
  );
}

function LinkCard({ href, title, chip, body }: { href: string; title: string; chip: string; body: string }) {
  return (
    <Link href={href} className="panel p-4 block hover:border-ink-4 transition-colors">
      <span className="chip text-ink-3">{chip}</span>
      <div className="text-[15px] text-ink mt-2">{title} →</div>
      <p className="text-[12px] text-ink-3 mt-1 leading-snug">{body}</p>
    </Link>
  );
}
