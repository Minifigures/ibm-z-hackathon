import type { NextConfig } from "next";

// BACKEND_URL is consumed at BUILD time by Next.js rewrites (baked into the
// routes manifest). For Code Engine deploys, the frontend image is built
// inside Code Engine's buildrun, so the deployed backend URL is the safe
// default. Locally, `BACKEND_URL=http://localhost:8000 npm run dev` overrides.
const BACKEND_URL =
  process.env.BACKEND_URL ??
  "https://backend.29vrap7vinsk.us-south.codeengine.appdomain.cloud";

const config: NextConfig = {
  reactStrictMode: true,
  // NOTE: tried `output: 'standalone'` to drop the runner image from
  // ~242 MB to ~80 MB and stay under ICR's 0.5 GB Lite-tier quota, but
  // the standalone server.js failed to serve the app on Code Engine
  // (container kept returning "upstream connect error" through ingress).
  // Reverted to the classic full-node_modules + `npm run start` setup
  // for now; the CI workflow's prune-before-build step keeps ICR usage
  // manageable for our deploy cadence.
  env: {
    NEXT_PUBLIC_API_BASE: process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000",
  },
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${BACKEND_URL}/:path*` },
    ];
  },
};

export default config;
