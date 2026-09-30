/** Source registry — every endpoint here was verified in the 2026-09-30 audit (docs/observatory.md). */
import type { SourceDef, SourceId } from "./types.ts";

export const DONKI_BASE = "https://ccmc.gsfc.nasa.gov/DONKI-API/get";
export const DSN_URL = "https://eyes.nasa.gov/dsn/data/dsn.xml";
export const DSN_CONFIG_URL = "https://eyes.nasa.gov/dsn/config.xml";
export const NOAA_WIND_URL = "https://services.swpc.noaa.gov/json/rtsw/rtsw_wind_1m.json";
export const NOAA_MAG_URL = "https://services.swpc.noaa.gov/json/rtsw/rtsw_mag_1m.json";
export const HORIZONS_URL = "https://ssd.jpl.nasa.gov/api/horizons.api";
export const PERSEVERANCE_URL = "https://mars.nasa.gov/rss/api/?feed=raw_images&category=mars2020&feedtype=json&page=0&order=date_received+desc";
export const CURIOSITY_URL = "https://mars.nasa.gov/api/v1/raw_image_items/?order=created_at%20desc&page=0&condition_1=msl:mission";

export const SOURCES: SourceDef[] = [
  {
    id: "dsn", name: "DSN Now", provider: "NASA/JPL", classification: "LIVE",
    officialUrl: "https://eyes.nasa.gov/dsn/dsn.html", endpoints: [DSN_URL, DSN_CONFIG_URL], documentedApi: false,
    sourceCadenceS: 5, pollS: 5, cacheS: 10, parserVersion: "dsn-xml/1",
    fields: ["complex", "antenna", "azimuth", "elevation", "wind", "activity", "uplink/downlink active", "signal type", "band", "data rate", "power", "spacecraft", "up/down range"],
    attribution: "NASA/JPL · Deep Space Network (DSN Now)", optional: true,
    notes: "Undocumented application data file used by the official DSN Now app (updates every 5 s). Not a published API: it may change without notice, so the adapter is optional and degrades gracefully. Frequency (always 0) and round-trip light time (usually -1) are not shown when unreported.",
  },
  {
    id: "noaa", name: "NOAA SWPC real-time solar wind", provider: "NOAA Space Weather Prediction Center", classification: "NEAR REAL-TIME",
    officialUrl: "https://www.swpc.noaa.gov/products/real-time-solar-wind", endpoints: [NOAA_WIND_URL, NOAA_MAG_URL], documentedApi: false,
    sourceCadenceS: 60, pollS: 300, cacheS: 60, parserVersion: "rtsw-1m/1",
    fields: ["time", "source spacecraft", "proton speed", "density", "temperature", "Bt", "Bx/By/Bz (GSM)", "quality flag"],
    attribution: "NOAA SWPC · Real-Time Solar Wind (L1)", optional: false,
    notes: "Public NOAA JSON data service. Each file holds 24 h of 1-minute samples from several L1 spacecraft; the `active` flag marks the operational source. Conditional GET + gzip.",
  },
  {
    id: "donki", name: "NASA DONKI", provider: "NASA CCMC (M2M)", classification: "NEAR REAL-TIME EVENTS",
    officialUrl: "https://ccmc.gsfc.nasa.gov/DONKI/", endpoints: ["CME", "FLR", "SEP", "IPS", "GST", "notifications"].map((t) => `${DONKI_BASE}/${t}`), documentedApi: true,
    sourceCadenceS: 600, pollS: 600, cacheS: 600, parserVersion: "donki-api/1",
    fields: ["official ID", "type", "event time", "class / location", "linked events", "detail link"],
    attribution: "NASA CCMC · DONKI (Space Weather Database Of Notifications, Knowledge, Information)", optional: false,
    notes: "New API base since 2026-09-30 (the old kauai.ccmc and api.nasa.gov/DONKI endpoints redirect). No API key. startDate and endDate are both required.",
  },
  {
    id: "horizons", name: "JPL Horizons", provider: "NASA/JPL Solar System Dynamics", classification: "CURRENT COMPUTED",
    officialUrl: "https://ssd.jpl.nasa.gov/horizons/", endpoints: [HORIZONS_URL], documentedApi: true,
    sourceCadenceS: 300, pollS: 300, cacheS: 300, parserVersion: "horizons-api-1.2/1",
    fields: ["RA / DEC", "Earth–Mars distance", "range-rate", "one-way light time", "solar elongation"],
    attribution: "NASA/JPL Horizons (computed ephemeris)", optional: false,
    notes: "Computed ephemeris, not telemetry. Server-side only (no browser CORS).",
  },
  {
    id: "perseverance", name: "Perseverance raw images", provider: "NASA Mars Exploration Program", classification: "NEWLY PUBLISHED",
    officialUrl: "https://mars.nasa.gov/mars2020/multimedia/raw-images/", endpoints: [PERSEVERANCE_URL], documentedApi: false,
    sourceCadenceS: 300, pollS: 300, cacheS: 300, parserVersion: "m2020-raw/1",
    fields: ["image ID", "camera", "sol", "LMST", "acquired (UTC)", "received on Earth", "image URLs", "dimensions", "credit"],
    attribution: "NASA/JPL-Caltech · Mars 2020 raw images", optional: false,
    notes: "Website feed (undocumented). Slow (12–15 s). Images are newly PUBLISHED, typically hours after acquisition.",
  },
  {
    id: "curiosity", name: "Curiosity raw images", provider: "NASA Mars Exploration Program", classification: "NEWLY PUBLISHED",
    officialUrl: "https://mars.nasa.gov/msl/multimedia/raw-images/", endpoints: [CURIOSITY_URL], documentedApi: false,
    sourceCadenceS: 180, pollS: 180, cacheS: 180, parserVersion: "msl-raw/1",
    fields: ["image ID", "instrument", "sol", "LMST", "acquired", "received on Earth", "published", "thumbnail flag", "image URL", "credit"],
    attribution: "NASA/JPL-Caltech · MSL raw images", optional: false,
    notes: "Website feed (undocumented). Images are newly PUBLISHED, typically hours after acquisition.",
  },
];

export const SOURCE_BY_ID = Object.fromEntries(SOURCES.map((s) => [s.id, s])) as Record<SourceId, SourceDef>;

/** DSN spacecraft codes for Mars missions (from DSN config.xml names). */
export const MARS_SPACECRAFT = new Set(["msl", "m20", "mro", "mros", "m01o", "m01s", "mvn", "mex", "tgo", "emm", "escb", "escg", "nsyt", "mer1", "mer2"]);

/** DEEPSIFT research datasets — shown separately, never mixed into live views. */
export const RESEARCH_ARCHIVE = [
  { id: "navcam-pds", name: "Curiosity Navcam (PDS)", classification: "ARCHIVAL / RESEARCH", note: "Phase 3 held-out test and validation periods — frozen", href: "/final-test" },
  { id: "mission-control", name: "Mission Control historical replay", classification: "ARCHIVAL / RESEARCH", note: "Replay of the frozen held-out test", href: "/mission-control" },
  { id: "rems-rad", name: "REMS / RAD (Phase 1–2)", classification: "ARCHIVAL / RESEARCH", note: "Archived environmental data used in Phase 2", href: "/research" },
] as const;
