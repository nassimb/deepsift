/** Private admin access rule — pure logic, no imports (unit-tested in tests/admin-access.test.ts).
 *  Exactly one GitHub account may use /admin: the login AND the immutable numeric account id must both match, so a renamed
 *  or re-registered "nassimb" handle cannot inherit access. Evaluated server-side only (proxy.ts and the admin layout). */
export const ADMIN_GITHUB_LOGIN = "nassimb";
export const ADMIN_GITHUB_ID = 3143068;

export type AdminUser = { login?: unknown; ghid?: unknown } | null | undefined;
export type AdminAccess = "ok" | "login" | "forbidden";

export function adminAccess(user: AdminUser): AdminAccess {
  if (!user || (user.login == null && user.ghid == null)) return "login";
  const login = typeof user.login === "string" ? user.login.toLowerCase() : "";
  const id = typeof user.ghid === "number" ? user.ghid : typeof user.ghid === "string" && /^\d+$/.test(user.ghid) ? Number(user.ghid) : NaN;
  return login === ADMIN_GITHUB_LOGIN && id === ADMIN_GITHUB_ID ? "ok" : "forbidden";
}

/** Only same-site /admin paths are accepted as post-login destinations (no open redirect). */
export function safeAdminPath(p: unknown): string {
  return typeof p === "string" && /^\/admin(\/[A-Za-z0-9/_-]*)?$/.test(p) && !p.startsWith("/admin/login") ? p : "/admin/comms";
}

/** Auth is usable only when all three server-side secrets exist; otherwise /admin fails closed (503). */
export function authConfigured(env: Record<string, string | undefined>): boolean {
  return Boolean(env.AUTH_SECRET && env.AUTH_GITHUB_ID && env.AUTH_GITHUB_SECRET);
}
