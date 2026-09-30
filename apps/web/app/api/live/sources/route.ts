import { RESEARCH_ARCHIVE, SOURCES } from "@/lib/observatory/registry";

export const dynamic = "force-static";

export function GET() {
  return Response.json({ sources: SOURCES, researchArchive: RESEARCH_ARCHIVE }, { headers: { "cache-control": "public, s-maxage=3600" } });
}
