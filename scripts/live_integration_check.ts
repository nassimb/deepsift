// One-shot live check of every Live Observatory source (queries each source ONCE; never used in CI).
//   node scripts/live_integration_check.ts
import { fetchCuriosity, fetchDonki, fetchDsn, fetchHorizons, fetchNoaa, fetchPerseverance, type Fetched } from "../apps/web/lib/observatory/fetchers.ts";
import { dsnContacts } from "../apps/web/lib/observatory/parsers.ts";

const now = new Date();
const rows: [string, Promise<Fetched<unknown>>, (d: any) => string][] = [
  ["DSN", fetchDsn(), (d) => `${d.dishes.length} dishes, ${dsnContacts(d).length} active links, source time ${d.sourceTime}`],
  ["NOAA", fetchNoaa(), (d) => `${d.length} active L1 samples, latest ${d.at(-1)?.time} (${d.at(-1)?.source}) ${d.at(-1)?.speed} km/s`],
  ["DONKI", fetchDonki(now), (d) => `${d.length} events in 7 days, newest ${d[0]?.id ?? "—"}`],
  ["HORIZONS", fetchHorizons(now), (d) => `${(d.distanceKm / 1e6).toFixed(1)} million km, light time ${d.lightTimeMin.toFixed(2)} min (API ${d.apiVersion})`],
  ["PERSEVERANCE", fetchPerseverance(5), (d) => `${d.length} images, newest ${d[0]?.imageId} (${d[0]?.cameraLabel}, sol ${d[0]?.sol})`],
  ["CURIOSITY", fetchCuriosity(5), (d) => `${d.length} images, newest ${d[0]?.imageId} (${d[0]?.cameraLabel}, sol ${d[0]?.sol})`],
];
let bad = 0;
for (const [name, p, describe] of rows) {
  const r = await p;
  const status = r.data && r.meta.ok ? "OK" : r.data ? "DEGRADED" : "FAILED";
  if (status !== "OK") bad++;
  console.log(`${name.padEnd(14)}${status.padEnd(10)}${(r.meta.durationMs + " ms").padEnd(10)}${r.data ? describe(r.data) : r.meta.error}`);
}
process.exit(bad ? 1 : 0);
