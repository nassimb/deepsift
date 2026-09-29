"use client";

/* Views of the private comms console. All state is browser-local (CommsProvider → localStorage). */
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { ASSETS } from "@/lib/comms/assets";
import { FACT_BY_ID } from "@/lib/comms/facts";
import { AUDIENCES, AUDIENCE_LABEL, IDEAS, IDEA_BY_ID, PILLARS, PILLAR_LABEL, type Mode } from "@/lib/comms/library";
import { CADENCE, performanceByPillar, planWeek, recommend, reviewWeek, weekStart, ymd, type Recommendation } from "@/lib/comms/recommend";
import { STATUSES, createFromIdea, exportState, importState, postsOf, type CommsState, type EditorialItem, type Status } from "@/lib/comms/store";
import { itemForIdea, useComms } from "./CommsProvider";
import { DraftCard } from "./DraftCard";
import { ReplyHistory } from "./ReplyLab";
import { AttachFiles, Chip, CopyButton, Section, StatusChip } from "./ui";

const DAY = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

export function StorageNotice() {
  const { saved } = useComms();
  return (
    <p className="text-[11px] text-ink-3" data-testid="storage-notice">
      Editorial state is stored locally in this browser in v1. Use EXPORT COMMS DATA to back it up or move it to another browser.
      {!saved && <span style={{ color: "var(--s-critical)" }}> Browser storage is unavailable — changes will be lost on reload.</span>}
    </p>
  );
}

export function DataTools() {
  const { state, replace } = useComms();
  const file = useRef<HTMLInputElement>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [mode, setMode] = useState<"merge" | "replace">("merge");
  const doExport = () => {
    const blob = new Blob([exportState(state)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `deepsift-comms-${ymd(new Date())}.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    setMsg(`Exported ${state.items.length} item(s).`);
  };
  const doImport = async (f: File) => {
    try {
      const r = importState(await f.text(), state, mode);
      replace(r.state);
      setMsg(`Imported ${r.imported} item(s)${r.skipped ? `, skipped ${r.skipped} invalid` : ""} (${mode}).`);
    } catch (e) {
      setMsg(`Import failed: ${(e as Error).message}`);
    }
    if (file.current) file.current.value = "";
  };
  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="data-tools">
      <button type="button" className="btn" onClick={doExport} data-testid="export">Export comms data</button>
      <button type="button" className="btn" onClick={() => file.current?.click()} data-testid="import">Import comms data</button>
      <select value={mode} onChange={(e) => setMode(e.target.value as "merge" | "replace")} className="bg-panel-2 border border-line text-ink-2 text-[11px] px-1.5 py-1" data-testid="import-mode">
        <option value="merge">merge (keep newer)</option>
        <option value="replace">replace all</option>
      </select>
      <input ref={file} type="file" accept="application/json,.json" className="hidden" data-testid="import-file" onChange={(e) => e.target.files?.[0] && doImport(e.target.files[0])} />
      {msg && <span className="text-[11px] text-ink-2" data-testid="data-msg">{msg}</span>}
    </div>
  );
}

function ModeSwitch() {
  const { mode, setMode } = useComms();
  const opts: [Mode, string][] = [["ALL", "All audiences"], ["RESEARCH", "Technical / research"], ["FAN", "Space fan"]];
  return (
    <div className="flex flex-wrap gap-1.5" data-testid="mode-switch">
      {opts.map(([m, l]) => (
        <button key={m} type="button" className="btn" data-active={mode === m ? "true" : undefined} onClick={() => setMode(m)} data-testid={`mode-${m}`}>{l}</button>
      ))}
    </div>
  );
}

function Reasons({ r }: { r: Recommendation }) {
  return (
    <ul className="text-[12px] text-ink-3 list-disc pl-5 space-y-0.5" data-testid="reasons">
      {r.reasons.map((x) => <li key={x}>{x}</li>)}
    </ul>
  );
}

// ─── TODAY ────────────────────────────────────────────────────────────────
export function TodayView() {
  const { state, ready, mode } = useComms();
  const [today] = useState(() => new Date());
  // The recommendation is computed from a snapshot, so acting on it (draft, approve…) doesn't swap it away mid-session.
  const [snap, setSnap] = useState<CommsState | null>(null);
  // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time snapshot once browser storage has loaded
  useEffect(() => { if (ready && !snap) setSnap(state); }, [ready, snap, state]);
  const rec = useMemo(() => recommend(snap ?? state, today, mode), [snap, state, today, mode]);
  const [chosen, setChosen] = useState<string | null>(null);
  const cad = CADENCE[today.getDay()];
  const pickedId = chosen ?? rec.primary?.idea.id ?? null;
  const picked = pickedId ? IDEA_BY_ID[pickedId] : null;
  const pickedItem = picked ? itemForIdea(state, picked.id) : null;
  const queue = state.items.filter((i) => ["DRAFT", "APPROVED", "SCHEDULED_ON_X"].includes(i.status)).sort((a, b) => String(a.planned_at ?? "9").localeCompare(String(b.planned_at ?? "9")));
  const dueToday = state.items.filter((i) => i.planned_at === ymd(today) && i.status !== "REJECTED" && i.idea_id !== pickedId);

  if (!ready) return <p className="text-ink-3 text-[12px]">Loading local editorial state…</p>;
  return (
    <>
      <div className="space-y-2">
        <div className="label">{DAY[today.getDay()]} · {ymd(today)} · slot: {cad.label}</div>
        <h1 className="text-[22px] sm:text-[26px] text-ink">What should I post today?</h1>
        <ModeSwitch />
        <StorageNotice />
      </div>

      {dueToday.length > 0 && (
        <Section title="Already planned for today" testid="due-today">
          <div className="space-y-4">{dueToday.map((it) => <DraftCard key={it.id} item={it} />)}</div>
        </Section>
      )}

      <Section title={chosen && chosen !== rec.primary?.idea.id ? "Selected alternative" : "Today's recommendation"} testid="recommendation"
        right={<button type="button" className="btn" onClick={() => { setSnap(state); setChosen(null); }} data-testid="refresh-rec">Refresh recommendation</button>}>
        {rec.primary ? (
          <div className="space-y-3">
            {(!chosen || chosen === rec.primary.idea.id) && <Reasons r={rec.primary} />}
            {picked && <DraftCard key={picked.id + (pickedItem?.id ?? "")} idea={picked} item={pickedItem && pickedItem.status !== "POSTED" && pickedItem.status !== "REJECTED" ? pickedItem : null} testid="today-card" />}
            {chosen && chosen !== rec.primary.idea.id && <button type="button" className="btn" onClick={() => setChosen(null)}>← Back to today&apos;s recommendation</button>}
          </div>
        ) : (
          <p className="text-[13px] text-ink-3">Every idea is already in your queue or posted. Add ideas to lib/comms/library.ts.</p>
        )}
      </Section>

      <Section title="3 alternatives" testid="alternatives">
        <div className="grid gap-3 md:grid-cols-3">
          {rec.alternatives.map((r) => (
            <div key={r.idea.id} className="panel p-3 space-y-2" data-testid="alternative">
              <div className="flex flex-wrap gap-1.5"><Chip>{PILLAR_LABEL[r.idea.pillar]}</Chip><Chip>{AUDIENCE_LABEL[r.idea.audience]}</Chip></div>
              <div className="text-[13px] text-ink">{r.idea.title}</div>
              <div className="text-[12px] text-ink-2">{r.idea.hooks[r.idea.defaultHook]}</div>
              <Reasons r={r} />
              <button type="button" className="btn" onClick={() => { setChosen(r.idea.id); window.scrollTo({ top: 0, behavior: "smooth" }); }} data-testid="use-alternative">Use this</button>
            </div>
          ))}
        </div>
      </Section>

      <Section title={`Queue (${queue.length})`} testid="queue">
        {queue.length ? (
          <ul className="text-[12px] space-y-1">
            {queue.map((i) => (
              <li key={i.id} className="flex flex-wrap items-center gap-2">
                <StatusChip status={i.status} />
                <span className="mono text-ink-3 w-24">{i.scheduled_at?.replace("T", " ") ?? i.planned_at ?? "unplanned"}</span>
                <span className="text-ink-2">{IDEA_BY_ID[i.idea_id ?? ""]?.title ?? i.text.split("\n")[0]}</span>
              </li>
            ))}
          </ul>
        ) : <p className="text-[12px] text-ink-3">Nothing drafted yet.</p>}
      </Section>

      <Section title="How publishing works (zero-cost)" testid="workflow">
        <ol className="text-[12px] text-ink-2 list-decimal pl-5 space-y-0.5">
          <li>Pick a draft; edit it if you like. The claim checker re-runs on every change.</li>
          <li>APPROVE (only possible when CLAIM CHECK = PASS).</li>
          <li>OPEN IN X: X&apos;s own web composer opens in a new tab with the text prefilled.</li>
          <li>In X, attach the visual and publish — or use X&apos;s native scheduling to pick a date and time.</li>
          <li>Back here: MARK SCHEDULED (date/time) or MARK POSTED (paste the post URL).</li>
        </ol>
        <p className="text-[11px] text-ink-4">No X API, no paid scheduler, no automatic posting. DEEPSIFT itself never publishes or schedules anything.</p>
      </Section>

      <Section title="Data" testid="data"><DataTools /></Section>
    </>
  );
}

// ─── LIBRARY ──────────────────────────────────────────────────────────────
export function LibraryView() {
  const { state, ready } = useComms();
  const [pillar, setPillar] = useState<string>("");
  const [aud, setAud] = useState<string>("");
  const [open, setOpen] = useState<string | null>(null);
  const list = IDEAS.filter((i) => (!pillar || i.pillar === pillar) && (!aud || i.audience === aud));
  if (!ready) return null;
  return (
    <>
      <div className="space-y-2">
        <h1 className="text-[22px] text-ink">Content library</h1>
        <p className="text-[12px] text-ink-3">{IDEAS.length} seed ideas built only from VERIFIED_FACTS (lib/comms/library.ts). Every hook variant and thread post passes the claim checker in CI.</p>
        <div className="flex flex-wrap gap-2">
          <select value={pillar} onChange={(e) => setPillar(e.target.value)} className="bg-panel-2 border border-line text-ink-2 text-[12px] px-2 py-1" data-testid="filter-pillar">
            <option value="">All categories</option>
            {PILLARS.map((p) => <option key={p} value={p}>{PILLAR_LABEL[p]}</option>)}
          </select>
          <select value={aud} onChange={(e) => setAud(e.target.value)} className="bg-panel-2 border border-line text-ink-2 text-[12px] px-2 py-1" data-testid="filter-audience">
            <option value="">All audiences</option>
            {AUDIENCES.map((a) => <option key={a} value={a}>{AUDIENCE_LABEL[a]}</option>)}
          </select>
        </div>
      </div>
      <ul className="space-y-2" data-testid="library">
        {list.map((i) => {
          const it = itemForIdea(state, i.id);
          return (
            <li key={i.id} className="space-y-2" data-testid="library-idea" data-idea={i.id}>
              <button type="button" className="w-full text-left panel p-3 flex flex-wrap items-center gap-2 hover:border-[var(--ink-4)]" onClick={() => setOpen(open === i.id ? null : i.id)}>
                <Chip>{PILLAR_LABEL[i.pillar]}</Chip>
                <Chip>{AUDIENCE_LABEL[i.audience]}</Chip>
                {it && <StatusChip status={it.status} />}
                <span className="text-[13px] text-ink">{i.title}</span>
                <span className="text-[12px] text-ink-3 w-full sm:w-auto sm:ml-auto">{i.hooks[i.defaultHook]}</span>
              </button>
              {open === i.id && <DraftCard idea={i} item={it && it.status !== "POSTED" ? it : null} />}
            </li>
          );
        })}
      </ul>
    </>
  );
}

// ─── CALENDAR ─────────────────────────────────────────────────────────────
export function CalendarView() {
  const { state, ready, put, mode } = useComms();
  const [monday, setMonday] = useState(() => weekStart(new Date()));
  const [openId, setOpenId] = useState<string | null>(null);
  const days = Array.from({ length: 7 }, (_, k) => new Date(monday.getFullYear(), monday.getMonth(), monday.getDate() + k));
  const shift = (w: number) => setMonday(new Date(monday.getFullYear(), monday.getMonth(), monday.getDate() + 7 * w));
  const itemsOn = (d: string) => state.items.filter((i) => (i.scheduled_at?.slice(0, 10) ?? i.planned_at) === d);
  const planThisWeek = () => {
    for (const p of planWeek(state, monday, mode)) {
      if (!p.idea || itemsOn(p.date).some((i) => i.status !== "REJECTED")) continue;
      put(createFromIdea(p.idea, { status: "IDEA", planned_at: p.date }));
    }
  };
  const addIdea = (date: string, ideaId: string) => ideaId && put(createFromIdea(IDEA_BY_ID[ideaId], { status: "IDEA", planned_at: date }));
  const openItem = state.items.find((i) => i.id === openId) ?? null;
  if (!ready) return null;
  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-[22px] text-ink">Content calendar</h1>
          <p className="text-[12px] text-ink-3">Default cadence: 5 original posts a week (Mon–Fri). Weekends optional. Nothing here publishes anything.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn" onClick={() => shift(-1)} data-testid="prev-week">← Prev</button>
          <span className="mono text-[12px] text-ink-2 self-center" data-testid="week-label">Week of {ymd(monday)}</span>
          <button type="button" className="btn" onClick={() => shift(1)} data-testid="next-week">Next →</button>
          <button type="button" className="btn" data-active="true" onClick={planThisWeek} data-testid="plan-week">Plan this week</button>
        </div>
      </div>
      <div className="grid gap-2 md:grid-cols-7" data-testid="calendar">
        {days.map((d) => {
          const key = ymd(d);
          const cad = CADENCE[d.getDay()];
          const items = itemsOn(key);
          return (
            <div key={key} className="panel p-2 space-y-2 min-h-[140px]" data-testid="cal-day" data-date={key} style={{ opacity: cad.optional ? 0.8 : 1 }}>
              <div className="flex items-baseline justify-between gap-1">
                <span className="text-[12px] text-ink">{DAY[d.getDay()].slice(0, 3)} <span className="mono text-ink-3">{key.slice(5)}</span></span>
              </div>
              <div className="label leading-tight">{cad.label}</div>
              {items.map((i) => (
                <button key={i.id} type="button" onClick={() => setOpenId(openId === i.id ? null : i.id)} data-testid="cal-item"
                  className="w-full text-left border border-line p-1.5 space-y-1 hover:border-[var(--ink-4)]">
                  <StatusChip status={i.status} />
                  {i.scheduled_at && <div className="mono text-[10px] text-ink-3">{i.scheduled_at.slice(11)}</div>}
                  <div className="text-[11px] text-ink-2 leading-snug">{IDEA_BY_ID[i.idea_id ?? ""]?.title ?? i.text.slice(0, 60)}</div>
                  <div className="text-[10px] text-ink-4">{PILLAR_LABEL[i.pillar]}</div>
                </button>
              ))}
              <select value="" onChange={(e) => addIdea(key, e.target.value)} className="w-full bg-panel-2 border border-line text-ink-3 text-[11px] px-1 py-1" data-testid="cal-add">
                <option value="">+ add idea…</option>
                <optgroup label={`Fits: ${cad.label}`}>
                  {IDEAS.filter((i) => cad.pillars.includes(i.pillar)).map((i) => <option key={i.id} value={i.id}>{i.title}</option>)}
                </optgroup>
                <optgroup label="Other">
                  {IDEAS.filter((i) => !cad.pillars.includes(i.pillar)).map((i) => <option key={i.id} value={i.id}>{i.title}</option>)}
                </optgroup>
              </select>
            </div>
          );
        })}
      </div>
      {openItem && <DraftCard key={openItem.id} item={openItem} />}
    </>
  );
}

// ─── HISTORY ──────────────────────────────────────────────────────────────
export function HistoryView() {
  const { state, ready } = useComms();
  const [status, setStatus] = useState<Status | "">("");
  const [openId, setOpenId] = useState<string | null>(null);
  const items = state.items.filter((i) => !status || i.status === status).sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  if (!ready) return null;
  return (
    <>
      <div className="space-y-2">
        <h1 className="text-[22px] text-ink">Post history</h1>
        <StorageNotice />
        <DataTools />
        <select value={status} onChange={(e) => setStatus(e.target.value as Status | "")} className="bg-panel-2 border border-line text-ink-2 text-[12px] px-2 py-1" data-testid="filter-status">
          <option value="">All statuses</option>
          {STATUSES.map((s) => <option key={s}>{s}</option>)}
        </select>
      </div>
      {items.length === 0 && <p className="text-[12px] text-ink-3">No post history yet in this browser.</p>}
      <ul className="space-y-2" data-testid="history">
        {items.map((i) => <HistoryRow key={i.id} it={i} open={openId === i.id} onToggle={() => setOpenId(openId === i.id ? null : i.id)} />)}
      </ul>
      <ReplyHistory compact />
    </>
  );
}

function HistoryRow({ it, open, onToggle }: { it: EditorialItem; open: boolean; onToggle: () => void }) {
  const kv: [string, string][] = [
    ["draft id", it.id], ["category", PILLAR_LABEL[it.pillar]], ["audience", AUDIENCE_LABEL[it.audience]], ["format", it.format],
    ["planned_at", it.planned_at ?? "—"], ["scheduled_at", it.scheduled_at?.replace("T", " ") ?? "—"], ["posted_at", it.posted_at ?? "—"],
    ["X URL", it.x_url ?? "—"], ["visual", it.visual ?? "—"], ["claims used", it.claims.join(", ") || "—"], ["notes", it.notes || "—"],
  ];
  return (
    <li className="panel p-3 space-y-2" data-testid="history-row" data-status={it.status}>
      <button type="button" className="w-full text-left flex flex-wrap items-center gap-2" onClick={onToggle}>
        <StatusChip status={it.status} />
        <span className="text-[13px] text-ink">{IDEA_BY_ID[it.idea_id ?? ""]?.title ?? it.text.split("\n")[0]}</span>
        <span className="mono text-[10px] text-ink-4 ml-auto">{it.updated_at.slice(0, 16).replace("T", " ")}</span>
      </button>
      <dl className="grid gap-x-4 gap-y-0.5 text-[11px] sm:grid-cols-[120px_1fr]">
        {kv.map(([k, v]) => (<Fragment key={k}><dt className="text-ink-4">{k}</dt><dd className="text-ink-2 mono break-all">{v}</dd></Fragment>))}
      </dl>
      <pre className="whitespace-pre-wrap break-words font-sans text-[12px] text-ink-2 border-l border-line pl-3">{postsOf(it).join("\n\n———\n\n")}</pre>
      <div className="text-[11px] text-ink-4">History: {it.log.map((l) => `${l.status} ${l.at.slice(0, 16).replace("T", " ")}`).join(" → ")} · {it.revisions.length} text revision(s)</div>
      {open && <DraftCard item={it} />}
      {!open && <button type="button" className="btn" onClick={onToggle}>Open</button>}
    </li>
  );
}

// ─── ASSETS ───────────────────────────────────────────────────────────────
export function AssetsView() {
  return (
    <>
      <div className="space-y-1">
        <h1 className="text-[22px] text-ink">Approved visuals</h1>
        <p className="text-[12px] text-ink-3">Existing DEEPSIFT assets only — read-only references to the site and the public repository. No generated imagery. Navcam images: NASA/JPL-Caltech (display previews, contrast-stretched).</p>
        <p className="text-[12px] text-ink-3">For X, always attach the PNG or JPEG file (DOWNLOAD). X does not accept SVG.</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" data-testid="assets">
        {ASSETS.map((a) => (
          <div key={a.id} className="panel p-3 space-y-2" data-testid="asset" data-asset={a.id}>
            <div className="aspect-[16/10] bg-panel-2 border border-line flex items-center justify-center overflow-hidden">
              {a.preview ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={a.preview} alt={a.name} className="max-w-full max-h-full object-contain" loading="lazy" />
              ) : (
                <span className="label text-center px-3">{a.kind === "RECORDING" ? "record from /mission-control" : a.kind === "DOCUMENT" ? "PDF" : "capture from the live page"}</span>
              )}
            </div>
            <div className="flex flex-wrap gap-1.5"><Chip>{a.kind}</Chip>{a.pillars.map((p) => <Chip key={p}>{PILLAR_LABEL[p]}</Chip>)}</div>
            <div className="text-[13px] text-ink">{a.name}</div>
            <p className="text-[12px] text-ink-3">{a.description}</p>
            {a.caption && <p className="text-[11px] text-ink-4 italic">Caption: {a.caption}</p>}
            <div className="mono text-[10px] text-ink-4 break-all">{a.path}</div>
            <AttachFiles files={a.files} />
            <div className="flex gap-2">
              <a className="btn" href={a.open} target="_blank" rel="noopener noreferrer" data-testid="asset-open">Open ↗</a>
              <CopyButton text={a.path} label="Copy path" testid="asset-copy" />
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

// ─── WEEKLY REVIEW + PERFORMANCE ──────────────────────────────────────────
export function ReviewView() {
  const { state, ready } = useComms();
  const [monday, setMonday] = useState(() => weekStart(new Date()));
  const r = useMemo(() => reviewWeek(state, monday), [state, monday]);
  const perf = useMemo(() => performanceByPillar(state), [state]);
  if (!ready) return null;
  const shift = (w: number) => setMonday(new Date(monday.getFullYear(), monday.getMonth(), monday.getDate() + 7 * w));
  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-2">
        <h1 className="text-[22px] text-ink">Weekly content review</h1>
        <div className="flex gap-2">
          <button type="button" className="btn" onClick={() => shift(-1)}>← Prev</button>
          <span className="mono text-[12px] text-ink-2 self-center">Week of {ymd(monday)}</span>
          <button type="button" className="btn" onClick={() => shift(1)}>Next →</button>
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-4" data-testid="week-kpis">
        {[["Posts planned", r.planned], ["Posts completed", r.completed], ["Scheduled on X", r.scheduled], ["Unused content ideas", r.unusedIdeas]].map(([k, v]) => (
          <div key={k as string} className="panel p-3"><div className="label">{k}</div><div className="mono text-[22px] text-ink">{v}</div></div>
        ))}
      </div>
      <Section title="Suggestions" testid="suggestions">
        <ul className="text-[13px] text-ink-2 list-disc pl-5 space-y-1">{r.suggestions.map((s) => <li key={s}>{s}</li>)}</ul>
        {!r.suggestions.length && <p className="text-[12px] text-ink-3">Nothing to flag — balanced week.</p>}
      </Section>
      <div className="grid gap-6 md:grid-cols-3">
        <Section title="Categories used"><Counts m={r.pillars} label={(k) => PILLAR_LABEL[k as keyof typeof PILLAR_LABEL] ?? k} /></Section>
        <Section title="Audiences targeted"><Counts m={r.audiences} label={(k) => AUDIENCE_LABEL[k as keyof typeof AUDIENCE_LABEL] ?? k} /></Section>
        <Section title="Claims repeated">
          {r.repeatedClaims.length ? (
            <ul className="text-[12px] text-ink-2 space-y-1">{r.repeatedClaims.map((c) => <li key={c.fact}><span className="mono">{c.count}×</span> {FACT_BY_ID[c.fact]?.short_claim ?? c.fact}</li>)}</ul>
          ) : <p className="text-[12px] text-ink-3">No claim used twice.</p>}
        </Section>
      </div>
      <Section title="Performance by category (manually entered)" testid="performance">
        <p className="text-[11px] text-ink-4">Observations only. Samples are tiny; nothing is optimized automatically from these numbers. Qualified replies matter more than views.</p>
        {perf.length ? (
          <div className="overflow-x-auto panel">
            <table className="w-full text-[12px]">
              <thead><tr className="text-left border-b border-line">{["category", "posts", "with results", "qualified replies", "views", "likes", "replies", "reposts"].map((h) => <th key={h} className="px-3 py-2 label font-normal">{h}</th>)}</tr></thead>
              <tbody className="mono text-ink-2">
                {perf.map((p) => (
                  <tr key={p.pillar} className="border-b border-line">
                    <td className="px-3 py-1.5 font-sans text-ink">{PILLAR_LABEL[p.pillar]}</td>
                    <td className="px-3 py-1.5">{p.posts}</td><td className="px-3 py-1.5">{p.withMetrics}</td><td className="px-3 py-1.5">{p.qualified}</td>
                    <td className="px-3 py-1.5">{p.views}</td><td className="px-3 py-1.5">{p.likes}</td><td className="px-3 py-1.5">{p.replies}</td><td className="px-3 py-1.5">{p.reposts}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <p className="text-[12px] text-ink-3">No posted items yet.</p>}
      </Section>
    </>
  );
}

function Counts({ m, label }: { m: Record<string, number>; label: (k: string) => string }) {
  const e = Object.entries(m).sort((a, b) => b[1] - a[1]);
  return e.length ? <ul className="text-[12px] text-ink-2 space-y-0.5">{e.map(([k, v]) => <li key={k}><span className="mono">{v}×</span> {label(k)}</li>)}</ul> : <p className="text-[12px] text-ink-3">None.</p>;
}
