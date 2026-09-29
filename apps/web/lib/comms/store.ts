/** Private editorial state — v1 lives ONLY in this browser's localStorage (key below). Export/import as JSON to back up or
 *  move between browsers. Pure state transitions are unit-tested (tests/comms-store.test.ts); the two storage helpers at the
 *  bottom are the only browser-dependent code. Nothing here talks to X or any server. */
import { checkPost, checkThread } from "./claims.ts";
import type { Audience, ContentIdea, HookStyle, Pillar } from "./library.ts";
import { composePost, composeThread } from "./library.ts";
import { postIdFromUrl } from "./xintent.ts";

export const STORAGE_KEY = "deepsift-comms-v1";
export const SCHEMA = "deepsift-comms";

export type Status = "IDEA" | "DRAFT" | "APPROVED" | "SCHEDULED_ON_X" | "POSTED" | "REJECTED";
export const STATUSES: Status[] = ["IDEA", "DRAFT", "APPROVED", "SCHEDULED_ON_X", "POSTED", "REJECTED"];
export type Format = "SHORT" | "THREAD";

export interface Metrics {
  views?: number;
  likes?: number;
  replies?: number;
  reposts?: number;
  bookmarks?: number;
  link_clicks?: number;
}
export const METRIC_KEYS: (keyof Metrics)[] = ["views", "likes", "replies", "reposts", "bookmarks", "link_clicks"];

export interface QualifiedReply {
  type: string;
  note: string;
}
export const QUALIFIED_TYPES = ["Researcher", "Spacecraft engineer", "Robotics engineer", "NASA/JPL/ESA/academic profile", "Other expert"];

export interface LogEntry {
  at: string;
  status: Status;
  note?: string;
}

export interface EditorialItem {
  id: string;
  idea_id: string | null;
  pillar: Pillar;
  audience: Audience;
  hook_style: HookStyle | null;
  format: Format;
  text: string;
  thread: string[];
  visual: string | null;
  claims: string[];
  status: Status;
  planned_at: string | null;
  scheduled_at: string | null;
  posted_at: string | null;
  x_url: string | null;
  thread_urls: string[];
  notes: string;
  metrics: Metrics;
  qualified_replies: QualifiedReply[];
  created_at: string;
  updated_at: string;
  log: LogEntry[];
  revisions: { at: string; text: string }[];
}

export type Relevance = "STRONG" | "MODERATE" | "WEAK" | "NONE";
export type PromoRisk = "LOW" | "MEDIUM" | "HIGH";

/** A reply drafted in the Reply Lab (browser-local, like everything else). */
export interface ReplyRecord {
  id: string;
  created_at: string;
  updated_at: string;
  post_text: string;
  post_url: string | null;
  author_name: string;
  author_handle: string;
  context: string;
  reply: string;
  style: string;
  angle: string | null;
  facts: string[];
  relevance: Relevance;
  promo_risk: PromoRisk;
  value: string;
  link: string | null;
  posted: boolean;
  reply_url: string | null;
}

export interface CommsState {
  schema: typeof SCHEMA;
  version: 1;
  items: EditorialItem[];
  /** Reply Lab history (optional so older exports still import). */
  replies?: ReplyRecord[];
}

export const emptyState = (): CommsState => ({ schema: SCHEMA, version: 1, items: [], replies: [] });

export const upsertReply = (s: CommsState, r: ReplyRecord): CommsState => {
  const list = s.replies ?? [];
  return { ...s, replies: list.some((x) => x.id === r.id) ? list.map((x) => (x.id === r.id ? r : x)) : [...list, r] };
};

function validReply(x: unknown): x is ReplyRecord {
  const r = x as ReplyRecord;
  return !!r && typeof r.id === "string" && typeof r.post_text === "string" && typeof r.reply === "string" && typeof r.updated_at === "string" && Array.isArray(r.facts);
}

const newId = (now: Date) => `d-${now.getTime().toString(36)}-${Math.floor(Math.random() * 1e6).toString(36)}`;

/** Posts of an item as they would go to X. */
export const postsOf = (it: Pick<EditorialItem, "format" | "text" | "thread">): string[] => (it.format === "THREAD" ? it.thread : [it.text]);

export function claimStatus(it: Pick<EditorialItem, "format" | "text" | "thread">): "PASS" | "FAIL" {
  return it.format === "THREAD" ? checkThread(it.thread).status : checkPost(it.text).status;
}

function claimsOf(it: Pick<EditorialItem, "format" | "text" | "thread">, extra: string[] = []): string[] {
  const s = new Set(extra);
  for (const p of postsOf(it)) for (const f of checkPost(p).facts) s.add(f);
  return [...s];
}

export function createFromIdea(idea: ContentIdea, opts: { style?: HookStyle; format?: Format; status?: "IDEA" | "DRAFT"; planned_at?: string | null; now?: Date } = {}): EditorialItem {
  const now = opts.now ?? new Date();
  const style = opts.style ?? idea.defaultHook;
  const format = opts.format ?? "SHORT";
  const text = composePost(idea, style);
  const thread = composeThread(idea, style);
  const at = now.toISOString();
  const status = opts.status ?? "DRAFT";
  const base = { format, text, thread };
  return {
    id: newId(now), idea_id: idea.id, pillar: idea.pillar, audience: idea.audience, hook_style: style, format, text, thread,
    visual: idea.visual, claims: claimsOf(base, idea.facts), status, planned_at: opts.planned_at ?? null, scheduled_at: null, posted_at: null,
    x_url: null, thread_urls: [], notes: "", metrics: {}, qualified_replies: [], created_at: at, updated_at: at,
    log: [{ at, status }], revisions: [{ at, text: postsOf(base).join("\n\n———\n\n") }],
  };
}

const touch = (it: EditorialItem, now: Date, patch: Partial<EditorialItem>, status?: Status, note?: string): EditorialItem => {
  const at = now.toISOString();
  const next = { ...it, ...patch, updated_at: at };
  if (status && status !== it.status) next.log = [...it.log, { at, status, ...(note ? { note } : {}) }];
  if (status) next.status = status;
  return next;
};

/** Edit the text. Any edit of an approved/scheduled post sends it back to DRAFT (it must be re-checked and re-approved). */
export function editContent(it: EditorialItem, patch: { text?: string; thread?: string[]; format?: Format; hook_style?: HookStyle | null; visual?: string | null }, now = new Date()): EditorialItem {
  if (it.status === "POSTED") throw new Error("A posted item can't be edited — add notes instead.");
  const merged = { ...it, ...patch };
  const changed = merged.text !== it.text || merged.format !== it.format || merged.thread.join("\u0000") !== it.thread.join("\u0000");
  const status: Status = changed && it.status !== "REJECTED" ? "DRAFT" : it.status;
  const at = now.toISOString();
  const revisions = changed ? [...it.revisions, { at, text: postsOf(merged).join("\n\n———\n\n") }] : it.revisions;
  return touch(it, now, { ...patch, claims: claimsOf(merged, it.claims), revisions }, status, changed && status !== it.status ? "edited" : undefined);
}

export function toDraft(it: EditorialItem, now = new Date()): EditorialItem {
  return it.status === "IDEA" ? touch(it, now, {}, "DRAFT") : it;
}

export function approve(it: EditorialItem, now = new Date()): EditorialItem {
  if (it.status === "POSTED") throw new Error("Already posted.");
  if (claimStatus(it) !== "PASS") throw new Error("CLAIM CHECK FAIL — fix the draft before approving.");
  return touch(it, now, {}, "APPROVED");
}

export function reject(it: EditorialItem, note = "", now = new Date()): EditorialItem {
  if (it.status === "POSTED") throw new Error("Already posted.");
  return touch(it, now, {}, "REJECTED", note || undefined);
}

export function reopen(it: EditorialItem, now = new Date()): EditorialItem {
  if (it.status !== "REJECTED") return it;
  return touch(it, now, {}, "DRAFT", "reopened");
}

export function plan(it: EditorialItem, date: string | null, now = new Date()): EditorialItem {
  if (date !== null && !/^\d{4}-\d{2}-\d{2}$/.test(date)) throw new Error("Planned date must be YYYY-MM-DD.");
  return touch(it, now, { planned_at: date });
}

/** Manual record that the post was scheduled in X's own composer. DEEPSIFT publishes nothing. */
export function markScheduled(it: EditorialItem, date: string, time: string, now = new Date()): EditorialItem {
  if (!(it.status === "APPROVED" || it.status === "SCHEDULED_ON_X")) throw new Error("Approve the post before marking it scheduled.");
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !/^\d{2}:\d{2}$/.test(time)) throw new Error("Scheduled date and time are required.");
  return touch(it, now, { scheduled_at: `${date}T${time}`, planned_at: date }, "SCHEDULED_ON_X");
}

/** Manual record that the post is live. Everything is optional and stored as entered — never verified through any X API.
 *  A URL, if given, must look like an X post URL; the publication time defaults to now. */
export function markPosted(it: EditorialItem, opts: { xUrl?: string; date?: string; time?: string; notes?: string } = {}, now = new Date()): EditorialItem {
  if (!(it.status === "APPROVED" || it.status === "SCHEDULED_ON_X")) throw new Error("Only an approved or scheduled post can be marked posted.");
  const url = (opts.xUrl ?? "").trim();
  if (url && !postIdFromUrl(url)) throw new Error("That isn't an X post URL (https://x.com/<user>/status/<id>) — fix it or leave it empty.");
  const date = (opts.date ?? "").trim();
  const time = (opts.time ?? "").trim();
  if (date && !/^\d{4}-\d{2}-\d{2}$/.test(date)) throw new Error("Publication date must be YYYY-MM-DD.");
  if (time && !/^\d{2}:\d{2}$/.test(time)) throw new Error("Publication time must be HH:MM.");
  if (time && !date) throw new Error("Enter the publication date too, or leave both empty.");
  const posted_at = date ? `${date}T${time || "00:00"}` : now.toISOString();
  const notes = opts.notes ? (it.notes ? `${it.notes}\n${opts.notes}` : opts.notes) : it.notes;
  return touch(it, now, { x_url: url || null, posted_at, notes }, "POSTED");
}

/** Add or correct the X post URL after posting (stored as entered). */
export function setXUrl(it: EditorialItem, xUrl: string, now = new Date()): EditorialItem {
  const url = xUrl.trim();
  if (url && !postIdFromUrl(url)) throw new Error("That isn't an X post URL (https://x.com/<user>/status/<id>).");
  return touch(it, now, { x_url: url || null });
}

export function setThreadUrl(it: EditorialItem, index: number, url: string, now = new Date()): EditorialItem {
  const urls = [...it.thread_urls];
  urls[index] = url.trim();
  return touch(it, now, { thread_urls: urls });
}

export function setMetrics(it: EditorialItem, metrics: Metrics, now = new Date()): EditorialItem {
  const clean: Metrics = {};
  for (const k of METRIC_KEYS) {
    const v = metrics[k];
    if (v !== undefined && v !== null && Number.isFinite(Number(v)) && Number(v) >= 0) clean[k] = Math.floor(Number(v));
  }
  return touch(it, now, { metrics: clean });
}

export function setQualified(it: EditorialItem, replies: QualifiedReply[], now = new Date()): EditorialItem {
  return touch(it, now, { qualified_replies: replies.filter((r) => r.type).map((r) => ({ type: String(r.type).slice(0, 80), note: String(r.note ?? "").slice(0, 500) })) });
}

export function setNotes(it: EditorialItem, notes: string, now = new Date()): EditorialItem {
  return touch(it, now, { notes });
}

export const upsert = (s: CommsState, it: EditorialItem): CommsState => ({ ...s, items: s.items.some((x) => x.id === it.id) ? s.items.map((x) => (x.id === it.id ? it : x)) : [...s.items, it] });
export const remove = (s: CommsState, id: string): CommsState => ({ ...s, items: s.items.filter((x) => x.id !== id) });

// ─── export / import ──────────────────────────────────────────────────────
export function exportState(s: CommsState, now = new Date()): string {
  return JSON.stringify({ ...s, exported_at: now.toISOString(), note: "DEEPSIFT private comms console — editorial state (v1, browser-local)." }, null, 2);
}

function validItem(x: unknown): x is EditorialItem {
  const i = x as EditorialItem;
  return (
    !!i && typeof i.id === "string" && typeof i.text === "string" && Array.isArray(i.thread) && i.thread.every((t) => typeof t === "string") &&
    STATUSES.includes(i.status) && (i.format === "SHORT" || i.format === "THREAD") && typeof i.pillar === "string" && typeof i.created_at === "string" &&
    typeof i.updated_at === "string" && Array.isArray(i.log)
  );
}

/** Parse an export. `merge` keeps the newer copy of each item (by updated_at); `replace` swaps everything. */
export function importState(json: string, current: CommsState, mode: "merge" | "replace" = "merge"): { state: CommsState; imported: number; skipped: number } {
  let data: unknown;
  try {
    data = JSON.parse(json);
  } catch {
    throw new Error("Not valid JSON.");
  }
  const d = data as Partial<CommsState>;
  if (!d || d.schema !== SCHEMA || d.version !== 1 || !Array.isArray(d.items)) throw new Error("Not a DEEPSIFT comms export (schema/version mismatch).");
  const good: EditorialItem[] = [];
  let skipped = 0;
  for (const raw of d.items) {
    if (!validItem(raw)) { skipped++; continue; }
    const r = raw as EditorialItem;
    good.push({ ...r, metrics: r.metrics ?? {}, qualified_replies: r.qualified_replies ?? [], thread_urls: r.thread_urls ?? [], revisions: r.revisions ?? [], notes: r.notes ?? "", claims: r.claims ?? [] });
  }
  const replies: ReplyRecord[] = [];
  for (const raw of Array.isArray(d.replies) ? d.replies : []) {
    if (validReply(raw)) replies.push(raw);
    else skipped++;
  }
  if (mode === "replace") return { state: { schema: SCHEMA, version: 1, items: good, replies }, imported: good.length + replies.length, skipped };
  const byId = new Map(current.items.map((i) => [i.id, i]));
  for (const it of good) {
    const cur = byId.get(it.id);
    if (!cur || it.updated_at > cur.updated_at) byId.set(it.id, it);
  }
  const rById = new Map((current.replies ?? []).map((r) => [r.id, r]));
  for (const r of replies) {
    const cur = rById.get(r.id);
    if (!cur || r.updated_at > cur.updated_at) rById.set(r.id, r);
  }
  return { state: { schema: SCHEMA, version: 1, items: [...byId.values()], replies: [...rById.values()] }, imported: good.length + replies.length, skipped };
}

// ─── browser storage (the only side-effecting code) ───────────────────────
export function loadState(): CommsState {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return emptyState();
    return importState(raw, emptyState(), "replace").state;
  } catch {
    return emptyState();
  }
}

export function saveState(s: CommsState): boolean {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
    return true;
  } catch {
    return false;
  }
}
