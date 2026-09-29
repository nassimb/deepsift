"use client";

import { useState } from "react";
import { copyImageToClipboard } from "@/lib/comms/clipboardImage";
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

/** PNG/JPEG files to attach on X (X does not accept SVG). Same-origin, so the browser downloads them directly. */
export function AttachFiles({ files, testid = "attach" }: { files: { url: string; format: string }[]; testid?: string }) {
  if (!files.length) return <div className="text-[11px] text-ink-4" data-testid={`${testid}-none`}>No attachable image — record or capture it yourself (save as PNG or JPEG).</div>;
  return (
    <div className="flex flex-wrap items-center gap-2" data-testid={testid}>
      <span className="text-[11px] text-ink-3">Attach on X:</span>
      {files.map((f) => (
        <span key={f.url} className="flex flex-wrap gap-1 max-w-full">
          <a className="btn" href={f.url} download data-testid={`${testid}-file`} data-format={f.format} title={f.url.split("/").pop()}>
            Download {f.format}{files.length > 1 ? ` ${files.indexOf(f) + 1}` : ""}
          </a>
          <CopyImageButton url={f.url} testid={`${testid}-copy`} />
        </span>
      ))}
    </div>
  );
}

export function CopyImageButton({ url, testid = "copy-image" }: { url: string; testid?: string }) {
  const [state, setState] = useState<"idle" | "ok" | "fail">("idle");
  return (
    <button type="button" className="btn" data-testid={testid} onClick={async () => {
      setState((await copyImageToClipboard(url)) ? "ok" : "fail");
      setTimeout(() => setState("idle"), 2200);
    }}>
      {state === "ok" ? "IMAGE COPIED — ⌘V in X" : state === "fail" ? "COPY FAILED — download it" : "Copy image"}
    </button>
  );
}
