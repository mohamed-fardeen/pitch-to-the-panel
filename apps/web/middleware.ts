/**
 * NextAuth.js v5 middleware.
 *
 * Runs on the edge runtime for every request. Decides whether the user
 * has a valid session and either lets the request through, redirects to
 * /signin, or redirects to /.
 *
 * Public routes (no auth required): /, /signin, /api/auth/*, /api/agents
 * Protected routes (auth required): /app/*, /api/pitches/*, /api/revise-pitch
 */

import NextAuth from "next-auth";
import { authConfig } from "./auth.config";

const PUBLIC_PATHS = [
  "/",
  "/signin",
  "/signout",
  "/api/auth",
  "/api/agents",
  "/_next",
  "/favicon.ico",
];

function isPublic(pathname: string): boolean {
  return PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(p + "/"));
}

const { auth } = NextAuth(authConfig);

export default auth((req) => {
  const { nextUrl, auth: session } = req;
  const isLoggedIn = !!session?.user;
  const pathname = nextUrl.pathname;

  if (isPublic(pathname)) {
    return; // pass through
  }

  if (!isLoggedIn) {
    // Redirect to sign-in
    const signinUrl = new URL("/signin", nextUrl);
    signinUrl.searchParams.set("callbackUrl", pathname);
    return Response.redirect(signinUrl);
  }

  // Authenticated, non-public — pass through
  return;
});

export const config = {
  // Match all routes except static assets and the auth API itself
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\..*).*)"],
};