/** Source adapters: pure parsers with schema checks. Input = the raw upstream payload (string or parsed JSON);
 *  output = normalized records. Fields the source doesn't report (0 / -1 / blank) become null — never invented. */
import { MARS_SPACECRAFT } from "./registry.ts";
import { SchemaError, type DonkiEvent, type DsnContact, type DsnDish, type DsnState, type Geometry, type MarsImage, type SolarWindSample } from "./types.ts";

const COMPLEX: Record<string, string> = { gdscc: "Goldstone", mdscc: "Madrid", cdscc: "Canberra" };
const num = (v: unknown): number | null => {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};
/** Source "-1" means "not reported". */
const reported = (v: unknown): number | null => {
  const n = num(v);
  return n === null || n < 0 ? null : n;
};
const isoZ = (s: unknown): string | null => {
  if (typeof s !== "string" || !s.trim()) return null;
  let t = s.trim();
  if (!/[zZ]|[+-]\d\d:?\d\d$/.test(t)) t += "Z";
  const ms = Date.parse(t);
  return Number.isFinite(ms) ? new Date(ms).toISOString() : null;
};

// ─── DSN Now (XML) ──────────────────────────────────────────────────────────
const attrs = (s: string): Record<string, string> => Object.fromEntries([...s.matchAll(/([A-Za-z_][\w-]*)="([^"]*)"/g)].map((m) => [m[1], m[2]]));

export function parseDsnConfig(xml: string): Record<string, string> {
  if (!/<config[\s>]/.test(xml)) throw new SchemaError("dsn-config", "missing <config> root");
  const map: Record<string, string> = {};
  for (const m of xml.matchAll(/<spacecraft\b([^>]*)\/?>/g)) {
    const a = attrs(m[1]);
    if (a.name) map[a.name.toLowerCase()] = a.friendlyName || a.name;
  }
  return map;
}

export function parseDsn(xml: string): DsnState {
  if (typeof xml !== "string" || !/<dsn[\s>]/.test(xml)) throw new SchemaError("dsn", "missing <dsn> root");
  const stations: DsnState["stations"] = [];
  const dishes: DsnDish[] = [];
  let station = "";
  let dish: DsnDish | null = null;
  for (const m of xml.matchAll(/<(\/?)(station|dish|upSignal|downSignal|target)\b([^>]*?)(\/?)>/g)) {
    const [, close, tag, body] = m;
    if (close) { if (tag === "dish") dish = null; continue; }
    const a = attrs(body);
    if (tag === "station") {
      const t = num(a.timeUTC);
      if (!a.name || t === null) throw new SchemaError("dsn", "station without name/timeUTC");
      station = a.name;
      stations.push({ code: a.name, name: a.friendlyName || COMPLEX[a.name] || a.name, time: new Date(t).toISOString() });
    } else if (tag === "dish") {
      if (!a.name) throw new SchemaError("dsn", "dish without name");
      dish = {
        name: a.name, complex: COMPLEX[station] ?? station, azimuth: num(a.azimuthAngle), elevation: num(a.elevationAngle), windSpeed: num(a.windSpeed),
        activity: a.activity ?? "", isMSPA: a.isMSPA === "true", isArray: a.isArray === "true", isDDOR: a.isDDOR === "true", signals: [], targets: [],
      };
      dishes.push(dish);
    } else if (dish && (tag === "upSignal" || tag === "downSignal")) {
      const rate = num(a.dataRate);
      dish.signals.push({
        direction: tag === "upSignal" ? "up" : "down", active: a.active === "true", signalType: a.signalType ?? "",
        dataRate: rate && rate > 0 ? rate : null, band: a.band || null, power: a.power === "" || a.power === undefined ? null : num(a.power),
        spacecraftCode: (a.spacecraft ?? "").toLowerCase(), spacecraftId: a.spacecraftID ?? null,
      });
    } else if (dish && tag === "target") {
      dish.targets.push({ code: (a.name ?? "").toLowerCase(), id: a.id ?? null, uplegRangeKm: reported(a.uplegRange), downlegRangeKm: reported(a.downlegRange), rtltS: reported(a.rtlt) });
    }
  }
  if (!stations.length) throw new SchemaError("dsn", "no <station> elements");
  if (!dishes.length) throw new SchemaError("dsn", "no <dish> elements");
  const sourceTime = stations.map((s) => s.time).sort().at(-1)!;
  return { sourceTime, stations, dishes };
}

/** Active links (≥ 1 active up or down signal) grouped per dish ↔ spacecraft. */
export function dsnContacts(state: DsnState, names: Record<string, string> = {}): DsnContact[] {
  const out: DsnContact[] = [];
  for (const d of state.dishes) {
    const bySc = new Map<string, typeof d.signals>();
    for (const s of d.signals) if (s.active && s.spacecraftCode) bySc.set(s.spacecraftCode, [...(bySc.get(s.spacecraftCode) ?? []), s]);
    for (const [sc, sigs] of bySc) {
      // a dish can carry several signals per direction (e.g. S-band telemetry + K-band science): combine them in a stable way
      const ups = sigs.filter((s) => s.direction === "up");
      const downs = sigs.filter((s) => s.direction === "down");
      const sum = (xs: typeof sigs) => (xs.some((x) => x.dataRate !== null) ? xs.reduce((n, x) => n + (x.dataRate ?? 0), 0) : null);
      const bands = [...new Set(sigs.map((x) => x.band).filter((x): x is string => !!x))].sort();
      const powers = downs.map((x) => x.power).filter((x): x is number => x !== null);
      const t = d.targets.find((x) => x.code === sc);
      out.push({
        key: `${d.name}|${sc}`, dish: d.name, complex: d.complex, spacecraftCode: sc, spacecraftName: names[sc] ?? sc.toUpperCase(), mars: MARS_SPACECRAFT.has(sc),
        direction: ups.length && downs.length ? "BOTH" : ups.length ? "UPLINK" : "DOWNLINK", band: bands.length ? bands.join("+") : null, downRate: sum(downs), upRate: sum(ups),
        downPower: powers.length ? Math.max(...powers) : null, rangeKm: t?.downlegRangeKm ?? t?.uplegRangeKm ?? null, azimuth: d.azimuth, elevation: d.elevation, activity: d.activity,
      });
    }
  }
  return out;
}

// ─── NOAA SWPC real-time solar wind ─────────────────────────────────────────
type NoaaRow = Record<string, unknown> & { time_tag: string; active: boolean; source: string };

export function parseNoaa(wind: unknown, mag: unknown): SolarWindSample[] {
  if (!Array.isArray(wind) || !Array.isArray(mag)) throw new SchemaError("noaa", "expected two JSON arrays");
  const check = (r: unknown, f: string) => {
    const x = r as NoaaRow;
    if (!x || typeof x.time_tag !== "string" || typeof x.active !== "boolean" || !(f in x)) throw new SchemaError("noaa", `row missing time_tag/active/${f}`);
  };
  if (wind[0]) check(wind[0], "proton_speed");
  if (mag[0]) check(mag[0], "bt");
  const minute = (t: string) => isoZ(t)!.slice(0, 16);
  const by = new Map<string, SolarWindSample>();
  const get = (r: NoaaRow) => {
    const k = minute(r.time_tag);
    const cur = by.get(k) ?? { time: `${k}:00.000Z`, source: r.source, speed: null, density: null, temperature: null, bt: null, bx: null, by: null, bz: null, quality: null };
    by.set(k, cur);
    return cur;
  };
  for (const r of wind as NoaaRow[]) {
    if (!r.active) continue;
    const s = get(r);
    s.source = r.source;
    s.speed = num(r.proton_speed);
    s.density = num(r.proton_density);
    s.temperature = num(r.proton_temperature);
    s.quality = num(r.overall_quality);
  }
  for (const r of mag as NoaaRow[]) {
    if (!r.active) continue;
    const s = get(r);
    s.bt = num(r.bt);
    s.bx = num(r.bx_gsm);
    s.by = num(r.by_gsm);
    s.bz = num(r.bz_gsm);
    if (s.quality === null) s.quality = num(r.overall_quality);
  }
  return [...by.values()].sort((a, b) => a.time.localeCompare(b.time));
}

// ─── NASA DONKI ─────────────────────────────────────────────────────────────
export const DONKI_TYPES = ["CME", "FLR", "SEP", "IPS", "GST", "notifications"] as const;
type Raw = Record<string, unknown>;
const first = (s: unknown, n = 160) => (typeof s === "string" ? s.replace(/[#*]/g, "").replace(/\s+/g, " ").trim().slice(0, n) : "");

export function parseDonki(type: (typeof DONKI_TYPES)[number], payload: unknown): DonkiEvent[] {
  if (!Array.isArray(payload)) {
    const p = payload as Raw;
    throw new SchemaError("donki", p && typeof p === "object" && "status" in p ? `HTTP ${p.status} ${p.error ?? ""}`.trim() : "expected a JSON array");
  }
  const out: DonkiEvent[] = [];
  for (const r of payload as Raw[]) {
    const version = r.versionId != null ? String(r.versionId) : null;
    if (type === "CME") out.push({ id: String(r.activityID), type: "CME", time: isoZ(r.startTime)!, title: `Coronal mass ejection${r.sourceLocation ? ` · ${r.sourceLocation}` : ""}`, detail: first(r.note), link: (r.link as string) ?? null, version });
    else if (type === "FLR") out.push({ id: String(r.flrID), type: "FLR", time: isoZ(r.beginTime)!, title: `Solar flare ${r.classType ?? ""}`.trim(), detail: [r.peakTime ? `peak ${r.peakTime}` : "", r.sourceLocation ? `at ${r.sourceLocation}` : "", r.activeRegionNum ? `AR ${r.activeRegionNum}` : ""].filter(Boolean).join(" · "), link: (r.link as string) ?? null, version });
    else if (type === "SEP") out.push({ id: String(r.sepID), type: "SEP", time: isoZ(r.eventTime)!, title: "Solar energetic particle event", detail: ((r.instruments as Raw[]) ?? []).map((i) => i.displayName).join(", "), link: (r.link as string) ?? null, version });
    else if (type === "IPS") out.push({ id: String(r.activityID), type: "IPS", time: isoZ(r.eventTime)!, title: `Interplanetary shock${r.location ? ` · ${r.location}` : ""}`, detail: ((r.instruments as Raw[]) ?? []).map((i) => i.displayName).join(", "), link: (r.link as string) ?? null, version });
    else if (type === "GST") {
      const kp = ((r.allKpIndex as Raw[]) ?? []).map((k) => num(k.kpIndex) ?? 0);
      out.push({ id: String(r.gstID), type: "GST", time: isoZ(r.startTime)!, title: `Geomagnetic storm${kp.length ? ` · Kp max ${Math.max(...kp)}` : ""}`, detail: "", link: (r.link as string) ?? null, version });
    } else out.push({ id: String(r.messageID), type: "NOTIFICATION", time: isoZ(r.messageIssueTime)!, title: `Notification · ${r.messageType ?? ""}`.trim(), detail: first(r.messageBody), link: (r.messageURL as string) ?? null, version: null });
  }
  return out.filter((e) => e.id && e.id !== "undefined" && e.time);
}

// ─── JPL Horizons ───────────────────────────────────────────────────────────
const MON: Record<string, string> = { Jan: "01", Feb: "02", Mar: "03", Apr: "04", May: "05", Jun: "06", Jul: "07", Aug: "08", Sep: "09", Oct: "10", Nov: "11", Dec: "12" };
export const AU_KM = 149_597_870.7;

export function horizonsQuery(now: Date): Record<string, string> {
  const f = (d: Date) => d.toISOString().slice(0, 16).replace("T", " ");
  return {
    format: "json", COMMAND: "'499'", CENTER: "'500@399'", MAKE_EPHEM: "'YES'", EPHEM_TYPE: "'OBSERVER'",
    START_TIME: `'${f(now)}'`, STOP_TIME: `'${f(new Date(now.getTime() + 60_000))}'`, STEP_SIZE: "'1 m'", QUANTITIES: "'1,20,21,23'", CSV_FORMAT: "'YES'",
  };
}

export function parseHorizons(payload: unknown): Geometry {
  const p = payload as { result?: string; signature?: { version?: string }; error?: string };
  if (!p || typeof p !== "object") throw new SchemaError("horizons", "not a JSON object");
  if (p.error) throw new SchemaError("horizons", p.error.slice(0, 120));
  if (typeof p.result !== "string" || !p.result.includes("$$SOE")) throw new SchemaError("horizons", "no $$SOE ephemeris block");
  if (p.signature?.version && !p.signature.version.startsWith("1.")) throw new SchemaError("horizons", `unexpected API version ${p.signature.version}`);
  const line = p.result.split("$$SOE")[1].split("\n").map((l) => l.trim()).find((l) => l.length > 0 && !l.startsWith("$$"));
  if (!line) throw new SchemaError("horizons", "empty ephemeris");
  const c = line.split(",").map((x) => x.trim());
  // Date, solar-presence, lunar-presence, RA, DEC, delta (AU), deldot (km/s), 1-way LT (min), S-O-T (deg), /r
  const dm = c[0].match(/^(\d{4})-([A-Za-z]{3})-(\d{2}) (\d{2}):(\d{2})/);
  if (!dm || c.length < 9) throw new SchemaError("horizons", "unexpected CSV columns");
  const au = num(c[5]);
  return {
    computedFor: `${dm[1]}-${MON[dm[2]]}-${dm[3]}T${dm[4]}:${dm[5]}:00.000Z`, raDec: c[3] && c[4] ? `${c[3]} / ${c[4]}` : null,
    distanceAu: au, distanceKm: au === null ? null : au * AU_KM, rangeRateKmS: num(c[6]), lightTimeMin: num(c[7]), elongationDeg: num(c[8]), apiVersion: p.signature?.version ?? null,
  };
}

// ─── Mars raw images ────────────────────────────────────────────────────────
/** Readable labels for instrument codes seen in the feeds. Unknown codes are shown as reported — the list is not exhaustive. */
const CAMERA_LABEL: Record<string, string> = {
  NAV_LEFT_A: "Left Navcam (A)", NAV_LEFT_B: "Left Navcam (B)", NAV_RIGHT_A: "Right Navcam (A)", NAV_RIGHT_B: "Right Navcam (B)",
  FHAZ_LEFT_A: "Front Hazcam left (A)", FHAZ_LEFT_B: "Front Hazcam left (B)", FHAZ_RIGHT_A: "Front Hazcam right (A)", FHAZ_RIGHT_B: "Front Hazcam right (B)",
  RHAZ_LEFT_A: "Rear Hazcam left (A)", RHAZ_LEFT_B: "Rear Hazcam left (B)", RHAZ_RIGHT_A: "Rear Hazcam right (A)", RHAZ_RIGHT_B: "Rear Hazcam right (B)",
  MAST_LEFT: "Mastcam left", MAST_RIGHT: "Mastcam right", MAHLI: "MAHLI", MARDI: "MARDI", CHEMCAM_RMI: "ChemCam RMI",
  NAVCAM_LEFT: "Navcam left", NAVCAM_RIGHT: "Navcam right", FRONT_HAZCAM_LEFT_A: "Front Hazcam left", FRONT_HAZCAM_RIGHT_A: "Front Hazcam right",
  REAR_HAZCAM_LEFT: "Rear Hazcam left", REAR_HAZCAM_RIGHT: "Rear Hazcam right", MCZ_LEFT: "Mastcam-Z left", MCZ_RIGHT: "Mastcam-Z right",
  SUPERCAM_RMI: "SuperCam RMI", SKYCAM: "MEDA SkyCam", PIXL_MCC: "PIXL MCC", SHERLOC_WATSON: "SHERLOC WATSON", SHERLOC_ACI: "SHERLOC ACI",
  CACHECAM: "CacheCam", EDL_RDCAM: "EDL rover down-look", LCAM: "Lander Vision System",
};
const cam = (code: string) => CAMERA_LABEL[code] ?? code.replace(/_/g, " ");
const lmst = (s: unknown) => (typeof s === "string" ? s.match(/M(\d\d:\d\d:\d\d)/)?.[1] ?? null : null);
const dims = (s: unknown): [number | null, number | null] => {
  const m = typeof s === "string" ? s.match(/\((\d+),(\d+)(?:,(\d+),(\d+))?\)/) : null;
  if (!m) return [null, null];
  return m[3] ? [Number(m[3]) - Number(m[1]) + 1, Number(m[4]) - Number(m[2]) + 1] : [Number(m[1]), Number(m[2])];
};

export function parsePerseverance(payload: unknown): MarsImage[] {
  const p = payload as { images?: Raw[] };
  if (!p || !Array.isArray(p.images)) throw new SchemaError("perseverance", "missing images[]");
  return p.images.map((r) => {
    const files = (r.image_files as Raw) ?? {};
    const camera = String((r.camera as Raw)?.instrument ?? "UNKNOWN");
    const [w, h] = dims((r.extended as Raw)?.dimension);
    const sample = typeof r.sample_type === "string" ? r.sample_type : null;
    return {
      imageId: String(r.imageid), rover: "Perseverance" as const, camera, cameraLabel: cam(camera), sol: num(r.sol), lmst: lmst(r.date_taken_mars),
      acquired: isoZ(r.date_taken_utc), reachedEarth: isoZ(r.date_received), published: null,
      imageUrl: String(files.large ?? files.medium ?? files.full_res ?? ""), thumbUrl: (files.small as string) ?? null, detailUrl: (r.link as string) ?? null,
      width: w, height: h, sampleType: sample, thumbnail: sample === "Thumbnail", credit: String(r.credit ?? "NASA/JPL-Caltech"), title: String(r.title ?? "").trim(),
    };
  }).filter((i) => i.imageId && i.imageUrl);
}

export function parseCuriosity(payload: unknown): MarsImage[] {
  const p = payload as { items?: Raw[] };
  if (!p || !Array.isArray(p.items)) throw new SchemaError("curiosity", "missing items[]");
  return p.items.map((r) => {
    const camera = String(r.instrument ?? "UNKNOWN");
    const ext = (r.extended as Raw) ?? {};
    const [w, h] = dims(r.subframe_rect);
    const url = String(r.https_url ?? r.url ?? "").replace(/^http:/, "https:");
    return {
      imageId: String(r.imageid), rover: "Curiosity" as const, camera, cameraLabel: cam(camera), sol: num(r.sol), lmst: lmst(ext.lmst),
      acquired: isoZ(r.date_taken), reachedEarth: isoZ(r.date_received), published: isoZ(r.created_at),
      imageUrl: url, thumbUrl: null, detailUrl: typeof r.link === "string" ? (r.link.startsWith("http") ? r.link : `https://mars.nasa.gov${r.link}`) : null,
      width: w, height: h, sampleType: (ext.sample_type as string) ?? null, thumbnail: r.is_thumbnail === true || ext.sample_type === "thumbnail",
      credit: String(r.image_credit ?? "NASA/JPL-Caltech"), title: String(r.title ?? "").trim(),
    };
  }).filter((i) => i.imageId && i.imageUrl);
}
