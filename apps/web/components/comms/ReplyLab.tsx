"use client";

/* REPLY LAB — paste someone's X post, contribute something useful, mention DEEPSIFT only when it belongs.
   Deterministic (lib/comms/reply.ts): no model, no API. Nothing is posted; OPEN IN X opens X's own reply composer. */
import { useMemo, useState } from "react";
import { FACT_BY_ID } from "@/lib/comms/facts";
import {
  ANGLE_BY_ID, LINK_URL, REPLY_STYLES, SEMANTIC_LIMITATION, STYLE_LABEL, analyzePost, checkReply, conversationValue, draftStyle, expertQuestion,
  linkRecommendation, mentionsProject, pickAngles, primaryOptions, promoRisk, recommend, repetition, shouldMention, wouldMakeSenseWithoutDeepsift,
  type LinkRec, type ReplyDraft, type ReplyInput,
} from "@/lib/comms/reply";
import { upsertReply, type ReplyRecord } from "@/lib/comms/store";
import { postIdFromUrl, xIntentUrl } from "@/lib/comms/xintent";
import { useComms } from "./CommsProvider";
import { Chip, CopyButton, Section } from "./ui";

const REL_COLOR: Record<string, string> = { DIRECT: "var(--s-good)", ADJACENT: "var(--a-full)", WEAK: "var(--s-warn)", NONE: "var(--ink-3)", STRONG: "var(--s-good)", MODERATE: "var(--a-full)" };
const RISK_COLOR = { LOW: "var(--s-good)", MEDIUM: "var(--s-warn)", HIGH: "var(--s-critical)" } as const;
const field = "bg-panel-2 border border-line text-ink text-[13px] px-3 py-2 w-full min-w-0";

const newReplyId = () => `r-${Date.now().toString(36)}-${Math.floor(Math.random() * 1e6).toString(36)}`;

export function ReplyLabView() {
  const { state, ready, replace } = useComms();
  const [form, setForm] = useState<ReplyInput>({ text: "", url: "", authorName: "", authorHandle: "", context: "" });
  const [input, setInput] = useState<ReplyInput | null>(null);
  const [override, setOverride] = useState(false);
  const [angleId, setAngleId] = useState<string | null>(null);
  const [choice, setChoice] = useState<string>("NATURAL");
  const [text, setText] = useState("");
  const [editing, setEditing] = useState(false);
  const [link, setLink] = useState<LinkRec | null>(null);
  const [savedId, setSavedId] = useState<string | null>(null);

  const history = useMemo(() => state.replies ?? [], [state.replies]);
  const rep = useMemo(() => repetition(history), [history]);
  const a = useMemo(() => (input ? analyzePost(input) : null), [input]);
  const angles = useMemo(() => (a ? pickAngles(a, rep, override) : []), [a, rep, override]);
  const angle = (angleId && angles.find((g) => g.id === angleId)) || angles[0] || null;
  const options = useMemo(() => (a ? primaryOptions(a, angle, override) : []), [a, angle, override]);
  const styles = useMemo(() => (a ? REPLY_STYLES.map((s) => ({ ...draftStyle(s, a, angle, override), key: `STYLE:${s}` })) : []), [a, angle, override]);
  const all: ReplyDraft[] = [...options, ...styles];
  const mention = a ? shouldMention(a, rep, override, angle) : null;
  const rec = a && mention ? recommend(a, options, mention) : null;
  const current = all.find((o) => o.key === choice) ?? rec ?? null;
  const q = a ? expertQuestion(a) : null;
  const linkRec = a ? linkRecommendation(a) : null;
  const chosenLink: LinkRec = link ?? linkRec?.link ?? "NONE";
  const check = useMemo(() => checkReply(text, { relevance: a?.relevance, override }), [text, a, override]);
  const risk = a && text.trim() ? promoRisk(text, a) : null;
  const cv = a ? conversationValue(a, text, current) : null;
  const without = text.trim() ? wouldMakeSenseWithoutDeepsift(text) : null;

  const pick = (d: ReplyDraft | null | undefined) => {
    setChoice(d?.key ?? "NATURAL");
    setText(d?.available ? d.text : "");
    setEditing(false);
    setSavedId(null);
  };

  const analyze = () => {
    if (!form.text.trim()) return;
    const next = { ...form };
    setInput(next);
    setAngleId(null);
    setLink(null);
    setOverride(false);
    const an = analyzePost(next);
    const g = pickAngles(an, rep)[0] ?? null;
    const opts = primaryOptions(an, g);
    pick(recommend(an, opts, shouldMention(an, rep, false, g)));
  };

  const toggleOverride = (on: boolean) => {
    setOverride(on);
    if (!a) return;
    const g = pickAngles(a, rep, on)[0] ?? null;
    const opts = primaryOptions(a, g, on);
    if (on) pick(opts[3].available ? opts[3] : opts[0]);
    else pick(recommend(a, opts, shouldMention(a, rep, false, g)));
  };

  const changeAngle = (id: string) => {
    setAngleId(id);
    if (!a) return;
    const g = ANGLE_BY_ID[id];
    const d = [...primaryOptions(a, g, override), ...REPLY_STYLES.map((s) => ({ ...draftStyle(s, a, g, override), key: `STYLE:${s}` }))].find((o) => o.key === choice);
    if (d?.available) setText(d.text);
  };

  const withLink = chosenLink !== "NONE" ? `${text}\n\n${LINK_URL[chosenLink]}` : text;
  const replyTo = postIdFromUrl(input?.url);

  const save = () => {
    if (!a || !input || !text.trim()) return;
    const now = new Date().toISOString();
    const project = mentionsProject(text);
    const rec2: ReplyRecord = {
      id: savedId ?? newReplyId(),
      created_at: history.find((h) => h.id === savedId)?.created_at ?? now, updated_at: now,
      post_text: input.text, post_url: input.url || null, author_name: input.authorName ?? "", author_handle: input.authorHandle ?? "",
      context: input.context ?? "", reply: text, style: current?.label || choice, angle: project ? current?.angle ?? null : null,
      facts: project ? [...new Set([...check.facts, ...(current?.facts ?? [])])] : check.facts,
      relevance: a.relevance, promo_risk: risk?.risk ?? "LOW", value: cv?.what ?? "", link: chosenLink === "NONE" ? null : LINK_URL[chosenLink],
      posted: false, reply_url: null, mentions_project: project, domain: a.domain ?? undefined,
    };
    replace(upsertReply(state, rec2));
    setSavedId(rec2.id);
  };

  if (!ready) return null;
  const factsShown = [...new Set([...check.facts, ...(mentionsProject(text) ? current?.facts ?? [] : [])])];
  return (
    <>
      <div className="space-y-1">
        <h1 className="text-[22px] text-ink">Reply lab</h1>
        <p className="text-[13px] text-ink-2">Paste a post. Contribute something useful. Mention DEEPSIFT only when it genuinely belongs in the conversation.</p>
      </div>

      <form className="space-y-2" data-testid="reply-form" onSubmit={(e) => { e.preventDefault(); analyze(); }}>
        <label className="label block" htmlFor="post-text">Paste an X post</label>
        <textarea id="post-text" required data-testid="post-input" className={`${field} min-h-[140px] leading-relaxed`} placeholder="Post text (required)"
          value={form.text} onChange={(e) => setForm({ ...form, text: e.target.value })} />
        <div className="grid gap-2 sm:grid-cols-3">
          <input className={field} placeholder="Post URL (optional)" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} data-testid="post-url" />
          <input className={field} placeholder="Author name (optional)" value={form.authorName} onChange={(e) => setForm({ ...form, authorName: e.target.value })} data-testid="author-name" />
          <input className={field} placeholder="Author handle (optional)" value={form.authorHandle} onChange={(e) => setForm({ ...form, authorHandle: e.target.value })} data-testid="author-handle" />
        </div>
        <input className={field} placeholder="My context (optional) — e.g. “works on onboard autonomy”, “I want to ask a question”, “don't mention DEEPSIFT”"
          value={form.context} onChange={(e) => setForm({ ...form, context: e.target.value })} data-testid="my-context" />
        <button type="submit" className="btn" data-active="true" data-testid="analyze" style={{ padding: "9px 16px" }}>Analyze post</button>
      </form>

      {a && input && (
        <div className="space-y-6" data-testid="reply-result">
          <p className="text-[11px] text-ink-4" data-testid="semantic-note">{SEMANTIC_LIMITATION}</p>

          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
            <div className="panel p-3 space-y-1" data-testid="topic">
              <div className="label">Original topic</div>
              <div className="mono text-[14px] text-ink" data-testid="domain-value">{a.domain ?? "—"}</div>
              <p className="text-[12px] text-ink-3">{a.about}</p>
            </div>
            <div className="panel p-3 space-y-1" data-testid="value">
              <div className="label">What could I add?</div>
              <div className="text-[13px] text-ink" data-testid="value-value">{cv?.what}</div>
              {!cv?.reply && <div className="mono text-[16px]" style={{ color: "var(--s-warn)" }} data-testid="dont-reply">DON&apos;T REPLY</div>}
            </div>
            <div className="panel p-3 space-y-1" data-testid="relevance">
              <div className="label">DEEPSIFT relevance</div>
              <div className="mono text-[18px]" style={{ color: REL_COLOR[a.relevance] }} data-testid="relevance-value">{a.relevance}</div>
              {a.noConnection && <div className="mono text-[12px] text-ink" data-testid="no-connection">NO NATURAL DEEPSIFT CONNECTION</div>}
              <p className="text-[12px] text-ink-3">{a.relevanceWhy}</p>
            </div>
            <div className="panel p-3 space-y-1" data-testid="mention">
              <div className="label">Should DEEPSIFT be mentioned?</div>
              <div className="mono text-[18px]" style={{ color: mention?.mention ? "var(--a-full)" : "var(--ink-2)" }} data-testid="mention-value">{mention?.mention ? "YES" : "NO"}</div>
              <p className="text-[12px] text-ink-3">{mention?.why}</p>
            </div>
          </div>

          <div className="flex flex-wrap gap-x-6 gap-y-2 text-[12px]">
            <span data-testid="recent-mentions" className="text-ink-3">
              <span className="label mr-1">Recent project mentions</span>
              {rep.recentCount ? `${rep.recentMentions} of last ${rep.recentCount} replies mentioned DEEPSIFT` : "no saved replies yet"} <span className="text-ink-4">(target ≈ 15–30%)</span>
            </span>
            {(a.relevance === "WEAK") && !a.suppressProject && (
              <label className="flex items-center gap-1.5 text-ink-3" data-testid="override-label">
                <input type="checkbox" checked={override} onChange={(e) => toggleOverride(e.target.checked)} data-testid="override" />
                Project-connection override (not recommended here)
              </label>
            )}
          </div>

          {rep.warnings.length > 0 && (
            <ul className="text-[12px] space-y-1" data-testid="repetition" style={{ color: "var(--s-warn)" }}>{rep.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
          )}

          <Section title="Recommended reply" testid="recommended">
            <div className="flex flex-wrap gap-1.5" data-testid="options">
              {options.map((o) => (
                <button key={o.key} type="button" className="btn" data-active={choice === o.key ? "true" : undefined} disabled={!o.available} title={o.unavailableReason}
                  onClick={() => pick(o)} data-testid={`opt-${o.key}`}>{o.label}{rec?.key === o.key ? " · recommended" : ""}</button>
              ))}
            </div>
            <div className="flex flex-wrap gap-1.5" data-testid="styles">
              {styles.map((s) => (
                <button key={s.style} type="button" className="btn" data-active={choice === s.key ? "true" : undefined} disabled={!s.available}
                  title={s.unavailableReason} onClick={() => pick(s)} data-testid={`style-${s.style}`}>{STYLE_LABEL[s.style]}</button>
              ))}
            </div>
            {angles.length > 1 && current?.project && (
              <label className="text-[11px] text-ink-3 flex flex-wrap items-center gap-2">
                DEEPSIFT talking point
                <select value={angle?.id ?? ""} onChange={(e) => changeAngle(e.target.value)} className="bg-panel-2 border border-line text-ink-2 text-[12px] px-2 py-1 max-w-full" data-testid="angle-select">
                  {angles.map((g) => <option key={g.id} value={g.id}>{g.label}{rep.angleCounts[g.id] ? ` (used ${rep.angleCounts[g.id]}× recently)` : ""}</option>)}
                </select>
              </label>
            )}
            {current && !current.available && <p className="text-[12px]" style={{ color: "var(--s-warn)" }} data-testid="unavailable">{current.unavailableReason}</p>}

            {editing ? (
              <textarea data-testid="reply-editor" className={`${field} min-h-[140px] leading-relaxed`} value={text} onChange={(e) => setText(e.target.value)} />
            ) : (
              <pre data-testid="reply-text" className="whitespace-pre-wrap break-words font-sans text-[14px] leading-relaxed text-ink bg-panel-2 border border-line p-3 min-h-[60px]">
                {text || <span className="text-ink-4">{a.noConnection ? "Nothing generated — no subject to respond to. Write your own with EDIT, or don't reply." : "No draft."}</span>}
              </pre>
            )}

            <div className="flex flex-wrap gap-3 text-[11px] items-center">
              <span className="mono" data-testid="reply-chars" style={{ color: check.chars > 280 ? "var(--s-critical)" : "var(--ink-3)" }}>{check.chars} / 280 characters</span>
              <span className="mono" data-testid="reply-claim" style={{ color: text.trim() && check.status === "PASS" ? "var(--s-good)" : "var(--s-critical)" }}>
                CLAIM CHECK {text.trim() ? check.status : "—"}
              </span>
              {risk && (
                <span data-testid="promo-risk"><span className="label mr-1">Promotional risk</span><span className="mono" style={{ color: RISK_COLOR[risk.risk] }} data-testid="promo-value">{risk.risk}</span><span className="text-ink-3"> — {risk.why}</span></span>
              )}
            </div>
            {without !== null && (
              <p className="text-[12px]" data-testid="promotionality">
                <span className="label mr-1">Would this reply make sense if I had never built DEEPSIFT?</span>
                <span className="mono" data-testid="promotionality-value" style={{ color: without ? "var(--s-good)" : "var(--s-warn)" }}>{without ? "YES" : "NO"}</span>
                {!without && <span className="text-ink-3"> — it relies on your own experiment{a.relevance === "DIRECT" ? "; fine here, the connection is direct." : a.relevance === "ADJACENT" ? "; acceptable only because it adds a concrete finding." : "; rejected unless you use the override."}</span>}
              </p>
            )}
            {text.trim() && check.status === "FAIL" && (
              <ul className="text-[12px] space-y-0.5" data-testid="reply-issues" style={{ color: "var(--s-serious)" }}>
                {check.issues.map((i, k) => <li key={k}>[{i.rule}] {i.message}{i.match ? ` — “${i.match}”` : ""}</li>)}
              </ul>
            )}
            {check.warnings.length > 0 && <ul className="text-[12px]" style={{ color: "var(--s-warn)" }} data-testid="reply-warnings">{check.warnings.map((w, k) => <li key={k}>[{w.rule}] {w.message}</li>)}</ul>}
            {risk?.risk === "HIGH" && options[0]?.available && (
              <p className="text-[12px]" style={{ color: "var(--s-critical)" }} data-testid="promo-warning">
                High promotional risk. Less promotional alternative: <button type="button" className="underline" onClick={() => pick(options[0])}>use the natural reply</button>.
              </p>
            )}

            <div className="flex flex-wrap gap-2 border-t border-line pt-3">
              <CopyButton text={text} label="Copy reply" testid="copy-reply" />
              <CopyButton text={withLink} label={`Copy + link${chosenLink !== "NONE" ? ` (${chosenLink.toLowerCase()})` : ""}`} testid="copy-link" />
              <button type="button" className="btn" onClick={() => setEditing(!editing)} data-testid="edit-reply">{editing ? "Done" : "Edit"}</button>
              <button type="button" className="btn" disabled={!text.trim()} onClick={save} data-testid="save-reply">{savedId ? "Saved ✓ (save again)" : "Save to history"}</button>
              {input.url && <a className="btn" href={input.url} target="_blank" rel="noopener noreferrer" data-testid="open-original">Open original post ↗</a>}
              {text.trim() && check.status === "PASS" ? (
                <a className="btn" data-active="true" href={xIntentUrl(text, replyTo)} target="_blank" rel="noopener noreferrer" data-testid="open-x-reply">Open in X ↗</a>
              ) : (
                <button type="button" className="btn" disabled data-testid="open-x-reply" title="Needs a reply that passes the claim check.">Open in X ↗</button>
              )}
            </div>
            <p className="text-[11px] text-ink-3" data-testid="reply-x-help">
              {replyTo ? "OPEN IN X opens X's reply composer under the original post with your text prefilled. You review and publish it yourself."
                : "No valid post URL: X would open a new post, not a reply. Paste the post URL above for a real reply. Nothing is ever published automatically."}
            </p>
          </Section>

          <div className="grid gap-4 md:grid-cols-2">
            <Section title="Conversation-value test" testid="value-test">
              <ul className="text-[12px] space-y-0.5">
                {cv?.checks.map((c) => (
                  <li key={c.key} className="flex gap-2"><span className="mono w-8" style={{ color: c.ok ? "var(--s-good)" : "var(--ink-4)" }}>{c.ok ? "YES" : "NO"}</span><span className="text-ink-2">{c.label}</span></li>
                ))}
              </ul>
              {!cv?.reply && <p className="text-[12px]" style={{ color: "var(--s-warn)" }}>None apply → DON&apos;T REPLY.</p>}
            </Section>
            <div className="space-y-4">
              <Section title="Expert question" testid="expert-question">
                {q ? (
                  <div className="space-y-2">
                    <p className="text-[13px] text-ink-2">{q}</p>
                    <button type="button" className="btn" onClick={() => pick({ ...all.find((o) => o.key === "STYLE:QUESTION")!, text: q, available: true })} data-testid="use-question">Use as reply</button>
                  </div>
                ) : <p className="text-[12px] text-ink-3">None.</p>}
              </Section>
              <Section title="Link recommendation" testid="link-rec">
                <div className="flex flex-wrap items-center gap-2 text-[12px]">
                  <span className="mono text-ink" data-testid="link-value">{linkRec?.link}</span>
                  <span className="text-ink-3">— {linkRec?.why}</span>
                </div>
                <select value={chosenLink} onChange={(e) => setLink(e.target.value as LinkRec)} className="bg-panel-2 border border-line text-ink-2 text-[12px] px-2 py-1" data-testid="link-select">
                  {(["NONE", "MISSION CONTROL", "FINAL TEST", "RESEARCH", "GITHUB", "HOMEPAGE"] as LinkRec[]).map((l) => <option key={l}>{l}</option>)}
                </select>
              </Section>
            </div>
          </div>

          <Section title="Alternatives" testid="alternatives">
            <ul className="grid gap-2 md:grid-cols-2">
              {all.filter((o, i) => o.available && o.key !== choice && o.text !== text && all.findIndex((x) => x.available && x.text === o.text) === i).slice(0, 4).map((o) => (
                <li key={o.key} className="panel p-2 space-y-1">
                  <div className="flex items-center gap-2"><span className="label">{o.label}</span>{o.project && <Chip>mentions your project</Chip>}<button type="button" className="btn ml-auto" onClick={() => pick(o)}>Use</button></div>
                  <p className="text-[12px] text-ink-2 whitespace-pre-wrap">{o.text}</p>
                </li>
              ))}
            </ul>
          </Section>

          <Section title="Facts used" testid="facts-used">
            {factsShown.length ? (
              <ul className="text-[12px] space-y-1">
                {factsShown.map((f) => (
                  <li key={f}><span className="mono text-ink-4">{f}</span> — <span className="text-ink-2">{FACT_BY_ID[f]?.short_claim}</span> <span className="text-ink-4">({FACT_BY_ID[f]?.source_file})</span></li>
                ))}
              </ul>
            ) : <p className="text-[12px] text-ink-3">No DEEPSIFT facts in this reply.</p>}
          </Section>
        </div>
      )}

      <ReplyHistory />
    </>
  );
}

export function ReplyHistory({ compact = false }: { compact?: boolean }) {
  const { state, replace } = useComms();
  const list = [...(state.replies ?? [])].sort((x, y) => y.created_at.localeCompare(x.created_at));
  const update = (r: ReplyRecord, patch: Partial<ReplyRecord>) => replace(upsertReply(state, { ...r, ...patch, updated_at: new Date().toISOString() }));
  return (
    <Section title={`Reply history (${list.length})`} testid="reply-history">
      {list.length === 0 && <p className="text-[12px] text-ink-3">No saved replies in this browser yet.</p>}
      <ul className="space-y-2">
        {list.slice(0, compact ? 10 : 100).map((r) => (
          <li key={r.id} className="panel p-3 space-y-1.5 text-[12px]" data-testid="reply-row">
            <div className="flex flex-wrap items-center gap-2">
              <Chip color={REL_COLOR[r.relevance]}>{r.relevance}</Chip>
              <Chip color={RISK_COLOR[r.promo_risk]}>risk {r.promo_risk}</Chip>
              {r.domain && <Chip>{r.domain}</Chip>}
              <Chip>{r.style}</Chip>
              {(r.mentions_project ?? /DEEPSIFT/i.test(r.reply)) ? <Chip color="var(--a-full)">mentions DEEPSIFT</Chip> : <Chip>no project mention</Chip>}
              {r.posted ? <Chip color="var(--s-good)">POSTED</Chip> : <Chip>NOT POSTED</Chip>}
              <span className="mono text-[10px] text-ink-4 ml-auto">{r.created_at.slice(0, 16).replace("T", " ")}</span>
            </div>
            <div className="text-ink-3">
              {r.author_name || r.author_handle ? `${r.author_name} ${r.author_handle}`.trim() + ": " : ""}“{r.post_text.slice(0, 140)}{r.post_text.length > 140 ? "…" : ""}”
              {r.post_url && <> · <a className="underline" href={r.post_url} target="_blank" rel="noopener noreferrer">original</a></>}
            </div>
            <pre className="whitespace-pre-wrap break-words font-sans text-ink-2 border-l border-line pl-2">{r.reply}</pre>
            <div className="text-ink-4">facts: {r.facts.join(", ") || "none"} · value: {r.value}{r.link ? ` · link: ${r.link}` : ""}</div>
            <div className="flex flex-wrap items-center gap-2">
              <label className="flex items-center gap-1 text-ink-3">
                <input type="checkbox" checked={r.posted} onChange={(e) => update(r, { posted: e.target.checked })} data-testid="reply-posted" /> posted
              </label>
              <input className="bg-panel-2 border border-line text-ink-2 text-[11px] px-2 py-1 min-w-0 flex-1" placeholder="Reply URL (optional, once posted)" defaultValue={r.reply_url ?? ""}
                onBlur={(e) => e.target.value.trim() !== (r.reply_url ?? "") && update(r, { reply_url: e.target.value.trim() || null })} data-testid="reply-url" />
            </div>
          </li>
        ))}
      </ul>
    </Section>
  );
}
