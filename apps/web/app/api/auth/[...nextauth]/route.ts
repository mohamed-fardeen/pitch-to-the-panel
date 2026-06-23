/**
 * NextAuth API route.
 *
 * Exposes:
 *   GET  /api/auth/signin
 *   POST /api/auth/signin/:provider
 *   GET  /api/auth/signout
 *   GET  /api/auth/session
 *   GET  /api/auth/csrf
 *   GET  /api/auth/providers
 *
 * The handlers are exported from auth.ts. This file just re-exports them
 * with the correct HTTP method signatures.
 */

import { handlers } from "../../../../auth";

export const { GET, POST } = handlers;