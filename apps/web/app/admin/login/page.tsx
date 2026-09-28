import type { Metadata } from "next";
import { auth, signIn, signOut } from "@/auth";
import { adminAccess, safeAdminPath } from "@/lib/admin/access";

export const metadata: Metadata = { title: "Sign in", robots: { index: false, follow: false } };

export default async function AdminLogin({ searchParams }: PageProps<"/admin/login">) {
  const sp = await searchParams;
  const next = safeAdminPath(sp.next);
  const session = await auth();
  const access = adminAccess(session?.user);
  const error = typeof sp.error === "string" ? sp.error : null;

  return (
    <main className="min-h-screen flex items-center justify-center px-4">
      <div className="panel p-6 w-full max-w-[420px] space-y-4">
        <div className="mono tracking-[0.2em] text-[12px] text-ink">DEEPSIFT · PRIVATE</div>
        <p className="text-[13px] text-ink-2">This area is private. Sign in with the authorized GitHub account.</p>
        {error && <p className="text-[12px]" style={{ color: "var(--s-warn)" }}>Sign-in failed ({error}). Try again.</p>}
        {session?.user && (
          <p className="text-[12px] text-ink-3" data-testid="signed-in-as">
            Signed in as <span className="mono text-ink">{session.user.login ?? "unknown"}</span>
            {access === "forbidden" ? " — this account is not allowed (403)." : "."}
          </p>
        )}
        {access !== "ok" && (
          <form action={async () => { "use server"; await signIn("github", { redirectTo: next }); }}>
            <button type="submit" className="btn w-full" data-active="true" style={{ padding: "10px 14px" }}>Sign in with GitHub</button>
          </form>
        )}
        {access === "ok" && <a href={next} className="btn inline-block">Continue to the console →</a>}
        {session?.user && (
          <form action={async () => { "use server"; await signOut({ redirectTo: "/admin/login" }); }}>
            <button type="submit" className="btn w-full" data-testid="logout">Sign out</button>
          </form>
        )}
      </div>
    </main>
  );
}
