import { ACTION_COLOR } from "@/lib/format";
import { ACT_LABEL, ACT_ORDER, HOME } from "@/lib/home";

/** Static preview of the replay timeline: every candidate event of the segment, by instrument and final decision. */
export function ReplayPreview() {
  const r = HOME.replay;
  return (
    <div className="panel p-3">
      <div className="hidden sm:block"><Lanes W={1180} laneH={30} font={10} every={2} /></div>
      <div className="sm:hidden"><Lanes W={360} laneH={30} font={11} every={5} /></div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-1 pt-1 mono text-[10px] text-ink-3">
        <span>SOL →</span>
        {ACT_ORDER.map((a) => (
          <span key={a} className="flex items-center gap-1.5">
            <i className="inline-block w-2.5 h-2.5" style={{ background: ACTION_COLOR[a] }} />
            {ACT_LABEL[a]} {r.final_actions[a] ?? 0}
          </span>
        ))}
        <span className="sm:ml-auto">{r.events} candidate events · {r.samples.toLocaleString()} samples</span>
      </div>
    </div>
  );
}

/** Same data at two sizes: phones get larger type and fewer ticks instead of a shrunken desktop chart. */
function Lanes({ W, laneH, font, every }: { W: number; laneH: number; font: number; every: number }) {
  const r = HOME.replay;
  const s0 = r.sols[0], s1 = r.sols[1] + 1;
  const L = 46, R = 8;
  const lanes = ["REMS", "RAD"];
  const X = (s: number) => L + ((s - s0) / (s1 - s0)) * (W - L - R);
  const H = lanes.length * (laneH + 10) + 30;
  const ticks = Array.from({ length: Math.floor((s1 - s0) / every) + 1 }, (_, i) => s0 + i * every);
  const bo = r.blackout;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img"
      aria-label={`Timeline of ${r.events} candidate events over sols ${r.sols[0]} to ${r.sols[1]}, coloured by downlink decision`}>
      <rect x={X(bo.start_sol)} y={0} width={X(bo.end_sol) - X(bo.start_sol)} height={H - 24} fill="var(--panel-2)" />
      <text x={X(bo.start_sol) + 4} y={font} fontSize={font - 1} className="mono" fill="var(--ink-3)">
        {W > 600 ? "OUTAGE USED IN THE BLACKOUT DEMO" : "OUTAGE"}
      </text>
      {lanes.map((lane, li) => {
        const y = 16 + li * (laneH + 10);
        return (
          <g key={lane}>
            <text x={0} y={y + laneH / 2 + 4} fontSize={font} className="mono" fill="var(--ink-2)">{lane}</text>
            <line x1={L} x2={W - R} y1={y + laneH / 2} y2={y + laneH / 2} stroke="var(--line)" />
            {r.event_rows.filter((e) => e[1] === lane).map((e) => (
              <rect key={e[0]} x={X(e[2])} y={y + 3} width={Math.max(W > 600 ? 2 : 1.5, X(e[3]) - X(e[2]))} height={laneH - 6}
                fill={ACTION_COLOR[e[5]]} opacity={0.95}>
                <title>{`${e[0]} · ${e[4] ?? ""} · ${ACT_LABEL[e[5]]}`}</title>
              </rect>
            ))}
          </g>
        );
      })}
      {ticks.map((t) => (
        <text key={t} x={X(t)} y={H - 6} fontSize={font} textAnchor="middle" className="mono" fill="var(--ink-3)">{t}</text>
      ))}
    </svg>
  );
}
