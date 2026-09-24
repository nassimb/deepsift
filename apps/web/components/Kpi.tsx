export function Kpi({ label, value, sub, title }: { label: string; value: React.ReactNode; sub?: React.ReactNode; title?: string }) {
  return (
    <div className="px-3 py-2 border-r border-line min-w-0" title={title}>
      <div className="label truncate">{label}</div>
      <div className="mono text-[19px] leading-7 text-ink truncate">{value}</div>
      {sub != null && <div className="mono text-[10px] text-ink-3 truncate">{sub}</div>}
    </div>
  );
}

export function Section({ title, right, children, className = "" }: { title: string; right?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <section className={`panel flex flex-col min-h-0 ${className}`}>
      <div className="flex items-center gap-2 px-3 h-8 border-b border-line shrink-0">
        <span className="label" style={{ color: "var(--ink-2)" }}>
          {title}
        </span>
        <div className="ml-auto flex items-center gap-2">{right}</div>
      </div>
      <div className="flex-1 min-h-0">{children}</div>
    </section>
  );
}
