/** SHAREABILITY CHECK — transparent YES/NO factors with plain suggestions. Deliberately not a score and never a
 *  probability of going viral. Pure logic. */
import { factsIn } from "./claims.ts";

export interface ShareFactor {
  key: string;
  label: string;
  ok: boolean;
  suggestion: string;
}

const JARGON = /\b(AUROC|pHash|farthest-point|monoton\w*|EDR|PLACES|embedding\w*|MobileNetV2|QUALITY_V2|bootstrap|CI|SHA-256|acquisitions?|REMS|RAD|non-monotonic|pre-registered|stereo-safe|tier)\b/gi;
const INTERNAL = /\b(METADATA_POSITION|POSITION_PLUS_EMBEDDING\w*|EVERY_NTH_FRAME|UNIFORM_DISTANCE|trav\d+|P[0-5]\b|V[123]\b|Jev)\b/;
const CONTRAST = /\b(but|didn['’]t|did not|mostly|instead|only|not|simpler|fail(ed|s)?|then|no measurable|wasn['’]t|none|without)\b/i;

export function shareability(text: string, hasVisual: boolean): ShareFactor[] {
  const firstLine = text.split("\n")[0].trim();
  const hookJargon = firstLine.match(JARGON) ?? [];
  const allJargon = new Set((text.match(JARGON) ?? []).map((j) => j.toLowerCase()));
  const numbers = text.match(/\d+(?:\.\d+)?\s?(?:%|m\b|×)/g) ?? [];
  const facts = factsIn(text);
  return [
    { key: "hook", label: "Strong opening sentence", ok: firstLine.length > 0 && firstLine.length <= 90 && hookJargon.length === 0,
      suggestion: firstLine.length > 90 ? "Hook is too long — cut it under 90 characters." : hookJargon.length ? `Hook is too technical (${hookJargon.join(", ")}).` : "Open with the finding or the question." },
    { key: "one_idea", label: "One clear idea", ok: facts.length <= 3, suggestion: "More than three facts — split this into a thread or two posts." },
    { key: "visual", label: "Visual available", ok: hasVisual, suggestion: "Needs a visual — pick an asset." },
    { key: "number", label: "Specific number", ok: numbers.length > 0 || facts.length > 0 || /[+−-]\d*\.\d+|\b\d+\.\d+\b/.test(text), suggestion: "Add one verified number." },
    { key: "contrast", label: "Surprising contrast", ok: CONTRAST.test(text), suggestion: "State what didn't work or what was expected vs what happened." },
    { key: "no_paper", label: "Understandable without the paper", ok: !INTERNAL.test(text), suggestion: "Replace internal names (method IDs, V1/V2/V3, traverse IDs) with plain words." },
    { key: "jargon", label: "No jargon overload", ok: allJargon.size <= 2 && numbers.length <= 4,
      suggestion: numbers.length > 4 ? "Too many numbers — keep the one that matters most." : `Too much jargon (${[...allJargon].join(", ")}).` },
  ];
}
