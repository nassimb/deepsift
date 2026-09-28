/** POST /api/subscribe — adds an e-mail to the DEEPSIFT updates list (Neon 'Deepsift', table `subscribers`).
 *  Called only when a visitor submits the footer form; no research page depends on it. DATABASE_URL is server-only. */
import { neon } from "@neondatabase/serverless";

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

export async function POST(request: Request) {
  const origin = request.headers.get("origin");
  if (origin && new URL(origin).host !== new URL(request.url).host) {
    return Response.json({ ok: false, error: "Cross-origin requests are not accepted." }, { status: 403 });
  }
  let body: { email?: unknown; website?: unknown };
  try {
    body = await request.json();
  } catch {
    return Response.json({ ok: false, error: "Invalid request." }, { status: 400 });
  }
  if (typeof body.website === "string" && body.website.trim() !== "") return Response.json({ ok: true }); // honeypot field
  const email = typeof body.email === "string" ? body.email.trim() : "";
  if (email.length > 254 || !EMAIL.test(email)) {
    return Response.json({ ok: false, error: "Please enter a valid e-mail address." }, { status: 400 });
  }
  const url = process.env.DATABASE_URL;
  if (!url) return Response.json({ ok: false, error: "Sign-ups are not available yet — please try again later." }, { status: 503 });
  try {
    const sql = neon(url);
    await sql`INSERT INTO subscribers (email) VALUES (${email}) ON CONFLICT (email_normalized) DO NOTHING`;
  } catch {
    return Response.json({ ok: false, error: "Could not save your e-mail right now — please try again later." }, { status: 500 });
  }
  return Response.json({ ok: true });
}
