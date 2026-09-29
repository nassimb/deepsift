/** Put a post's image on the clipboard as PNG so it can be pasted (⌘V / Ctrl+V) into X's composer.
 *  X's web intent cannot carry attachments, and the X API is deliberately not used — this keeps publishing manual.
 *  Browsers only accept image/png on the clipboard, so JPEGs are converted to PNG in memory (the file itself is unchanged). */

async function pngBlob(url: string): Promise<Blob> {
  const res = await fetch(url, { cache: "force-cache" });
  if (!res.ok) throw new Error(`image ${res.status}`);
  const blob = await res.blob();
  if (blob.type === "image/png") return blob;
  const bmp = await createImageBitmap(blob);
  const canvas = document.createElement("canvas");
  canvas.width = bmp.width;
  canvas.height = bmp.height;
  canvas.getContext("2d")!.drawImage(bmp, 0, 0);
  return await new Promise<Blob>((ok, fail) => canvas.toBlob((b) => (b ? ok(b) : fail(new Error("png conversion failed"))), "image/png"));
}

/** True when the image is on the clipboard. The ClipboardItem gets a promise synchronously, which Safari requires. */
export async function copyImageToClipboard(url: string): Promise<boolean> {
  try {
    if (typeof ClipboardItem === "undefined" || !navigator.clipboard?.write) return false;
    await navigator.clipboard.write([new ClipboardItem({ "image/png": pngBlob(url) })]);
    return true;
  } catch {
    return false;
  }
}
