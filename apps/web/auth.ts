/** Auth.js (GitHub OAuth) for the private /admin area. Server-side only: secrets come from AUTH_SECRET, AUTH_GITHUB_ID and
 *  AUTH_GITHUB_SECRET (never NEXT_PUBLIC_*). Any GitHub user can complete sign-in, but lib/admin/access.ts allows exactly one
 *  account; everyone else gets 403. Sessions are stateless encrypted JWT cookies — no database. */
import NextAuth from "next-auth";
import GitHub from "next-auth/providers/github";

declare module "next-auth" {
  interface Session {
    user: { login?: string; ghid?: number; name?: string | null; image?: string | null };
  }
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [GitHub],
  session: { strategy: "jwt", maxAge: 60 * 60 * 12 },
  pages: { signIn: "/admin/login", error: "/admin/login" },
  callbacks: {
    jwt({ token, profile }) {
      if (profile) {
        token.login = typeof profile.login === "string" ? profile.login : undefined;
        token.ghid = typeof profile.id === "number" ? profile.id : Number(profile.id);
      }
      return token;
    },
    session({ session, token }) {
      return { ...session, user: { name: session.user?.name ?? null, image: session.user?.image ?? null, login: token.login as string | undefined, ghid: token.ghid as number | undefined } };
    },
  },
});
