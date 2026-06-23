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

module.exports = nextConfig;
