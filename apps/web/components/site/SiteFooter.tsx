"use client";

/* Site footer: GitHub, contact (address assembled only on click, so it is not in the page HTML), updates sign-up.
   The sign-up posts to /api/subscribe only when the visitor submits; nothing is requested on page load. */
import { useState } from "react";

export const GITHUB_URL = "https://github.com/nassimb/deepsift";
const CONTACT = ["nassimmontreal", "gmail.com"];

export function SiteFooter() {
  const [email, setEmail] = useState("");
  const [website, setWebsite] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "ok" | "error">("idle");
  const [msg, setMsg] = useState("");

  const contact = () => {
    window.location.href = `mailto:${CONTACT.join("@")}?subject=${encodeURIComponent("DEEPSIFT")}`;
  };
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setState("sending");
    try {
      const r = await fetch("/api/subscribe", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ email, website }) });
      const j = (await r.json()) as { ok: boolean; error?: string };
      if (j.ok) {
        setState("ok");
        setMsg("Thanks — you're on the list for DEEPSIFT updates.");
        setEmail("");
      } else {
        setState("error");
        setMsg(j.error ?? "Something went wrong.");
      }
    } catch {
      setState("error");
      setMsg("Could not reach the server — please try again later.");
    }
  };

  return (
    <div className="border-t border-line">
      <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-6 grid gap-6 md:grid-cols-[1fr_minmax(0,420px)] items-start">
        <div className="space-y-2">
          <div className="mono tracking-[0.2em] text-[12px] text-ink">DEEPSIFT</div>
          <div className="flex flex-wrap gap-2">
            <a href={GITHUB_URL} target="_blank" rel="noreferrer" className="btn">GitHub ↗</a>
            <button type="button" className="btn" onClick={contact}>Contact ✉</button>
          </div>
          <p className="text-[11px] text-ink-4">Questions, criticism or collaboration — the contact button opens your e-mail app.</p>
        </div>
        <form onSubmit={submit} className="space-y-2" aria-label="Get DEEPSIFT updates">
          <label htmlFor="updates-email" className="label block">Get DEEPSIFT updates</label>
          <div className="flex gap-2">
            <input id="updates-email" type="email" required autoComplete="email" placeholder="you@example.com" value={email}
              onChange={(e) => setEmail(e.target.value)} className="min-w-0 flex-1 bg-panel-2 border border-line text-ink text-[13px] px-3 py-2" />
            <input type="text" tabIndex={-1} autoComplete="off" aria-hidden="true" value={website} onChange={(e) => setWebsite(e.target.value)}
              className="hidden" name="website" />
            <button type="submit" className="btn" data-active="true" disabled={state === "sending"} style={{ padding: "8px 14px" }}>
              {state === "sending" ? "…" : "Subscribe"}
            </button>
          </div>
          <p className="text-[11px] min-h-[1em]" role="status" style={{ color: state === "error" ? "var(--s-warn)" : "var(--ink-3)" }}>
            {msg || "Occasional research updates. Your e-mail is stored only for this list; ask to be removed any time via Contact."}
          </p>
        </form>
      </div>
    </div>
  );
}
