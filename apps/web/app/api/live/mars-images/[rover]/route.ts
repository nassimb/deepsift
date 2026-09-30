import { fetchCuriosity, fetchPerseverance } from "@/lib/observatory/fetchers";
import { liveJson } from "@/lib/observatory/route";

export const dynamic = "force-dynamic";
export const maxDuration = 60; // the Mars 2020 feed takes 12–15 s to respond

export async function GET(_req: Request, ctx: { params: Promise<{ rover: string }> }) {
  const { rover } = await ctx.params;
  if (rover !== "perseverance" && rover !== "curiosity") return new Response("not found", { status: 404 });
  const r = rover === "perseverance" ? await fetchPerseverance(40) : await fetchCuriosity(60);
  if (!r.data) return liveJson(rover, { error: r.meta.error ?? "no data", meta: r.meta }, false);
  const images = r.data.filter((i) => !i.thumbnail).slice(0, 30);
  return liveJson(rover, { meta: r.meta, images, note: "Newly PUBLISHED images (not live camera). Tier 0 cannot know when DEEPSIFT first saw them — that needs the collector." }, true);
}
