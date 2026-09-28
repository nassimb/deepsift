/** Opens X's official web composer — no API, no OAuth, nothing posted automatically.
 *  Format verified against X's Web Intent reference (docs.x.com/x-for-websites/post-button/guides/web-intent):
 *  https://x.com/intent/tweet?text=…  (text: UTF-8, URL-encoded; in_reply_to: parent post ID for threads). */
export const X_INTENT_BASE = "https://x.com/intent/tweet";

export function xIntentUrl(text: string, inReplyTo?: string | null): string {
  const q = new URLSearchParams({ text });
  if (inReplyTo && /^\d{5,25}$/.test(inReplyTo)) q.set("in_reply_to", inReplyTo);
  return `${X_INTENT_BASE}?${q.toString()}`;
}

/** Post ID from a pasted X/Twitter status URL, or null. */
export function postIdFromUrl(url: string | null | undefined): string | null {
  const m = (url ?? "").trim().match(/^https:\/\/(?:www\.|mobile\.)?(?:x|twitter)\.com\/[A-Za-z0-9_]{1,15}\/status\/(\d{5,25})(?:[/?#].*)?$/);
  return m ? m[1] : null;
}
