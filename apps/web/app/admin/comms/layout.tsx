/* Private comms console shell. Authorization is enforced server-side twice: in proxy.ts (403/redirect before render) and
   here (defense in depth). Editorial state never leaves the browser (localStorage). */
import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { auth, signOut } from "@/auth";
import { CommsNav } from "@/components/comms/CommsNav";
import { CommsProvider } from "@/components/comms/CommsProvider";
import { adminAccess } from "@/lib/admin/access";

export const metadata: Metadata = { title: { default: "Comms console", template: "%s · Comms" }, robots: { index: false, follow: false, nocache: true } };

export default async function CommsLayout({ children }: { children: React.ReactNode }) {
  const session = await auth();
  const access = adminAccess(session?.user);
  if (access === "login") redirect("/admin/login?next=/admin/comms");
  if (access === "forbidden")
    return (
      <main className="p-8 mono text-[13px]" data-testid="forbidden">
        403 FORBIDDEN — this GitHub account is not allowed. <a className="underline" href="/admin/login">Sign out</a>
      </main>
    );

  return (
    <CommsProvider>
      <header className="sticky top-0 z-20 border-b border-line" style={{ background: "var(--bg)" }}>
        <div className="px-3 sm:px-4 min-h-11 py-1.5 flex flex-wrap items-center gap-x-4 gap-y-1">
          <a href="/admin/comms" className="mono tracking-[0.2em] text-[12px] text-ink whitespace-nowrap">DEEPSIFT · COMMS</a>
          <span className="mono text-[10px] text-ink-4 border border-line-2 px-1.5 py-0.5">PRIVATE</span>
          <CommsNav />
          <div className="ml-auto flex items-center gap-2 text-[11px] text-ink-3">
            <span className="mono" data-testid="whoami">@{session?.user?.login}</span>
            <form action={async () => { "use server"; await signOut({ redirectTo: "/admin/login" }); }}>
              <button type="submit" className="btn" data-testid="logout">Sign out</button>
            </form>
          </div>
        </div>
      </header>
      <main className="max-w-[1240px] mx-auto px-4 sm:px-6 py-6 space-y-8">{children}</main>
    </CommsProvider>
  );
}
