/**
 * NextAuth.js v5 — full handler.
 *
 * This is the Node-runtime entry point. It exports:
 *   - `auth`        — the helper to call in Server Components
 *   - `handlers`    — the GET/POST handlers for the API route
 *   - `signIn`      — server action for sign-in
 *   - `signOut`     — server action for sign-out
 *
 * The slim config (no Node-only deps) lives in auth.config.ts and is
 * shared with middleware.ts.
 */

import NextAuth from "next-auth";
import { authConfig } from "./auth.config";

export const { handlers, auth, signIn, signOut } = NextAuth(authConfig);