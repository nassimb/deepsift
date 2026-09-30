/* Read-only proxy to the DEEPSIFT live collector, when one is configured (LIVE_COLLECTOR_URL, server-only; on the
   Raspberry Pi this is the collector's READ-ONLY listener behind the tunnel, authenticated with COLLECTOR_READ_TOKEN).
   On the public deployment it is unset until a host is chosen → 404 → the page runs in Tier 0 mode. */
export const dynamic = "force-dynamic";

const ALLOWED = new Set(["status", "events", "stream", "timeline", "images", "dsn-contacts", "healthz"]);

export async function GET(req: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const base = process.env.LIVE_COLLECTOR_URL;
  const { path } = await ctx.params;
  if (path.length !== 1 || !ALLOWED.has(path[0])) return new Response("not found", { status: 404 });
  if (!base) return Response.json({ ok: false, mode: "tier0", error: "collector not configured (Tier 0 mode)" }, { headers: { "cache-control": "public, s-maxage=60" } });
  const url = new URL(`/${path[0]}`, base);
  new URL(req.url).searchParams.forEach((v, k) => url.searchParams.set(k, v));
  try {
    const headers: Record<string, string> = { accept: path[0] === "stream" ? "text/event-stream" : "application/json" };
    // server-only read token for the collector's public listener (never sent to browsers)
    if (process.env.COLLECTOR_READ_TOKEN) headers.authorization = `Bearer ${process.env.COLLECTOR_READ_TOKEN}`;
    const up = await fetch(url, { cache: "no-store", headers, signal: req.signal });
    const out = new Headers({ "content-type": up.headers.get("content-type") ?? "application/json", "cache-control": "no-store", "x-robots-tag": "noindex" });
    return new Response(up.body, { status: up.status, headers: out });
  } catch {
    return Response.json({ ok: false, error: "collector unreachable" }, { status: 503 });
  }
}
