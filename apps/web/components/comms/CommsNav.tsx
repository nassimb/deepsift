"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS: [string, string][] = [
  ["/admin/comms", "Today"],
  ["/admin/comms/library", "Library"],
  ["/admin/comms/calendar", "Calendar"],
  ["/admin/comms/history", "History"],
  ["/admin/comms/review", "Weekly review"],
  ["/admin/comms/assets", "Assets"],
];

export function CommsNav() {
  const path = usePathname();
  return (
    <nav className="flex flex-wrap gap-x-3 gap-y-1 text-[12px]" aria-label="Comms console">
      {LINKS.map(([h, l]) => {
        const active = path === h;
        return (
          <Link key={h} href={h} aria-current={active ? "page" : undefined} className={active ? "text-ink underline underline-offset-4" : "text-ink-3 hover:text-ink"}>
            {l}
          </Link>
        );
      })}
    </nav>
  );
}
