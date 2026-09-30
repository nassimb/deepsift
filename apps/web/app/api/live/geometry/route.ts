import { fetchHorizons } from "@/lib/observatory/fetchers";
import { liveJson } from "@/lib/observatory/route";

export const dynamic = "force-dynamic";

export async function GET() {
  const r = await fetchHorizons(new Date());
  if (!r.data) return liveJson("horizons", { error: r.meta.error ?? "no data", meta: r.meta }, false);
  return liveJson("horizons", { meta: r.meta, geometry: r.data, label: "Computed by JPL Horizons — ephemeris, not telemetry" }, true);
}
