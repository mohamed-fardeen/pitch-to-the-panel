/**
 * NextAuth.js v5 configuration (edge-compatible).
 *
 * This file is imported by:
 *   - auth.ts            (Node runtime, full feature set)
 *   - middleware.ts      (edge runtime, slim feature set)
 *
 * Anything that needs Node APIs (e.g. database adapters, fs) lives in
 * auth.ts, NOT here. The edge runtime can't import those.
 *
 * Providers enabled:
 *   - Google  (Google OAuth 2.0)
 *   - GitHub  (GitHub OAuth)
 *   - Credentials (email + password; not wired up in Tier 0 — placeholder)
 *
 * See auth.ts for the full handler that exposes API routes.
 */

import type { NextAuthConfig } from "next-auth";
import Google from "next-auth/providers/google";
import GitHub from "next-auth/providers/github";
import Credentials from "next-auth/providers/credentials";

const ALLOWED_EMAILS = (process.env.PANELMIND_ALLOWED_EMAILS ?? "")
  .split(",")
  .map((s) => s.trim().toLowerCase())
  .filter(Boolean);

export const authConfig: NextAuthConfig = {
  // Required: trust the host header in dev. In prod, NEXTAUTH_URL must be set.
  trustHost: true,

  pages: {
    signIn: "/signin",
    signOut: "/signout",
    error: "/signin",
  },

  providers: [
    // Only configure a provider if its env vars are set. This lets the
    // app boot in environments where not all providers are configured.
    ...(process.env.GOOGLE_ID && process.env.GOOGLE_SECRET
      ? [
          Google({
            clientId: process.env.GOOGLE_ID,
            clientSecret: process.env.GOOGLE_SECRET,
            // Request email scope so we can show the user's email in the UI
            authorization: { params: { prompt: "consent", access_type: "offline" } },
          }),
        ]
      : []),
    ...(process.env.GITHUB_ID && process.env.GITHUB_SECRET
      ? [
          GitHub({
            clientId: process.env.GITHUB_ID,
            clientSecret: process.env.GITHUB_SECRET,
          }),
        ]
      : []),
    // Credentials provider for local dev. Accepts any email + password
    // combo (no actual validation — this is for testing the sign-in flow
    // without setting up OAuth). Disable in production by setting
    // PANELMIND_ALLOW_DEV_LOGIN=false.
    ...(process.env.PANELMIND_ALLOW_DEV_LOGIN !== "false"
      ? [
          Credentials({
            id: "dev-credentials",
            name: "Local dev (no password)",
            credentials: {
              email: { label: "Email", type: "email", placeholder: "dev@panelmind.local" },
              password: { label: "Password", type: "password", placeholder: "any" },
            },
            async authorize(credentials) {
              if (!credentials?.email) return null;
              // Local dev: accept any email, no password check
              return {
                id: credentials.email as string,
                email: credentials.email as string,
                name: (credentials.email as string).split("@")[0],
                image: null,
              };
            },
          }),
        ]
      : []),
  ],

  callbacks: {
    /**
     * Gate which emails can sign in. Empty allowlist = allow everyone.
     * Set PANELMIND_ALLOWED_EMAILS to a comma-separated list to restrict.
     */
    signIn({ user }) {
      if (ALLOWED_EMAILS.length === 0) return true;
      return ALLOWED_EMAILS.includes((user.email ?? "").toLowerCase());
    },

    /**
     * Add the user id and provider to the session token. The frontend
     * reads session.user.id to make authenticated API calls.
     */
    async jwt({ token, user, account }) {
      if (user && account) {
        token.userId = (user as any).id ?? token.sub;
        token.provider = account.provider;
      }
      return token;
    },

    async session({ session, token }) {
      if (session.user && token.userId) {
        (session.user as any).id = token.userId;
        (session.user as any).provider = token.provider;
      }
      return session;
    },
  },

  session: {
    strategy: "jwt",
    maxAge: 30 * 24 * 60 * 60, // 30 days
  },
};