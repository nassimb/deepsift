/** Downlink representation of one Navcam acquisition — pure logic, no data imports (unit-tested in tests/representation.test.ts).
 *  Eyes come from the frozen PDS product IDs (Navcam IDs start with NL… / NR…). A stereo acquisition that is retained is sent
 *  as a FULL_STEREO_PAIR (both eyes at the full-quality tier); otherwise as a THUMBNAIL_PAIR. Mono acquisitions are never
 *  called stereo: FULL_MONO / THUMBNAIL_MONO. */
export type Representation = "FULL_STEREO_PAIR" | "THUMBNAIL_PAIR" | "FULL_MONO" | "THUMBNAIL_MONO";
export type EyeTier = "FULL" | "THUMBNAIL" | "NONE";

export interface AcquisitionProducts {
  stereo: boolean;
  primary: string[];
  thumbnails: string[];
}

export const eyeOf = (productId: string): "L" | "R" | "?" => (productId[1] === "L" ? "L" : productId[1] === "R" ? "R" : "?");

export function representation(a: AcquisitionProducts, retained: boolean): Representation {
  if (a.stereo) return retained ? "FULL_STEREO_PAIR" : "THUMBNAIL_PAIR";
  return retained ? "FULL_MONO" : "THUMBNAIL_MONO";
}

/** Eyes to display: LEFT/RIGHT for stereo, a single MONO for mono (never labelled stereo). */
export function eyeLabels(a: AcquisitionProducts): { key: string; label: "LEFT" | "RIGHT" | "MONO" }[] {
  if (!a.stereo) return [{ key: a.primary[0] ? eyeOf(a.primary[0]) : "M", label: "MONO" }];
  return [{ key: "L", label: "LEFT" }, { key: "R", label: "RIGHT" }];
}

/** Tier at which each eye is actually represented, from the product IDs present for that eye. */
export function eyeTiers(a: AcquisitionProducts, retained: boolean): Record<string, EyeTier> {
  const eyes = a.stereo ? ["L", "R"] : [a.primary[0] ? eyeOf(a.primary[0]) : a.thumbnails[0] ? eyeOf(a.thumbnails[0]) : "?"];
  const out: Record<string, EyeTier> = {};
  for (const e of eyes) {
    const full = a.primary.some((p) => eyeOf(p) === e || (!a.stereo && a.primary.length === 1));
    const thumb = a.thumbnails.some((p) => eyeOf(p) === e || (!a.stereo && a.thumbnails.length === 1));
    out[e] = retained && full ? "FULL" : thumb ? "THUMBNAIL" : "NONE";
  }
  return out;
}

/** A stereo pair is broken when exactly one eye is represented at the full-quality tier while its paired eye is not. */
export function stereoBroken(a: AcquisitionProducts, retained: boolean): boolean {
  if (!a.stereo) return false;
  const t = eyeTiers(a, retained);
  return (t.L === "FULL") !== (t.R === "FULL");
}

export const productForEye = (ids: string[], eye: string, stereo: boolean): string | null =>
  (stereo ? ids.find((p) => eyeOf(p) === eye) : ids[0]) ?? null;
