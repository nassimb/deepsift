/* Read-only proxy to the DEEPSIFT live collector, when one is configured (LIVE_COLLECTOR_URL, server-only).
   On the public deployment it is unset until a host is chosen → 404 → the page runs in Tier 0 mode. */
export const dynamic = "force-dynamic";

const ALLOWED = new Set(["status", "events", "stream", "timeline", "images", "dsn-contacts"]);

export async function GET(req: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const base = process.env.LIVE_COLLECTOR_URL;
  const { path } = await ctx.params;
  if (path.length !== 1 || !ALLOWED.has(path[0])) return new Response("not found", { status: 404 });
  if (!base) return Response.json({ ok: false, mode: "tier0", error: "collector not configured (Tier 0 mode)" }, { headers: { "cache-control": "public, s-maxage=60" } });
  const url = new URL(`/${path[0]}`, base);
  new URL(req.url).searchParams.forEach((v, k) => url.searchParams.set(k, v));
  try {
    const up = await fetch(url, { cache: "no-store", headers: { accept: path[0] === "stream" ? "text/event-stream" : "application/json" }, signal: req.signal });
    const headers = new Headers({ "content-type": up.headers.get("content-type") ?? "application/json", "cache-control": "no-store", "x-robots-tag": "noindex" });
    return new Response(up.body, { status: up.status, headers });
  } catch {
    return Response.json({ ok: false, error: "collector unreachable" }, { status: 503 });
  }
}
