import { fetchDsn, fetchDsnNames } from "@/lib/observatory/fetchers";
import { dsnContacts } from "@/lib/observatory/parsers";
import { liveJson } from "@/lib/observatory/route";

export const dynamic = "force-dynamic";

let names: { at: number; map: Record<string, string> } | null = null;

export async function GET() {
  if (!names || Date.now() - names.at > 86_400_000) {
    const n = await fetchDsnNames();
    if (n.data) names = { at: Date.now(), map: n.data };
  }
  const r = await fetchDsn();
  if (!r.data) return liveJson("dsn", { error: r.meta.error ?? "no data", meta: r.meta }, false);
  return liveJson("dsn", { meta: r.meta, sourceTime: r.data.sourceTime, stations: r.data.stations, dishes: r.data.dishes, contacts: dsnContacts(r.data, names?.map ?? {}) }, true);
}
