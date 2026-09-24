"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api, type Status } from "@/lib/api";

const LINKS = [
  ["/control", "Mission Control"],
  ["/blackout", "Blackout"],
  ["/experiments", "Experiments"],
  ["/study", "Study"],
  ["/explorer", "Data Explorer"],
  ["/audit", "Audit"],
  ["/config", "Config"],
  ["/research", "Research"],
];

export function useStatus(pollMs = 5000) {
  const [status, setStatus] = useState<Status | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    const tick = () =>
      api<Status>("/api/status")
        .then((s) => alive && (setStatus(s), setErr(null)))
        .catch((e) => alive && setErr(String(e.message ?? e)));
    tick();
    const id = setInterval(tick, pollMs);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [pollMs]);
  return { status, err };
}

export function SourceBadges({ status, replay = true }: { status: Status | null; replay?: boolean }) {
  if (!status) return null;
  const src = status.data_source;
  const srcLabel =
    src === "NASA_PDS" ? "NASA PDS · REAL DATA" : src === "LOCAL_NASA_SAMPLE" ? "LOCAL NASA SAMPLE" : "SYNTHETIC TEST DATA";
  const eng = status.engine;
  return (
    <div className="flex items-center gap-2">
      {replay && (
        <span className="chip" style={{ color: "var(--ink)", borderColor: "var(--ink-4)" }} title="Historical data replayed as if arriving now. Not a live feed.">
          MISSION REPLAY
        </span>
      )}
      <span className="chip" style={{ color: src === "SYNTHETIC_TEST_DATA" ? "var(--s-warn)" : "var(--ink-2)" }} title="Where the bytes came from">
        {srcLabel}
      </span>
      <span
        className="chip"
        style={{ color: eng?.is_real_model ? "var(--ink-2)" : "var(--s-warn)", borderColor: eng?.is_real_model ? undefined : "#5a4412" }}
        title={eng?.is_real_model ? "Decisions from a real model" : "Heuristic stand-in; not Jev. Set TYPESAFE_API_KEY to use Jev."}
      >
        ENGINE {eng?.is_real_model ? eng.name.toUpperCase() : "MOCK · HEURISTIC"}
      </span>
      <span className="chip" style={{ color: status.deep_available ? "var(--ink-2)" : "var(--ink-4)" }}>
        DEEP {status.deep_available ? status.deep_provider?.toUpperCase() : "UNAVAILABLE"}
      </span>
    </div>
  );
}

export function Nav({ right }: { right?: React.ReactNode }) {
  const path = usePathname();
  const { status, err } = useStatus();
  return (
    <header className="border-b border-line bg-panel">
      <div className="flex items-center gap-6 px-4 h-11">
        <Link href="/" className="flex items-baseline gap-3 shrink-0">
          <span className="mono font-semibold tracking-[0.2em] text-[13px] text-ink">DEEPSIFT</span>
          <span className="label hidden lg:inline">Autonomous science triage</span>
        </Link>
        <nav className="flex items-center gap-1 overflow-x-auto">
          {LINKS.map(([href, label]) => (
            <Link
              key={href}
              href={href}
              className="mono text-[11px] uppercase tracking-[0.06em] px-2 py-1 whitespace-nowrap"
              style={{ color: path === href ? "var(--ink)" : "var(--ink-3)", borderBottom: path === href ? "1px solid var(--ink)" : "1px solid transparent" }}
            >
              {label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-3">
          {right}
          <span className="flex items-center gap-1.5 mono text-[11px]" title={err ?? status?.error ?? "pipeline API reachable"}>
            <span
              className={status?.online ? "" : "state-pulse"}
              style={{ width: 7, height: 7, borderRadius: 7, background: status?.online ? "var(--s-good)" : err ? "var(--s-critical)" : "var(--s-warn)" }}
            />
            <span style={{ color: "var(--ink-2)" }}>{status?.online ? "ONLINE" : err ? "API OFFLINE" : "STARTING"}</span>
          </span>
        </div>
      </div>
    </header>
  );
}
