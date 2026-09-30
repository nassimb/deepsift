/* Private collector console — /admin/live-data. Gated by proxy.ts (nassimb only) and re-checked here.
   Reads the local collector server-side; FORCE REFRESH uses a server-only token and never reaches the browser. */
import type { Metadata } from "next";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { adminAccess } from "@/lib/admin/access";
import { fmtAge } from "@/lib/observatory/health";
import { SOURCES } from "@/lib/observatory/registry";

export const metadata: Metadata = { title: "Live data · admin", robots: { index: false, follow: false, nocache: true } };
export const dynamic = "force-dynamic";

type Src = { id: string; name: string; health: string; enabled: boolean; intervalS: number; lastPoll: string | null; lastSuccess: string | null; lastSourceTime: string | null; lastIngest: string | null; lastError: string | null; consecutiveErrors: number; pollMs: number | null; bytes: number | null; parse: string | null; status: number | null; dedupeDrops: number; parserVersion: string };
type Status = { version: string; startedAt: string; uptimeS: number; dbBytes: number; eventsTotal: number; eventsToday: number; lastEventAt: string | null; dbPath: string; sources: Src[] };
type Poll = { source_id: string; at: string; status: number; ok: number; not_modified: number; duration_ms: number; bytes: number; parse: string; error: string | null; new_events: number; dedupe_drops: number };

async function get<T>(path: string): Promise<T | null> {
  const base = process.env.LIVE_COLLECTOR_URL;
  if (!base) return null;
  try {
    const headers: Record<string, string> = process.env.COLLECTOR_READ_TOKEN ? { authorization: `Bearer ${process.env.COLLECTOR_READ_TOKEN}` } : {};
    const r = await fetch(new URL(path, base), { cache: "no-store", headers });
    return r.ok ? ((await r.json()) as T) : null;
  } catch {
    return null;
  }
}

async function refresh(formData: FormData) {
  "use server";
  const session = await auth();
  if (adminAccess(session?.user) !== "ok") return;
  // admin actions go to the collector's full local API only (never exposed through the tunnel)
  const base = adminBase();
  const token = process.env.COLLECTOR_ADMIN_TOKEN;
  const source = String(formData.get("source") ?? "");
  if (!base || !token || !SOURCES.some((s) => s.id === source)) return;
  await fetch(new URL(`/admin/refresh?source=${source}`, base), { method: "POST", headers: { authorization: `Bearer ${token}` } }).catch(() => {});
  revalidatePath("/admin/live-data");
}

/** Force refresh needs the full (admin) API: COLLECTOR_ADMIN_URL, or a local LIVE_COLLECTOR_URL. Behind a tunnel it is unavailable by design. */
function adminBase(): string | null {
  if (process.env.COLLECTOR_ADMIN_URL) return process.env.COLLECTOR_ADMIN_URL;
  const u = process.env.LIVE_COLLECTOR_URL;
  return u && /^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?\/?$/.test(u) ? u : null;
}

const C: Record<string, string> = { ONLINE: "var(--s-good)", DEGRADED: "var(--s-warn)", STALE: "var(--s-serious)", OFFLINE: "var(--s-critical)" };
const ago = (iso: string | null) => (iso ? `${fmtAge((Date.now() - Date.parse(iso)) / 1000)} ago` : "—");

export default async function LiveDataAdmin() {
  const session = await auth();
  const access = adminAccess(session?.user);
  if (access === "login") redirect("/admin/login?next=/admin/live-data");
  if (access === "forbidden") return <main className="p-8 obs-mono text-[13px]">403 FORBIDDEN</main>;
  const status = await get<Status>("/status");
  const polls = (await get<{ polls: Poll[] }>("/polls?limit=80"))?.polls ?? [];
  const canRefresh = !!process.env.COLLECTOR_ADMIN_TOKEN && !!adminBase();
  return (
    <main className="max-w-[1400px] mx-auto px-4 sm:px-6 py-6 space-y-6">
      <div className="flex flex-wrap items-baseline gap-3">
        <h1 className="obs-mono text-[18px] tracking-[0.12em] text-ink">LIVE DATA · COLLECTOR CONSOLE</h1>
        <span className="obs-mono text-[10px] text-ink-4 border border-line-2 px-1.5 py-0.5">PRIVATE</span>
        <a href="/data-stream" className="text-[12px] underline text-ink-3 ml-auto">Public observatory →</a>
      </div>
      {!status ? (
        <div className="panel p-4 text-[13px] text-ink-2" data-testid="collector-offline">
          Collector not reachable{process.env.LIVE_COLLECTOR_URL ? ` at ${process.env.LIVE_COLLECTOR_URL}` : " (LIVE_COLLECTOR_URL not set — Tier 0 only)"}. Start it locally with <code className="obs-mono">services/collector/run-local.sh</code>.
        </div>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6 obs-mono" data-testid="collector-kpis">
            {[["version", status.version], ["uptime", fmtAge(status.uptimeS)], ["SQLite size", `${(status.dbBytes / 1e6).toFixed(1)} MB`], ["events stored", String(status.eventsTotal)], ["events today", String(status.eventsToday)], ["last event", ago(status.lastEventAt)]].map(([k, v]) => (
              <div key={k} className="panel p-3"><div className="text-[9px] tracking-[0.15em] text-ink-4">{k.toUpperCase()}</div><div className="text-[15px] text-ink">{v}</div></div>
            ))}
          </div>
          <div className="overflow-x-auto panel">
            <table className="w-full text-[11.5px] obs-mono" data-testid="collector-sources">
              <thead><tr className="text-left border-b border-line">{["source", "status", "interval", "last poll", "last success", "source time", "last ingest", "poll", "bytes", "parse", "dedupe drops", "errors", "last error", ""].map((h) => <th key={h} className="px-2 py-2 label font-normal">{h}</th>)}</tr></thead>
              <tbody>
                {status.sources.map((s) => (
                  <tr key={s.id} className="border-b border-line align-top">
                    <td className="px-2 py-1.5 text-ink">{s.name}<div className="text-[9.5px] text-ink-4">{s.parserVersion}</div></td>
                    <td className="px-2 py-1.5" style={{ color: C[s.health] }}>{s.enabled ? s.health : "DISABLED"}</td>
                    <td className="px-2 py-1.5 text-ink-3">{s.intervalS} s</td>
                    <td className="px-2 py-1.5 text-ink-2">{ago(s.lastPoll)}</td>
                    <td className="px-2 py-1.5 text-ink-2">{ago(s.lastSuccess)}</td>
                    <td className="px-2 py-1.5 text-ink-3">{s.lastSourceTime?.slice(0, 19).replace("T", " ") ?? "—"}</td>
                    <td className="px-2 py-1.5 text-ink-3">{ago(s.lastIngest)}</td>
                    <td className="px-2 py-1.5 text-ink-3">{s.pollMs ?? "—"} ms</td>
                    <td className="px-2 py-1.5 text-ink-3">{s.bytes ? `${(s.bytes / 1024).toFixed(0)} KB` : "—"}</td>
                    <td className="px-2 py-1.5 text-ink-3">{s.parse ?? "—"}</td>
                    <td className="px-2 py-1.5 text-ink-3">{s.dedupeDrops}</td>
                    <td className="px-2 py-1.5 text-ink-3">{s.consecutiveErrors}</td>
                    <td className="px-2 py-1.5 max-w-[260px] break-words" style={{ color: s.lastError ? "var(--s-warn)" : "var(--ink-4)" }}>{s.lastError ?? "—"}</td>
                    <td className="px-2 py-1.5">
                      {canRefresh && (
                        <form action={refresh}><input type="hidden" name="source" value={s.id} /><button type="submit" className="btn" data-testid={`refresh-${s.id}`}>Force refresh</button></form>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="text-[11px] text-ink-4">Collector uptime since {status.startedAt} · store {status.dbPath}. {canRefresh ? "Force refresh triggers one poll (server-to-server token); it is not exposed publicly." : "Force refresh is available only on the collector host (it is never exposed through the tunnel): curl -X POST -H \"Authorization: Bearer $COLLECTOR_ADMIN_TOKEN\" http://127.0.0.1:8790/admin/refresh?source=dsn"}</div>
          <div className="overflow-x-auto panel">
            <table className="w-full text-[11px] obs-mono" data-testid="collector-polls">
              <thead><tr className="text-left border-b border-line">{["at", "source", "HTTP", "ok", "304", "ms", "bytes", "parse", "new events", "dedupe drops", "error"].map((h) => <th key={h} className="px-2 py-1.5 label font-normal">{h}</th>)}</tr></thead>
              <tbody>
                {polls.map((p, i) => (
                  <tr key={i} className="border-b border-line">
                    <td className="px-2 py-1 text-ink-3">{p.at.slice(11, 19)}</td><td className="px-2 py-1 text-ink-2">{p.source_id}</td><td className="px-2 py-1 text-ink-3">{p.status}</td>
                    <td className="px-2 py-1" style={{ color: p.ok ? "var(--s-good)" : "var(--s-critical)" }}>{p.ok ? "yes" : "no"}</td><td className="px-2 py-1 text-ink-4">{p.not_modified ? "304" : ""}</td>
                    <td className="px-2 py-1 text-ink-3">{p.duration_ms}</td><td className="px-2 py-1 text-ink-3">{p.bytes}</td><td className="px-2 py-1 text-ink-3">{p.parse}</td>
                    <td className="px-2 py-1 text-ink-2">{p.new_events}</td><td className="px-2 py-1 text-ink-3">{p.dedupe_drops}</td><td className="px-2 py-1" style={{ color: "var(--s-warn)" }}>{p.error ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </main>
  );
}
