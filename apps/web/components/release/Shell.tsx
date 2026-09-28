import Link from "next/link";
import { H, REL } from "@/lib/release";

import { GITHUB_URL, SiteFooter } from "@/components/site/SiteFooter";

export { GITHUB_URL };
export { NavLinks, PUBLIC_NAV } from "@/components/release/NavLinks";
import { NavLinks } from "@/components/release/NavLinks";

/** Full-width header row shared by Mission Control and every non-home page, so the logo and the menu sit in exactly the
 *  same place on each page (the homepage keeps its own centered ReleaseTopBar). */
export function TopBarRow({ label }: { label: string }) {
  return (
    <div className="px-3 sm:px-4 h-11 flex items-center gap-3">
      <Link href="/" className="mono font-semibold tracking-[0.2em] text-[13px] text-ink shrink-0">DEEPSIFT</Link>
      <span className="mono text-[11px] tracking-[0.12em] text-ink shrink-0 hidden sm:inline">{label}</span>
      <NavLinks />
    </div>
  );
}

export function PageTopBar({ label }: { label: string }) {
  return (
    <header className="sticky top-0 z-20 border-b border-line bg-bg/95 backdrop-blur">
      <TopBarRow label={label} />
    </header>
  );
}

export function ReleaseTopBar() {
  return (
    <header className="sticky top-0 z-20 border-b border-line bg-bg/95 backdrop-blur">
      <div className="max-w-[1240px] mx-auto px-4 sm:px-6 h-11 flex items-center gap-4">
        <Link href="/" className="mono font-semibold tracking-[0.2em] text-[13px] text-ink shrink-0">DEEPSIFT</Link>
        <span className="chip text-ink-3 hidden md:inline">v1 · RESEARCH RELEASE</span>
        <NavLinks />
      </div>
    </header>
  );
}

export function Section({ id, n, kicker, title, lead, children }: { id?: string; n?: string; kicker: string; title?: string; lead?: React.ReactNode; children?: React.ReactNode }) {
  return (
    <section id={id} className="border-b border-line scroll-mt-12">
      <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-12 sm:py-14">
        <div className="flex items-baseline gap-3 mb-2">
          {n && <span className="mono text-[11px] text-ink-4">{n}</span>}
          <span className="label">{kicker}</span>
        </div>
        {title && <h2 className="text-[22px] sm:text-[28px] leading-tight font-medium text-ink max-w-3xl">{title}</h2>}
        {lead && <div className="text-[14px] sm:text-[15px] text-ink-2 leading-relaxed max-w-3xl mt-2">{lead}</div>}
        {children && <div className="mt-6">{children}</div>}
      </div>
    </section>
  );
}

export function Source({ path }: { path: string }) {
  return <span className="mono text-[10px] text-ink-4 break-all">source · {path}</span>;
}

export function ReleaseFooter() {
  return (
    <footer>
      <SiteFooter />
      <div className="max-w-[1240px] mx-auto px-4 sm:px-6 pb-8 text-[12px] text-ink-3 space-y-2">
      <p>
        DEEPSIFT is an independent research prototype. It is not flight software, is not validated by or affiliated with NASA or JPL, and
        replays archived Planetary Data System observations — which contain only what the mission actually downlinked.
      </p>
      <p className="mono text-[10px] text-ink-4">
        Final test config {H.config_hash.slice(0, 12)}… (commit {H.config_commit}) · result commit {H.result_commit} · release data built from
        frozen artifacts at {REL.git_head} · integrity: {REL.reproducibility.integrity.files} scientific artifacts, aggregate SHA-256{" "}
        {REL.reproducibility.integrity.aggregate_sha256.slice(0, 12)}…
      </p>
      </div>
    </footer>
  );
}
