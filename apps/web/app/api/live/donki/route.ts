import { fetchDonki } from "@/lib/observatory/fetchers";
import { liveJson } from "@/lib/observatory/route";

export const dynamic = "force-dynamic";

export async function GET() {
  const r = await fetchDonki(new Date(), 7);
  if (!r.data) return liveJson("donki", { error: r.meta.error ?? "no data", meta: r.meta }, false);
  return liveJson("donki", { meta: r.meta, partialError: r.meta.ok ? null : r.meta.error, events: r.data.slice(0, 80) }, r.meta.ok);
}
