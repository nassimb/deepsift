/** Server-side gate for the private /admin area (runs before any /admin route renders).
 *  - auth not configured → 503 (fail closed)
 *  - no session → redirect to /admin/login
 *  - signed in as any GitHub account other than the allowed one → 403
 *  /admin/login itself is reachable so the sign-in button can be shown. Every /admin response is marked noindex. */
import { NextResponse, type NextFetchEvent, type NextRequest } from "next/server";
import { auth } from "@/auth";
import { adminAccess, authConfigured, safeAdminPath } from "@/lib/admin/access";

const NOINDEX = { "X-Robots-Tag": "noindex, nofollow", "Cache-Control": "private, no-store" };

const page = (status: number, title: string, body: string) =>
  new NextResponse(
    `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="robots" content="noindex,nofollow"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${status} ${title}</title></head>` +
      `<body style="background:#07080a;color:#e4e7ea;font:14px ui-monospace,monospace;padding:40px 16px"><h1 style="font-size:16px;letter-spacing:.15em">${status} ${title.toUpperCase()}</h1><p style="color:#a3abb4">${body}</p></body></html>`,
    { status, headers: { "content-type": "text/html; charset=utf-8", ...NOINDEX } },
  );

const gate = auth((req) => {
  const { pathname } = req.nextUrl;
  if (pathname === "/admin/login") {
    const res = NextResponse.next();
    Object.entries(NOINDEX).forEach(([k, v]) => res.headers.set(k, v));
    return res;
  }
  const access = adminAccess(req.auth?.user);
  if (access === "login") {
    const url = new URL("/admin/login", req.nextUrl.origin);
    url.searchParams.set("next", safeAdminPath(pathname));
    return NextResponse.redirect(url);
  }
  if (access === "forbidden")
    return page(403, "Forbidden", `This GitHub account is not allowed here. <a style="color:#6da7ec" href="/admin/login">Sign out or switch account</a>`);
  const res = NextResponse.next();
  Object.entries(NOINDEX).forEach(([k, v]) => res.headers.set(k, v));
  return res;
});

export default function proxy(req: NextRequest, ev: NextFetchEvent) {
  if (!authConfigured(process.env)) return page(503, "Admin not configured", "Server-side GitHub OAuth variables are not set.");
  return (gate as unknown as (r: NextRequest, e: NextFetchEvent) => Promise<Response> | Response)(req, ev);
}

export const config = { matcher: ["/admin", "/admin/:path*"] };
