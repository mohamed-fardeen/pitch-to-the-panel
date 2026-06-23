const { withSentryConfig } = require("@sentry/nextjs");

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Standalone output is the right choice for Docker deployments, but on
  // Windows it requires symlink privileges that aren't available in
  // most dev environments. We re-enable `output: "standalone"` in Tier 0c
  // when we add the Dockerfile (which runs in Linux).
  // output: "standalone",

  // The actual app routes live under the legacy `frontend/` for now
  // (the migration to apps/web/app/ is the Tier 0a work in progress).
  reactStrictMode: true,
};

module.exports = withSentryConfig(nextConfig, {
  // Sentry's build-time options. Most knobs are set via env vars in
  // sentry.client.config.ts and sentry.server.config.ts.
  silent: !process.env.CI,
  org: process.env.SENTRY_ORG,
  project: process.env.SENTRY_PROJECT,
  authToken: process.env.SENTRY_AUTH_TOKEN,
  // Wide flag to disable Sentry's build-time checks when DSN is unset
  disableLogger: !process.env.NEXT_PUBLIC_SENTRY_DSN,
});
