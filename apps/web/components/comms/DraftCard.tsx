"use client";

/* One post, from idea to POSTED. Every state change is a pure function from lib/comms/store.ts; approval is refused unless
   the deterministic claim checker passes. OPEN IN X only opens X's own composer (web intent) — nothing is published here. */
import { useMemo, useState } from "react";
import { ASSETS, ASSET_BY_ID } from "@/lib/comms/assets";
import { checkPost, X_LIMIT, type ClaimCheck } from "@/lib/comms/claims";
import { FACT_BY_ID } from "@/lib/comms/facts";
import { AUDIENCE_LABEL, HOOK_STYLES, IDEA_BY_ID, PILLAR_LABEL, composePost, composeThread, type ContentIdea, type HookStyle } from "@/lib/comms/library";
import { shareability } from "@/lib/comms/shareability";
import {
  METRIC_KEYS, QUALIFIED_TYPES, approve, claimStatus, createFromIdea, editContent, markPosted, markScheduled, plan, postsOf, reject, reopen,
  setMetrics, setXUrl, setNotes, setQualified, setThreadUrl, type EditorialItem, type Format, type Metrics,
} from "@/lib/comms/store";
import { copyImageToClipboard } from "@/lib/comms/clipboardImage";
import { postIdFromUrl, xIntentUrl } from "@/lib/comms/xintent";
import { useComms } from "./CommsProvider";
import { AttachFiles, Chip, CopyButton, StatusChip } from "./ui";

type Props = { idea?: ContentIdea | null; item?: EditorialItem | null; defaultOpen?: boolean; testid?: string };

export function DraftCard({ idea: ideaProp, item: itemProp, testid = "draft-card" }: Props) {
  const { put } = useComms();
  const idea = ideaProp ?? (itemProp?.idea_id ? IDEA_BY_ID[itemProp.idea_id] : null) ?? null;
  const [local, setLocal] = useState<{ style: HookStyle; format: Format }>({ style: itemProp?.hook_style ?? idea?.defaultHook ?? "SURPRISING", format: itemProp?.format ?? "SHORT" });
  const item = itemProp ?? null;
  const [editing, setEditing] = useState<string[] | null>(null);
  const [panel, setPanel] = useState<"none" | "schedule" | "posted">("none");
  const [err, setErr] = useState<string | null>(null);

  // Preview (no item yet) comes straight from the idea.
  const style = item?.hook_style ?? local.style;
  const format = item?.format ?? local.format;
  const posts: string[] = useMemo(
    () => editing ?? (item ? postsOf(item) : idea ? (format === "THREAD" ? composeThread(idea, style) : [composePost(idea, style)]) : []),
    [editing, item, idea, format, style],
  );
  const checks: ClaimCheck[] = useMemo(() => posts.map((p) => checkPost(p)), [posts]);
  const pass = posts.length > 0 && checks.every((c) => c.status === "PASS");
  const visualId = item?.visual ?? idea?.visual ?? null;
  const visual = visualId ? ASSET_BY_ID[visualId] : null;
  const share = useMemo(() => shareability(posts[0] ?? "", !!visual), [posts, visual]);
  const facts = useMemo(() => [...new Set([...(item?.claims ?? idea?.facts ?? []), ...checks.flatMap((c) => c.facts)])], [item, idea, checks]);
  const status = item?.status ?? null;

  const [xMsg, setXMsg] = useState<{ ok: boolean; text: string; fallback?: string } | null>(null);
  /** Copy the post's image (PNG) to the clipboard, then open X's composer with the text. Nothing is posted. */
  const openInX = async (text: string, inReplyTo: string | null, withImage: boolean) => {
    const url = xIntentUrl(text, inReplyTo);
    const file = withImage ? visual?.files[0] : undefined;
    const copied = file ? await copyImageToClipboard(file.url) : null;
    const w = window.open(url, "_blank");
    if (w) w.opener = null;
    const name = file?.url.split("/").pop();
    const extra = visual && visual.files.length > 1 ? ` This visual has ${visual.files.length} images — use “Copy image” below for the others.` : "";
    setXMsg(
      copied === true ? { ok: true, text: `Image copied (${name}). In X's composer press ⌘V (Ctrl+V on Windows) to attach it.${extra}`, fallback: w ? undefined : url }
      : copied === false ? { ok: false, text: `Couldn't copy the image automatically — use “Download” below and attach ${name} in X.`, fallback: w ? undefined : url }
      : { ok: true, text: withImage ? "No attachable image for this post — text only." : "Reply opened in X (images go with post 1).", fallback: w ? undefined : url },
    );
  };

  const act = (f: () => EditorialItem) => {
    try {
      setErr(null);
      put(f());
    } catch (e) {
      setErr((e as Error).message);
    }
  };
  /** Materialize an item from the idea preview (the first time you act on it). */
  const ensure = (): EditorialItem => item ?? createFromIdea(idea!, { style: local.style, format: local.format });

  const switchHook = (s: HookStyle) => {
    if (!idea) return;
    if (!item) return setLocal({ ...local, style: s });
    const old = idea.hooks[item.hook_style ?? idea.defaultHook];
    const swap = (t: string) => (t.startsWith(old) ? idea.hooks[s] + t.slice(old.length) : t);
    act(() => editContent(item, { hook_style: s, text: swap(item.text), thread: [swap(item.thread[0] ?? ""), ...item.thread.slice(1)] }));
  };
  const switchFormat = (f: Format) => {
    if (!item) return setLocal({ ...local, format: f });
    act(() => editContent(item, { format: f }));
  };
  const hookSwappable = !item || !idea || (item.status !== "POSTED" && (item.format === "SHORT" ? item.text : item.thread[0] ?? "").startsWith(idea.hooks[item.hook_style ?? idea.defaultHook]));

  const saveEdit = () => {
    if (!editing) return;
    const it = ensure();
    act(() => editContent(it, format === "THREAD" ? { thread: editing.filter((p) => p.trim()) } : { text: editing[0] }));
    setEditing(null);
  };

  const canApprove = pass && status !== "POSTED" && status !== "APPROVED" && status !== "SCHEDULED_ON_X" && !editing;
  const canX = !!item && (status === "APPROVED" || status === "SCHEDULED_ON_X" || status === "POSTED") && pass && !editing;
  const canSchedule = status === "APPROVED" || status === "SCHEDULED_ON_X";
  const canPost = status === "APPROVED" || status === "SCHEDULED_ON_X";

  return (
    <article className="panel p-4 space-y-4" data-testid={testid} data-idea={idea?.id ?? ""} data-status={status ?? "PREVIEW"}>
      <header className="flex flex-wrap items-center gap-2">
        {item ? <StatusChip status={item.status} /> : <Chip>PREVIEW</Chip>}
        <Chip testid="category">{PILLAR_LABEL[item?.pillar ?? idea!.pillar]}</Chip>
        <Chip testid="audience">{AUDIENCE_LABEL[item?.audience ?? idea!.audience]}</Chip>
        {idea && <span className="text-[13px] text-ink ml-1">{idea.title}</span>}
        {item && <span className="mono text-[10px] text-ink-4 ml-auto" data-testid="draft-id">{item.id}</span>}
      </header>

      {idea && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="label mr-1">Hook</span>
          {HOOK_STYLES.map((s) => (
            <button key={s} type="button" className="btn" data-active={style === s ? "true" : undefined} disabled={!hookSwappable || !!editing} onClick={() => switchHook(s)} data-testid={`hook-${s}`}>
              {s}
            </button>
          ))}
          <span className="label ml-3 mr-1">Format</span>
          {(["SHORT", "THREAD"] as Format[]).map((f) => (
            <button key={f} type="button" className="btn" data-active={format === f ? "true" : undefined} disabled={status === "POSTED" || !!editing} onClick={() => switchFormat(f)} data-testid={`format-${f}`}>
              {f === "SHORT" ? "SHORT POST" : "THREAD"}
            </button>
          ))}
        </div>
      )}
      {idea && (
        <div className="text-[12px] text-ink-3">
          <span className="label mr-2">Hook</span>
          <span data-testid="hook-text" className="text-ink-2">{idea.hooks[style]}</span>
        </div>
      )}

      <div className="space-y-3">
        {posts.map((p, i) => (
          <div key={i} className="space-y-1.5" data-testid="post">
            {format === "THREAD" && <div className="label">Post {i + 1} / {posts.length}</div>}
            {editing ? (
              <textarea data-testid="post-editor" className="w-full min-h-[150px] bg-panel-2 border border-line-2 text-ink text-[13px] p-3 leading-relaxed" value={editing[i]}
                onChange={(e) => setEditing(editing.map((x, j) => (j === i ? e.target.value : x)))} />
            ) : (
              <pre data-testid="post-text" className="whitespace-pre-wrap break-words font-sans text-[14px] leading-relaxed text-ink bg-panel-2 border border-line p-3">{p}</pre>
            )}
            <div className="flex flex-wrap items-center gap-2 text-[11px]">
              <span className="mono" data-testid="char-count" style={{ color: checks[i]?.chars > X_LIMIT ? "var(--s-critical)" : "var(--ink-3)" }}>
                {checks[i]?.chars ?? 0} / {X_LIMIT} characters
              </span>
              <span className="mono" data-testid="post-claim" style={{ color: checks[i]?.status === "PASS" ? "var(--s-good)" : "var(--s-critical)" }}>
                CLAIM CHECK {checks[i]?.status}
              </span>
              {format === "THREAD" && !editing && (
                <>
                  <CopyButton text={p} label={`Copy post ${i + 1}`} testid={`copy-post-${i}`} />
                  {canX && (
                    <a className="btn" target="_blank" rel="noopener noreferrer" data-testid={`open-x-${i}`}
                      href={xIntentUrl(p, i > 0 ? postIdFromUrl(item!.thread_urls[i - 1] || (i === 1 ? item!.x_url : null)) : null)}
                      onClick={(e) => { e.preventDefault(); void openInX(p, i > 0 ? postIdFromUrl(item!.thread_urls[i - 1] || (i === 1 ? item!.x_url : null)) : null, i === 0); }}>
                      Open post {i + 1} in X
                    </a>
                  )}
                  {item && i < posts.length - 1 && status !== "IDEA" && (
                    <input className="bg-panel-2 border border-line text-ink-2 text-[11px] px-2 py-1 min-w-0 w-[260px]" placeholder={`URL of post ${i + 1} once live (for replies)`}
                      defaultValue={item.thread_urls[i] ?? (i === 0 ? item.x_url ?? "" : "")} onBlur={(e) => e.target.value !== (item.thread_urls[i] ?? "") && act(() => setThreadUrl(item, i, e.target.value))} />
                  )}
                </>
              )}
            </div>
            {editing && format === "THREAD" && posts.length > 1 && (
              <button type="button" className="btn" onClick={() => setEditing(editing.filter((_, j) => j !== i))}>Remove post</button>
            )}
          </div>
        ))}
        {editing && format === "THREAD" && editing.length < 7 && (
          <button type="button" className="btn" onClick={() => setEditing([...editing, ""])}>+ Add post</button>
        )}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2" data-testid="claim-check">
          <div className="label">Claim check</div>
          <div className="mono text-[14px]" style={{ color: pass ? "var(--s-good)" : "var(--s-critical)" }} data-testid="claim-status">
            CLAIM CHECK {pass ? "PASS" : "FAIL"}
          </div>
          {!pass && (
            <ul className="space-y-1 text-[12px]" data-testid="claim-issues">
              {checks.flatMap((c, i) => c.issues.map((iss, k) => (
                <li key={`${i}-${k}`} style={{ color: "var(--s-serious)" }}>
                  {posts.length > 1 ? `Post ${i + 1}: ` : ""}[{iss.rule}] {iss.message}{iss.match ? ` — “${iss.match}”` : ""}
                </li>
              )))}
            </ul>
          )}
        </div>
        <div className="space-y-2" data-testid="shareability">
          <div className="label">Shareability check <span className="normal-case tracking-normal text-ink-4">(simple YES/NO factors — not a prediction)</span></div>
          <ul className="text-[12px] space-y-0.5">
            {share.map((f) => (
              <li key={f.key} className="flex gap-2">
                <span className="mono w-8" style={{ color: f.ok ? "var(--s-good)" : "var(--s-warn)" }}>{f.ok ? "YES" : "NO"}</span>
                <span className="text-ink-2">{f.label}</span>
                {!f.ok && <span className="text-ink-3">— {f.suggestion}</span>}
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2" data-testid="visual">
          <div className="label">Recommended visual</div>
          {visual ? (
            <div className="flex gap-3 items-start">
              {visual.preview && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={visual.preview} alt={visual.name} className="w-28 h-20 object-contain bg-panel-2 border border-line shrink-0" loading="lazy" />
              )}
              <div className="text-[12px] space-y-1 min-w-0">
                <div className="text-ink">{visual.name}</div>
                <div className="text-ink-3">{visual.description}</div>
                {visual.caption && <div className="text-ink-4 italic">Caption: {visual.caption}</div>}
                <a className="text-[11px] underline text-ink-2" href={visual.open} target="_blank" rel="noopener noreferrer">Open asset ↗</a>
                <AttachFiles files={visual.files} />
              </div>
            </div>
          ) : (
            <div className="text-[12px] text-ink-3">No visual — text only.</div>
          )}
          {item && status !== "POSTED" && (
            <select className="bg-panel-2 border border-line text-ink-2 text-[12px] px-2 py-1 max-w-full" value={visualId ?? ""} data-testid="visual-select"
              onChange={(e) => act(() => editContent(item, { visual: e.target.value || null }))}>
              <option value="">No visual</option>
              {ASSETS.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          )}
          {idea?.video && (
            <div className="text-[12px] border border-line p-2 space-y-1" data-testid="video-idea">
              <div className="label">Video idea · {idea.video.duration}</div>
              <div className="text-ink-2"><span className="text-ink-3">Start:</span> {idea.video.start}</div>
              <ol className="list-decimal pl-5 text-ink-2">{idea.video.steps.map((s) => <li key={s}>{s}</li>)}</ol>
              <div className="text-ink-3">Show: {idea.video.show.join(" · ")}</div>
            </div>
          )}
        </div>
        <div className="space-y-2" data-testid="sources">
          <div className="label">Sources (verified facts)</div>
          <ul className="space-y-1.5 text-[12px]">
            {facts.map((id) => {
              const f = FACT_BY_ID[id];
              if (!f) return null;
              return (
                <li key={id}>
                  <details>
                    <summary className="cursor-pointer text-ink-2"><span className="mono text-ink-4">{id}</span> — {f.short_claim}</summary>
                    <div className="pl-3 pt-1 space-y-0.5 text-ink-3">
                      <div><span className="text-ink-4">source:</span> <span className="mono break-all">{f.source_file}</span> → {f.source_field_or_section}</div>
                      <div><span className="text-ink-4">scope:</span> {f.scope}</div>
                      {f.limitations && <div><span className="text-ink-4">limits:</span> {f.limitations}</div>}
                      {f.forbidden_wording.length > 0 && <div><span className="text-ink-4">never say:</span> {f.forbidden_wording.join(" · ")}</div>}
                    </div>
                  </details>
                </li>
              );
            })}
          </ul>
        </div>
      </div>

      {err && <p className="text-[12px]" role="alert" data-testid="card-error" style={{ color: "var(--s-critical)" }}>{err}</p>}

      <div className="flex flex-wrap gap-2 items-center border-t border-line pt-3">
        {editing ? (
          <>
            <button type="button" className="btn" data-active="true" onClick={saveEdit} data-testid="save">Save</button>
            <button type="button" className="btn" onClick={() => setEditing(null)} data-testid="cancel">Cancel</button>
            <span className="text-[11px] text-ink-3">Saving an edit sends an approved post back to DRAFT.</span>
          </>
        ) : (
          <>
            <CopyButton text={posts.join("\n\n")} label="Copy" testid="copy" />
            <button type="button" className="btn" disabled={status === "POSTED"} onClick={() => setEditing([...posts])} data-testid="edit">Edit</button>
            <button type="button" className="btn" disabled={!canApprove} onClick={() => act(() => approve(ensure()))} data-testid="approve"
              title={pass ? "" : "The claim check must PASS before approval."}>Approve</button>
            {status === "REJECTED" ? (
              <button type="button" className="btn" onClick={() => act(() => reopen(item!))} data-testid="reopen">Reopen</button>
            ) : (
              <button type="button" className="btn" disabled={status === "POSTED"} onClick={() => act(() => reject(ensure()))} data-testid="reject">Reject</button>
            )}
            {canX ? (
              <a className="btn" data-active="true" href={xIntentUrl(posts[0])} target="_blank" rel="noopener noreferrer" data-testid="open-x"
                onClick={(e) => { e.preventDefault(); void openInX(posts[0], null, true); }}>Open in X ↗</a>
            ) : (
              <button type="button" className="btn" disabled data-testid="open-x" title="Approve first.">Open in X ↗</button>
            )}
            <button type="button" className="btn" disabled={!canSchedule} onClick={() => setPanel(panel === "schedule" ? "none" : "schedule")} data-testid="mark-scheduled">Mark scheduled</button>
            <button type="button" className="btn" disabled={!canPost} onClick={() => setPanel(panel === "posted" ? "none" : "posted")} data-testid="mark-posted">Mark posted</button>
            {status !== "POSTED" && (
              <label className="text-[11px] text-ink-3 flex items-center gap-1 ml-auto">
                Plan for
                <input type="date" className="bg-panel-2 border border-line text-ink-2 px-1 py-0.5" value={item?.planned_at ?? ""} data-testid="plan-date"
                  onChange={(e) => act(() => plan(ensure(), e.target.value || null))} />
              </label>
            )}
          </>
        )}
      </div>
      {!editing && (canX || status === "APPROVED") && (
        <p className="text-[11px] text-ink-3" data-testid="x-help">
          OPEN IN X copies the post&apos;s image to your clipboard (PNG) and opens X&apos;s own composer with the text prefilled. Press ⌘V in the
          composer to attach the image, then publish — or use X&apos;s native
          schedule option to pick a date and time. DEEPSIFT never publishes or schedules anything itself.{format === "THREAD" ? " For a thread, post 1 first, paste its URL, then open the next post (it opens as a reply)." : ""}
        </p>
      )}

      {xMsg && (
        <p className="text-[12px]" role="status" data-testid="x-msg" style={{ color: xMsg.ok ? "var(--s-good)" : "var(--s-warn)" }}>
          {xMsg.text}
          {xMsg.fallback && <> Your browser blocked the new tab — <a className="underline" href={xMsg.fallback} target="_blank" rel="noopener noreferrer">open X&apos;s composer</a>.</>}
        </p>
      )}
      {panel === "schedule" && item && <ScheduleForm item={item} onDone={(it) => { act(() => it); setPanel("none"); }} onError={setErr} />}
      {panel === "posted" && item && <PostedForm item={item} onDone={(it) => { act(() => it); setPanel("none"); }} onError={setErr} />}

      {item && (item.status === "SCHEDULED_ON_X" || item.status === "POSTED") && (
        <div className="text-[12px] text-ink-2 space-y-0.5" data-testid="x-record">
          {item.scheduled_at && <div>Scheduled on X for <span className="mono">{item.scheduled_at.replace("T", " ")}</span> (recorded manually)</div>}
          {item.posted_at && (
            <div>
              Posted <span className="mono">{item.posted_at.slice(0, 16).replace("T", " ")}</span>
              {item.x_url ? <> · <a className="underline" href={item.x_url} target="_blank" rel="noopener noreferrer">{item.x_url}</a></> : " · no X URL recorded"}
            </div>
          )}
          {item.status === "POSTED" && <PostedUrl item={item} onChange={(it) => act(() => it)} onError={setErr} />}
        </div>
      )}
      {item && item.status === "POSTED" && <AfterPost item={item} onChange={(it) => act(() => it)} />}
      {item && <Notes item={item} onChange={(it) => act(() => it)} />}
    </article>
  );
}

function ScheduleForm({ item, onDone, onError }: { item: EditorialItem; onDone: (it: EditorialItem) => void; onError: (e: string) => void }) {
  const [date, setDate] = useState(item.scheduled_at?.slice(0, 10) ?? item.planned_at ?? "");
  const [time, setTime] = useState(item.scheduled_at?.slice(11, 16) ?? "09:00");
  return (
    <form className="panel p-3 flex flex-wrap items-end gap-3" data-testid="schedule-form" onSubmit={(e) => {
      e.preventDefault();
      try { onDone(markScheduled(item, date, time)); } catch (x) { onError((x as Error).message); }
    }}>
      <label className="text-[11px] text-ink-3 flex flex-col gap-1">Scheduled date (as set in X)<input required type="date" value={date} onChange={(e) => setDate(e.target.value)} className="bg-panel-2 border border-line text-ink px-2 py-1" data-testid="schedule-date" /></label>
      <label className="text-[11px] text-ink-3 flex flex-col gap-1">Time<input required type="time" value={time} onChange={(e) => setTime(e.target.value)} className="bg-panel-2 border border-line text-ink px-2 py-1" data-testid="schedule-time" /></label>
      <button type="submit" className="btn" data-active="true" data-testid="schedule-save">Save as SCHEDULED_ON_X</button>
      <p className="text-[11px] text-ink-4 w-full">Record only. The post is scheduled in X&apos;s own composer; DEEPSIFT does not publish it.</p>
    </form>
  );
}

function PostedForm({ item, onDone, onError }: { item: EditorialItem; onDone: (it: EditorialItem) => void; onError: (e: string) => void }) {
  const [url, setUrl] = useState(item.x_url ?? "");
  const [date, setDate] = useState(item.scheduled_at?.slice(0, 10) ?? "");
  const [time, setTime] = useState(item.scheduled_at?.slice(11, 16) ?? "");
  const [notes, setN] = useState("");
  const input = "bg-panel-2 border border-line text-ink px-2 py-1";
  return (
    <form className="panel p-3 space-y-2" data-testid="posted-form" onSubmit={(e) => {
      e.preventDefault();
      try { onDone(markPosted(item, { xUrl: url, date, time, notes })); } catch (x) { onError((x as Error).message); }
    }}>
      <label className="text-[11px] text-ink-3 flex flex-col gap-1">X post URL (optional)<input type="url" placeholder="https://x.com/you/status/…" value={url} onChange={(e) => setUrl(e.target.value)} className={input} data-testid="posted-url" /></label>
      <div className="flex flex-wrap gap-3">
        <label className="text-[11px] text-ink-3 flex flex-col gap-1">Publication date (optional — default: now)<input type="date" value={date} onChange={(e) => setDate(e.target.value)} className={input} data-testid="posted-date" /></label>
        <label className="text-[11px] text-ink-3 flex flex-col gap-1">Time (optional)<input type="time" value={time} onChange={(e) => setTime(e.target.value)} className={input} data-testid="posted-time" /></label>
      </div>
      <label className="text-[11px] text-ink-3 flex flex-col gap-1">Notes (optional)<input value={notes} onChange={(e) => setN(e.target.value)} className={input} data-testid="posted-notes" /></label>
      <button type="submit" className="btn" data-active="true" data-testid="posted-save">Save as POSTED</button>
      <p className="text-[11px] text-ink-4">You published it yourself in X. Everything here is stored as entered — never checked through any X API. Views, likes, replies etc. can be added below once saved.</p>
    </form>
  );
}

function PostedUrl({ item, onChange, onError }: { item: EditorialItem; onChange: (it: EditorialItem) => void; onError: (e: string) => void }) {
  const [url, setUrl] = useState(item.x_url ?? "");
  return (
    <form className="flex flex-wrap gap-2 items-center" onSubmit={(e) => { e.preventDefault(); try { onChange(setXUrl(item, url)); } catch (x) { onError((x as Error).message); } }}>
      <input type="url" placeholder="https://x.com/you/status/…" value={url} onChange={(e) => setUrl(e.target.value)} data-testid="x-url-edit"
        className="bg-panel-2 border border-line text-ink text-[12px] px-2 py-1 min-w-0 flex-1" />
      <button type="submit" className="btn" data-testid="x-url-save">{item.x_url ? "Update URL" : "Add URL"}</button>
    </form>
  );
}

function AfterPost({ item, onChange }: { item: EditorialItem; onChange: (it: EditorialItem) => void }) {
  const [m, setM] = useState<Metrics>(item.metrics);
  const [qType, setQType] = useState(QUALIFIED_TYPES[0]);
  const [qNote, setQNote] = useState("");
  return (
    <div className="grid gap-4 md:grid-cols-2" data-testid="after-post">
      <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); onChange(setMetrics(item, m)); }}>
        <div className="label">Results (manual, optional)</div>
        <div className="grid grid-cols-3 gap-2">
          {METRIC_KEYS.map((k) => (
            <label key={k} className="text-[10px] text-ink-3 flex flex-col gap-0.5">{k.replace("_", " ")}
              <input type="number" min={0} value={m[k] ?? ""} data-testid={`metric-${k}`} onChange={(e) => setM({ ...m, [k]: e.target.value === "" ? undefined : Number(e.target.value) })}
                className="bg-panel-2 border border-line text-ink px-1.5 py-1 min-w-0" />
            </label>
          ))}
        </div>
        <button type="submit" className="btn" data-testid="metrics-save">Save results</button>
      </form>
      <div className="space-y-2">
        <div className="label">Qualified replies</div>
        <p className="text-[11px] text-ink-4">Who replied with relevant expertise — entered by you, never inferred. Matters more than views.</p>
        <ul className="text-[12px] text-ink-2 space-y-0.5" data-testid="qualified-list">
          {item.qualified_replies.map((q, i) => (
            <li key={i} className="flex gap-2 items-baseline">
              <span className="mono text-[11px]">{q.type}</span><span className="text-ink-3">{q.note}</span>
              <button type="button" className="text-[10px] underline text-ink-4" onClick={() => onChange(setQualified(item, item.qualified_replies.filter((_, j) => j !== i)))}>remove</button>
            </li>
          ))}
        </ul>
        <div className="flex flex-wrap gap-2">
          <select value={qType} onChange={(e) => setQType(e.target.value)} className="bg-panel-2 border border-line text-ink-2 text-[12px] px-2 py-1" data-testid="qualified-type">
            {QUALIFIED_TYPES.map((t) => <option key={t}>{t}</option>)}
          </select>
          <input value={qNote} onChange={(e) => setQNote(e.target.value)} placeholder="note (optional)" className="bg-panel-2 border border-line text-ink text-[12px] px-2 py-1 min-w-0 flex-1" />
          <button type="button" className="btn" data-testid="qualified-add" onClick={() => { onChange(setQualified(item, [...item.qualified_replies, { type: qType, note: qNote }])); setQNote(""); }}>Add</button>
        </div>
      </div>
    </div>
  );
}

function Notes({ item, onChange }: { item: EditorialItem; onChange: (it: EditorialItem) => void }) {
  const [v, setV] = useState(item.notes);
  return (
    <label className="block text-[11px] text-ink-3 space-y-1">
      <span className="label">Notes</span>
      <textarea value={v} onChange={(e) => setV(e.target.value)} onBlur={() => v !== item.notes && onChange(setNotes(item, v))} data-testid="notes"
        className="w-full min-h-[48px] bg-panel-2 border border-line text-ink-2 text-[12px] p-2" />
    </label>
  );
}

export { claimStatus };
