"use client";

/* Public top navigation. The active page is read from the URL, so every page gets its underline without passing a prop. */
import Link from "next/link";
import { usePathname } from "next/navigation";

export const PUBLIC_NAV: [string, string][] = [
  ["/mission-control", "Mission control"],
  ["/final-test", "Final test"],
  ["/research", "Research"],
  ["/reproducibility", "Reproducibility"],
  ["/limitations", "Limitations"],
];
/** Same menu locally and in production. The Phase 1–2 telemetry cockpit (/control) is not linked; it stays reachable
 *  by URL in local mode (it needs the local FastAPI service). */
const LINKS: [string, string][] = PUBLIC_NAV;

export function NavLinks() {
  const path = usePathname();
  return (
    <nav className="ml-auto min-w-0 flex items-center gap-1 overflow-x-auto">
      {LINKS.map(([h, l]) => {
        const active = path === h || path.startsWith(`${h}/`);
        return (
          <Link key={h} href={h} aria-current={active ? "page" : undefined} className="mono text-[11px] uppercase tracking-[0.06em] px-2 py-1 whitespace-nowrap hover:text-ink"
            style={{ color: active ? "var(--ink)" : "var(--ink-3)", borderBottom: active ? "1px solid var(--ink)" : "1px solid transparent" }}>{l}</Link>
        );
      })}
    </nav>
  );
}
