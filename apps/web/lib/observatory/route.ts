/** Helpers for the public Tier 0 routes: CDN caching bounds upstream load to ~1 request per cache window, whatever the
 *  number of visitors. Errors are returned as data (ok:false) with a short cache so the page can show DEGRADED. */
import { SOURCE_BY_ID } from "./registry.ts";
import type { SourceId } from "./types.ts";

export function liveJson(src: SourceId, body: Record<string, unknown>, ok: boolean): Response {
  const s = SOURCE_BY_ID[src];
  const maxAge = ok ? s.cacheS : Math.min(15, s.cacheS);
  return new Response(JSON.stringify({ source: { id: s.id, name: s.name, provider: s.provider, classification: s.classification, parserVersion: s.parserVersion, attribution: s.attribution, cacheS: s.cacheS }, fetchedAt: new Date().toISOString(), ok, ...body }), {
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": `public, max-age=0, s-maxage=${maxAge}, stale-while-revalidate=${maxAge * 2}`,
      "x-robots-tag": "noindex",
    },
  });
}
