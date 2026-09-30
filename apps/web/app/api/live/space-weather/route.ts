import { fetchNoaa } from "@/lib/observatory/fetchers";
import { liveJson } from "@/lib/observatory/route";

export const dynamic = "force-dynamic";

export async function GET() {
  const r = await fetchNoaa();
  if (!r.data) return liveJson("noaa", { error: r.meta.error ?? "no data", meta: r.meta }, false);
  // last 6 h at source (1-minute) resolution
  const cutoff = new Date(Date.now() - 6 * 3_600_000).toISOString();
  const samples = r.data.filter((s) => s.time >= cutoff);
  // plasma and field arrive on slightly different minutes: report the latest of each with its own time (no merging, no interpolation)
  const latestPlasma = [...r.data].reverse().find((x) => x.speed !== null || x.density !== null || x.temperature !== null) ?? null;
  const latestField = [...r.data].reverse().find((x) => x.bt !== null || x.bz !== null) ?? null;
  return liveJson("noaa", { meta: r.meta, latest: r.data.at(-1) ?? null, latestPlasma, latestField, samples, context: "Earth / L1 space environment — not Mars conditions" }, true);
}
