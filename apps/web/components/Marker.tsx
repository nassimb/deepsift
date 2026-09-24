import { TYPE_COLOR } from "@/lib/format";

/** Event-class glyph. Shape is the primary identity channel for the three neutral classes;
 *  colour carries identity only for the three validated science classes. */
export function glyphPath(type: string | null, r: number): string {
  switch (type) {
    case "radiation": // diamond
      return `M0,${-r * 1.25} L${r * 1.25},0 L0,${r * 1.25} L${-r * 1.25},0 Z`;
    case "thermal": // triangle
      return `M0,${-r * 1.3} L${r * 1.2},${r * 0.9} L${-r * 1.2},${r * 0.9} Z`;
    case "instrument_anomaly": // cross
      return `M${-r},${-r} L${r},${r} M${r},${-r} L${-r},${r}`;
    case "unknown": // square
      return `M${-r},${-r} H${r} V${r} H${-r} Z`;
    default: // circle (atmospheric, nominal)
      return `M${-r},0 a${r},${r} 0 1,0 ${2 * r},0 a${r},${r} 0 1,0 ${-2 * r},0`;
  }
}

export function Glyph({ type, size = 10, x = 0, y = 0 }: { type: string | null; size?: number; x?: number; y?: number }) {
  const r = size / 2;
  const stroke = type === "instrument_anomaly";
  const hollow = type === "unknown";
  return (
    <path
      d={glyphPath(type, r)}
      transform={`translate(${x},${y})`}
      fill={stroke || hollow ? "none" : TYPE_COLOR[type ?? "nominal"]}
      stroke={TYPE_COLOR[type ?? "nominal"]}
      strokeWidth={stroke ? 2 : hollow ? 1.5 : 0}
    />
  );
}

export function GlyphIcon({ type, size = 10 }: { type: string | null; size?: number }) {
  const s = size + 4;
  return (
    <svg width={s} height={s} viewBox={`${-s / 2} ${-s / 2} ${s} ${s}`} className="inline-block align-middle">
      <Glyph type={type} size={size} />
    </svg>
  );
}
