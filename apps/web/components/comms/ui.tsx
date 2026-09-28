"use client";

import { useState } from "react";
import type { Status } from "@/lib/comms/store";

export const STATUS_COLOR: Record<Status, string> = {
  IDEA: "var(--ink-3)",
  DRAFT: "var(--ink-2)",
  APPROVED: "var(--a-full)",
  SCHEDULED_ON_X: "var(--s-warn)",
  POSTED: "var(--s-good)",
  REJECTED: "var(--s-critical)",
};

export function Chip({ children, color, testid }: { children: React.ReactNode; color?: string; testid?: string }) {
  return (
    <span data-testid={testid} className="mono text-[10px] tracking-[0.12em] uppercase px-1.5 py-0.5 border" style={{ color: color ?? "var(--ink-3)", borderColor: color ?? "var(--line-2)" }}>
      {children}
    </span>
  );
}

export function StatusChip({ status }: { status: Status }) {
  return <Chip color={STATUS_COLOR[status]} testid="status">{status}</Chip>;
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      ta.remove();
      return ok;
    } catch {
      return false;
    }
  }
}

export function CopyButton({ text, label = "Copy", testid = "copy" }: { text: string; label?: string; testid?: string }) {
  const [state, setState] = useState<"idle" | "ok" | "fail">("idle");
  return (
    <button type="button" className="btn" data-testid={testid} onClick={async () => {
      const ok = await copyText(text);
      setState(ok ? "ok" : "fail");
      setTimeout(() => setState("idle"), 1800);
    }}>
      {state === "ok" ? "COPIED" : state === "fail" ? "COPY FAILED" : label}
    </button>
  );
}

export function Section({ title, children, right, testid }: { title: string; children: React.ReactNode; right?: React.ReactNode; testid?: string }) {
  return (
    <section className="space-y-3" data-testid={testid}>
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line pb-1.5">
        <h2 className="label">{title}</h2>
        {right}
      </div>
      {children}
    </section>
  );
}
