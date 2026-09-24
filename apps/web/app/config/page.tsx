"use client";

import { useEffect, useState } from "react";
import { Section } from "@/components/Kpi";
import { Nav, SourceBadges, useStatus } from "@/components/Nav";
import { api } from "@/lib/api";

type Cfg = Record<string, unknown>;
interface Change {
  changed_at: string;
  from_version: string;
  to_version: string;
  diff: { path: string; before: unknown; after: unknown }[];
  note: string;
}

// editable fields grouped for researchers; everything else stays in config/default.yaml
const FIELDS: [string, string, string][] = [
  ["detection.z_threshold", "Candidate |z| threshold (REMS)", "σ vs nearest-local-time baseline"],
  ["detection.rad_z_threshold", "Candidate |z| threshold (RAD)", "σ"],
  ["detection.dip_threshold_pa", "Pressure dip threshold", "Pa below 60 s running median"],
  ["detection.noise_ratio_threshold", "Noise ratio threshold", "× baseline sample-to-sample noise"],
  ["detection.baseline_sols", "Baseline sols", "trailing sols in the baseline"],
  ["gating.auto_threshold", "Engine confidence: automatic routing ≥", "0–1"],
  ["gating.uncertain_threshold", "Engine confidence: keep-but-uncertain ≥", "0–1; below → rules / deep"],
  ["gating.deep_request_threshold", "Deep analysis threshold", "P(needs_deep_analysis)"],
  ["priority.weights.science_value", "Weight · science value", ""],
  ["priority.weights.mission_relevance", "Weight · mission relevance", ""],
  ["priority.weights.anomaly_strength", "Weight · anomaly strength", ""],
  ["priority.weights.novelty", "Weight · novelty", ""],
  ["priority.confidence_penalty", "Confidence penalty λ", "U × (1 − λ(1 − conf))"],
  ["priority.cost_exponent", "Cost exponent β", "scheduler density = U / KB^β"],
  ["priority.thresholds.full_data", "Threshold · FULL DATA", "utility ≥"],
  ["priority.thresholds.compress", "Threshold · COMPRESS", "utility ≥"],
  ["priority.thresholds.summary_only", "Threshold · SUMMARY", "utility ≥"],
  ["compression.decimation_factor", "Compression decimation", "COMPRESS keeps 1 of N records"],
  ["compression.fidelity.compress", "Assumed fidelity · COMPRESS", "proxy metric assumption"],
  ["compression.fidelity.summary_only", "Assumed fidelity · SUMMARY", "proxy metric assumption"],
  ["downlink.pass_bytes", "Downlink per relay pass", "bytes"],
  ["downlink.passes_per_sol", "Relay passes per sol", ""],
  ["downlink.storage_bytes", "Onboard storage", "bytes"],
  ["blackout.storage_bytes", "Storage during blackout", "bytes"],
  ["blackout.duration_sols", "Default blackout duration", "sols"],
];

function get(o: Cfg, path: string): unknown {
  return path.split(".").reduce<unknown>((a, k) => (a as Cfg)?.[k], o);
}
function setPath(path: string, v: unknown): Cfg {
  const keys = path.split(".");
  const out: Cfg = {};
  let cur = out;
  keys.forEach((k, i) => {
    if (i === keys.length - 1) cur[k] = v;
    else cur = cur[k] = {} as Cfg;
  });
  return out;
}
function merge(a: Cfg, b: Cfg): Cfg {
  const o: Cfg = { ...a };
  for (const [k, v] of Object.entries(b)) o[k] = v && typeof v === "object" && !Array.isArray(v) ? merge((o[k] as Cfg) ?? {}, v as Cfg) : v;
  return o;
}

export default function ConfigPage() {
  const { status } = useStatus();
  const [cfg, setCfg] = useState<Cfg | null>(null);
  const [version, setVersion] = useState("");
  const [changes, setChanges] = useState<Change[]>([]);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () =>
    api<{ version: string; config: Cfg; changes: Change[] }>("/api/config").then((r) => {
      setCfg(r.config);
      setVersion(r.version);
      setChanges(r.changes);
      setDraft({});
    });
  useEffect(() => {
    void load();
  }, []);

  const apply = async () => {
    let patch: Cfg = {};
    for (const [p, v] of Object.entries(draft)) patch = merge(patch, setPath(p, Number(v)));
    setBusy(true);
    try {
      const r = await api<{ version: string; changes: unknown[]; rerun: string; ms: number }>("/api/config", { method: "PUT", body: JSON.stringify({ patch, note }) });
      setMsg(`config ${r.version} · ${r.changes.length} change(s) · ${r.rerun === "full" ? "full pipeline re-run" : "re-scored stored decisions"} in ${r.ms.toFixed(0)} ms`);
      setNote("");
      await load();
    } catch (e) {
      setMsg(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col">
      <Nav right={<SourceBadges status={status} replay={false} />} />
      <div className="flex-1 grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-3 p-3">
        <Section title={`Researcher configuration · version ${version}`}>
          <div className="p-3">
            <table className="w-full text-[12px]">
              <tbody>
                {cfg &&
                  FIELDS.map(([path, label, hint]) => {
                    const cur = get(cfg, path);
                    const dirty = draft[path] != null && Number(draft[path]) !== cur;
                    return (
                      <tr key={path} className="border-b border-line">
                        <td className="py-1 pr-2 text-ink-2">{label}</td>
                        <td className="mono text-[10px] text-ink-4 pr-2">{path}</td>
                        <td className="w-28">
                          <input
                            type="number"
                            step="any"
                            value={draft[path] ?? String(cur)}
                            onChange={(e) => setDraft({ ...draft, [path]: e.target.value })}
                            className="w-full"
                            style={{ borderColor: dirty ? "var(--ink-2)" : undefined }}
                          />
                        </td>
                        <td className="mono text-[10px] text-ink-3 pl-2">{hint}</td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
            <div className="flex items-center gap-2 mt-3">
              <input type="text" placeholder="note for the audit log (why?)" value={note} onChange={(e) => setNote(e.target.value)} className="flex-1" />
              <button className="btn" disabled={busy || !Object.keys(draft).length} onClick={apply}>
                {busy ? "Applying…" : "Apply & record"}
              </button>
            </div>
            {msg && <div className="mono text-[11px] text-ink-2 mt-2">{msg}</div>}
            <div className="text-[11px] text-ink-3 mt-3 leading-relaxed">
              Detection / compression changes re-run the full pipeline on the raw products. Gating, priority, downlink and objective changes
              re-score stored engine decisions without new engine calls. Engine selection (mock / Jev) and deep-analysis provider are set in
              <span className="mono"> config/default.yaml</span> plus environment variables.
            </div>
          </div>
        </Section>
        <Section title={`Change history · ${changes.length}`}>
          <div className="p-3 space-y-3 overflow-y-auto">
            {changes.map((c, i) => (
              <div key={i} className="border-b border-line pb-2">
                <div className="mono text-[10px] text-ink-3">
                  {c.changed_at.slice(0, 19).replace("T", " ")} UTC · {c.from_version} → {c.to_version} {c.note && `· “${c.note}”`}
                </div>
                {c.diff.map((d) => (
                  <div key={d.path} className="mono text-[11px]">
                    <span className="text-ink-2">{d.path}</span> <span className="text-ink-4">{JSON.stringify(d.before)}</span> →{" "}
                    <span className="text-ink">{JSON.stringify(d.after)}</span>
                  </div>
                ))}
              </div>
            ))}
            {!changes.length && <div className="text-ink-3 text-[12px]">No changes recorded yet.</div>}
          </div>
        </Section>
      </div>
    </div>
  );
}
