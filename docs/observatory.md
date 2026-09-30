# DEEPSIFT Live Data Observatory (`/data-stream`)

An **operational / observability layer**: it collects, timestamps and displays public signals around deep-space and
Mars operations. It does **not** feed, modify or re-run any DEEPSIFT science (Phase 3, Scheduler V3, POSITION,
Mission Control's frozen results, the paper, the 52 public claims). Any future study using live data would be a
separate, explicit experiment.

## Sources (audited 2026-09-30)

| source | endpoint used | label | cadence (source / collector / page cache) | notes |
|---|---|---|---|---|
| DSN Now | `eyes.nasa.gov/dsn/data/dsn.xml` + `dsn/config.xml` | **LIVE** | 5 s / 5 s / 10 s | **Undocumented** application file used by NASA's DSN Now app. Optional adapter: schema-checked, parser `dsn-xml/1`, degrades to DEGRADED/STALE without affecting other sources. Frequency (always 0) and round-trip light time (usually −1) are never shown. |
| NOAA SWPC | `services.swpc.noaa.gov/json/rtsw/rtsw_{wind,mag}_1m.json` | **NEAR REAL-TIME** | 1 min / 5 min (conditional GET + gzip; every minute sample ingested) / 60 s | Earth/L1 — never Mars conditions. `active` flag = operational spacecraft (ACE / IMAP / SOLAR1). Nulls stay missing. |
| NASA DONKI | `ccmc.gsfc.nasa.gov/DONKI-API/get/{CME,FLR,SEP,IPS,GST,notifications}` | **NEAR REAL-TIME EVENTS** | event-driven / 10 min / 10 min | New API base since 2026-09-30 (old `kauai.ccmc…/DONKI/WS` and `api.nasa.gov/DONKI` redirect). No key. `startDate` + `endDate` required. |
| JPL Horizons | `ssd.jpl.nasa.gov/api/horizons.api` (v1.2) | **CURRENT COMPUTED** | on demand / 5 min / 5 min | Ephemeris, not telemetry. Server-side only (no CORS). |
| Perseverance raw images | `mars.nasa.gov/rss/api/?feed=raw_images&category=mars2020…` | **NEWLY PUBLISHED** | – / 5 min / 5 min | Undocumented website feed, 12–15 s responses. Acquired + reached-Earth timestamps; no publication timestamp. |
| Curiosity raw images | `mars.nasa.gov/api/v1/raw_image_items/…` | **NEWLY PUBLISHED** | – / 3 min / 3 min | Undocumented website feed. Acquired, reached-Earth **and** published timestamps. |
| DEEPSIFT PDS / REMS / RAD | frozen release data | **ARCHIVAL / RESEARCH** | – | Shown only in the separate Research Archive section, never in live views. |

Never used: "LIVE FROM MARS", "LIVE ROVER CAMERA", "LIVE CURIOSITY TELEMETRY", or any claim that a DSN contact carried a specific image.

## Architecture

```
official sources → lib/observatory (fetchers → parsers → events/dedupe/health)
   ├── Tier 0 (public, Vercel): app/api/live/* — CDN-cached routes (s-maxage = cache window) → /data-stream
   │     page polls them; event stream = "events since you opened this page" (real diffs of successive states)
   └── collector (local now): services/collector — node:sqlite store live_observatory/data/observatory.sqlite,
         read-only API + SSE on 127.0.0.1:8790 → Next proxy /api/live/collector/* (only when LIVE_COLLECTOR_URL is set)
         → stored history, first-seen timestamps, time windows; private console /admin/live-data (nassimb only)
```

`lib/observatory/*.ts` is pure TypeScript shared by the page, the routes, the collector and the tests.

## Event model & dedupe

`LiveDataEvent` (lib/observatory/types.ts): event_id, dedupe_key, source, provider, classification, event_type,
mission, spacecraft, instrument, timestamp_source, timestamp_ingested, timestamp_updated, status, bytes, title,
summary, raw_reference, source_url, metadata. Types: `dsn_contact_started|updated|ended`, `solar_wind_sample`,
`donki_event`, `horizons_refresh`, `mars_image_published`, `source_error`, `source_recovered`.

| source | dedupe key |
|---|---|
| DSN | dish + spacecraft + first-observed time (start/end), + source time (update: direction, band set or ≥ 25 % rate change) |
| NOAA | measurement minute + source spacecraft |
| DONKI | official ID + version |
| Horizons | computed-for time |
| Mars images | image ID |

Unchanged polls create no events. On first run the collector **backfills silently** (images, DONKI, NOAA 24 h) and
marks backfilled images `backfill=1`: they are plotted at NASA's own time, never as "first seen" at start-up. Contacts
already active when the collector starts are recorded as starting then and say so.

## Three image timestamps (never conflated)

ACQUIRED (on Mars, from NASA) · REACHED EARTH (NASA `date_received`) · PUBLISHED (Curiosity `created_at` only) ·
FIRST SEEN BY DEEPSIFT (collector clock; unavailable in Tier 0).

## Health & staleness

ONLINE ≤ 2× cadence and no error streak · DEGRADED errors/partial or > 2× · STALE > 5× · OFFLINE disabled, never
succeeded, or > max(1 h, 5×). Every value shows its age ("updated 4 s ago", "STALE · last success 37 min ago"); the
last good value stays visible with its age, never presented as current. Failures emit `source_error` /
`source_recovered` events; the collector backs off exponentially (max 16×, ≤ 30 min).

## Central visualization (LIVE DATA FIELD)

x = time (UTC, now at the right edge; windows NOW/15 min/1 h/6 h/24 h) · rows = source → sub-source (DSN antenna,
NOAA speed / Bz, DONKI type, Horizons, rover camera) · colour = source · DSN contact = horizontal interval
(filled = downlink, outlined = uplink only, full opacity = both; thickness ∝ log reported data rate, hairline if not
reported; orange frame = Mars-linked) · NOAA = measured line · DONKI = diamond at official event time · Horizons =
refresh tick · Mars image = point at first-seen (collector) or published / reached-Earth (Tier 0 and backfill).
Every mark is a real record; new marks pulse once.

## Retention (collector)

DSN snapshots 7 d (sampled every 5 min) · contacts forever · NOAA 1-min 90 d then hourly · Horizons 5-min 7 d then
hourly · image metadata forever (no image files stored) · solar-wind sample events 7 d (samples remain) · poll log 7 d ·
metrics 30 d.

## Running locally

```bash
services/collector/run-local.sh                                   # background, logs in live_observatory/data/collector.log
curl http://127.0.0.1:8790/status                                  # health, uptime, SQLite size
node --disable-warning=MODULE_TYPELESS_PACKAGE_JSON scripts/live_integration_check.ts   # one-shot live check of all sources
```

Intervals: `POLL_DSN_S`, `POLL_NOAA_S`, `POLL_DONKI_S`, `POLL_HORIZONS_S`, `POLL_CURIOSITY_S`, `POLL_PERSEVERANCE_S`;
`DISABLE_<SOURCE>=1` turns an adapter off. Web app (apps/web/.env.local, server-only): `LIVE_COLLECTOR_URL`,
`COLLECTOR_ADMIN_TOKEN` (the same token the collector reads; generated into live_observatory/data/admin_token).

## Environment variables

- Tier 0 (Vercel): **none**. No NASA API key is needed (DONKI's new API has none).
- Collector host (later, not chosen yet): `LIVE_COLLECTOR_URL` (Vercel, server-only) and `COLLECTOR_ADMIN_TOKEN`
  (server-only, on both sides). Never `NEXT_PUBLIC_*`.

## Load estimate

~21,000 upstream requests/day (DSN 17,280), ~250 MB/day in; ~10 MB/day stored before rollups (≈ 3.6 GB/year).
Public routes are CDN-cached, so upstream load does not grow with visitors.
