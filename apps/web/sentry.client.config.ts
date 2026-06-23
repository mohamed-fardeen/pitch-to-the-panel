/**
 * Sentry client-side config (Tier 1b).
 *
 * Runs in the browser. Initializes Sentry with the browser SDK.
 * Activated when NEXT_PUBLIC_SENTRY_DSN is set.
 *
 * See https://docs.sentry.io/platforms/javascript/guides/nextjs/
 */

import * as Sentry from "@sentry/nextjs";

const SENTRY_DSN = process.env.NEXT_PUBLIC_SENTRY_DSN;

if (SENTRY_DSN) {
  Sentry.init({
    dsn: SENTRY_DSN,
    environment: process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT ?? "development",
    tracesSampleRate: parseFloat(
      process.env.NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE ?? "0.1"
    ),
    // Capture fewer sessions in production
    replaysSessionSampleRate: 0.1,
    replaysOnErrorSampleRate: 1.0,
    // Don't ship PII by default
    sendDefaultPii: false,
  });
}